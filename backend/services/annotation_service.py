"""
====================================================================
SERVIÇO DE ANOTAÇÕES DE DOCUMENTOS - CREDITOIMO
====================================================================
Serviço MongoDB para gestão de anotações contextuais em documentos.

Funcionalidades:
- Criar, listar, atualizar e eliminar anotações
- Filtrar por documento ou processo
- Resolver/reabrir anotações
- Estatísticas de anotações por processo
====================================================================
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from database import db
from models.annotation import ANNOTATION_TYPES, VALID_ANNOTATION_TYPES

logger = logging.getLogger(__name__)

COLLECTION_NAME = "document_annotations"


async def create_annotation(data: dict, author_id: str, author_name: str) -> dict:
    """
    Cria uma nova anotação de documento.

    Args:
        data: Dados da anotação (process_id, document_path, document_name, page, x, y, comment, annotation_type, color)
        author_id: ID do utilizador que cria a anotação
        author_name: Nome do utilizador que cria a anotação

    Returns:
        Dicionário com a anotação criada
    """
    try:
        annotation_type = data.get("annotation_type", "note")

        # Validação do tipo de anotação
        if annotation_type not in VALID_ANNOTATION_TYPES:
            raise ValueError(f"Tipo de anotação inválido: {annotation_type}. Tipos válidos: {', '.join(VALID_ANNOTATION_TYPES)}")

        # Determinar cor: usar a cor personalizada ou a cor padrão do tipo
        color = data.get("color")
        if not color:
            color = ANNOTATION_TYPES.get(annotation_type, {}).get("color", "#3B82F6")

        now = datetime.now(timezone.utc).isoformat()

        annotation_doc = {
            "id": str(uuid.uuid4()),
            "process_id": data["process_id"],
            "document_path": data["document_path"],
            "document_name": data["document_name"],
            "page": data["page"],
            "x": data["x"],
            "y": data["y"],
            "comment": data["comment"],
            "annotation_type": annotation_type,
            "color": color,
            "author_id": author_id,
            "author_name": author_name,
            "created_at": now,
            "updated_at": None,
            "resolved": False,
            "resolved_by": None,
            "resolved_at": None,
        }

        await db[COLLECTION_NAME].insert_one(annotation_doc)

        logger.info(f"Anotação criada: {annotation_doc['id']} - documento={data['document_name']} página={data['page']} tipo={annotation_type}")

        return annotation_doc

    except ValueError as e:
        logger.warning(f"Erro de validação ao criar anotação: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro ao criar anotação: {e}", exc_info=True)
        raise


async def get_document_annotations(document_path: str, process_id: str) -> List[dict]:
    """
    Retorna todas as anotações para um documento específico.

    Args:
        document_path: Caminho do documento no storage
        process_id: ID do processo

    Returns:
        Lista de anotações, ordenadas por página e depois por created_at
    """
    try:
        annotations = await db[COLLECTION_NAME].find(
            {
                "document_path": document_path,
                "process_id": process_id,
            },
            {"_id": 0}
        ).sort([
            ("page", 1),
            ("created_at", 1),
        ]).to_list(500)

        return annotations

    except Exception as e:
        logger.error(f"Erro ao obter anotações do documento {document_path}: {e}", exc_info=True)
        raise


async def get_process_annotations(process_id: str, include_resolved: bool = True) -> List[dict]:
    """
    Retorna todas as anotações para um processo.

    Args:
        process_id: ID do processo
        include_resolved: Se True, inclui anotações resolvidas; se False, apenas pendentes

    Returns:
        Lista de anotações, ordenadas por created_at descendente
    """
    try:
        query = {"process_id": process_id}

        if not include_resolved:
            query["resolved"] = False

        annotations = await db[COLLECTION_NAME].find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).to_list(500)

        return annotations

    except Exception as e:
        logger.error(f"Erro ao obter anotações do processo {process_id}: {e}", exc_info=True)
        raise


async def update_annotation(annotation_id: str, data: dict, user_id: str) -> Optional[dict]:
    """
    Atualiza campos de uma anotação existente.

    Args:
        annotation_id: ID da anotação
        data: Campos a atualizar (comment, annotation_type, color, resolved)
        user_id: ID do utilizador que faz a atualização

    Returns:
        Anotação atualizada ou None se não encontrada
    """
    try:
        # Verificar se a anotação existe
        existing = await db[COLLECTION_NAME].find_one({"id": annotation_id}, {"_id": 0})
        if not existing:
            return None

        # Construir o update apenas com campos fornecidos
        update_fields: Dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        if "comment" in data and data["comment"] is not None:
            update_fields["comment"] = data["comment"]

        if "annotation_type" in data and data["annotation_type"] is not None:
            annotation_type = data["annotation_type"]
            if annotation_type not in VALID_ANNOTATION_TYPES:
                raise ValueError(f"Tipo de anotação inválido: {annotation_type}")
            update_fields["annotation_type"] = annotation_type
            # Actualizar a cor para o padrão do novo tipo se não houver cor personalizada
            update_fields["color"] = ANNOTATION_TYPES.get(annotation_type, {}).get("color", "#3B82F6")

        if "color" in data and data["color"] is not None:
            update_fields["color"] = data["color"]

        if "resolved" in data and data["resolved"] is not None:
            resolved = data["resolved"]
            update_fields["resolved"] = resolved
            if resolved:
                update_fields["resolved_by"] = user_id
                update_fields["resolved_at"] = datetime.now(timezone.utc).isoformat()
            else:
                update_fields["resolved_by"] = None
                update_fields["resolved_at"] = None

        await db[COLLECTION_NAME].update_one(
            {"id": annotation_id},
            {"$set": update_fields}
        )

        # Retornar a anotação actualizada
        updated = await db[COLLECTION_NAME].find_one({"id": annotation_id}, {"_id": 0})

        logger.info(f"Anotação atualizada: {annotation_id} por user={user_id}")

        return updated

    except ValueError as e:
        logger.warning(f"Erro de validação ao atualizar anotação {annotation_id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Erro ao atualizar anotação {annotation_id}: {e}", exc_info=True)
        raise


async def delete_annotation(annotation_id: str, user_id: str) -> bool:
    """
    Elimina uma anotação. Apenas o autor ou um admin pode eliminar.

    Args:
        annotation_id: ID da anotação
        user_id: ID do utilizador que tenta eliminar

    Returns:
        True se eliminada com sucesso, False caso contrário
    """
    try:
        # Verificar se a anotação existe
        annotation = await db[COLLECTION_NAME].find_one({"id": annotation_id})
        if not annotation:
            return False

        # Verificar permissões: autor ou admin
        author_id = annotation.get("author_id")
        if author_id != user_id:
            # Verificar se é admin
            user = await db.users.find_one({"id": user_id}, {"_id": 0, "role": 1})
            if not user or user.get("role") != "admin":
                logger.warning(f"Utilizador {user_id} tentou eliminar anotação {annotation_id} sem permissão")
                return False

        result = await db[COLLECTION_NAME].delete_one({"id": annotation_id})

        if result.deleted_count > 0:
            logger.info(f"Anotação eliminada: {annotation_id} por user={user_id}")
            return True

        return False

    except Exception as e:
        logger.error(f"Erro ao eliminar anotação {annotation_id}: {e}", exc_info=True)
        raise


async def resolve_annotation(
    annotation_id: str,
    user_id: str,
    user_name: str,
    resolved: bool,
) -> Optional[dict]:
    """
    Alterna o estado de resolução de uma anotação.

    Args:
        annotation_id: ID da anotação
        user_id: ID do utilizador que resolve/reabre
        user_name: Nome do utilizador
        resolved: True para resolver, False para reabrir

    Returns:
        Anotação atualizada ou None se não encontrada
    """
    try:
        existing = await db[COLLECTION_NAME].find_one({"id": annotation_id}, {"_id": 0})
        if not existing:
            return None

        now = datetime.now(timezone.utc).isoformat()

        if resolved:
            update_fields = {
                "resolved": True,
                "resolved_by": user_id,
                "resolved_at": now,
                "updated_at": now,
            }
        else:
            update_fields = {
                "resolved": False,
                "resolved_by": None,
                "resolved_at": None,
                "updated_at": now,
            }

        await db[COLLECTION_NAME].update_one(
            {"id": annotation_id},
            {"$set": update_fields}
        )

        updated = await db[COLLECTION_NAME].find_one({"id": annotation_id}, {"_id": 0})

        action = "resolvida" if resolved else "reaberta"
        logger.info(f"Anotação {action}: {annotation_id} por {user_name} ({user_id})")

        return updated

    except Exception as e:
        logger.error(f"Erro ao resolver anotação {annotation_id}: {e}", exc_info=True)
        raise


async def get_annotation_stats(process_id: str) -> dict:
    """
    Retorna estatísticas de anotações para um processo.

    Args:
        process_id: ID do processo

    Returns:
        Dicionário com contagens por tipo, resolvidas vs pendentes, total
    """
    try:
        # Contagem total e por estado de resolução
        total_pipeline = [
            {"$match": {"process_id": process_id}},
            {"$group": {
                "_id": None,
                "total": {"$sum": 1},
                "resolved": {"$sum": {"$cond": [{"$eq": ["$resolved", True]}, 1, 0]}},
                "pending": {"$sum": {"$cond": [{"$eq": ["$resolved", False]}, 1, 0]}},
            }}
        ]

        total_result = await db[COLLECTION_NAME].aggregate(total_pipeline).to_list(1)
        total_data = total_result[0] if total_result else {"total": 0, "resolved": 0, "pending": 0}

        # Contagem por tipo
        by_type_pipeline = [
            {"$match": {"process_id": process_id}},
            {"$group": {
                "_id": "$annotation_type",
                "count": {"$sum": 1},
                "resolved": {"$sum": {"$cond": [{"$eq": ["$resolved", True]}, 1, 0]}},
                "pending": {"$sum": {"$cond": [{"$eq": ["$resolved", False]}, 1, 0]}},
            }},
            {"$sort": {"count": -1}},
        ]

        by_type_results = await db[COLLECTION_NAME].aggregate(by_type_pipeline).to_list(20)

        by_type = {}
        for item in by_type_results:
            type_name = item["_id"]
            by_type[type_name] = {
                "label": ANNOTATION_TYPES.get(type_name, {}).get("label", type_name),
                "color": ANNOTATION_TYPES.get(type_name, {}).get("color", "#6B7280"),
                "total": item["count"],
                "resolved": item["resolved"],
                "pending": item["pending"],
            }

        return {
            "process_id": process_id,
            "total": total_data["total"],
            "resolved": total_data["resolved"],
            "pending": total_data["pending"],
            "by_type": by_type,
        }

    except Exception as e:
        logger.error(f"Erro ao obter estatísticas de anotações do processo {process_id}: {e}", exc_info=True)
        raise
