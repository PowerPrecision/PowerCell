"""GET/POST/PUT clientes — get, create, update.

Extraído de `routes/clients.py`.
"""
from __future__ import annotations

import uuid
import logging
import asyncio
import copy
import re
import os
import unicodedata
from typing import List, Optional
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError
from fastapi import HTTPException, Request

from database import db
from services.workflow_phases import fases_do_utilizador
from models.client import (
    Client, ClientCreate, ClientUpdate,
    ClientContact, ClientPersonalData,
    find_or_create_client_key,
    generate_portal_access_code,
)
from services.auth import get_effective_role
from models.auth import UserRole
from services.encryption import (
    encryption_service,
    encrypt_client_data,
    decrypt_client_data,
    decrypt_clients_list,
    generate_nif_hash,
    generate_email_hash,
    generate_telefone_hash,
)
from services.client_uniqueness import (
    IDENTIDADE_ASSOCIAR,
    IDENTIDADE_DA_MESMA_REDE,
    IDENTIDADE_OPACA,
    assert_cliente_unico,
    associar_rede_ao_cliente,
    construir_erro_de_duplicado,
    erro_opaco_de_duplicado,
    rede_do_cliente,
    resolver_identidade,
    so_o_que_mudou,
)
from services.process_service import get_next_process_number
from services.s3_document_root import pasta_para_gravar
from services.s3_storage import s3_service
from services.tenant_network import rede_de_omissao, resolve_tenant_stamp
# No TOPO de propósito: importado à primeira chamada, dentro de um `patch("database.db")` de um teste, o
# módulo ficava com o `db` do duplo para sempre (a armadilha da ordem de importação).
from services.client_window import e_visitante_do_cliente, ids_dos_processos_visiveis
from utils.input_sanitization import (
    sanitize_email, sanitize_name, sanitize_phone, sanitize_nif,
    sanitize_string, sanitize_url, log_sanitization_rejection,
)
from utils.search_filters import create_accent_insensitive_regex, build_multiword_search_filter

logger = logging.getLogger(__name__)

from services.client_portal_email import _send_portal_welcome_email_safe
from services.encryption import limpar_blind_indexes_de_campos_vazios
from services.nascimento_protegido import proteger_caminhos
from services.campos_limpaveis import (
    aliases_a_limpar_no_cliente,
    campos_pessoais_limpos,
    exigir_nome,
    limpar_espelhos_nos_processos,
)

class _SemAcessoAoPortal(Exception):
    """Sinal interno: o visitante de um cliente partilhado não recebe o acesso ao Portal."""


