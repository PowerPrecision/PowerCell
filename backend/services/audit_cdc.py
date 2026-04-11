"""
====================================================================
CDC AUDIT LISTENER - Change Data Capture para Compliance
====================================================================
Listener que monitoriza MongoDB Change Streams nas coleções
principais (processes, document_metadata) e regista automaticamente
eventos de auditoria numa coleção dedicada `compliance_audit_logs`.

SEGURANÇA - MODO FANTASMA (Ghost Mode):
- Utilizadores com role "indexacao" operam em modo fantasma.
- O serviço de update injeta `_updated_by_role` e `_ghost_mode` nos
  updatedFields antes de escrever na BD.
- Este listener verifica PRIMEIRO esses campos efémeros e descarta
  silenciosamente o evento se `_ghost_mode` for True.
- Após processamento, os campos auxiliares são removidos via $unset
  para não poluir os dados de negócio.

ARQUITECTURA:
- Executa como asyncio background task (server.py startup)
- Tolerante a falhas (reconexão automática com backoff)
- Circuit breaker: desliga-se após falhas consecutivas excessivas
====================================================================
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from database import db

logger = logging.getLogger(__name__)

# ==== CONSTANTES DE CONFIGURAÇÃO ====

# Roles que operam em modo fantasma (sem registo de auditoria)
GHOST_ROLES = {"indexacao"}

# Coleções a monitorizar com Change Streams
WATCHED_COLLECTIONS = ["processes", "document_metadata"]

# Coleção de destino para registos de auditoria
AUDIT_COLLECTION = "compliance_audit_logs"

# Campos auxiliares injectados no update (efémeros)
EPHEMERAL_FIELDS = {"_updated_by_role", "_ghost_mode", "_updated_by"}

# Configuração de circuit breaker
MAX_CONSECUTIVE_FAILURES = 10
RESTART_DELAY_SECONDS = 60


class CDCListener:
    """
    Listener de Change Data Capture para auditoria de compliance.

    Monitoriza alterações nas coleções watcheadas e regista eventos
    na coleção de compliance, com bypass para roles em modo fantasma.
    """

    def __init__(self):
        self._running = False
        self._consecutive_failures = 0
        self._processed_count = 0
        self._ghost_discarded_count = 0
        self._started_at: Optional[datetime] = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def stats(self) -> dict:
        return {
            "running": self._running,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "processed_count": self._processed_count,
            "ghost_discarded_count": self._ghost_discarded_count,
            "consecutive_failures": self._consecutive_failures,
        }

    # ==== PONTO DE ENTRADA PRINCIPAL ====

    async def start(self):
        """
        Inicia o listener de CDC para todas as colecções monitorizadas.
        Executa como coroutine infinita com reconexão automática.
        """
        self._running = True
        self._started_at = datetime.now(timezone.utc)
        logger.info(
            f"🔍 CDC Audit Listener iniciado — "
            f"monitorizando: {WATCHED_COLLECTIONS} | "
            f"ghost roles: {GHOST_ROLES}"
        )

        # Criar índices na coleção de auditoria
        await self._ensure_indexes()

        while self._running:
            for collection_name in WATCHED_COLLECTIONS:
                if not self._running:
                    break
                await self._watch_collection(collection_name)

            # Se saiu do loop sem _running=False, esperar antes de reiniciar
            if self._running:
                logger.warning(
                    f"CDC listener reiniciando em {RESTART_DELAY_SECONDS}s "
                    f"(falhas consecutivas: {self._consecutive_failures})"
                )
                await asyncio.sleep(RESTART_DELAY_SECONDS)

    def stop(self):
        """Para o listener de forma graciosa."""
        self._running = False
        logger.info("🛑 CDC Audit Listener parado")

    # ==== WATCH INDIVIDUAL ====

    async def _watch_collection(self, collection_name: str):
        """
        Monitoriza uma coleção específica via Change Stream.

        Tenta estabelecer o change stream. Se a BD não suportar
        (ex: replica set não configurado), faz backoff e tenta novamente.
        """
        try:
            collection = getattr(db, collection_name)

            # Pipeline: apenas operações de update (ignorar inserts/delete
            # pois a auditoria de criação/eliminação é feita explicitamente)
            pipeline = [
                {"$match": {"operationType": "update"}},
            ]

            async with collection.watch(pipeline) as stream:
                logger.info(
                    f"📡 Change Stream activo na coleção '{collection_name}'"
                )
                self._consecutive_failures = 0  # Reset on success

                async for change_event in stream:
                    if not self._running:
                        break

                    try:
                        await self._process_change_event(
                            change_event, collection_name
                        )
                        self._processed_count += 1
                        self._consecutive_failures = 0
                    except Exception as event_err:
                        self._consecutive_failures += 1
                        logger.error(
                            f"Erro ao processar evento CDC "
                            f"[{collection_name}]: {event_err}"
                        )

                        # Circuit breaker
                        if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                            logger.critical(
                                f"⚠️ CDC Circuit Breaker activado: "
                                f"{MAX_CONSECUTIVE_FAILURES} falhas consecutivas. "
                                f"Parando listener."
                            )
                            self._running = False
                            return

        except Exception as stream_err:
            self._consecutive_failures += 1
            logger.warning(
                f"Change Stream falhou para '{collection_name}': {stream_err}. "
                f"Tentando novamente em {RESTART_DELAY_SECONDS}s..."
            )
            await asyncio.sleep(RESTART_DELAY_SECONDS)

    # ==== PROCESSAMENTO DO EVENTO ====

    async def _process_change_event(
        self, change_event: dict, collection_name: str
    ):
        """
        Processa um evento individual do Change Stream.

        FLUXO:
        1. ✅ GHOST MODE CHECK (primeira validação — bypass imediato)
        2. Extrair metadata do evento
        3. Construir documento de auditoria
        4. Inserir na coleção compliance_audit_logs
        5. Limpar campos efémeros via $unset
        """
        # ================================================================
        # 1. GHOST MODE — PRIMEIRA VALIDAÇÃO
        # Se o utilizador que fez o update está em modo fantasma,
        # descartar o evento IMEDIATAMENTE sem qualquer registo.
        # Esta é a primeira verificação para poupar recursos do servidor.
        # ================================================================
        update_desc = change_event.get("fullDocument") or {}
        # Para updates, os campos modificados vêm em updateDescription
        operation_type = change_event.get("operationType", "")

        if operation_type == "update":
            update_fields = (
                change_event
                .get("updateDescription", {})
                .get("updatedFields", {})
            )
        else:
            update_fields = {}

        ghost_mode = update_fields.get("_ghost_mode", False)
        updated_by_role = update_fields.get("_updated_by_role", "")

        if ghost_mode is True or updated_by_role in GHOST_ROLES:
            self._ghost_discarded_count += 1
            logger.debug(
                f"[CDC GHOST] Evento descartado — modo fantasma activo "
                f"(role={updated_by_role}, ghost={ghost_mode}) "
                f"coleção={collection_name}"
            )
            # Ainda assim, limpar os campos efémeros
            await self._cleanup_ephemeral_fields(
                change_event, collection_name, update_fields
            )
            return

        # ================================================================
        # 2. EXTRAIR METADATA
        # ================================================================
        document_id = change_event.get("documentKey", {}).get("_id")
        ns = change_event.get("ns", {})
        db_name = ns.get("db", "")
        collection = ns.get("coll", collection_name)

        # Tentar obter o ID de negócio (campo "id" do documento)
        business_id = update_fields.get("id") or update_fields.get("process_id")
        if not business_id:
            # Buscar o campo "id" no fullDocument se disponível
            full_doc = change_event.get("fullDocument")
            if full_doc:
                business_id = (
                    full_doc.get("id") or full_doc.get("process_id")
                )

        updated_by = update_fields.get("_updated_by", "unknown")
        updated_by_role_fallback = update_fields.get(
            "_updated_by_role", "unknown"
        )

        # Obter timestamp do evento (resumeToken)
        cluster_time = change_event.get("clusterTime")
        event_timestamp = (
            cluster_time.as_datetime() if cluster_time
            else datetime.now(timezone.utc)
        )

        # Filtrar campos de negócio (remover campos auxiliares)
        business_fields = {
            k: v for k, v in update_fields.items()
            if k not in EPHEMERAL_FIELDS
        }

        # Obter removedFields (se houver)
        removed_fields = (
            change_event
            .get("updateDescription", {})
            .get("removedFields", [])
        )

        # ================================================================
        # 3. CONSTRUIR DOCUMENTO DE AUDITORIA
        # ================================================================
        audit_doc = {
            "id": str(uuid.uuid4()),
            "event_type": "cdc_update",
            "collection": collection,
            "database": db_name,
            "document_id": str(document_id) if document_id else None,
            "business_id": business_id,
            "updated_by": updated_by,
            "updated_by_role": updated_by_role_fallback,
            "updated_fields": business_fields,
            "removed_fields": removed_fields,
            "cluster_time": event_timestamp.isoformat() if hasattr(event_timestamp, "isoformat") else str(event_timestamp),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "_cdc_resume_token": change_event.get("_id"),
        }

        # ================================================================
        # 4. INSERIR NA COLEÇÃO DE COMPLIANCE
        # ================================================================
        try:
            await db[AUDIT_COLLECTION].insert_one(audit_doc)
            logger.debug(
                f"[CDC] Auditoria registada: {collection}.{business_id} "
                f"por {updated_by} ({updated_by_role_fallback})"
            )
        except Exception as insert_err:
            logger.error(
                f"Erro ao inserir registo CDC: {insert_err}"
            )
            raise

        # ================================================================
        # 5. LIMPAR CAMPOS EFÉMEROS
        # Remover os campos auxiliares do documento original
        # para não poluir os dados de negócio.
        # ================================================================
        await self._cleanup_ephemeral_fields(
            change_event, collection_name, update_fields
        )

    # ==== LIMPEZA DE CAMPOS EFÉMEROS ====

    async def _cleanup_ephemeral_fields(
        self, change_event: dict, collection_name: str, update_fields: dict
    ):
        """
        Remove campos auxiliares (_updated_by_role, _ghost_mode, _updated_by)
        do documento usando $unset.

        Estes campos são injectados temporariamente para que o CDC
        possa determinar se o evento deve ser registado ou descartado.
        Após a decisão, são removidos para manter o documento limpo.
        """
        fields_to_unset = [
            field for field in EPHEMERAL_FIELDS
            if field in update_fields
        ]

        if not fields_to_unset:
            return

        try:
            document_key = change_event.get("documentKey", {})
            collection = getattr(db, collection_name)

            unset_op = {field: "" for field in fields_to_unset}
            await collection.update_one(
                document_key,
                {"$unset": unset_op}
            )
            logger.debug(
                f"[CDC] Campos efémeros removidos: {fields_to_unset} "
                f"de {collection_name}"
            )
        except Exception as cleanup_err:
            # Não falhar o processamento se a limpeza falhar
            logger.warning(
                f"Erro ao limpar campos efémeros: {cleanup_err}"
            )

    # ==== ÍNDICES ====

    async def _ensure_indexes(self):
        """
        Garante que os índices necessários existem na coleção
        compliance_audit_logs.
        """
        try:
            collection = db[AUDIT_COLLECTION]

            # Índice principal: busca por business_id + created_at
            await collection.create_index(
                [("business_id", 1), ("created_at", -1)],
                name="idx_cdc_business_id_created",
                background=True,
            )

            # Índice por utilizador
            await collection.create_index(
                [("updated_by", 1), ("created_at", -1)],
                name="idx_cdc_updated_by_created",
                background=True,
            )

            # Índice por coleção
            await collection.create_index(
                [("collection", 1), ("created_at", -1)],
                name="idx_cdc_collection_created",
                background=True,
            )

            # TTL: registos de auditoria expiram após 2 anos
            # (compliance — manter histórico longo mas com limite)
            await collection.create_index(
                [("created_at", 1)],
                name="idx_cdc_ttl",
                expireAfterSeconds=63072000,  # 2 anos em segundos
                background=True,
            )

            logger.info(
                f"✅ Índices CDC criados em '{AUDIT_COLLECTION}'"
            )
        except Exception as idx_err:
            logger.warning(
                f"Erro ao criar índices CDC (não fatal): {idx_err}"
            )


# ==== INSTÂNCIA GLOBAL ====

cdc_listener = CDCListener()


# ==== HELPER: INJECÇÃO DE CONTEXTO ====

def inject_cdc_context(update_data: dict, user: dict) -> dict:
    """
    Injecta campos de contexto de auditoria num dicionário de update.

    Esta função deve ser chamada ANTES de qualquer `db.collection.update_one()`
    para que o CDC listener possa determinar:
    - Quem fez a alteração (_updated_by)
    - Qual é a role (_updated_by_role)
    - Se está em modo fantasma (_ghost_mode)

    Os campos injectados são EFÉMEROS — serão removidos pelo listener
    após processar o evento.

    Args:
        update_data: Dicionário que será passado a `$set` no update_one
        user: Dicionário do utilizador autenticado

    Returns:
        O mesmo dicionário com os campos de contexto adicionados
    """
    if not user:
        # Sem utilizador (ex: sistema/automático) — não é ghost
        update_data["_updated_by"] = "system"
        update_data["_updated_by_role"] = "system"
        update_data["_ghost_mode"] = False
        return update_data

    user_role = user.get("role", "unknown")
    user_id = user.get("id", "unknown")

    update_data["_updated_by"] = user_id
    update_data["_updated_by_role"] = user_role
    update_data["_ghost_mode"] = user_role in GHOST_ROLES

    return update_data
