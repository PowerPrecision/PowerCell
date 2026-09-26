"""Upload/download de documentos no Portal do Cliente.

Extraído de `routes/portal.py`.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from services.s3_storage import s3_service
from services.document_process_resolve import (
    assert_path_within_document_root,
    assert_s3_file_belongs_to_process,
)
from services.s3_content_quarantine import exigir_conteudo_valido
from services.portal_assigned_users import get_all_assigned_user_ids as _get_all_assigned_user_ids
from services.portal_onboarding_advance import _trigger_onboarding_check
from services.notification_service import send_notification_with_preference_check
from services.redis_cache import invalidate_stats_cache

logger = logging.getLogger(__name__)


# ====================================================================
# INCIDENTE P0 (Set 2026) — o `file_key` do cliente NÃO é de confiança
# ====================================================================
# O `confirm-upload` recebia o `file_key` do CORPO do pedido e validava-o
# apenas com `s3_service.file_exists()`. Um cliente autenticado no Portal
# pedia `backups/dump-2026-09-01.zip` e recebia de volta um URL pré-assinado
# para o descarregar — mais um registo em `db.documents` que passava a
# autorizar a mesma chave no `/portal/download-url` para sempre.
#
# As duas guardas que impedem isto existem desde o Épico 9
# (`document_process_resolve`), mas estavam ligadas só aos endpoints do CRM.
# O Portal — a ÚNICA superfície exposta a utilizadores externos — ficou de
# fora. Cada camada validava; a combinação não.
#
# NÃO se acrescenta aqui uma terceira verificação (ex.: rejeitar `..`): as
# chaves S3 são opacas, o `..` não é normalizado pelo serviço e a assinatura
# pré-assinada fica presa à chave EXACTA — uma guarda que não previne nada
# é um placebo, e este projecto já pagou por um
# (`build_company_scope_condition`).


def _dono_do_prefixo_s3(
    process: Optional[dict], client: Optional[dict]
) -> Optional[dict]:
    """Documento de onde sai o prefixo S3 autorizado para este cliente.

    O Portal tem DOIS fluxos e ambos têm de ser cobertos:
      * com processo — a pasta é a do processo (é a que o `upload-url` usa);
      * sem processo (onboarding) — a pasta é a do cliente.

    Devolve o dicionário na forma que as guardas partilhadas entendem
    (`s3_folder` / `client_name`); no cliente o nome vive em `nome`.

    Devolve `None` quando NADA identifica um dono — e aí o chamador recusa.
    Sem dono não há como provar posse, e o degradado de
    `assert_s3_file_belongs_to_process` com nome vazio aceitaria toda a raiz
    de documentos: o que num ecrã do CRM é um incómodo, aqui era a fuga.
    """
    # O processo vem primeiro de propósito: é a pasta que o `upload-url`
    # escolhe quando há processo, e as duas podem divergir.
    for candidato in (process, client):
        if not candidato:
            continue
        s3_folder = candidato.get("s3_folder")
        nome = candidato.get("client_name") or candidato.get("nome") or ""
        if s3_folder or nome.strip():
            return {"s3_folder": s3_folder, "client_name": nome}
    return None


def assert_portal_file_key_e_do_cliente(
    file_key: str,
    *,
    process: Optional[dict],
    client: Optional[dict],
) -> None:
    """Recusa (403) qualquer chave S3 que não esteja na pasta deste cliente.

    São duas guardas, não uma, e NENHUMA das duas é redundante — mas o
    motivo da primeira não é o óbvio, e só uma mutação o mostrou:

      1. `assert_s3_file_belongs_to_process` tira do alcance a pasta do
         cliente do vizinho (e da outra REDE), que começa pela mesma raiz.
         Como os prefixos que ela deriva começam sempre por
         `Documentação Clientes/`, ela já implica a raiz — e é por isso que
         apagar a guarda (2) não matava, à primeira, nenhum teste.
      2. `assert_path_within_document_root` é a defesa contra um prefixo de
         dono ENVENENADO: se o `s3_folder` gravado no processo apontar para
         fora da árvore de documentos (ex.: `backups`), a guarda (1) autoriza
         alegremente tudo o que estiver lá, porque do ponto de vista dela
         aquela É a pasta do cliente. O cliente não consegue escrever
         `s3_folder` (campo protegido no PUT /portal/me), mas a equipa e o
         `ensure_client_folder_mapping` conseguem — e um valor mau grava-se
         uma vez e vale para sempre.

    A ordem é essa de propósito: a raiz primeiro, porque é a que não confia
    no prefixo do dono.

    Raises:
        HTTPException(403): chave fora do âmbito, ou dono indeterminável.
    """
    from services.document_constants import ERROR_FILE_ACCESS_DENIED

    assert_path_within_document_root(file_key)

    dono = _dono_do_prefixo_s3(process, client)
    if dono is None:
        logger.warning(
            "[PORTAL][SECURITY] Sem pasta S3 nem nome para provar posse de "
            "%s (processo=%s, cliente=%s) — recusado.",
            file_key,
            (process or {}).get("id"),
            (client or {}).get("id"),
        )
        raise HTTPException(status_code=403, detail=ERROR_FILE_ACCESS_DENIED)

    assert_s3_file_belongs_to_process(file_key, dono)


async def _create_document_record(
    doc_id: str,
    process_id: Optional[str],
    file_key: str,
    original_filename: str,
    category: str,
    file_size: int,
    content_type: str,
    now: str,
    custom_label: str = None,
    client_id: Optional[str] = None,
):
    """Cria um registo de documento na BD com status RECEIVED.

    PACOTE 5 (bug dos uploads órfãos): `process_id` e `client_id` são agora
    sempre gravados quando conhecidos — um documento sem nenhum dos dois é
    irrecuperável no CRM (não aparece no Processo nem na ficha do Cliente).
    Se ambos faltarem, o upload é rejeitado (400) em vez de criar um órfão.
    """
    if not process_id and not client_id:
        raise HTTPException(
            status_code=400,
            detail="Sem cliente/processo associado. Não é possível guardar o documento.",
        )
    document = {
        "id": doc_id,
        "process_id": process_id,
        "filename": original_filename,
        "original_filename": original_filename,
        "category": category,
        "file_size": file_size,
        "content_type": content_type,
        "s3_path": file_key,
        "status": "RECEIVED",
        "uploaded_at": now,
        "uploaded_by": "portal_client",
        "source": "client_portal",
        "reviewed_by": "portal_client",
        "reviewed_at": now,
    }
    if client_id:
        document["client_id"] = client_id
    if custom_label:
        document["custom_label"] = custom_label
    await db.documents.insert_one(document)


async def _resolve_portal_client_id(
    client_data: dict,
    process: Optional[dict],
) -> Optional[str]:
    """
    Resolve o client_id do titular autenticado no Portal.

    PACOTE 5 (bug dos uploads órfãos): os tokens `magic_link` NÃO transportam
    `client_id` no payload e processos legados podem não ter `client_id`
    preenchido — nessas alturas o documento era gravado SEM client_id e
    ficava irrecuperável (órfão). Ordem de resolução:
      1. client_id explícito do client_data (access_code/no_process);
      2. claim client_id do token (verified_session / access_code_session);
      3. campo `client` do client_data (fluxo sem processo);
      4. `client_id` do processo;
      5. primeiro `client_ids[]` do processo (processos legados);
      6. mapeamento `portal_tokens` (client_id ↔ process_id).
    """
    token_payload = client_data.get("token_payload") or {}
    client = client_data.get("client") or {}

    client_id = (
        client_data.get("client_id")
        or token_payload.get("client_id")
        or client.get("id")
        or (process or {}).get("client_id")
    )

    if not client_id and process:
        client_ids = process.get("client_ids") or []
        if isinstance(client_ids, list) and client_ids:
            client_id = client_ids[0]

    if not client_id and process and process.get("id"):
        try:
            token_doc = await db.portal_tokens.find_one(
                {"process_id": process["id"]}, {"_id": 0, "client_id": 1}
            )
            if token_doc and token_doc.get("client_id"):
                client_id = token_doc["client_id"]
        except Exception as e:
            logger.warning(
                f"[PORTAL][CLIENT-ID] Falha ao resolver client_id via "
                f"portal_tokens para o processo {process.get('id')}: {e}"
            )

    return client_id


async def _reanchor_orphan_documents(process_id: str, client_id: str, now: str) -> int:
    """
    Re-ancora ao processo os documentos órfãos do cliente.

    PACOTE 5 (bug dos uploads órfãos): uploads feitos durante o onboarding
    (antes de o processo existir) ficam ancorados apenas ao `client_id`. Se
    por qualquer razão a âncora da criação do processo não os apanhou
    (concorrência, erro parcial, processos legados), cada novo upload com
    processo associado volta a tentar a re-âncora — garantindo que nenhum
    documento submetido pelo cliente fica invisível no Processo.
    """
    orphan_filter = {
        "client_id": client_id,
        "$or": [
            {"process_id": None},
            {"process_id": ""},
            {"process_id": {"$exists": False}},
        ],
    }
    result = await db.documents.update_many(
        orphan_filter,
        {"$set": {"process_id": process_id, "updated_at": now}},
    )
    reanchored = result.modified_count if result else 0
    if reanchored:
        logger.info(
            f"[PORTAL][RE-ANCHOR] {reanchored} documento(s) órfão(s) do cliente "
            f"{client_id} re-ancorados ao processo {process_id}"
        )
    return reanchored


async def _notify_assigned_team_upload(process: dict, filename: str, category: str):
    """Notifica TODOS os utilizadores atribuídos ao processo sobre um novo upload do cliente."""
    assigned_ids = _get_all_assigned_user_ids(process)
    if not assigned_ids:
        return

    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process.get("id", "")[:8]
    
    for uid in assigned_ids:
        try:
            user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if user:
                await send_notification_with_preference_check(
                    user.get("email"),
                    "Novo Documento Submetido",
                    f"O cliente {client_name} submeteu '{filename}' ({category}) no processo {process_ref} via Portal.",
                    notification_type="document_upload"
                )
        except Exception as e:
            logger.warning(f"Erro ao notificar utilizador {uid} sobre upload: {e}")


async def run_generate_portal_upload_url(data: dict, client_data: dict):
    """
    Gera uma pre-signed URL para upload direto ao S3.

    Suporta cliente sem processo (onboarding): usa pasta S3 do cliente.
    Com processo: usa pasta do processo. Categoria forçada a Index.
    """
    if not s3_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Serviço de armazenamento indisponível. Contacte o seu consultor."
        )

    process = client_data.get("process")
    client = client_data.get("client") or {}
    client_id = client_data.get("client_id") or (process or {}).get("client_id")
    process_id = process["id"] if process else None

    filename = data.get("filename", "")
    content_type = data.get("content_type", "application/octet-stream")
    category = data.get("category", "Outros")

    if category != "Index":
        logger.info(
            f"[PORTAL-PACOTE-BL] generate_upload_url: categoria original "
            f"'{category}' forçada para 'Index'. ficheiro={filename}"
        )
    category = "Index"

    if not filename:
        raise HTTPException(status_code=400, detail="Nome do ficheiro é obrigatório")

    safe_filename = filename.replace(" ", "_").replace("/", "-").replace("\\", "-")

    if process:
        storage_id = process_id
        client_name = process.get("client_name") or client.get("nome") or "cliente"
        s3_folder = process.get("s3_folder")
        target_collection = db.processes
    else:
        if not client_id:
            raise HTTPException(
                status_code=400,
                detail="Sem cliente associado. Não é possível fazer upload.",
            )
        storage_id = client_id
        client_name = client.get("nome") or "cliente"
        s3_folder = client.get("s3_folder")
        target_collection = db.clients

    # ── HOTFIX — Garantir mapeamento S3 (nunca deixar o cliente sem pasta) ──
    # Se ainda não há `s3_folder` guardado (no processo OU no cliente), resolve
    # /cria a pasta de forma robusta e persiste o mapeamento (via $set estrito,
    # apenas nesta chave) para que os próximos uploads/listagens sejam
    # consistentes e não dependam de matching por nome (fuzzy) a cada pedido.
    if not s3_folder:
        titular2_upload = (process or {}).get("titular2_data") or {}
        second_client_name = (process or {}).get("second_client_name") or titular2_upload.get("nome") or titular2_upload.get("name")
        mapping = await asyncio.to_thread(
            s3_service.ensure_client_folder_mapping,
            storage_id,
            client_name,
            second_client_name,
            s3_folder,
        )
        if mapping.get("success") and mapping.get("s3_folder"):
            s3_folder = mapping["s3_folder"]
            await target_collection.update_one(
                {"id": storage_id},
                {"$set": {"s3_folder": s3_folder}}
            )
            logger.info(
                f"[PORTAL][HOTFIX-S3-MAPPING] Mapeamento S3 {'criado' if mapping.get('created') else 'recuperado'} "
                f"para {'processo' if process else 'cliente'} {storage_id}: {s3_folder}"
            )

    result = s3_service.generate_upload_presigned_url(
        client_id=storage_id,
        client_name=client_name,
        category=category,
        filename=safe_filename,
        content_type=content_type,
        s3_folder=s3_folder,
        expiration=300
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Erro ao gerar link de upload. Tente novamente."
        )

    logger.info(
        f"[PORTAL] Upload URL gerada para {safe_filename} "
        f"(process={process_id or 'none'}, client={client_id}, cat: {category})"
    )

    return {
        "success": True,
        "upload_url": result["upload_url"],
        "file_key": result["file_key"],
        "expires_at": result["expires_at"],
        "expires_in_seconds": result["expires_in_seconds"],
        "method": "PUT",
        "headers": {"Content-Type": content_type},
    }


async def run_confirm_portal_upload(data: dict, client_data: dict):
    """
    Confirma upload para S3 e regista na base de dados.

    Sem processo: ancora ao client_id (órfão) até checklist completa criar o processo.
    Com processo: ancora ao process_id. Categoria forçada a Index.
    """
    # PACOTE DE — `uuid` já importado no topo do módulo; não re-importar aqui.

    process = client_data.get("process")
    process_id = process["id"] if process else None
    # PACOTE 5 (bug dos uploads órfãos) — resolução robusta do client_id:
    # tokens magic_link não o transportam e processos legados podem não o
    # ter gravado; sem este fallback o documento perdia a ligação ao cliente.
    client_id = await _resolve_portal_client_id(client_data, process)
    # Referência ao documento do cliente (fluxo sem processo / access_code):
    # usada para o nome do cliente no histórico do upload.
    client = client_data.get("client") or {}

    file_key = data.get("file_key")
    original_filename = data.get("original_filename")
    category = data.get("category", "Outros")
    file_size = data.get("file_size")
    content_type = data.get("content_type", "application/octet-stream")
    document_id = data.get("document_id")
    custom_label = data.get("custom_label")

    original_category_from_client = category
    category = "Index"
    if original_category_from_client and original_category_from_client != "Index":
        logger.info(
            f"[PORTAL-PACOTE-BL] Upload forçado para Index "
            f"(original={original_category_from_client}, file={original_filename})"
        )

    ai_categorization_info = None

    if not file_key:
        raise HTTPException(status_code=400, detail="file_key é obrigatório")
    if not original_filename:
        raise HTTPException(status_code=400, detail="original_filename é obrigatório")
    if not client_id and not process_id:
        raise HTTPException(status_code=400, detail="Sem cliente/processo associado")

    # INCIDENTE P0 — a posse da chave é verificada ANTES de tudo o resto:
    # antes de sondar o S3 (não se confirma a existência de uma chave que
    # vamos recusar — isso sozinho é um oráculo que diz o que há no bucket) e,
    # sobretudo, antes de QUALQUER escrita. Uma recusa que deixasse o registo
    # em `db.documents` não seria recusa nenhuma: é o registo que faz o
    # `/portal/download-url` autorizar a chave daí para a frente.
    assert_portal_file_key_e_do_cliente(file_key, process=process, client=client)

    # ── QUARENTENA (Set 2026) — validar os BYTES antes de existir registo ──
    # Com upload pré-assinado o backend nunca vê o ficheiro a passar, pelo que
    # a parede de magic bytes do CRM (`file_validation`) não pode ser chamada
    # no ponto de entrada. É chamada AQUI, depois do facto: um `HEAD` (tamanho
    # e tipo reais) e um `GET` de 2 KB (assinatura), ambos por
    # `asyncio.to_thread` — o `boto3` é síncrono e chamá-lo de uma corotina
    # pararia o event loop do worker inteiro à espera da rede.
    #
    # Isto SUBSTITUI o antigo `s3_service.file_exists(file_key)`: era a mesma
    # chamada `head_object`, feita de forma bloqueante e a responder a menos
    # perguntas. Fazer as duas seria pagar dois acessos pela mesma resposta —
    # e deixar a alguém, mais tarde, a escolha de apagar a errada.
    #
    # Reprovar aqui apaga o objecto e levanta 400; uma falha de LEITURA (S3 em
    # baixo) levanta 503 e **não apaga** — não se destrói o upload de um
    # cliente por causa de um soluço da infraestrutura.
    veredicto = await exigir_conteudo_valido(
        file_key, filename=original_filename
    )

    # O tamanho e o tipo passam a ser os REAIS, lidos do objecto — nunca os
    # que o cliente declarou no corpo do pedido. Era isto que fazia a base de
    # dados acreditar que um executável de 5 GB era um "PDF de 12 KB".
    file_size = veredicto.tamanho if veredicto.tamanho is not None else file_size
    content_type = veredicto.tipo_detectado or content_type

    now = datetime.now(timezone.utc).isoformat()

    # Satisfazer pedido REQUESTED (por process_id OU client_id)
    if document_id:
        # PACOTE 5 (bug dos uploads órfãos): pedidos do checklist gerados no
        # registo público/onboarding são ancorados APENAS ao `client_id`
        # (sem process_id). O match estrito por process_id falhava nesses
        # casos — o upload era registado como documento novo (duplicado) e o
        # pedido continuava pendente no Portal. Estratégia de duas tentativas:
        #   1. match estrito por process_id (comportamento clássico);
        #   2. se não casar, match pelo client_id — apenas para pedidos SEM
        #      process_id (nunca rouba pedidos de outro processo do mesmo
        #      cliente); o `$set` re-ancora-o ao processo desta submissão.
        match_q = {"id": document_id}
        if process_id:
            match_q["process_id"] = process_id
        elif client_id:
            match_q["client_id"] = client_id

        match_q_client_anchor = None
        if process_id and client_id:
            match_q_client_anchor = {
                "id": document_id,
                "client_id": client_id,
                "$or": [
                    {"process_id": None},
                    {"process_id": ""},
                    {"process_id": {"$exists": False}},
                ],
            }

        # PACOTE DE — APPEND logic: cada upload do portal é acrescentado ao
        # array `attached_files` (nunca substitui/apaga uploads anteriores).
        # Mantêm-se os campos top-level (`filename`, `s3_path`, `file_size`,
        # `content_type`, etc.) com $set para retrocompatibilidade —
        # `serialize_portal_document` e `run_get_portal_status` leem esses
        # campos directamente e devem continuar a reflectir o upload MAIS
        # RECENTE. O array `attached_files` preserva o histórico completo
        # (todos os ficheiros já submetidos para esta categoria).
        #
        # BUGFIX (E2E — lógica de quantidade, Set 2026): o status RECEIVED
        # (concluído) passa a ser decidido pela CONTAGEM — o pedido só fica
        # RECEIVED quando len(attached_files) >= expected_count (a quantidade
        # pedida, ex.: 3 recibos de vencimento). Antes, o 1º upload marcava
        # logo o pedido como concluído. Enquanto incompleto, mantém-se
        # REQUESTED/PENDING (o Portal continua a pedi-lo ao cliente).
        file_entry = {
            "file_id": str(uuid.uuid4()),
            "filename": original_filename,
            "original_filename": original_filename,
            "s3_path": file_key,
            "file_size": file_size,
            "content_type": content_type,
            "uploaded_at": now,
            "uploaded_by": "portal_client",
        }

        set_fields = {
            "filename": original_filename,
            "original_filename": original_filename,
            "file_size": file_size,
            "content_type": content_type,
            "s3_path": file_key,
            # Mantém category do pedido (checklist); ficheiro físico está em Index via S3 path
            "storage_category": "Index",
            "uploaded_at": now,
            "uploaded_by": "portal_client",
            "reviewed_by": "portal_client",
            "reviewed_at": now,
        }
        if client_id:
            set_fields["client_id"] = client_id
        if process_id:
            set_fields["process_id"] = process_id

        from services.document_portal_counts import apply_portal_request_upload

        progress = await apply_portal_request_upload(
            match_q,
            set_fields=set_fields,
            file_entry=file_entry,
            now=now,
        )

        # PACOTE 5 — 2ª tentativa: pedido ancorado só ao client_id (onboarding)
        if not progress.get("matched") and match_q_client_anchor:
            progress = await apply_portal_request_upload(
                match_q_client_anchor,
                set_fields=set_fields,
                file_entry=file_entry,
                now=now,
            )
            if progress.get("matched"):
                logger.info(
                    f"[PORTAL][RE-ANCHOR] Pedido {document_id} re-ancorado do "
                    f"client_id {client_id} para o processo {process_id}"
                )

        if progress.get("matched"):
            doc_id = document_id
            if progress.get("completed"):
                logger.info(
                    f"[PORTAL] Doc REQUESTED → RECEIVED: {document_id} "
                    f"({progress.get('uploaded_count')}/{progress.get('expected_count')} ficheiros)"
                )
            else:
                logger.info(
                    f"[PORTAL] Upload parcial {document_id}: "
                    f"{progress.get('uploaded_count')}/{progress.get('expected_count')} "
                    f"— pedido mantém-se pendente"
                )
        else:
            doc_id = str(uuid.uuid4())
            await _create_document_record(
                doc_id, process_id, file_key, original_filename,
                category, file_size, content_type, now, custom_label,
                client_id=client_id,
            )
    else:
        doc_id = str(uuid.uuid4())
        await _create_document_record(
            doc_id, process_id, file_key, original_filename,
            category, file_size, content_type, now, custom_label, client_id=client_id
        )

    # PACOTE 5 (bug dos uploads órfãos) — re-âncora defensiva: garante que
    # qualquer documento anterior do cliente que tenha ficado sem process_id
    # (uploads do onboarding anteriores à criação do processo) passa a
    # aparecer no Processo a partir deste upload.
    if process_id and client_id:
        try:
            await _reanchor_orphan_documents(process_id, client_id, now)
        except Exception as e:
            logger.warning(
                f"[PORTAL] Erro na re-âncora de documentos órfãos "
                f"(processo={process_id}, cliente={client_id}): {e}"
            )

    await invalidate_stats_cache()

    if process_id:
        try:
            from services.history import log_history
            client_name = (process or {}).get("client_name") or client.get("nome") or "Cliente"
            await log_history(
                process_id,
                user={"id": None, "name": f"{client_name} (Portal)", "role": "client_portal"},
                action="DOCUMENT_UPLOADED_BY_CLIENT",
                field="documento",
                old_value=None,
                new_value=f"{original_filename} [{category}]"
            )
        except Exception as e:
            logger.warning(f"[PORTAL] Erro ao registar histórico de upload: {e}")

        await _notify_assigned_team_upload(process, original_filename, category)

    # INCIDENTE P0 — o `temporary_url` SAIU da resposta de propósito.
    # Era ele a carga útil do ataque: um URL pré-assinado de leitura devolvido
    # no mesmo pedido que nomeava a chave. E não serve a ninguém — o cliente
    # acabou de enviar o ficheiro, já o tem; o `ClientPortal.jsx` lê apenas
    # `success` e nunca tocou neste campo. Sem ele, mesmo que uma guarda
    # regrida um dia, deixa de haver fuga de conteúdo no mesmo pedido: o
    # atacante teria de passar TAMBÉM pelo `/portal/download-url`.

    # Gatilho onboarding (criar processo se checklist completa)
    try:
        if client_id:
            from services.background_tasks import spawn_background_task

            spawn_background_task(
                _trigger_onboarding_check(client_id),
                name=f"onboarding-check:{client_id}",
            )
    except Exception as e:
        logger.warning(f"[PORTAL] Erro ao agendar verificação de onboarding: {e}")

    if process_id:
        try:
            from services.portal_documents_notify import check_and_notify_documents_complete
            from services.background_tasks import spawn_background_task

            company_id = process.get("company") or process.get("company_id")
            spawn_background_task(
                check_and_notify_documents_complete(process_id, company_id),
                name=f"docs-complete-notify:{process_id}",
            )
        except Exception as e:
            logger.warning(f"[PORTAL] Erro ao agendar gatilho de documentação completa: {e}")

    logger.info(
        f"[PORTAL] Upload confirmado: {original_filename} "
        f"(process={process_id or 'none'}, client={client_id})"
    )

    return {
        "success": True,
        "document_id": doc_id,
        "filename": original_filename,
        "category": category,
        "s3_path": file_key,
        "ai_categorization": ai_categorization_info,
        "process_id": process_id,
        "client_id": client_id,
    }


async def run_get_portal_download_url(file_key: str, client_data: dict):
    """
    Gera uma pre-signed URL para download de um documento do processo do cliente.

    SEGURANÇA:
    - Requer autenticação via token do portal
    - Valida que o ficheiro pertence ao processo do cliente (escopo do token)
    - URL temporária com validade de 1 hora
    - Bloqueia acesso a ficheiros de outros processos

    Query Params:
    - file_key: Caminho S3 do ficheiro (obrigatório)
    """
    if not file_key:
        raise HTTPException(status_code=400, detail="file_key é obrigatório.")

    if not s3_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Serviço de armazenamento indisponível."
        )

    # ── Validação de segurança: o ficheiro deve pertencer ao processo do cliente ──
    process = client_data.get("process")
    if not process:
        raise HTTPException(
            status_code=403,
            detail="Sem processo associado. Não é possível descarregar documentos."
        )

    process_id = process["id"]

    # INCIDENTE P0 — a mesma guarda AQUI, e não por excesso de zelo.
    # Este endpoint autoriza pela EXISTÊNCIA de um registo em `db.documents`
    # com este `s3_path` e este `process_id`. Durante a janela em que o
    # `confirm-upload` aceitava chaves arbitrárias, qualquer exploração deixou
    # exactamente esse registo — logo fechar só a escrita não fecha o que já
    # foi escrito. Com a guarda no caminho da LEITURA, os registos herdados
    # dessa janela deixam de ser servidos sem ser preciso limpar a colecção.
    assert_portal_file_key_e_do_cliente(
        file_key, process=process, client=client_data.get("client")
    )

    # Verificar se o documento existe na BD e pertence a este processo
    doc = await db.documents.find_one(
        {"s3_path": file_key, "process_id": process_id},
        {"_id": 0, "id": 1, "s3_path": 1}
    )

    # Fallback: verificar por file_key se s3_path não existir
    if not doc:
        doc = await db.documents.find_one(
            {"file_key": file_key, "process_id": process_id},
            {"_id": 0, "id": 1, "s3_path": 1}
        )

    if not doc:
        # Tentativa de acesso a ficheiro de outro processo — negar
        logger.warning(
            f"[PORTAL DOWNLOAD] Acesso negado: file_key={file_key} "
            f"não pertence ao processo {process_id}"
        )
        raise HTTPException(
            status_code=403,
            detail="Ficheiro não encontrado ou sem permissão de acesso."
        )

    # Verificar se o ficheiro existe no S3
    # `file_exists` faz um `head_object` — rede. Síncrono numa corotina, pára
    # o event loop do worker inteiro enquanto o S3 não responder (a mesma
    # família de defeito do `smtplib` no `send_email`). A assinatura do URL,
    # logo abaixo, é local e não precisa de thread.
    if not await asyncio.to_thread(s3_service.file_exists, file_key):
        raise HTTPException(
            status_code=404,
            detail="Ficheiro não encontrado no armazenamento."
        )

    # Gerar URL pré-assinada (válida por 1 hora)
    presigned_url = s3_service.get_presigned_url(file_key, expiration=3600)

    if not presigned_url:
        raise HTTPException(
            status_code=500,
            detail="Erro ao gerar link de download."
        )

    logger.info(
        f"[PORTAL DOWNLOAD] Download autorizado: file_key={file_key} "
        f"para processo {process_id}"
    )

    return {
        "success": True,
        "url": presigned_url,
        "expires_in": 3600,
    }