async def run_get_client(
    client_id: str,
    user: dict
):
    """Obter detalhes de um cliente."""
    client = await db.clients.find_one({"id": client_id}, {"_id": 0})
    
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Carregar detalhes dos processos (como titular principal E como 2º titular)
    process_ids_as_main = client.get("process_ids") or []
    
    # Procurar processos onde este cliente é 2º titular (second_client_id)
    processes_as_second = await db.processes.find(
        {"second_client_id": client_id},
        {"_id": 0, "id": 1}
    ).to_list(length=50)
    process_ids_as_second = [p["id"] for p in processes_as_second]
    
    # Combinar IDs (sem duplicados)
    all_process_ids = list(dict.fromkeys(process_ids_as_main + process_ids_as_second))

    # «JANELA, NÃO PORTA» (Lote 6): quem chega a esta ficha por um processo PARTILHADO vê esse
    # processo e mais nenhum. Tudo o que se deriva dos processos do cliente (a lista, a última
    # actividade, o acesso ao Portal) lê-se só sobre os que a janela deixa ver.
    all_process_ids = await ids_dos_processos_visiveis(
        user, all_process_ids, client_id=client_id, cliente=client,
    )
    visitante = await e_visitante_do_cliente(client, user)
    client["process_ids"] = [pid for pid in (client.get("process_ids") or []) if pid in all_process_ids]
    
    processes = []
    if all_process_ids:
        processes = await db.processes.find(
            {"id": {"$in": all_process_ids}},
            {"_id": 0, "id": 1, "process_number": 1, "status": 1, "process_type": 1, 
             "prioridade": 1, "created_at": 1, "updated_at": 1, "is_active": 1,
             "client_id": 1, "second_client_id": 1, "client_name": 1}
        ).to_list(length=50)
    
    # Enriquecer processos com labels, cores do workflow e role do cliente
    if processes:
        statuses = await fases_do_utilizador(user)
        status_map = {s["name"]: s for s in statuses}
        for p in processes:
            status_info = status_map.get(p.get("status"), {})
            p["status_label"] = status_info.get("label", p.get("status", ""))
            p["status_color"] = status_info.get("color", "#6B7280")
            
            # Determinar o role do cliente neste processo
            if p.get("second_client_id") == client_id and p.get("client_id") != client_id:
                p["client_role"] = "2º titular"
            elif p.get("client_id") == client_id:
                p["client_role"] = "titular"
            elif client_id in (p.get("process_ids") or []):
                p["client_role"] = "titular"
            else:
                p["client_role"] = "2º titular"
    
    client["processes"] = processes

    # ============================================================
    # PACOTE DA — latest_activity: atividade mais recente do cliente
    # ============================================================
    # Busca a última entrada da coleção activities ligada a qualquer
    # processo deste cliente (all_process_ids). O Frontend
    # (ClientDetailsModal) mostra isto na secção "Observações e IA"
    # para que o consultor veja a última interação registada.
    # ============================================================
    try:
        if all_process_ids:
            latest_act = await db.activities.find_one(
                {"process_id": {"$in": all_process_ids}, "comment": {"$exists": True, "$ne": ""}},
                {"_id": 0},
                sort=[("created_at", -1)]
            )
            client["latest_activity"] = latest_act
        else:
            client["latest_activity"] = None
    except Exception as e:
        logger.warning(f"Erro ao buscar latest_activity para cliente {client_id}: {e}")
        client["latest_activity"] = None

    # ============================================================
    # PACOTE DC — portal_access: Código de Acesso + magic link ativo
    # ============================================================
    try:
        portal_access_code = client.get("portal_access_code")
        active_short_id = None
        active_magic_link = None
        if all_process_ids:
            token_doc = await db.portal_tokens.find_one(
                {"process_id": {"$in": all_process_ids}},
                {"_id": 0, "short_id": 1, "process_id": 1, "created_at": 1}
            )
            if token_doc and token_doc.get("short_id"):
                active_short_id = token_doc["short_id"]
                _fe_url = os.environ.get("FRONTEND_URL", "").rstrip("/")
                if _fe_url:
                    active_magic_link = f"{_fe_url}/portal/{active_short_id}"
        if visitante:
            # O acesso do cliente ao Portal é do dono do cliente: com ele entrava-se em TUDO o
            # que o cliente vê, não só no processo partilhado.
            raise _SemAcessoAoPortal()
        client["portal_access"] = {
            "portal_access_code": portal_access_code,
            "short_id": active_short_id,
            "magic_link": active_magic_link,
            "has_active_token": active_short_id is not None,
        }
    except _SemAcessoAoPortal:
        client["portal_access"] = None
    except Exception as e:
        logger.warning(f"Erro ao buscar portal_access para cliente {client_id}: {e}")
        client["portal_access"] = None

    if visitante:
        client.pop("portal_access_code", None)

    # Desencriptar dados sensíveis
    client = decrypt_client_data(client)
    
    # Safeguard: garantir que created_at, updated_at e assigned_at são sempre válidos
    now_iso = datetime.now(timezone.utc).isoformat()
    if not client.get("created_at"):
        client["created_at"] = now_iso
    if not client.get("updated_at"):
        client["updated_at"] = now_iso
    if client.get("assigned_at") == "" or client.get("assigned_at") is False:
        client["assigned_at"] = None
    
    return client

