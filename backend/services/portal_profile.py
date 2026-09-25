"""Perfil do cliente no Portal (GET/PUT /me).

Extraído de `routes/portal.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from database import db
from services.process_status import DELETED_STATUS_VALUES, LEAD_STATUS_VALUES
from services.workflow_phases import carregar_fases

logger = logging.getLogger(__name__)


# LISTAS DE RECURSO, não a fonte de verdade. O que vale é o que sai do
# `form_config` (ver `carregar_campos_editaveis`); estas só cobrem o caso
# em que a configuração não está acessível, para o Portal não deixar de
# gravar por causa de uma falha de leitura.
PROFILE_UPDATABLE_CONTACT_FIELDS = {"email", "email_secundario", "telefone", "telefone_secundario"}
PROFILE_UPDATABLE_PERSONAL_FIELDS = {
    "morada_fiscal", "estado_civil", "profissao", "naturalidade",
    "nacionalidade", "data_nascimento", "documento_id", "data_validade_cc",
    "sexo",
}



def construir_query_de_processo_a_trancar(
    process_ids: list, fases: list,
) -> dict:
    """Processo que já saiu da recolha de documentos (PACOTE CQ).

    O perfil do cliente tranca quando o processo AVANÇA para além da
    fase de recolha. A regra estava escrita à mão em DOIS sítios, com
    `clientes_espera` e `documentacao` cravados — o primeiro é a fase
    inicial do seed e o segundo nem existe no motor. Bastava o admin
    renomear a fase inicial para o perfil trancar no dia em que o
    cliente se regista.

    Hoje: não tranca enquanto o processo estiver na macro-fase `novo`
    (recolha), for uma lead, estiver perdido ou eliminado. Um processo
    numa fase que o motor não conhece TRANCA — é o lado seguro: melhor
    um perfil trancado a mais do que dados a serem alterados debaixo de
    uma análise a decorrer.
    """
    from services.workflow_phases import nomes_por_macro

    nao_tranca = (
        list(LEAD_STATUS_VALUES)
        + nomes_por_macro(fases, "novo")
        + nomes_por_macro(fases, "perdido")
        + list(DELETED_STATUS_VALUES)
    )
    return {
        "id": {"$in": process_ids},
        "is_deleted": {"$ne": True},
        "status": {"$nin": nao_tranca},
    }

async def carregar_campos_editaveis() -> dict:
    """Campos que o Portal pode gravar, derivados do formulário interno.

    O allowlist e o que o Portal MOSTRA saem do mesmo sítio
    (`portal_profile_schema`), pelo que não podem divergir: era essa
    divergência que fazia o cliente gravar um campo e o valor desaparecer
    em silêncio.

    Degradação: se a configuração não estiver acessível, usa as listas de
    recurso — o Portal continua a gravar o que já gravava.
    """
    try:
        from services.portal_profile_schema import (
            build_portal_profile_schema,
            portal_updatable_fields,
        )
        from services.public_form_config import load_merged_form_fields

        schema = build_portal_profile_schema(await load_merged_form_fields())
        campos = portal_updatable_fields(schema)
        # A validação é sobre `dados_pessoais`: `contacto` vem sempre com
        # os extras do Portal (email/telefone secundários), pelo que um
        # esquema VAZIO parecia válido e deixava o Portal sem conseguir
        # gravar um único campo pessoal.
        if campos["dados_pessoais"]:
            return campos
        logger.warning("[PORTAL PROFILE] Esquema vazio; a usar listas de recurso")
    except Exception as e:  # noqa: BLE001 - degradação graciosa
        logger.warning(
            "[PORTAL PROFILE] Falha a derivar campos do form_config (%s); "
            "a usar listas de recurso", e,
        )

    return {
        "contacto": set(PROFILE_UPDATABLE_CONTACT_FIELDS),
        "dados_pessoais": set(PROFILE_UPDATABLE_PERSONAL_FIELDS),
    }
# Campos SENSÍVEIS que NÃO são devolvidos ao frontend (mesmo encriptados)
PROFILE_HIDDEN_FIELDS = {"nif", "nome_pai", "nome_mae", "altura"}

# ── CRÍTICO — HOTFIX MAPEAMENTOS S3 ──────────────────────────────────────
# Campos de topo-de-nível que o Portal do Cliente NUNCA pode escrever,
# independentemente do que vier no payload do pedido. Isto protege os
# mapeamentos internos S3 (pasta/mapping) e as relações com processos,
# que só devem ser geridos pelo backend/admin — nunca pelo cliente final.
# Usado como rede de segurança (defense-in-depth) sobre o whitelist já
# aplicado a `contacto` e `dados_pessoais`.
PORTAL_PROTECTED_CLIENT_FIELDS = {
    "id", "_id", "process_ids", "processes",
    "s3_folder", "s3_folder_path", "s3_mapping_id", "s3_mapping",
    "s3_mapping_updated_at", "s3_mapping_updated_by",
    "role", "is_active", "created_at", "created_by",
}


def _assert_no_protected_fields(mongo_update: dict) -> dict:
    """
    Rede de segurança final antes de qualquer escrita no MongoDB a partir
    do Portal do Cliente.

    Remove (e regista em log de aviso) qualquer chave de topo-de-nível —
    incluindo notação com ponto, ex. "s3_folder.x" — que corresponda a um
    campo protegido. Isto garante que, mesmo que um bug futuro introduza
    um campo não-whitelisted no update, os mapeamentos S3 e as relações
    com processos nunca são apagados ou sobrescritos pelo cliente.
    """
    safe_update = {}
    for key, value in mongo_update.items():
        top_level_key = key.split(".", 1)[0]
        if top_level_key in PORTAL_PROTECTED_CLIENT_FIELDS:
            logger.error(
                f"[PORTAL PROFILE][BLOQUEADO] Tentativa de escrever campo protegido "
                f"'{key}' via Portal do Cliente foi ignorada."
            )
            continue
        safe_update[key] = value
    return safe_update


def build_portal_profile_mongo_update(
    data: "ClientProfileUpdate",
    existing_client: dict,
    now: str,
    campos_editaveis: Optional[dict] = None,
    recusados: Optional[list] = None,
) -> dict:
    """
    Constrói o dicionário de atualização MongoDB para o Portal do Cliente.

    REGRAS DE SEGURANÇA (hotfix mapeamentos S3):
    - Usa ESTRITAMENTE `$set` com notação de ponto por campo individual
      (nunca substitui sub-documentos inteiros nem o documento completo).
    - Apenas os campos em PROFILE_UPDATABLE_CONTACT_FIELDS e
      PROFILE_UPDATABLE_PERSONAL_FIELDS podem ser escritos.
    - Aplica `_assert_no_protected_fields` como rede de segurança final,
      garantindo que `s3_folder`, `process_ids` e outros campos internos
      NUNCA são tocados a partir deste endpoint.

    Args:
        data: Payload validado do pedido (whitelist já aplicado ao nível
            dos sub-campos de `contacto` e `dados_pessoais`).
        existing_client: Documento atual do cliente (usado para merge de
            `field_metadata` sem perder histórico de campos não alterados).
        now: Timestamp ISO 8601 a usar em `updated_at` / `field_metadata`.

    Args (continuação):
        campos_editaveis: `{"contacto": set, "dados_pessoais": set}` vindo
            de `carregar_campos_editaveis` (derivado do `form_config`).
            Sem isto, usa as listas de recurso do módulo.
        recusados: lista onde são acrescentados os campos DESCARTADOS. O
            comportamento anterior era descartar em silêncio: o cliente
            preenchia, gravava, lia "Perfil atualizado com sucesso!" e o
            valor não existia. Quem chama usa isto para o dizer.

    Returns:
        dict: Pronto a ser usado como `{"$set": update}` num `update_one`.
            Vazio (exceto `updated_at`) se não houver campos válidos.
    """
    permitidos = campos_editaveis or {
        "contacto": PROFILE_UPDATABLE_CONTACT_FIELDS,
        "dados_pessoais": PROFILE_UPDATABLE_PERSONAL_FIELDS,
    }
    contacto_permitido = permitidos.get("contacto") or set()
    pessoais_permitidos = permitidos.get("dados_pessoais") or set()
    fora = recusados if recusados is not None else []

    update_fields = {}

    contacto_updates = {}
    if data.contacto:
        for key, value in data.contacto.items():
            if key not in contacto_permitido:
                fora.append(key)
                continue
            if key in ("email", "email_secundario") and value:
                try:
                    from services.encryption import encrypt_value, generate_email_hash
                    encrypted = encrypt_value(str(value).strip().lower())
                    if encrypted:
                        contacto_updates[key] = encrypted
                        if key == "email":
                            email_hash = generate_email_hash(str(value).strip().lower())
                            if email_hash:
                                contacto_updates["email_hash"] = email_hash
                    else:
                        contacto_updates[key] = str(value).strip().lower()
                except Exception:
                    contacto_updates[key] = str(value).strip().lower()
            else:
                contacto_updates[key] = value
        if contacto_updates:
            update_fields["contacto"] = contacto_updates

    dp_updates = {}
    if data.dados_pessoais:
        for key, value in data.dados_pessoais.items():
            if key in pessoais_permitidos:
                dp_updates[key] = value
            else:
                # O NIF cai aqui de propósito: está trancado por regra de
                # negócio e nunca é gravado pelo Portal.
                fora.append(key)
        if dp_updates:
            update_fields["dados_pessoais"] = dp_updates

    if not update_fields:
        return {}

    mongo_update = {"updated_at": now}

    for key, value in update_fields.get("contacto", {}).items():
        mongo_update[f"contacto.{key}"] = value

    for key, value in update_fields.get("dados_pessoais", {}).items():
        mongo_update[f"dados_pessoais.{key}"] = value

    field_metadata_portal = {}
    for key in update_fields.get("contacto", {}):
        field_metadata_portal[f"contacto.{key}"] = {"source": "client", "updated_at": now}
    for key in update_fields.get("dados_pessoais", {}):
        field_metadata_portal[f"dados_pessoais.{key}"] = {"source": "client", "updated_at": now}

    if field_metadata_portal:
        existing_fm = (existing_client or {}).get("field_metadata") or {}
        mongo_update["field_metadata"] = {**existing_fm, **field_metadata_portal}

    # Rede de segurança final: nunca deixar sair campos protegidos daqui,
    # mesmo que a lógica acima seja alterada no futuro sem cuidado.
    return _assert_no_protected_fields(mongo_update)


def _decrypt_if_needed(value):
    """Desencripta um valor se tiver o prefixo ENC:."""
    if not value or not isinstance(value, str) or not value.startswith("ENC:"):
        return value
    try:
        from services.encryption import decrypt_value
        decrypted = decrypt_value(value)
        return decrypted if decrypted else value
    except Exception:
        return value


def _get_client_id_from_token(client_data: dict) -> Optional[str]:
    """
    Extrai o client_id dos dados do token do portal.

    Para access_code_session com "no_process": client_id vem no payload.
    Para outros tipos: client_id vem do campo client_id do processo.
    """
    # Caso 1: token access_code_session com "no_process"
    if client_data.get("client_id"):
        return client_data["client_id"]

    # Caso 2: processo com client_id
    process = client_data.get("process")
    if process and process.get("client_id"):
        return process["client_id"]

    return None


async def run_get_client_profile(client_data: dict):
    """
    Retorna os dados pessoais do cliente autenticado para o formulário
    de perfil no Portal do Cliente.

    SEGURANÇA:
    - Requer autenticação via token do portal (get_current_client)
    - NÃO devolve campos sensíveis (NIF, nome dos pais, etc.)
    - Desencripta campos encriptados (ENC:) antes de enviar
    - Indica se o cliente tem processo associado (para bloqueio de edição)
    """
    client_id = _get_client_id_from_token(client_data)

    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível identificar o cliente. Verifique a sua autenticação."
        )

    # Buscar dados do cliente
    client = await db.clients.find_one(
        {"id": client_id},
        {"_id": 0, "portal_access_code": 0, "notas": 0, "fonte": 0, "tags": 0, "created_by": 0}
    )

    if not client:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado."
        )

    # Determinar se o cliente tem processo associado (para bloqueio de edição)
    process_ids = client.get("process_ids", [])
    has_process = False
    is_data_confirmed = False
    if process_ids:
        # PACOTE CQ — O perfil é trancado se o processo avançar para além
        # da fase de recolha de documentos. Avalia diretamente as Fases do
        # Kanban (Status) em vez da flag is_indexed (que pode não estar
        # atualizada atempadamente na BD).
        # Fix: Normalize process status filters — inclui ambas as
        # variações (singular/plural) de "eliminado" e "desistência".
        active_process = await db.processes.find_one(
            construir_query_de_processo_a_trancar(
                process_ids, await carregar_fases(),
            ),
            {"_id": 0, "id": 1, "is_data_confirmed": 1}
        )
        has_process = active_process is not None
        # Fix: Sync Portal Profile with core CRM data — `is_data_confirmed`
        # vive no Processo (marcado True pela Indexação), mas este endpoint
        # devolvia sempre False. Sem isto, o Portal nunca mostrava o alerta
        # "Dados Bloqueados para Análise" mesmo depois dos dados terem sido
        # confirmados pela equipa de Indexação.
        if active_process:
            is_data_confirmed = active_process.get("is_data_confirmed") is True

    # Preparar dados pessoais (desencriptar campos encriptados + ocultar sensíveis)
    dados_pessoais = client.get("dados_pessoais", {}) or {}
    clean_dados_pessoais = {}
    for key, value in dados_pessoais.items():
        if key in PROFILE_HIDDEN_FIELDS:
            continue  # Não devolver campos sensíveis
        clean_dados_pessoais[key] = _decrypt_if_needed(value)

    # Preparar dados de contacto (desencriptar campos encriptados)
    contacto = client.get("contacto", {}) or {}
    clean_contacto = {}
    for key, value in contacto.items():
        # Ocultar email_hash (campo interno para blind index)
        if key.endswith("_hash"):
            continue
        clean_contacto[key] = _decrypt_if_needed(value)

    # O Portal renderiza a partir DESTE esquema, derivado do mesmo
    # `form_config` que alimenta o formulário interno. Enviá-lo daqui é o
    # que impede as duas listas de voltarem a divergir.
    form_schema: list = []
    try:
        from services.portal_profile_schema import build_portal_profile_schema
        from services.public_form_config import load_merged_form_fields

        form_schema = build_portal_profile_schema(await load_merged_form_fields())
    except Exception as e:  # noqa: BLE001 - o perfil abre à mesma
        logger.warning("[PORTAL PROFILE] Falha a montar o esquema: %s", e)

    return {
        "id": client.get("id"),
        "nome": client.get("nome", ""),
        "contacto": clean_contacto,
        "dados_pessoais": clean_dados_pessoais,
        "form_schema": form_schema,
        "has_process": has_process,
        # PACOTE BM — flag de dados confirmados/congelados pela Indexação.
        # Quando true, o Portal bloqueia todos os campos de input do perfil.
        "is_data_confirmed": is_data_confirmed,
    }


class ClientProfileUpdate(BaseModel):
    """Schema para atualização de perfil do cliente via Portal."""
    contacto: Optional[dict] = None
    dados_pessoais: Optional[dict] = None


async def run_update_client_profile(data: ClientProfileUpdate, client_data: dict):
    """
    Atualiza os dados pessoais do cliente autenticado.

    REGRAS DE SEGURANÇA:
    - Requer autenticação via token do portal
    - BLOQUEIA a atualização se o cliente já tiver um Process associado
      → Retorna 403: 'Dados trancados. Processo já em análise.'
    - Apenas campos permitidos são atualizados (whitelist)
    - NIF e nome NÃO podem ser alterados pelo cliente
    - Campos encriptados são re-encriptados antes de guardar
    """
    client_id = _get_client_id_from_token(client_data)

    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível identificar o cliente. Verifique a sua autenticação."
        )

    # ── REGRA CRÍTICA: Verificar se o cliente tem processo associado ──
    # NOTA: a projeção inclui apenas os campos efetivamente necessários
    # (process_ids para a verificação de bloqueio, field_metadata para o
    # merge de proveniência). NUNCA projetar/usar campos internos como
    # s3_folder — este endpoint não deve ler nem escrever mapeamentos S3.
    client = await db.clients.find_one(
        {"id": client_id},
        {"_id": 0, "process_ids": 1, "field_metadata": 1}
    )

    if not client:
        raise HTTPException(
            status_code=404,
            detail="Cliente não encontrado."
        )

    process_ids = client.get("process_ids", [])
    if process_ids:
        # PACOTE CQ — O perfil é trancado se o processo avançar para além
        # da fase de recolha de documentos. Avalia diretamente as Fases do
        # Kanban (Status) em vez da flag is_indexed.
        # Fix: Normalize process status filters — inclui ambas as
        # variações (singular/plural) de "eliminado" e "desistência".
        active_process = await db.processes.find_one(
            construir_query_de_processo_a_trancar(
                process_ids, await carregar_fases(),
            ),
            {"_id": 0, "id": 1}
        )
        if active_process:
            raise HTTPException(
                status_code=403,
                detail="Dados trancados. O seu processo já se encontra em análise."
            )

    # ── Construir atualização segura (whitelist + $set granular) ──
    # CRÍTICO (hotfix mapeamentos S3): a atualização usa ESTRITAMENTE $set
    # com chaves individuais (notação de ponto) para os campos que o
    # cliente tem permissão para editar. Nunca substitui o documento
    # completo nem sub-documentos inteiros, por isso `s3_folder`,
    # `process_ids` e outras relações internas nunca são tocados aqui.
    now = datetime.now(timezone.utc).isoformat()
    campos_editaveis = await carregar_campos_editaveis()
    recusados: list = []
    mongo_update = build_portal_profile_mongo_update(
        data, client, now, campos_editaveis=campos_editaveis, recusados=recusados
    )

    if recusados:
        # Antes descartava-se em silêncio: o cliente preenchia, gravava e
        # lia "Perfil atualizado com sucesso!" com o valor perdido.
        logger.warning(
            "[PORTAL PROFILE] Cliente %s enviou campos não editáveis: %s",
            client_id, sorted(set(recusados)),
        )

    if not mongo_update:
        return {
            "success": True,
            "message": "Nenhum campo para atualizar.",
            "updated_fields": [],
            "rejected_fields": sorted(set(recusados)),
        }

    updated_fields = [
        key for key in ("contacto", "dados_pessoais")
        if any(k.startswith(f"{key}.") for k in mongo_update)
    ]

    await db.clients.update_one(
        {"id": client_id},
        {"$set": mongo_update}
    )

    logger.info(
        f"[PORTAL PROFILE] Cliente {client_id} atualizou perfil: {updated_fields}"
    )

    return {
        "success": True,
        "rejected_fields": sorted(set(recusados)),
        "message": "Perfil atualizado com sucesso.",
        "updated_fields": updated_fields,
    }
