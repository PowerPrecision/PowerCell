"""«Arquivar no Processo»: do anexo de um email para a pasta do processo (Bloco 2).

O PEDIDO
========
Um botão nos anexos recebidos por email; ao clicar, o sistema sugere
automaticamente o processo activo associado ao endereço do remetente.

AS REGRAS (cada uma tem teste)
==============================
1. **Sugerir não é decidir.** Um remetente com UM processo activo vem
   pré-seleccionado; com dois ou mais não vem nenhum — arquivar o cartão de
   cidadão de uma pessoa no processo errado é um cruzamento de dados, e
   sair dele exige alguém que repare (a regra do `email_client_match`). A
   comparação de endereços é EXACTA.
2. **O âmbito da sugestão é o de PROCESSOS** (rede do utilizador + rede
   convidada de uma partilha): um remetente que seja cliente de outra rede
   não revela a ficha nem a sua existência.
3. **Para um email enviado, o endereço relevante é o do DESTINATÁRIO** — o
   remetente é o próprio utilizador. E os endereços do próprio utilizador
   nunca contam: sugerir o processo de quem escreve seria sempre errado.
4. **O arquivo é o upload**, não uma cópia dele: passa por
   `run_upload_file_s3` — validação por magic bytes, conversão, pasta
   `Index` + fila da IA se o processo está por indexar (e IA dispensada se
   já está), guarda de escrita da D-26, histórico, pedido do Portal. Duas
   implementações do mesmo desvio divergem sem dar erro.
5. **Idempotente por processo.** O anexo guarda onde foi arquivado
   (`archived_to`); arquivar de novo no mesmo processo devolve o que já
   existe em vez de duplicar o ficheiro e gastar uma segunda IA.
6. **Quem arquiva:** quem trata documentos — admin, CEO, diretor,
   administrativo, consultor e intermediário. A indexação é SÓ LEITURA nos
   documentos (regra do `S3FileManager`) e um parceiro não carrega ficheiros
   pela API do CRM.
7. **Sem rasto do perfil silenciado:** o `archived_by` não se grava para um
   utilizador `indexacao`/`track_history=False` (a regra do `log_history`).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import BackgroundTasks, HTTPException

from database import db
from services.document_intake import processo_ja_passou_a_indexacao
from services.email_access import _enderecos_configurados, papeis_do_utilizador
from services.email_client_match import (
    construir_condicao,
    motivo_do_processo,
    normalizar_enderecos,
)
from services.tenant_network import build_tenant_process_condition, com_isolamento
from services.workflow_phases import carregar_fases, nomes_terminais

logger = logging.getLogger(__name__)

PAPEIS_QUE_ARQUIVAM = frozenset(
    {
        "master", "admin", "ceo", "diretor", "administrativo", "consultor",
        "intermediario", "indexacao",
    }
)

#: Tecto de um anexo arquivado (o mesmo dos uploads do CRM).
TAMANHO_MAXIMO_BYTES = 25 * 1024 * 1024
LIMITE_DE_SUGESTOES = 10

PROJECCAO = {
    "_id": 0, "id": 1, "process_number": 1, "client_name": 1, "status": 1,
    "client_email": 1, "monitored_emails": 1, "titular2_data": 1,
    "consultor_names": 1, "created_at": 1, "is_indexed": 1, "skip_index": 1,
}


def enderecos_relevantes(email: dict) -> list[str]:
    """Quem é o «outro lado» da conversa: o remetente, ou os destinatários."""
    from services.email_process_crud import normalize_participant_email

    if str(email.get("direction") or "").lower() == "sent":
        brutos = [*(email.get("to_emails") or []), *(email.get("cc_emails") or [])]
    else:
        brutos = [email.get("from_email")]
    return normalizar_enderecos(normalize_participant_email(b) for b in brutos)


async def sugerir_processos(email: dict, user: dict) -> dict[str, Any]:
    """Os processos activos a que o outro lado da conversa pertence."""
    proprios = set(normalizar_enderecos(await _enderecos_configurados(user)))
    enderecos = [e for e in enderecos_relevantes(email) if e not in proprios]

    fases = await carregar_fases()
    rotulos = {f["name"]: (f.get("label") or f["name"]) for f in fases if isinstance(f, dict) and f.get("name")}

    ligado = str(email.get("process_id") or "")
    vinculos: list[dict] = []
    condicao_enderecos = construir_condicao(enderecos)
    if condicao_enderecos:
        vinculos.append(condicao_enderecos)
    if ligado:
        vinculos.append({"id": ligado})

    candidatos: list[dict] = []
    if vinculos:
        consulta = com_isolamento(
            await build_tenant_process_condition(user),
            {"$and": [
                {"$or": vinculos},
                {"status": {"$nin": nomes_terminais(fases)}},
                {"is_deleted": {"$ne": True}},
            ]},
        )
        try:
            candidatos = await db.processes.find(consulta, PROJECCAO).to_list(LIMITE_DE_SUGESTOES * 3)
        except Exception as exc:
            logger.warning("[EMAIL-ARCHIVE] Falha a procurar processos: %s", exc)
            candidatos = []

    candidatos.sort(key=lambda p: str(p.get("created_at") or ""), reverse=True)
    candidatos.sort(key=lambda p: p.get("id") != ligado)  # o já ligado primeiro

    sugestoes = [
        {
            "process_id": p.get("id"),
            "process_number": p.get("process_number"),
            "client_name": p.get("client_name"),
            "status": p.get("status"),
            "status_label": rotulos.get(p.get("status")) or p.get("status"),
            "consultor_names": p.get("consultor_names") or [],
            "motivo": "ligado a este email" if p.get("id") == ligado else motivo_do_processo(p, enderecos),
            "ligado": p.get("id") == ligado,
            # Diz ao ecrã se o ficheiro vai para a Index (e para a fila da IA)
            # ou para uma pasta à escolha — a decisão é do `document_intake`.
            "ja_indexado": processo_ja_passou_a_indexacao(p),
        }
        for p in candidatos[:LIMITE_DE_SUGESTOES]
        if p.get("id")
    ]

    sugerido: Optional[str] = None
    if ligado and any(s["process_id"] == ligado for s in sugestoes):
        sugerido = ligado  # a ligação explícita é uma decisão já tomada
    elif len(sugestoes) == 1:
        sugerido = sugestoes[0]["process_id"]

    return {
        "enderecos": enderecos,
        "sugestoes": sugestoes,
        "sugerido": sugerido,
        "ambiguo": len(sugestoes) > 1 and sugerido is None,
    }


def _ja_arquivado(anexo: dict, process_id: str) -> Optional[dict]:
    for registo in anexo.get("archived_to") or []:
        if isinstance(registo, dict) and registo.get("process_id") == process_id:
            return registo
    return None


async def arquivar_anexo(
    email: dict,
    attachment_id: str,
    data: dict,
    user: dict,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """Arquiva um anexo do email na pasta de um processo."""
    from services.document_upload import run_upload_file_s3
    from services.email_mailbox_ops import _load_attachment_bytes, _match_attachment

    if not (papeis_do_utilizador(user) & PAPEIS_QUE_ARQUIVAM):
        raise HTTPException(status_code=403, detail="O seu perfil não arquiva documentos em processos.")

    process_id = str((data or {}).get("process_id") or "").strip()
    if not process_id:
        raise HTTPException(status_code=400, detail="process_id é obrigatório")

    attachments = email.get("attachments") or []
    anexo, indice = _match_attachment(attachments, attachment_id)
    if not anexo:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")

    anterior = _ja_arquivado(anexo, process_id)
    if anterior:
        return {
            "success": True,
            "already_archived": True,
            "process_id": process_id,
            "path": anterior.get("path"),
            "message": "Este anexo já foi arquivado neste processo.",
        }

    conteudo = await _load_attachment_bytes(email, anexo, user)
    if not conteudo:
        raise HTTPException(status_code=404, detail="Conteúdo do anexo não disponível")
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise HTTPException(status_code=413, detail="O anexo excede o tamanho máximo para arquivar.")

    nome = anexo.get("filename") or anexo.get("file_name") or "anexo.pdf"
    tipo = anexo.get("content_type") or anexo.get("mime_type") or "application/octet-stream"

    # A guarda de ESCRITA (D-26) corre dentro do upload, antes de tocar no S3.
    resposta = await run_upload_file_s3(
        process_id,
        file_content=conteudo,
        original_filename=nome,
        content_type=tipo,
        category=str((data or {}).get("category") or "Outros"),
        empresa_nif=None,
        custom_filename=None,
        user=user,
        background_tasks=background_tasks,
        origem="email",
    )

    await _registar_arquivo(email, attachments, indice, process_id, resposta, user)
    return {**resposta, "process_id": process_id, "archived": True, "already_archived": False}


async def _registar_arquivo(
    email: dict, attachments: list, indice: int, process_id: str, resposta: dict, user: dict,
) -> None:
    """Grava no anexo ONDE foi arquivado. Nunca falha o arquivo (já está gravado)."""
    from services.history import _is_stealth_user

    registo: dict[str, Any] = {
        "process_id": process_id,
        "path": resposta.get("path"),
        "category": resposta.get("category"),
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
    if not _is_stealth_user(user):
        registo["archived_by"] = user.get("id")
    try:
        anexo = dict(attachments[indice])
        anexo["archived_to"] = [*(anexo.get("archived_to") or []), registo]
        atualizados = list(attachments)
        atualizados[indice] = anexo
        await db.emails.update_one({"id": email.get("id")}, {"$set": {"attachments": atualizados}})
    except Exception as exc:
        logger.warning(
            "[EMAIL-ARCHIVE] Anexo arquivado mas o registo no email falhou (%s); "
            "um segundo clique arquivaria de novo.", exc,
        )