async def _associar_cliente_global(
    existente: dict,
    rede: Optional[str],
    *,
    nome: str,
    email: Optional[str],
    telefone: Optional[str],
    nif: Optional[str],
    user: dict,
) -> Client:
    """D-42: o cliente já existe noutra rede e quem pede provou conhecê-lo — a rede passa a vê-lo como VISITANTE.

    Acrescenta a rede a ``redes_associadas`` e **mais nada**: o documento do
    cliente não se reescreve (nome, contactos e dados da outra rede ficam como
    estão) e a resposta devolve só o que quem pediu acabou de escrever, mais o
    `id` — nunca a ficha. O que esta equipa passa a ver do cliente é o que a
    janela (`client_window`) deixa: os processos da sua rede.
    """
    if not await associar_rede_ao_cliente(existente["id"], rede):
        # Sem rede determinável não há a quem dar a janela: seria devolver o id de um
        # cliente que a equipa não poderia abrir. O 409 opaco é a resposta honesta.
        raise erro_opaco_de_duplicado()
    logger.info(
        "[CLIENT-CREATE] Cliente global %s associado à rede %s por %s (NIF + Email provados).",
        existente.get("id"), rede, user.get("email"),
    )
    return Client(
        id=existente["id"],
        nome=nome,
        contacto=ClientContact(email=email, telefone=telefone),
        dados_pessoais=ClientPersonalData(nif=nif),
        portal_access_code=None,
    )


