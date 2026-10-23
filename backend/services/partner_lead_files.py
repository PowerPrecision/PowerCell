"""
====================================================================
FICHEIROS DA LEAD DO PARCEIRO → PASTA DEFINITIVA DO CLIENTE (D-39)
====================================================================
Quando a lead de um parceiro se associa a um cliente que já existe
(`b2b_client_match`), os ficheiros que o parceiro enviou antes da libertação
estão na pasta do REGISTO dele (`Documentação Clientes/{lead_id}/…`). Esta
pasta é temporária: quem trabalha o cliente procura-os na dele. Este módulo
copia-os para a pasta definitiva do cliente, reaponta a base de dados e só
depois apaga a origem — **ficheiro a ficheiro**, para que um URL de descarga
nunca aponte para uma chave que já não existe.

A ORDEM (e porque é esta)
  1. `head` da origem e do destino (chave EXACTA, estado de três valores);
  2. cópia (`copy_object_exact`) para um destino que NÃO existe — nunca se
     sobrescreve: um nome ocupado ganha ` (2)`, ` (3)`…;
  3. verificação da cópia (tamanho) — uma cópia que não bate é apagada;
  4. reapontar `db.documents` (`s3_path` e `attached_files[].s3_path`) e
     `db.document_metadata` — NO MESMO ACTO, antes de apagar a origem;
  5. só então apagar a origem.
  Se o processo morrer entre dois passos, a origem continua a ser a chave que
  a base de dados conhece (passos 1–4) ou o destino já é (passo 5), nunca uma
  chave inexistente. Uma segunda passagem retoma: o destino com o MESMO
  conteúdo (tamanho e ETag) é reaproveitado em vez de duplicado.

O QUE NÃO SE FAZ
  * Nada fora da pasta de origem: só se movem chaves DENTRO de
    `Documentação Clientes/{lead_id}` (por segmento) e o destino tem de estar
    dentro da raiz documental — mover para fora transformava a guarda de posse
    num passe para o bucket (precedente: Incidente P0 do Portal).
  * Nunca se descobrem ficheiros por listagem do S3: só se movem os que a base
    de dados regista. Um objecto sem registo é um upload nunca confirmado.
  * O `client_id` dos registos não muda: o registo do parceiro continua a ser
    dele; o que muda é onde o ficheiro físico vive.
  * Nunca levanta: quando isto corre, a associação JÁ aconteceu. Falhas ficam
    em `consolidacao_pendente` no rascunho e são repetidas por
    `consolidar_pendentes` (e por `scripts/consolidar_ficheiros_de_leads.py`).
====================================================================
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Optional

from database import db
from services.s3_document_root import (
    RAIZ,
    dentro_da_pasta,
    e_pasta_de_processo,
    normalizar,
    pasta_do_cliente,
    pasta_gravada,
    raiz_do_cliente_de,
)
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)

#: Quantas chaves de destino se experimentam antes de desistir de um nome ocupado.
MAX_SUFIXOS = 50
LIMITE_DE_REGISTOS = 5000

MOVIDO = "movido"
JA_MOVIDO = "ja_movido"
FALHOU = "falhou"
FORA_DA_ORIGEM = "fora_da_origem"
ORIGEM_AUSENTE = "origem_ausente"


# ════════════════════════════════════════════════════════════════════
#  PURAS
# ════════════════════════════════════════════════════════════════════
def pasta_de_origem(lead_id: Any) -> Optional[str]:
    """A pasta temporária da lead — derivada do ID, nunca de um ponteiro gravado."""
    return pasta_do_cliente(lead_id)


def pasta_de_destino(existente: dict) -> Optional[str]:
    """A pasta definitiva do cliente existente: o ponteiro gravado, ou a derivada do ID.

    Um ponteiro que aponta para a pasta de um PROCESSO sobe à do cliente (a mesma subida que a
    leitura faz). Fora da raiz documental não há destino — nunca se grava onde a guarda de posse
    não alcança.
    """
    bruto = pasta_gravada(existente.get("s3_folder"), contexto=f"consolidação ({existente.get('id')})")
    pasta = bruto or pasta_do_cliente(existente.get("id"))
    if pasta and e_pasta_de_processo(pasta):
        pasta = raiz_do_cliente_de(pasta)
    if not pasta or not dentro_da_pasta(pasta, RAIZ):
        return None
    return normalizar(pasta)


def pastas_compativeis(origem: Optional[str], destino: Optional[str]) -> bool:
    """Origem e destino existem, são distintos e nenhum contém o outro."""
    if not origem or not destino:
        return False
    return not dentro_da_pasta(origem, destino) and not dentro_da_pasta(destino, origem)


def chave_de_destino(chave: str, origem: str, destino: str) -> Optional[str]:
    """A mesma chave, relativa à origem, sob o destino. ``None`` se não está DENTRO da origem."""
    if not dentro_da_pasta(chave, origem):
        return None
    alvo, base = normalizar(chave), normalizar(origem)
    if alvo == base:
        return None
    return f"{normalizar(destino)}/{alvo[len(base) + 1:]}"


def com_sufixo(chave: str, n: int) -> str:
    """``a/b/ficheiro.pdf`` + 2 → ``a/b/ficheiro (2).pdf`` (o sufixo vai antes da extensão)."""
    pasta, _, nome = chave.rpartition("/")
    base, ponto, extensao = nome.rpartition(".")
    if not ponto or not base:
        nome_novo = f"{nome} ({n})"
    else:
        nome_novo = f"{base} ({n}).{extensao}"
    return f"{pasta}/{nome_novo}" if pasta else nome_novo


def mesmo_conteudo(a: dict, b: dict) -> bool:
    """Dois objectos são o mesmo conteúdo? Tamanho igual e ETag igual (ou multipart: só o tamanho)."""
    if a.get("tamanho") != b.get("tamanho") or a.get("tamanho") is None:
        return False
    ea, eb = a.get("etag") or "", b.get("etag") or ""
    if "-" in ea or "-" in eb:
        return True
    return bool(ea) and ea == eb


def chaves_dos_registos(documentos: list[dict]) -> list[str]:
    """As chaves S3 registadas (topo e `attached_files`), sem repetições, pela ordem em que aparecem."""
    vistas: dict[str, None] = {}
    for doc in documentos:
        if isinstance(doc.get("s3_path"), str) and doc["s3_path"].strip():
            vistas.setdefault(doc["s3_path"], None)
        for anexo in doc.get("attached_files") or []:
            if isinstance(anexo, dict) and isinstance(anexo.get("s3_path"), str) and anexo["s3_path"].strip():
                vistas.setdefault(anexo["s3_path"], None)
    return list(vistas)


# ════════════════════════════════════════════════════════════════════
#  S3 (em thread: o boto3 é síncrono)
# ════════════════════════════════════════════════════════════════════
async def _head(chave: str) -> tuple[str, Optional[dict]]:
    return await asyncio.to_thread(s3_service.head_object_metadata, chave)


async def _escolher_destino(origem_meta: dict, desejado: str) -> tuple[str, Optional[str], bool]:
    """``(estado, chave, ja_la_esta)``. ``ja_la_esta``: o destino tem o MESMO conteúdo (retoma)."""
    for n in range(1, MAX_SUFIXOS + 1):
        candidata = desejado if n == 1 else com_sufixo(desejado, n)
        estado, meta = await _head(candidata)
        if estado == "erro":
            return "erro", None, False
        if estado == "ausente":
            return "ok", candidata, False
        if mesmo_conteudo(origem_meta, meta or {}):
            return "ok", candidata, True
    return "erro", None, False


async def _copiar_e_verificar(chave: str, final: str, origem_meta: dict) -> bool:
    if not await asyncio.to_thread(s3_service.copy_object_exact, chave, final):
        return False
    estado, meta = await _head(final)
    if estado == "ok" and (meta or {}).get("tamanho") == origem_meta.get("tamanho"):
        return True
    # Uma cópia que não bate não fica: apaga-se SÓ a que acabámos de criar.
    await asyncio.to_thread(s3_service.delete_file, final)
    return False


# ════════════════════════════════════════════════════════════════════
#  BASE DE DADOS
# ════════════════════════════════════════════════════════════════════
async def _reapontar(chave: str, nova: str, *, lead_id: str, client_id: str, agora: str) -> None:
    """Reaponta TODOS os registos que guardavam a chave. Levanta se a base de dados falhar."""
    rasto = {"lead_id": lead_id, "client_id": client_id, "s3_path_anterior": chave, "em": agora}
    await db.documents.update_many({"s3_path": chave}, {"$set": {"s3_path": nova, "consolidado": rasto}})
    await db.documents.update_many(
        {"attached_files.s3_path": chave},
        {"$set": {"attached_files.$[el].s3_path": nova, "consolidado": rasto}},
        array_filters=[{"el.s3_path": chave}],
    )
    await db.document_metadata.update_many({"s3_path": chave}, {"$set": {"s3_path": nova}})


async def _mover_um(chave: str, desejado: str, *, lead_id: str, client_id: str, agora: str) -> tuple[str, Optional[str]]:
    estado_o, meta_o = await _head(chave)
    if estado_o == "erro":
        return FALHOU, None
    if estado_o == "ausente":
        # A origem já não existe: se o destino está lá, uma passagem anterior apagou-a antes de a
        # base de dados acompanhar — reaponta-se. Se não, o registo estava partido: não se inventa.
        estado_d, _meta = await _head(desejado)
        if estado_d == "ok":
            try:
                await _reapontar(chave, desejado, lead_id=lead_id, client_id=client_id, agora=agora)
            except Exception as exc:  # noqa: BLE001
                logger.error("[D-39] Falha a reapontar %s: %s", chave, exc)
                return FALHOU, None
            return JA_MOVIDO, desejado
        return (ORIGEM_AUSENTE, None) if estado_d == "ausente" else (FALHOU, None)

    estado, final, ja_la_esta = await _escolher_destino(meta_o or {}, desejado)
    if estado != "ok" or not final:
        return FALHOU, None
    if not ja_la_esta and not await _copiar_e_verificar(chave, final, meta_o or {}):
        return FALHOU, None

    try:
        await _reapontar(chave, final, lead_id=lead_id, client_id=client_id, agora=agora)
    except Exception as exc:  # noqa: BLE001 — a origem continua a ser a chave conhecida: nada partido
        logger.error("[D-39] Falha a reapontar %s → %s: %s (a origem fica intacta)", chave, final, exc)
        return FALHOU, None

    if not await asyncio.to_thread(s3_service.delete_file, chave):
        logger.warning("[D-39] %s copiado e reapontado, mas a origem não foi apagada (repetir).", chave)
    return MOVIDO, final


# ════════════════════════════════════════════════════════════════════
#  A OPERAÇÃO
# ════════════════════════════════════════════════════════════════════
async def _registos_da_lead(lead_id: str, origem: str) -> list[dict]:
    prefixo = {"$regex": f"^{re.escape(normalizar(origem))}/"}
    docs = await db.documents.find(
        {"$or": [{"client_id": lead_id}, {"s3_path": prefixo}, {"attached_files.s3_path": prefixo}]},
        {"_id": 0, "id": 1, "s3_path": 1, "attached_files": 1},
    ).to_list(LIMITE_DE_REGISTOS)
    return docs


async def _garantir_mapeamento_do_destino(existente: dict, destino: str) -> None:
    """Um cliente sem `s3_folder` ganha o ponteiro da pasta onde acabámos de pôr os ficheiros.

    Sem ele a listagem do CRM trata o cliente como «sem mapeamento» e não mostra nada.
    Só escreve se o campo continua por preencher (nunca por cima de um mapeamento).
    """
    from services.s3_document_root import PastaGravadaInvalida, pasta_para_gravar

    if pasta_gravada(existente.get("s3_folder")):
        return
    try:
        pasta = pasta_para_gravar(destino, contexto=f"consolidação de ficheiros ({existente.get('id')})")
    except PastaGravadaInvalida as erro:
        logger.error("[D-39] %s", erro)
        return
    if pasta:
        await db.clients.update_one(
            {"id": existente["id"], "$or": [{"s3_folder": None}, {"s3_folder": ""}]},
            {"$set": {"s3_folder": pasta}},
        )


async def consolidar_ficheiros_da_lead(lead_id: str, existente: dict, *, agora: str) -> dict[str, Any]:
    """Move os ficheiros da lead para a pasta definitiva de ``existente``. Nunca levanta."""
    relatorio: dict[str, Any] = {
        MOVIDO: 0, JA_MOVIDO: 0, FALHOU: 0, FORA_DA_ORIGEM: 0, ORIGEM_AUSENTE: 0, "pendente": False,
    }
    try:
        origem = pasta_de_origem(lead_id)
        destino = pasta_de_destino(existente)
        if not pastas_compativeis(origem, destino):
            logger.warning(
                "[D-39] Sem pastas utilizáveis para a lead %s (origem=%r destino=%r): "
                "consolidar à mão com o religamento de pastas.", lead_id, origem, destino,
            )
            relatorio["pendente"] = True
            relatorio["sem_pastas"] = True
            await db.partner_drafts.update_one(
                {"id": lead_id}, {"$set": {"consolidacao_pendente": {"desde": agora, "motivo": "sem_pastas"}}},
            )
            return relatorio
        if not s3_service.is_configured():
            relatorio["pendente"] = True
            return relatorio

        registos = await _registos_da_lead(lead_id, origem)
        for chave in chaves_dos_registos(registos):
            if dentro_da_pasta(chave, destino):
                relatorio[JA_MOVIDO] += 1
                continue
            desejado = chave_de_destino(chave, origem, destino)
            if desejado is None:
                # Registos de outra pasta (nunca se tocam) — não é uma falha desta lead.
                relatorio[FORA_DA_ORIGEM] += 1
                continue
            resultado, _final = await _mover_um(
                chave, desejado, lead_id=lead_id, client_id=existente["id"], agora=agora,
            )
            relatorio[resultado] += 1

        relatorio["pendente"] = bool(relatorio[FALHOU])
        if relatorio[MOVIDO] or relatorio[JA_MOVIDO]:
            await _garantir_mapeamento_do_destino(existente, destino)
        await _registar_resultado(lead_id, existente["id"], destino, relatorio, agora)
    except Exception as exc:  # noqa: BLE001 — a associação já aconteceu; dizer, nunca derrubar
        logger.error("[D-39] Falha inesperada a consolidar os ficheiros da lead %s: %s", lead_id, exc)
        relatorio["pendente"] = True
        try:
            await db.partner_drafts.update_one(
                {"id": lead_id}, {"$set": {"consolidacao_pendente": {"desde": agora, "ficheiros": -1}}},
            )
        except Exception:  # noqa: BLE001
            pass
    return relatorio


async def _registar_resultado(lead_id: str, client_id: str, destino: str, relatorio: dict, agora: str) -> None:
    """Deixa o estado onde a equipa e o retry o encontram (sem dados pessoais)."""
    if relatorio["pendente"]:
        pendentes = relatorio[FALHOU]
        await db.partner_drafts.update_one(
            {"id": lead_id}, {"$set": {"consolidacao_pendente": {"desde": agora, "ficheiros": pendentes}}},
        )
        return
    await db.partner_drafts.update_one({"id": lead_id}, {"$unset": {"consolidacao_pendente": ""}})
    await db.clients.update_one(
        {"id": client_id, "partner_leads.lead_id": lead_id},
        {"$set": {
            "partner_leads.$.pasta_dos_documentos_do_lead": destino,
            "partner_leads.$.ficheiros_consolidados_em": agora,
        }},
    )


async def consolidar_pendentes(*, limite: int = 50, agora: str, aplicar: bool = True) -> dict[str, int]:
    """Repete a consolidação das leads associadas que ficaram a meio (ou nunca correram)."""
    leads = await db.partner_drafts.find(
        {"consolidacao_pendente": {"$exists": True}, "matched_client_id": {"$nin": [None, ""]}},
        {"_id": 0, "id": 1, "matched_client_id": 1},
    ).to_list(limite)
    resumo = {"pendentes": len(leads), "concluidas": 0, "ainda_pendentes": 0}
    if not aplicar:
        return resumo
    for lead in leads:
        existente = await db.clients.find_one({"id": lead["matched_client_id"]}, {"_id": 0, "id": 1, "s3_folder": 1})
        if not existente:
            resumo["ainda_pendentes"] += 1
            continue
        relatorio = await consolidar_ficheiros_da_lead(lead["id"], existente, agora=agora)
        resumo["ainda_pendentes" if relatorio["pendente"] else "concluidas"] += 1
    return resumo


__all__ = [
    "consolidar_ficheiros_da_lead",
    "consolidar_pendentes",
    "chave_de_destino",
    "chaves_dos_registos",
    "com_sufixo",
    "mesmo_conteudo",
    "pasta_de_destino",
    "pasta_de_origem",
    "pastas_compativeis",
]
