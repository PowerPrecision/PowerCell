"""
====================================================================
PORTAL DO PARCEIRO — O FILTRO DE VIABILIDADE: rascunhos e libertação
====================================================================
A REGRA DE NEGÓCIO (Out 2026)
  O parceiro preenche os dados e envia documentos no seu portal, mas a
  lead só passa para o lado da equipa interna se submeter um ficheiro
  categorizado como **Comprovativo de Pagamento**. Sem ele, o registo
  fica **retido no lado do parceiro** (Pendente) e a equipa não o vê.

POR QUE É QUE O RASCUNHO NÃO VIVE EM `db.clients`
  A primeira ideia foi uma marca no cliente («retido») e filtrar todas as
  listagens da equipa. Há mais de vinte superfícies que listam ou
  resolvem clientes (registos, pesquisa, «Os Meus Clientes», por id, o
  Smart Match, os alertas…) e este projecto já falhou o inventário delas
  cinco vezes: um filtro esquecido numa só mostraria à equipa — ou a outra
  rede — o registo de um parceiro que ainda nem pagou. Um rascunho numa
  **colecção própria** (`partner_drafts`) não pode vazar por omissão: não
  há superfície da equipa que o leia, por construção.

O CICLO
      (submeter)        (comprovativo)         (validar/rejeitar)
    ──► pendente ───────────► [db.clients] ───────────────────────►
           │                        │  lead_status "new" + validação
           │ 60 dias parado         │  financeira "pendente"
           ▼                        │
        expirado                    └── rejeitada ──► devolvida (volta
                                                      ao parceiro, com
                                                      o motivo)

  * **O id mantém-se** na libertação: os ficheiros já enviados (pasta do
    cliente, `db.documents`) continuam a apontar para o mesmo cliente.
  * **A libertação é um MOVIMENTO**, não uma cópia: o rascunho sai da
    colecção do parceiro quando o cliente nasce na da equipa — duas
    cópias a divergir seriam o defeito do duplo carimbo.
  * **O comprovativo é uma marca do FICHEIRO**
    (`comprovativo_de_pagamento: true`, posta pelo servidor a partir da
    categoria pedida) — nunca o nome do ficheiro nem o que o corpo diz
    sobre si.
  * Depois de **devolvida**, só um comprovativo NOVO (enviado depois da
    devolução) volta a libertar: o antigo foi o que a equipa rejeitou.

A VALIDAÇÃO FINANCEIRA NUNCA BLOQUEIA (ver `financial_validation`)
  Esta camada decide só se a lead **chega** à equipa. Depois de chegar,
  validar é um aviso visual: a operação não pára à espera dele.
====================================================================
"""
from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

COLECAO = "partner_drafts"

ESTADO_PENDENTE = "pendente"
ESTADO_EXPIRADO = "expirado"
ESTADO_DEVOLVIDA = "devolvida"

#: Estados em que o parceiro ainda pode mexer (editar, enviar ficheiros).
ESTADOS_EDITAVEIS = (ESTADO_PENDENTE, ESTADO_DEVOLVIDA)

ROTULOS_DOS_ESTADOS = {
    ESTADO_PENDENTE: "Pendente — falta o comprovativo de pagamento",
    ESTADO_EXPIRADO: "Expirado",
    ESTADO_DEVOLVIDA: "Devolvida pela equipa",
}

#: A categoria que liberta a lead. O valor canónico (o que o ecrã envia).
CATEGORIA_DO_COMPROVATIVO = "Comprovativo_Pagamento"
ROTULO_DO_COMPROVATIVO = "Comprovativo de Pagamento"

#: Dias sem actividade (edições e envios) até uma lead pendente expirar.
DIAS_ATE_EXPIRAR = 60

#: O campo, no cliente libertado, que guarda a validação financeira.
CAMPO_VALIDACAO = "validacao_financeira"


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


# ════════════════════════════════════════════════════════════════════
#  PURAS
# ════════════════════════════════════════════════════════════════════
_CONECTORES = frozenset({"de", "da", "do", "das", "dos"})


def normalizar_categoria(valor: Any) -> str:
    """«Comprovativo de Pagamento», «comprovativo_pagamento»… → a mesma chave."""
    texto = unicodedata.normalize("NFKD", _texto(valor)).encode("ascii", "ignore").decode()
    palavras = [p for p in re.split(r"[^a-z0-9]+", texto.lower()) if p]
    # Os conectores não distinguem categorias («de Pagamento» = «Pagamento»);
    # o resto da palavra conta inteiro.
    return "_".join(p for p in palavras if p not in _CONECTORES)


_CHAVE_DO_COMPROVATIVO = normalizar_categoria(CATEGORIA_DO_COMPROVATIVO)


def e_comprovativo_de_pagamento(categoria: Any) -> bool:
    """A categoria pedida é a do Comprovativo de Pagamento?

    Compara a chave normalizada INTEIRA: «Comprovativo_IBAN» tem a mesma
    primeira palavra e NÃO liberta uma lead — um prefixo comum não é uma
    categoria.
    """
    return normalizar_categoria(categoria) == _CHAVE_DO_COMPROVATIVO


