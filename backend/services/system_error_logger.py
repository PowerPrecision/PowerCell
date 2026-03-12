"""
====================================================================
SYSTEM ERROR LOGGER - CREDITOIMO
====================================================================
Sistema centralizado de logs de erros para administradores.

Funcionalidades:
- Registar erros de diferentes componentes (scraper, API, validação, etc.)
- Visualizar logs com filtros e paginação
- Marcar erros como lidos/resolvidos
- Estatísticas de erros por período
====================================================================
"""

import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class SystemErrorLogger:
    """Logger centralizado de erros do sistema."""
    
    def __init__(self):
        self._db = None
    
    async def _get_db(self):
        """Lazy load database connection."""
        if self._db is None:
            from database import db
            self._db = db
        return self._db
    
    async def log_error(
        self,
        error_type: str,
        message: str,
        component: str = "general",
        details: Dict[str, Any] = None,
        severity: str = "warning",
        user_id: str = None,
        request_path: str = None
    ) -> str:
        """
        Regista um erro no sistema.
        
        Args:
            error_type: Tipo de erro (scraper_error, api_error, validation_error, etc.)
            message: Mensagem descritiva
            component: Componente que gerou o erro (scraper, auth, processes, etc.)
            details: Detalhes adicionais
            severity: Nível (info, warning, error, critical)
            user_id: ID do utilizador afectado (se aplicável)
            request_path: Path do request (se aplicável)
            
        Returns:
            ID do erro registado
        """
        db = await self._get_db()
        
        error_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        error_log = {
            "id": error_id,
            "type": error_type,
            "message": message,
            "component": component,
            "details": details or {},
            "severity": severity,
            "user_id": user_id,
            "request_path": request_path,
            "timestamp": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "hour": now.hour,
            "read": False,
            "resolved": False,
            "resolved_at": None,
            "resolved_by": None,
            "notes": None
        }
        
        try:
            await db.system_error_logs.insert_one(error_log)
            logger.debug(f"System error logged: [{severity}] {component}/{error_type}: {message[:100]}")
            return error_id
        except Exception as e:
            logger.error(f"Failed to log system error: {e}")
            return ""
    
    async def get_errors(
        self,
        page: int = 1,
        limit: int = 50,
        severity: str = None,
        component: str = None,
        error_type: str = None,
        resolved: bool = None,
        read: bool = None,
        days: int = None
    ) -> Dict[str, Any]:
        """
        Obtém lista de erros com filtros e paginação.
        
        Returns:
            Dict com errors, total, page, pages
        """
        db = await self._get_db()
        
        query = {}
        
        if severity:
            query["severity"] = severity
        if component:
            query["component"] = component
        if error_type:
            query["type"] = error_type
        if resolved is not None:
            query["resolved"] = resolved
        if read is not None:
            query["read"] = read
        if days:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            query["timestamp"] = {"$gte": cutoff}
        
        # Contar total
        total = await db.system_error_logs.count_documents(query)
        
        # Buscar com paginação
        skip = (page - 1) * limit
        cursor = db.system_error_logs.find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1).skip(skip).limit(limit)
        
        errors = await cursor.to_list(limit)
        
        return {
            "errors": errors,
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit,
            "limit": limit
        }
    
    async def get_error_by_id(self, error_id: str) -> Optional[Dict[str, Any]]:
        """Obtém um erro específico pelo ID."""
        db = await self._get_db()
        return await db.system_error_logs.find_one({"id": error_id}, {"_id": 0})
    
    async def mark_as_read(self, error_ids: List[str]) -> int:
        """Marca erros como lidos."""
        db = await self._get_db()
        result = await db.system_error_logs.update_many(
            {"id": {"$in": error_ids}},
            {"$set": {"read": True}}
        )
        return result.modified_count
    
    async def mark_as_resolved(
        self,
        error_id: str,
        resolved_by: str,
        notes: str = None
    ) -> bool:
        """Marca um erro como resolvido."""
        db = await self._get_db()
        result = await db.system_error_logs.update_one(
            {"id": error_id},
            {
                "$set": {
                    "resolved": True,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                    "resolved_by": resolved_by,
                    "notes": notes
                }
            }
        )
        return result.modified_count > 0
    
    async def bulk_mark_as_resolved(
        self,
        error_ids: list,
        resolved_by: str
    ) -> int:
        """Marca múltiplos erros como resolvidos em massa."""
        if not error_ids:
            return 0
        
        db = await self._get_db()
        result = await db.system_error_logs.update_many(
            {"id": {"$in": error_ids}, "resolved": {"$ne": True}},
            {
                "$set": {
                    "resolved": True,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                    "resolved_by": resolved_by,
                    "notes": "Resolvido em massa"
                }
            }
        )
        return result.modified_count
    
    async def resolve_all_unresolved(self, resolved_by: str) -> int:
        """Marca TODOS os erros não resolvidos como resolvidos."""
        db = await self._get_db()
        result = await db.system_error_logs.update_many(
            {"resolved": {"$ne": True}},
            {
                "$set": {
                    "resolved": True,
                    "resolved_at": datetime.now(timezone.utc).isoformat(),
                    "resolved_by": resolved_by,
                    "notes": "Limpar todos os erros"
                }
            }
        )
        return result.modified_count
    
    async def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Obtém estatísticas de erros."""
        db = await self._get_db()
        
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        
        # Total por severidade
        pipeline_severity = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        severity_stats = await db.system_error_logs.aggregate(pipeline_severity).to_list(10)
        
        # Total por componente
        pipeline_component = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": "$component", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        component_stats = await db.system_error_logs.aggregate(pipeline_component).to_list(20)
        
        # Total por tipo de erro
        pipeline_type = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": "$type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]
        type_stats = await db.system_error_logs.aggregate(pipeline_type).to_list(20)
        
        # Por dia
        pipeline_daily = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {"_id": "$date", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        daily_stats = await db.system_error_logs.aggregate(pipeline_daily).to_list(days + 1)
        
        # Contagens gerais
        total = await db.system_error_logs.count_documents({"timestamp": {"$gte": cutoff}})
        unread = await db.system_error_logs.count_documents({"timestamp": {"$gte": cutoff}, "read": False})
        unresolved = await db.system_error_logs.count_documents({"timestamp": {"$gte": cutoff}, "resolved": False})
        critical = await db.system_error_logs.count_documents({"timestamp": {"$gte": cutoff}, "severity": "critical"})
        
        return {
            "period_days": days,
            "total": total,
            "unread": unread,
            "unresolved": unresolved,
            "critical": critical,
            "by_severity": {s["_id"]: s["count"] for s in severity_stats},
            "by_component": {c["_id"]: c["count"] for c in component_stats},
            "by_type": {t["_id"]: t["count"] for t in type_stats},
            "daily": [{"date": d["_id"], "count": d["count"]} for d in daily_stats]
        }
    
    async def cleanup_old_errors(self, days: int = 90) -> int:
        """Remove erros antigos (mais de X dias)."""
        db = await self._get_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = await db.system_error_logs.delete_many({"timestamp": {"$lt": cutoff}})
        return result.deleted_count


# Instância global
system_error_logger = SystemErrorLogger()


# Função helper para uso rápido
async def log_system_error(
    error_type: str,
    message: str,
    component: str = "general",
    details: Dict[str, Any] = None,
    severity: str = "warning"
) -> str:
    """Função de conveniência para registar erros."""
    return await system_error_logger.log_error(
        error_type=error_type,
        message=message,
        component=component,
        details=details,
        severity=severity
    )