async def run_create_client(
    client_data: ClientCreate,
    user: dict,
    *,
    frontend_url: Optional[str] = None,
):
    """Criar um novo cliente."""
    
    # Sanitizar inputs do utilizador
    sanitized_nome = sanitize_name(client_data.nome)
    if not sanitized_nome:
        log_sanitization_rejection("nome", client_data.nome or "", "Nome vazio ou inválido após sanitização")
        raise HTTPException(status_code=400, detail="Nome inválido. Use apenas letras e espaços.")
    
    # VALIDAÇÃO: E-mail obrigatório para acesso ao Portal do Cliente
    if not client_data.email or not client_data.email.strip():
        raise HTTPException(
            status_code=400,
            detail="O e-mail é obrigatório para a criação do Portal do Cliente."
        )
    
    sanitized_email = sanitize_email(client_data.email) if client_data.email else None
    if client_data.email and not sanitized_email:
        log_sanitization_rejection("email", client_data.email, "Email inválido após sanitização")
        raise HTTPException(status_code=400, detail="Formato de email inválido.")
    
    sanitized_telefone = sanitize_phone(client_data.telefone) if client_data.telefone else None
    
    sanitized_nif = sanitize_nif(client_data.nif) if client_data.nif else None
    if client_data.nif and not sanitized_nif:
        log_sanitization_rejection("nif", client_data.nif, "NIF inválido após sanitização")
        raise HTTPException(status_code=400, detail="NIF inválido. Deve ter 9 dígitos.")
    
    sanitized_fonte = sanitize_string(client_data.fonte, max_length=100) if client_data.fonte else None
    sanitized_notas = sanitize_string(client_data.notas, max_length=500) if client_data.notas else None

    # ── Unicidade de NIF/Email: UM PONTO ÚNICO (Lote 2, ponto 4) ───────
    # A mesma regra corre agora na edição (`run_update_client`). Estava
    # escrita aqui à mão e NÃO existia lá — logo o bloco em linha saiu
    # para `client_uniqueness`, para as duas portas não poderem divergir.
    # D-38: a regra é por REDE — a de destino é a do carimbo que o cliente vai
    # levar, por isso resolve-se ANTES da verificação (e não depois, como estava).
    carimbo = await resolve_tenant_stamp(
        user, active_company_id=user.get("active_company_id"),
    )
    # Sem carimbo o cliente nasce por carimbar — e a pilha por carimbar pertence
    # à rede de omissão —, logo é nela (toda, não só a parte por carimbar) que
    # se procura o duplicado.
    # D-42: a identidade é GLOBAL (NIF/Email; o telemóvel não conta). Um cliente
    # que já existe NOUTRA rede não é um erro quando quem pede prova conhecê-lo
    # (NIF e Email do mesmo cliente): associa-se, sem copiar nem mostrar a ficha.
    rede_de_destino = (carimbo or {}).get("network_id") or rede_de_omissao()
    identidade = await resolver_identidade(
        sanitized_nif, sanitized_email, rede=rede_de_destino,
    )
    if identidade.veredicto == IDENTIDADE_DA_MESMA_REDE:
        raise construir_erro_de_duplicado(identidade.cliente, sanitized_nif, sanitized_email)
    if identidade.veredicto == IDENTIDADE_OPACA:
        raise erro_opaco_de_duplicado()
    if identidade.veredicto == IDENTIDADE_ASSOCIAR:
        return await _associar_cliente_global(
            identidade.cliente, rede_de_destino,
            nome=sanitized_nome, email=sanitized_email, telefone=sanitized_telefone,
            nif=sanitized_nif, user=user,
        )

    now = datetime.now(timezone.utc).isoformat()
    
    client = Client(
        id=str(uuid.uuid4()),
        nome=sanitized_nome,
        contacto=ClientContact(
            email=sanitized_email,
            telefone=sanitized_telefone
        ),
        dados_pessoais=ClientPersonalData(
            nif=sanitized_nif
        ),
        portal_access_code=generate_portal_access_code(),
        fonte=sanitized_fonte,
        notas=sanitized_notas,
        created_at=now,
        updated_at=now,
        created_by=user.get("email"),
        created_by_name=(user.get("name") or "").strip() or None,
        # BUGFIX (UX Fix #3, Fev 2026): sem isto, o cliente nunca aparecia na
        # lista "Registos de Clientes" (a query dessa página filtra sempre
        # por registration_completed=True — antes só era definido pelo
        # registo público).
        registration_completed=True,
    )
    
    # Encriptar campos sensíveis antes de guardar
    client_dict = client.model_dump()
    client_dict = encrypt_client_data(client_dict)

    # ============================================================
    # PACOTE 9 — AUTO-ATRIBUIÇÃO AO CRIADOR (Consultor/Intermediário)
    # ============================================================
    # Se quem cria o cliente tem perfil activo de Consultor ou Intermediário,
    # o cliente fica automaticamente atribuído ao próprio criador. Sem isto,
    # o cliente recém-criado (fase de Pré-Registo, ainda sem processo) não
    # aparecia de imediato na lista "Os Meus Clientes".
    # Usa o cargo EFECTIVO (X-Active-Role/UCR) — multi-perfis validados pelo
    # perfil activo, não pela role primária do JWT.
    creator_role = (user.get("effective_role") or user.get("role") or "").lower()
    if creator_role in ("consultor", "intermediario"):
        client_dict["assigned_to"] = user.get("id")
        client_dict["assigned_at"] = now
        logger.info(
            f"[CLIENT-CREATE] Auto-atribuição ao criador ({creator_role}): "
            f"cliente {client.id} → {user.get('id')}"
        )

    # ── Carimbo de rede na ESCRITA (D-31) ──
    # `POST /clients` nunca carimbou: o cliente nascia por carimbar e só o
    # grupo incumbente o via nas listagens. Com o pedido por ID fechado à
    # rede, um cliente criado por um utilizador de outra rede deixava de ter
    # dono visível. `resolve_tenant_stamp` devolve `None` sem contexto de
    # empresa, e aí NÃO se carimba (uma rede errada é permanente).
    if carimbo:
        client_dict.update(carimbo)

    try:
        await db.clients.insert_one(client_dict)
    except DuplicateKeyError:
        # A corrida que a procura não apanha: dois pedidos com o mesmo NIF/Email ao mesmo
        # tempo. O índice único parcial (`db_indexes`, D-42) é a última linha de defesa.
        logger.info("[CLIENT-CREATE] Índice único recusou o cliente (corrida de NIF/Email).")
        raise erro_opaco_de_duplicado()

    logger.info(f"Cliente criado: {client.id} - {client.nome} por {user.get('email')}")

    # ============================================================
    # PACOTE FQ-3 — Garantir mapeamento de pasta S3 logo na criação
    # ============================================================
    # Antes, a pasta S3 do cliente só era criada de forma "lazy" no
    # primeiro upload via Portal (ver `services/portal_upload_ops.py`).
    # Isto deixava o cliente sem `s3_folder` até esse momento, o que
    # atrasava/quebrava fluxos que dependem do mapeamento logo após a
    # criação (Explorer S3 admin, checklist de documentos, etc.).
    # Chamamos `ensure_client_folder_mapping` já aqui, imediatamente a
    # seguir à inserção do cliente na BD, e persistimos o resultado via
    # `$set` estrito apenas na chave `s3_folder`.
    try:
        s3_mapping = await asyncio.to_thread(
            s3_service.ensure_client_folder_mapping,
            client.id,
            sanitized_nome,
            None,
            None,
        )
        pasta = pasta_para_gravar(
            s3_mapping.get("s3_folder"),
            contexto=f"criação do cliente {client.id}",
        ) if s3_mapping.get("success") else None
        if pasta:
            await db.clients.update_one(
                {"id": client.id},
                {"$set": {"s3_folder": pasta}}
            )
            client_dict["s3_folder"] = pasta
            logger.info(
                f"[CLIENT-CREATE][S3-MAPPING] Mapeamento S3 "
                f"{'criado' if s3_mapping.get('created') else 'recuperado'} "
                f"para cliente {client.id}: {s3_mapping['s3_folder']}"
            )
        else:
            logger.warning(
                f"[CLIENT-CREATE][S3-MAPPING] Não foi possível criar/recuperar "
                f"mapeamento S3 para cliente {client.id} ({client.nome})"
            )
    except Exception as e:
        logger.warning(
            f"[CLIENT-CREATE][S3-MAPPING] Erro ao criar mapeamento S3 "
            f"para cliente {client.id}: {e}"
        )

    # ============================================================
    # BUGFIX (Ajuste Arquitetural, Fev 2026): a geração de pedidos de
    # documento e o email de boas-vindas passaram a ser responsabilidade
    # exclusiva da criação do Processo (services/process_create.py —
    # create_default_portal_documents / send_portal_welcome_email_from_process),
    # já que agora todo o Cliente criado manualmente ("Novo Cliente") tem
    # sempre um Processo associado (estado PRE_REGISTO). Manter a geração
    # também aqui, ao nível do Cliente, criava pedidos "orfãos" (sem
    # process_id) que nunca chegavam a ser mostrados no Portal.
    # ============================================================

    # ============================================================
    # PACOTE CY — Enviar email de boas-vindas do Portal em background
    # ============================================================
    # Antes o email NÃO era enviado na criação do cliente (só gerava o
    # portal_access_code). Agora dispara em background via asyncio.create_task
    # para não atrasar a resposta da API. Falhas são logadas mas não
    # rebentam o fluxo de criação.
    #
    # `skip_welcome_email=True` quando o chamador vai criar um Processo
    # imediatamente a seguir (evita duplicar o email — nesse caso o email
    # dispara em `send_portal_welcome_email_from_process`).
    # ============================================================
    if sanitized_email and not client_data.skip_welcome_email:
        # PACOTE BH — spawn com referência forte (services/background_tasks):
        # `asyncio.create_task` puro mantém apenas referência fraca e a task
        # podia ser recolhida pelo GC antes de enviar o email.
        # PACOTE 10 — user_id explícito para o task_log do monitor global.
        from services.background_tasks import spawn_background_task

        spawn_background_task(_send_portal_welcome_email_safe(
            client_email=sanitized_email,
            client_name=sanitized_nome,
            portal_access_code=client.portal_access_code,
            client_id=client.id,
            user_id=user.get("id"),
            frontend_url=frontend_url,
            user=user,
        ), name=f"portal-welcome-email:{client.id}")

    # Desencriptar para a resposta
    client_dict = decrypt_client_data(client_dict)
    return Client(**client_dict)