def estado_do_rascunho(rascunho: Optional[dict]) -> str:
    estado = _texto((rascunho or {}).get("partner_stage"))
    return estado if estado in ROTULOS_DOS_ESTADOS else ESTADO_PENDENTE


def pode_ser_editado(rascunho: Optional[dict]) -> bool:
    return estado_do_rascunho(rascunho) in ESTADOS_EDITAVEIS


def limite_de_inactividade(dias: int = DIAS_ATE_EXPIRAR, *, agora: Optional[datetime] = None) -> str:
    """O ISO abaixo do qual uma lead parada expirou."""
    return ((agora or _agora()) - timedelta(days=dias)).isoformat()


def condicao_de_inactivos(limite: str) -> dict:
    """Parado = nem `updated_at` nem `last_activity_at` chegam ao limite.

    Edições e envios do parceiro escrevem `last_activity_at`; edições da
    equipa escrevem `updated_at`. Olhar só para um deles expirava leads
    com trabalho recente.
    """
    return {
        "$and": [
            {"$or": [{"updated_at": {"$lt": limite}}, {"updated_at": {"$exists": False}}]},
            {"$or": [{"last_activity_at": {"$lt": limite}}, {"last_activity_at": {"$exists": False}}]},
        ]
    }


# ════════════════════════════════════════════════════════════════════
#  O COMPROVATIVO
# ════════════════════════════════════════════════════════════════════
async def comprovativo_do_caso(client_id: str, *, desde: Optional[str] = None) -> Optional[dict]:
    """O comprovativo enviado para esta lead, ou ``None``.

    `desde` (ISO) só conta os enviados depois dessa data — é o que impede o
    comprovativo que a equipa rejeitou de libertar a lead outra vez.
    """
    consulta: dict[str, Any] = {"client_id": client_id, "comprovativo_de_pagamento": True}
    docs = await db.documents.find(consulta, {"_id": 0}).to_list(50)

    melhor: Optional[dict] = None
    for doc in docs:
        for ficheiro in _ficheiros_do_documento(doc):
            enviado = _texto(ficheiro.get("uploaded_at"))
            if desde and enviado <= desde:
                continue
            if melhor is None or enviado > _texto(melhor.get("uploaded_at")):
                melhor = ficheiro
    return melhor


def _ficheiros_do_documento(doc: dict) -> list[dict]:
    anexos = [a for a in (doc.get("attached_files") or []) if isinstance(a, dict) and a.get("s3_path")]
    if anexos:
        return [
            {
                "file_id": a.get("file_id"),
                "filename": a.get("original_filename") or a.get("filename"),
                "s3_path": a["s3_path"],
                "uploaded_at": a.get("uploaded_at"),
            }
            for a in anexos
        ]
    if doc.get("s3_path"):
        return [{
            "file_id": doc.get("id"),
            "filename": doc.get("original_filename") or doc.get("filename"),
            "s3_path": doc["s3_path"],
            "uploaded_at": doc.get("uploaded_at"),
        }]
    return []


# ════════════════════════════════════════════════════════════════════
#  LIBERTAR (rascunho → equipa)
# ════════════════════════════════════════════════════════════════════
async def carregar_rascunho(client_id: str) -> Optional[dict]:
    return await db.partner_drafts.find_one({"id": client_id}, {"_id": 0})


async def libertar_se_tiver_comprovativo(client_id: str) -> Optional[dict]:
    """Se o rascunho já tem um comprovativo válido, passa-o à equipa.

    Idempotente: se o cliente já existe na equipa (uma libertação anterior
    que não chegou a apagar o rascunho) só limpa o rascunho — não duplica
    o registo nem repete o aviso. Devolve o cliente libertado, ou ``None``
    quando não havia o que libertar.
    """
    rascunho = await carregar_rascunho(client_id)
    if not rascunho or not pode_ser_editado(rascunho):
        return None

    desde = (rascunho.get("devolucao") or {}).get("em") if estado_do_rascunho(rascunho) == ESTADO_DEVOLVIDA else None
    comprovativo = await comprovativo_do_caso(client_id, desde=desde)
    if not comprovativo:
        return None

    agora = _agora().isoformat()

    ja_existe = await db.clients.find_one({"id": client_id}, {"_id": 0, "id": 1})
    if ja_existe:
        await db.partner_drafts.delete_one({"id": client_id})
        return None

    cliente = {k: v for k, v in rascunho.items() if k not in ("partner_stage", "last_activity_at", "devolucao")}
    cliente.update({
        "lead_status": "new",
        "updated_at": agora,
        "released_at": agora,
        CAMPO_VALIDACAO: {
            "estado": "pendente",
            "desde": agora,
            "comprovativo": {
                "file_id": comprovativo.get("file_id"),
                "filename": comprovativo.get("filename"),
                "uploaded_at": comprovativo.get("uploaded_at"),
            },
        },
    })
    # O histórico de devoluções acompanha a lead: a equipa vê que já foi
    # devolvida uma vez e porquê.
    if rascunho.get("devolucao"):
        cliente["devolucoes_anteriores"] = [rascunho["devolucao"]]

    await db.clients.insert_one(dict(cliente))
    await db.partner_drafts.delete_one({"id": client_id})
    logger.info("[PARCEIRO] Lead %s libertada para a equipa (comprovativo recebido).", client_id)
    return cliente


