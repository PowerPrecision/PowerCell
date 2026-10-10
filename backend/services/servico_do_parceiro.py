"""Serviço pago pelo parceiro — o controlo simples do CRM (Out 2026, Portal do Parceiro).

A REGRA DE NEGÓCIO
  O parceiro NÃO recebe comissões: **paga-nos** pelo tratamento do processo do
  cliente dele. Por isso não há motor de cálculo financeiro — só um controlo
  que a equipa interna consulta e actualiza na ficha do processo:

      [ ] Serviço pago pelo parceiro        Observações: ______________

  Uma caixa de verificação e um texto livre. Nada de valores, taxas nem
  datas de vencimento (decisão de produto da V1).

ONDE VIVE — NUMA COLECÇÃO À PARTE (`process_partner_service`), COMO A ORIGEM
  O motivo é o da origem financeira do processo: `ProcessResponse` tem `extra="allow"`
  e o documento do processo sai inteiro em dezenas de leitores. Aqui o
  motivo extra é que **o parceiro nunca lê este dado** — o Portal do
  Parceiro não devolve o documento do processo (DTO por lista positiva) e,
  mesmo assim, é mais seguro um dado financeiro não estar no documento do
  que lembrar-se de o tirar. Um único leitor (este módulo) e um único
  escritor: a restrição por perfil é uma propriedade da arquitectura.
  O campo não é sobrescrito por um `PUT /processes/{id}` genérico.

AS REGRAS
  1. **Só se aplica a processos com parceiro** (`assigned_parceiro_id`). Sem
     parceiro o `GET` diz `aplicavel: false` (o ecrã não desenha o cartão) e
     o `PUT` recusa — uma caixa «paga pelo parceiro» num processo sem parceiro
     é lixo que alguém acabaria por ler.
  2. **Quem VÊ:** a equipa que vê o processo (papel EFECTIVO: master, admin,
     CEO, diretor, administrativo, consultor, intermediário). A Indexação não
     (não tem rasto nem trabalho financeiro).
  3. **Quem ALTERA:** gestão e administrativo (é o back-office que sabe se o
     parceiro pagou) — master, admin, CEO, diretor, administrativo.
  4. **O processo tem de estar no âmbito** (404 igual ao de «não existe»). Para
     alterar, a casa DONA: uma rede convidada vê mas não altera (como a
     origem financeira).
  5. **Rasto.** O histórico do processo diz que o estado mudou (aqui o valor
     pode ir: quem lê o histórico vê o cartão); o trilho de auditoria leva o
     antes e o depois. Observações: regista-se que mudaram, nunca o texto.
     O rasto nunca falha a operação.
  6. **Idempotente**: gravar o que já lá está não deixa rasto.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from database import db
from services.history import _is_stealth_user, log_history
from services.role_scope import PAPEIS_GLOBAIS
from services.tenant_access_context import resolver_papel_efectivo
from services.tenant_network import (
    CAMPOS_DO_CARIMBO,
    PROJECCAO_DO_CARIMBO,
    documento_no_ambito,
    processo_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

COLECAO = "process_partner_service"
LIMITE_DE_OBSERVACOES = 1000

PAPEIS_QUE_VEEM = ("master", "admin", "ceo", "diretor", "administrativo", "consultor", "intermediario")
PAPEIS_QUE_ALTERAM = ("master", "admin", "ceo", "diretor", "administrativo")
PAPEIS_SEM_FRONTEIRA = tuple(sorted(PAPEIS_GLOBAIS))

ERRO_PROCESSO_NAO_ENCONTRADO = "Processo não encontrado"
ERRO_SEM_PERMISSAO_PARA_VER = "Não tem permissão para ver o controlo do serviço do parceiro."
ERRO_SEM_PERMISSAO_PARA_ALTERAR = (
    "Só a gestão e o administrativo alteram o controlo do serviço do parceiro."
)
ERRO_NAO_E_A_CASA_DONA = "Só a empresa dona do processo pode alterar o controlo do serviço do parceiro."
ERRO_SEM_PARCEIRO = "Este processo não tem parceiro atribuído."


class ServicoDoParceiroBody(BaseModel):
    """Corpo do PUT. `extra="forbid"`: nada entra que não esteja escrito.

    Os dois campos são opcionais para o ecrã poder gravar só a caixa ou só o
    texto; pelo menos um tem de vir.
    """

    model_config = ConfigDict(extra="forbid")

    pago: Optional[bool] = None
    observacoes: Optional[str] = Field(None, max_length=5000)


# Só etiquetas a sério (`<b>`, `</p>`, `<img ...>`): «3 < 5 e 5 > 3» é texto.
_TAGS = re.compile(r"</?[A-Za-z][^>]*>")
_CONTROLO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def limpar_observacoes(valor: Any) -> str:
    """Texto livre: sem etiquetas HTML nem caracteres de controlo, com
    quebras de linha preservadas e tamanho limitado. PURA.

    Não passa pelo `sanitize_string` do resto do CRM: esse junta as linhas
    num só parágrafo, e uma observação de várias linhas deixava de se ler.
    """
    if valor is None:
        return ""
    texto = _CONTROLO.sub("", str(valor).replace("\r\n", "\n").replace("\r", "\n"))
    texto = _TAGS.sub("", texto)
    linhas = [" ".join(linha.split()) for linha in texto.split("\n")]
    texto = "\n".join(linhas).strip()
    return texto[:LIMITE_DE_OBSERVACOES]


def descrever(process_id: str, processo: Optional[dict], doc: Optional[dict], *, pode_alterar: bool) -> dict:
    """O que a API devolve. Sem parceiro: `aplicavel: false`."""
    aplicavel = bool((processo or {}).get("assigned_parceiro_id"))
    doc = doc or {}
    return {
        "process_id": process_id,
        "aplicavel": aplicavel,
        "parceiro": (
            {"id": processo.get("assigned_parceiro_id"), "nome": processo.get("parceiro_name")}
            if aplicavel else None
        ),
        "pago": bool(doc.get("pago")) if aplicavel else False,
        "pago_em": doc.get("pago_em") if aplicavel and doc.get("pago") else None,
        "observacoes": (doc.get("observacoes") or "") if aplicavel else "",
        "actualizado_por": doc.get("actualizado_por_nome") if aplicavel else None,
        "actualizado_em": doc.get("actualizado_em") if aplicavel else None,
        "pode_alterar": bool(pode_alterar and aplicavel),
    }


async def _papel(user: dict, request: Optional[Request], permitidos: tuple[str, ...], erro: str) -> str:
    papel = await resolver_papel_efectivo(
        user, request,
        traduzir_todos_os_perfis=lambda p: str(p or "").strip().lower() in permitidos,
    )
    if papel.lower() not in permitidos:
        raise HTTPException(status_code=403, detail=erro)
    return papel.lower()


async def _carregar_processo(process_id: str, user: dict, papel: str, *, para_alterar: bool) -> dict:
    scope = await resolve_tenant_scope(user)
    processo = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "id": 1, "assigned_parceiro_id": 1, "parceiro_name": 1, "partner_network_ids": 1,
         **PROJECCAO_DO_CARIMBO},
    )
    atravessa_redes = papel in PAPEIS_SEM_FRONTEIRA
    if not processo or not (atravessa_redes or processo_no_ambito(processo, scope)):
        raise HTTPException(status_code=404, detail=ERRO_PROCESSO_NAO_ENCONTRADO)
    if para_alterar and not atravessa_redes and not documento_no_ambito(processo, scope):
        raise HTTPException(status_code=403, detail=ERRO_NAO_E_A_CASA_DONA)
    return processo


def _resumo_para_o_trilho(doc: Optional[dict]) -> Optional[str]:
    if not doc:
        return None
    return f"pago={'sim' if doc.get('pago') else 'não'}; observacoes={'sim' if doc.get('observacoes') else 'não'}"


async def run_get_servico(process_id: str, user: dict, request: Optional[Request] = None) -> dict:
    papel = await _papel(user, request, PAPEIS_QUE_VEEM, ERRO_SEM_PERMISSAO_PARA_VER)
    processo = await _carregar_processo(process_id, user, papel, para_alterar=False)
    doc = await db.process_partner_service.find_one({"process_id": process_id}, {"_id": 0})
    # `pode_alterar` diz ao ecrã se desenha a caixa activa; a decisão final
    # é do PUT. Papel de leitura e casa dona.
    scope = await resolve_tenant_scope(user)
    pode = papel in PAPEIS_QUE_ALTERAM and (papel in PAPEIS_SEM_FRONTEIRA or documento_no_ambito(processo, scope))
    return descrever(process_id, processo, doc, pode_alterar=pode)


async def run_set_servico(
    process_id: str,
    body: ServicoDoParceiroBody,
    user: dict,
    request: Optional[Request] = None,
) -> dict:
    if body.pago is None and body.observacoes is None:
        raise HTTPException(status_code=422, detail="Indique se o serviço foi pago e/ou as observações.")

    papel = await _papel(user, request, PAPEIS_QUE_ALTERAM, ERRO_SEM_PERMISSAO_PARA_ALTERAR)
    processo = await _carregar_processo(process_id, user, papel, para_alterar=True)
    if not processo.get("assigned_parceiro_id"):
        raise HTTPException(status_code=422, detail=ERRO_SEM_PARCEIRO)

    antes = await db.process_partner_service.find_one({"process_id": process_id}, {"_id": 0})
    pago = bool(antes.get("pago")) if antes else False
    observacoes = (antes or {}).get("observacoes") or ""
    if body.pago is not None:
        pago = bool(body.pago)
    if body.observacoes is not None:
        observacoes = limpar_observacoes(body.observacoes)

    if antes and bool(antes.get("pago")) == pago and (antes.get("observacoes") or "") == observacoes:
        return descrever(process_id, processo, antes, pode_alterar=True)

    agora = datetime.now(timezone.utc).isoformat()
    documento = {
        "process_id": process_id,
        "pago": pago,
        "observacoes": observacoes,
        # Quando foi marcado como pago (e só enquanto estiver marcado).
        "pago_em": (
            (antes or {}).get("pago_em") if (antes or {}).get("pago") and pago else (agora if pago else None)
        ),
        "actualizado_por_id": user.get("id"),
        "actualizado_por_nome": user.get("name"),
        "actualizado_em": agora,
        # O carimbo do PROCESSO: o controlo é do mesmo âmbito que ele.
        **{c: processo[c] for c in CAMPOS_DO_CARIMBO if processo.get(c) not in (None, "")},
    }
    # Upsert por `process_id` (índice único): duas escritas concorrentes
    # convergem num só registo — a última vence, sem duplicar.
    await db.process_partner_service.update_one({"process_id": process_id}, {"$set": documento}, upsert=True)

    await _deixar_rasto(process_id, user, request, papel, antes, documento)
    return descrever(process_id, processo, documento, pode_alterar=True)


async def _deixar_rasto(
    process_id: str,
    user: dict,
    request: Optional[Request],
    papel: str,
    antes: Optional[dict],
    depois: dict,
) -> None:
    """Histórico + trilho de auditoria. **Nunca** propaga."""
    if _is_stealth_user(user):
        return
    pago_antes = bool((antes or {}).get("pago"))
    try:
        if pago_antes != bool(depois.get("pago")):
            await log_history(
                process_id, user,
                "Marcou o serviço como pago pelo parceiro" if depois.get("pago")
                else "Desmarcou o serviço como pago pelo parceiro",
                "servico_pago_pelo_parceiro",
            )
        if ((antes or {}).get("observacoes") or "") != (depois.get("observacoes") or ""):
            # Sem o texto: regista-se que mudou.
            await log_history(
                process_id, user, "Atualizou as observações do serviço do parceiro", "servico_do_parceiro_observacoes"
            )
    except Exception as erro:  # noqa: BLE001 — o rasto não falha a operação
        logger.warning("[SERVICO-PARCEIRO] Histórico não gravado para %s: %s", process_id, erro)
    try:
        from services.audit_trail_service import log_audit_event

        await log_audit_event(
            process_id, user, "Atualizou o controlo do serviço pago pelo parceiro",
            field="servico_do_parceiro",
            old_value=_resumo_para_o_trilho(antes),
            new_value=_resumo_para_o_trilho(depois),
            request=request,
            metadata={"papel_efectivo": papel},
        )
    except Exception as erro:  # noqa: BLE001
        logger.warning("[SERVICO-PARCEIRO] Trilho de auditoria não gravado para %s: %s", process_id, erro)


__all__ = [
    "COLECAO",
    "LIMITE_DE_OBSERVACOES",
    "PAPEIS_QUE_ALTERAM",
    "PAPEIS_QUE_VEEM",
    "ServicoDoParceiroBody",
    "descrever",
    "limpar_observacoes",
    "run_get_servico",
    "run_set_servico",
]