def _seccao_decifrada(client: dict, seccao: str) -> dict:
    """Uma secção do cliente (`contacto`/`dados_pessoais`) em claro, para fazer merge."""
    from services.encryption import decrypt_client_data

    return decrypt_client_data({seccao: client.get(seccao) or {}}).get(seccao) or {}


def sync_de_contactos_limpos(campos_limpos) -> dict:
    """`$set` que tira dos PROCESSOS os contactos que o cliente deixou de ter."""
    sync: dict = {}
    if "email" in campos_limpos:
        sync.update({
            "client_email": "", "personal_data.email": "", "personal_data.email_hash": "",
        })
    if "telefone" in campos_limpos:
        sync.update({
            "client_phone": "", "personal_data.telefone": "", "personal_data.phone": "",
            "personal_data.telefone_hash": "",
        })
    return sync


async def run_update_client(
    client_id: str,
    client_data: ClientUpdate,
    request: Request,
    user: dict
):
    """Actualizar dados de um cliente."""
    client = await db.clients.find_one({"id": client_id})
    
    if not client:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Verificar permissão de edição
    user_role = user.get("role", "")
    user_permissions = user.get("permissions", {})
    user_actions = user_permissions.get("actions", [])
    
    # Se o utilizador tem permissões personalizadas, verificar se tem "edit_client"
    # Caso contrário, verificar pelo role (roles que historicamente podem editar)
    can_edit = "edit_client" in user_actions
    if not can_edit and not user_actions:
        # Sem permissões personalizadas - verificar pelo role
        from models.auth import UserRole
        can_edit = user_role in [UserRole.MASTER, UserRole.ADMIN, UserRole.CEO, UserRole.CONSULTOR,
                                UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]
    
    if not can_edit:
        raise HTTPException(
            status_code=403, 
            detail="Não tem permissão para editar dados do cliente. Apenas visualização."
        )
    
    # O nome não se apaga: pedido com `nome` vazio é um erro (400) e recusa-se
    # ANTES de gravar o que quer que seja no mesmo pedido. Ignorá-lo em silêncio
    # seria o sintoma do bug que isto corrige (grava «com sucesso» e o valor volta).
    exigir_nome(client_data.model_fields_set, client_data.nome)

    # Sanitizar inputs
    sanitized_nome = None
    if client_data.nome:
        sanitized_nome = sanitize_name(client_data.nome)
        if not sanitized_nome:
            log_sanitization_rejection("nome", client_data.nome, "Nome vazio ou inválido após sanitização")
            raise HTTPException(status_code=400, detail="Nome inválido. Use apenas letras e espaços.")
    
    # Unicidade (Lote 2, ponto 4): guardamos o que ESTA submissão traz, e
    # nunca o resultado do merge com o que já está em base. O valor em base
    # está ENCRIPTADO, e calcular o índice cego sobre um criptograma dá um
    # hash que nunca casa — a guarda passaria sempre, calada.
    email_submetido: Optional[str] = None
    nif_submetido: Optional[str] = None

    sanitized_contacto = None
    contactos_limpos: list = []
    submetidos_contacto: set = set()
    if client_data.contacto:
        contact_dump = client_data.contacto.model_dump(exclude_unset=True)
        # Campo ESCRITO vazio (`""`/`null`/só espaços) = «apaga». Resolve-se ANTES
        # de sanitizar (um email em branco não é um email inválido) e leva o
        # índice cego do valor antigo consigo, senão a pesquisa e a guarda de
        # duplicados continuam a achar o cliente pelo email que ele já não tem.
        contactos_limpos = limpar_blind_indexes_de_campos_vazios(contacto=contact_dump)
        if "email" in contact_dump and contact_dump["email"]:
            s_email = sanitize_email(contact_dump["email"])
            if not s_email:
                log_sanitization_rejection("contacto.email", contact_dump["email"], "Email inválido após sanitização")
                raise HTTPException(status_code=400, detail="Formato de email inválido.")
            contact_dump["email"] = s_email
            email_submetido = s_email
        if "telefone" in contact_dump and contact_dump["telefone"]:
            contact_dump["telefone"] = sanitize_phone(contact_dump["telefone"]) or contact_dump["telefone"]
        if "telefone_secundario" in contact_dump and contact_dump["telefone_secundario"]:
            contact_dump["telefone_secundario"] = sanitize_phone(contact_dump["telefone_secundario"]) or contact_dump["telefone_secundario"]
        # Merge with existing contacto to preserve fields not in this update.
        # O existente vem DECIFRADO: o merge passa por `encrypt_client_data`, que
        # recalcula o índice cego a partir do valor que lhe dão — com o telefone
        # ainda cifrado, calculava-o sobre o criptograma e o `telefone_hash` de um
        # cliente deixava de casar com o número só por se editar o email.
        existing_contacto = _seccao_decifrada(client, "contacto")
        submetidos_contacto = set(contact_dump)
        sanitized_contacto = {**existing_contacto, **contact_dump}
    
    sanitized_dados_pessoais = None
    pessoais_limpos: list = []
    if client_data.dados_pessoais:
        pessoais_dump = client_data.dados_pessoais.model_dump(exclude_unset=True)
        if "nif" in pessoais_dump and pessoais_dump["nif"]:
            s_nif = sanitize_nif(pessoais_dump["nif"])
            if not s_nif:
                log_sanitization_rejection("dados_pessoais.nif", pessoais_dump["nif"], "NIF inválido após sanitização")
                raise HTTPException(status_code=400, detail="NIF inválido. Deve ter 9 dígitos.")
            pessoais_dump["nif"] = s_nif
            nif_submetido = s_nif
        for str_field in ["nome", "documento_id", "morada_fiscal", "phone", "telefone", "nacionalidade", "profissao"]:
            if str_field in pessoais_dump and pessoais_dump[str_field]:
                pessoais_dump[str_field] = sanitize_string(str(pessoais_dump[str_field]), max_length=200)
        # Campo ESCRITO vazio (`""`/`null`/espaços) = «apaga», como nos contactos:
        # o valor, o índice cego (nif_hash) e os nomes alternativos do mesmo dado.
        pessoais_limpos = campos_pessoais_limpos(pessoais_dump)
        limpar_blind_indexes_de_campos_vazios(dados_pessoais=pessoais_dump)
        # Merge with existing dados_pessoais to preserve fields not in this update
        existing_pessoais = _seccao_decifrada(client, "dados_pessoais")
        sanitized_dados_pessoais = {
            **existing_pessoais,
            **aliases_a_limpar_no_cliente(existing_pessoais, pessoais_limpos),
            **pessoais_dump,
        }
    
    sanitized_notas = sanitize_string(client_data.notas, max_length=500) if client_data.notas is not None else None

    # ── Unicidade de NIF/Email na EDIÇÃO (Lote 2, ponto 4) ─────────────
    # A criação já recusava; aqui não havia guarda nenhuma, pelo que
    # bastava abrir um cliente e trocar o NIF para o de outro. A mesma
    # função das duas portas, com `excluir_id`: sem ele o cliente casava
    # CONSIGO PRÓPRIO e gravar sem mexer no NIF devolvia 409.
    # D-38: três campos, na rede DESTE cliente, e só o que mudou (um duplicado
    # antigo em que não se tocou não pode travar a edição de outro campo).
    nif_a_verificar, email_a_verificar = so_o_que_mudou(client, nif_submetido, email_submetido)
    await assert_cliente_unico(
        nif_a_verificar, email_a_verificar,
        rede=rede_do_cliente(client), excluir_id=client_id,
    )

    update_dict = {"updated_at": datetime.now(timezone.utc).isoformat()}

    if sanitized_nome:
        update_dict["nome"] = sanitized_nome
    if sanitized_contacto:
        update_dict["contacto"] = sanitized_contacto
    if sanitized_dados_pessoais:
        update_dict["dados_pessoais"] = sanitized_dados_pessoais
    if client_data.tags is not None:
        update_dict["tags"] = client_data.tags
    if sanitized_notas is not None:
        update_dict["notas"] = sanitized_notas

    # PACOTE CS — Data Provenance: aceitar field_metadata do frontend
    # e fazer merge seguro (não apaga metadata de campos não atualizados).
    # Formato: {"dados_pessoais.nif": {"source": "manual", "updated_at": "...", "confidence": 0.95}}
    raw_body = await request.json() if hasattr(request, 'json') else {}
    field_metadata = raw_body.get("field_metadata")
    if field_metadata and isinstance(field_metadata, dict):
        existing_metadata = client.get("field_metadata") or {}
        merged_metadata = {**existing_metadata, **field_metadata}
        update_dict["field_metadata"] = merged_metadata

    # RGPD: Encriptar dados sensíveis antes de actualizar
    # Isto garante que NIFs, telefones e outros dados sensíveis
    # são guardados encriptados, mesmo em actualizações
    update_dict = encrypt_client_data(update_dict)

    await db.clients.update_one(
        {"id": client_id},
        {"$set": update_dict}
    )
    
    # === SYNC TO LINKED PROCESSES: Propagate name, email, phone, dados_pessoais ===
    # A edição só se propaga aos processos que a JANELA de quem edita deixa ver (Lote 6): um
    # visitante de um processo partilhado não reescreve os outros processos do cliente.
    process_ids_do_cliente = client.get("process_ids", [])
    process_ids = await ids_dos_processos_visiveis(
        user, process_ids_do_cliente, client_id=client_id, cliente=client,
    ) if process_ids_do_cliente else []
    if process_ids:
        process_sync = {}

        # 1. Sincronizar NOME do cliente → client_name em todos os processos
        if sanitized_nome:
            process_sync["client_name"] = sanitized_nome
            process_sync["personal_data.nome"] = sanitized_nome
            process_sync["personal_data.name"] = sanitized_nome

        # 2. Sincronizar EMAIL do cliente
        if sanitized_contacto:
            new_email = sanitized_contacto.get("email")
            new_phone = sanitized_contacto.get("telefone")

            if new_email:
                process_sync["client_email"] = new_email
                process_sync["personal_data.email"] = new_email
                from services.encryption import generate_email_hash
                process_sync["personal_data.email_hash"] = generate_email_hash(new_email)
            # O telefone só segue quando ESTA submissão o trouxe: o do cliente é
            # lido decifrado e os processos guardam o `client_phone` cifrado.
            if new_phone and "telefone" in submetidos_contacto:
                process_sync["client_phone"] = new_phone
                process_sync["personal_data.telefone"] = new_phone
                process_sync["personal_data.phone"] = new_phone

            # Contacto APAGADO: tem de sair também dos processos, senão o ecrã
            # do processo volta a mostrar o valor antigo (o email apagado
            # «reaparecia» depois do toast de sucesso).
            process_sync.update(sync_de_contactos_limpos(contactos_limpos))

        # 3. Sincronizar DADOS PESSOAIS (NIF, morada, etc.) para personal_data dos processos
        if sanitized_dados_pessoais:
            dados_sync_map = {
                "nif": "personal_data.nif",
                "documento_id": "personal_data.documento_id",
                "data_nascimento": "personal_data.data_nascimento",
                "birth_date": "personal_data.data_nascimento",
                "morada_fiscal": "personal_data.morada_fiscal",
                "estado_civil": "personal_data.estado_civil",
                "profissao": "personal_data.profissao",
                "nacionalidade": "personal_data.nacionalidade",
                "naturalidade": "personal_data.naturalidade",
                "sexo": "personal_data.sexo",
                "nome_pai": "personal_data.nome_pai",
                "nome_mae": "personal_data.nome_mae",
                "data_validade_cc": "personal_data.data_validade_cc",
            }
            # Adicionar NIF hash se NIF foi alterado
            if "nif" in sanitized_dados_pessoais and sanitized_dados_pessoais["nif"]:
                from services.encryption import generate_nif_hash
                nif_hash = generate_nif_hash(sanitized_dados_pessoais["nif"])
                if nif_hash:
                    process_sync["personal_data.nif_hash"] = nif_hash

            for src_key, dst_key in dados_sync_map.items():
                if src_key in sanitized_dados_pessoais and sanitized_dados_pessoais[src_key] is not None:
                    process_sync[dst_key] = sanitized_dados_pessoais[src_key]

        if process_sync:
            # D-15: a data de nascimento segue cifrada (e com o ano ao lado).
            await db.processes.update_many(
                {"id": {"$in": process_ids}},
                {"$set": proteger_caminhos(process_sync)}
            )
            logger.info(f"Sincronizados dados para {len(process_ids)} processos do cliente {client_id}: {list(process_sync.keys())}")

    # Campos pessoais APAGADOS: o que o `process_sync` acima não cobre — o índice
    # cego (`nif_hash`), a cópia da raiz (`client_nif`) e os nomes alternativos.
    # Procura também por `client_id`: o `process_ids` da ficha nem sempre está
    # mantido e um processo que escapasse guardava o NIF antigo para sempre.
    await limpar_espelhos_nos_processos(
        db, client_id, process_ids, pessoais_limpos, apenas_ids=process_ids,
    )

    logger.info(f"Cliente {client_id} actualizado por {user.get('email')}")
    
    return {"success": True, "message": "Cliente actualizado"}