# ════════════════════════════════════════════════════════════════════
#  DEVOLVER (equipa → parceiro)
# ════════════════════════════════════════════════════════════════════
async def devolver_ao_parceiro(client_id: str, *, motivo: str, por: dict) -> Optional[dict]:
    """A lead rejeitada volta ao parceiro como `devolvida`, com o motivo.

    Move o cliente (que ainda não tem processo) da colecção da equipa para
    a do parceiro — sai de TODAS as listas da equipa, incluindo a fila do
    Index. Devolve o rascunho gravado, ou ``None`` se o cliente não existe.
    """
    cliente = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not cliente:
        return None
    agora = _agora().isoformat()

    rascunho = {k: v for k, v in cliente.items() if k not in ("lead_status", "released_at", CAMPO_VALIDACAO)}
    rascunho.update({
        "partner_stage": ESTADO_DEVOLVIDA,
        "last_activity_at": agora,
        "updated_at": agora,
        "devolucao": {
            "motivo": _texto(motivo),
            "por": _texto(por.get("id")),
            "por_nome": _texto(por.get("name")),
            "em": agora,
        },
    })
    await db.partner_drafts.insert_one(dict(rascunho))
    await db.clients.delete_one({"id": client_id})
    return rascunho


# ════════════════════════════════════════════════════════════════════
#  EXPIRAR (60 dias sem actividade)
# ════════════════════════════════════════════════════════════════════
async def expirar_leads_inactivas(
    dias: int = DIAS_ATE_EXPIRAR, *, agora: Optional[datetime] = None, bd: Any = None,
) -> dict[str, int]:
    """Leads de parceiros pendentes há mais de ``dias`` sem actividade → Expirado.

    Duas populações, as duas «pendentes na triagem»:
      * os rascunhos retidos (`partner_drafts`, ainda sem comprovativo);
      * as leads já libertadas que a equipa ainda não tratou
        (`db.clients`, `lead_status: "new"`, sem processo).
    Uma lead com processo, convertida ou já expirada nunca é tocada.
    Idempotente: correr duas vezes seguidas não altera nada na segunda.
    """
    bd = bd if bd is not None else db
    limite = limite_de_inactividade(dias, agora=agora)
    momento = (agora or _agora()).isoformat()

    retidos = await bd.partner_drafts.update_many(
        {"$and": [{"partner_stage": ESTADO_PENDENTE}, condicao_de_inactivos(limite)]},
        {"$set": {"partner_stage": ESTADO_EXPIRADO, "expired_at": momento}},
    )
    na_triagem = await bd.clients.update_many(
        {"$and": [
            {"submitted_by_partner_id": {"$nin": [None, ""]}},
            {"lead_status": "new"},
            {"process_ids": {"$in": [None, []]}},
            {"is_deleted": {"$ne": True}},
            condicao_de_inactivos(limite),
        ]},
        {"$set": {"lead_status": "expired", "expired_at": momento}},
    )
    resultado = {
        "rascunhos": int(getattr(retidos, "modified_count", 0) or 0),
        "na_triagem": int(getattr(na_triagem, "modified_count", 0) or 0),
    }
    if any(resultado.values()):
        logger.info("[PARCEIRO] Leads expiradas por inactividade (%d dias): %s", dias, resultado)
    return resultado


async def registar_actividade(client_id: str) -> None:
    """Edição ou envio do parceiro: adia a expiração. Nunca propaga."""
    try:
        agora = _agora().isoformat()
        r = await db.partner_drafts.update_one({"id": client_id}, {"$set": {"last_activity_at": agora}})
        if not getattr(r, "matched_count", 0):
            await db.clients.update_one(
                {"id": client_id, "submitted_by_partner_id": {"$nin": [None, ""]}},
                {"$set": {"last_activity_at": agora}},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO] Falha a registar a actividade de %s: %s", client_id, exc)


__all__ = [
    "CAMPO_VALIDACAO",
    "CATEGORIA_DO_COMPROVATIVO",
    "COLECAO",
    "DIAS_ATE_EXPIRAR",
    "ESTADOS_EDITAVEIS",
    "ESTADO_DEVOLVIDA",
    "ESTADO_EXPIRADO",
    "ESTADO_PENDENTE",
    "ROTULOS_DOS_ESTADOS",
    "ROTULO_DO_COMPROVATIVO",
    "carregar_rascunho",
    "comprovativo_do_caso",
    "condicao_de_inactivos",
    "devolver_ao_parceiro",
    "e_comprovativo_de_pagamento",
    "estado_do_rascunho",
    "expirar_leads_inactivas",
    "libertar_se_tiver_comprovativo",
    "limite_de_inactividade",
    "normalizar_categoria",
    "pode_ser_editado",
    "registar_actividade",
]
