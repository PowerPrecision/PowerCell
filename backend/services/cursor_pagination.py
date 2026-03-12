"""
====================================================================
SERVIÇO DE PAGINAÇÃO CURSOR-BASED - CREDITOIMO
====================================================================
Implementa paginação eficiente usando cursores em vez de offset.
Melhor performance para grandes datasets.
====================================================================
"""
import base64
import json
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from bson import ObjectId


def encode_cursor(data: Dict[str, Any]) -> str:
    """
    Codifica dados em um cursor base64.
    """
    # Converter valores não serializáveis
    serializable = {}
    for key, value in data.items():
        if isinstance(value, datetime):
            serializable[key] = {"__datetime__": value.isoformat()}
        elif isinstance(value, ObjectId):
            serializable[key] = {"__objectid__": str(value)}
        else:
            serializable[key] = value
    
    json_str = json.dumps(serializable, sort_keys=True)
    return base64.urlsafe_b64encode(json_str.encode()).decode()


def decode_cursor(cursor: str) -> Dict[str, Any]:
    """
    Decodifica um cursor base64 para dados.
    """
    try:
        json_str = base64.urlsafe_b64decode(cursor.encode()).decode()
        data = json.loads(json_str)
        
        # Restaurar valores
        restored = {}
        for key, value in data.items():
            if isinstance(value, dict):
                if "__datetime__" in value:
                    restored[key] = datetime.fromisoformat(value["__datetime__"])
                elif "__objectid__" in value:
                    restored[key] = ObjectId(value["__objectid__"])
                else:
                    restored[key] = value
            else:
                restored[key] = value
        
        return restored
    except Exception:
        return {}


def build_cursor_query(
    base_query: Dict[str, Any],
    cursor: Optional[str],
    sort_field: str = "created_at",
    sort_order: int = -1  # -1 = DESC, 1 = ASC
) -> Dict[str, Any]:
    """
    Constrói query com condição de cursor para paginação.
    
    Args:
        base_query: Query base (filtros)
        cursor: Cursor da página anterior
        sort_field: Campo de ordenação
        sort_order: Direção da ordenação (-1 = DESC, 1 = ASC)
    
    Returns:
        Query com condição de cursor
    """
    if not cursor:
        return base_query
    
    cursor_data = decode_cursor(cursor)
    if not cursor_data:
        return base_query
    
    # Obter valor do cursor para o campo de ordenação
    cursor_value = cursor_data.get(sort_field)
    cursor_id = cursor_data.get("id")
    
    if cursor_value is None:
        return base_query
    
    # Construir condição de cursor
    # Para DESC: buscar itens ANTES do cursor
    # Para ASC: buscar itens DEPOIS do cursor
    if sort_order == -1:
        cursor_condition = {
            "$or": [
                {sort_field: {"$lt": cursor_value}},
                {
                    "$and": [
                        {sort_field: cursor_value},
                        {"id": {"$lt": cursor_id}} if cursor_id else {}
                    ]
                }
            ]
        }
    else:
        cursor_condition = {
            "$or": [
                {sort_field: {"$gt": cursor_value}},
                {
                    "$and": [
                        {sort_field: cursor_value},
                        {"id": {"$gt": cursor_id}} if cursor_id else {}
                    ]
                }
            ]
        }
    
    # Combinar com query base
    if "$and" in base_query:
        base_query["$and"].append(cursor_condition)
    else:
        return {"$and": [base_query, cursor_condition]}
    
    return base_query


def create_cursor_from_item(
    item: Dict[str, Any],
    sort_field: str = "created_at"
) -> str:
    """
    Cria cursor a partir de um item.
    """
    cursor_data = {
        sort_field: item.get(sort_field),
        "id": item.get("id")
    }
    return encode_cursor(cursor_data)


async def paginate_cursor(
    collection,
    query: Dict[str, Any],
    limit: int = 20,
    cursor: Optional[str] = None,
    sort_field: str = "created_at",
    sort_order: int = -1,
    projection: Optional[Dict[str, Any]] = None
) -> Tuple[List[Dict], Optional[str], bool]:
    """
    Paginação cursor-based genérica.
    
    Args:
        collection: Colecção MongoDB
        query: Query de filtro
        limit: Número de itens por página
        cursor: Cursor da página anterior
        sort_field: Campo de ordenação
        sort_order: Direção da ordenação
        projection: Campos a retornar
    
    Returns:
        (items, next_cursor, has_more)
    """
    # Construir query com cursor
    paginated_query = build_cursor_query(query, cursor, sort_field, sort_order)
    
    # Buscar limit + 1 para saber se há mais páginas
    if projection is None:
        projection = {"_id": 0}
    elif "_id" not in projection:
        projection["_id"] = 0
    
    items = await collection.find(
        paginated_query,
        projection
    ).sort([(sort_field, sort_order), ("id", sort_order)]).limit(limit + 1).to_list(limit + 1)
    
    # Verificar se há mais páginas
    has_more = len(items) > limit
    if has_more:
        items = items[:limit]
    
    # Criar cursor para próxima página
    next_cursor = None
    if has_more and items:
        next_cursor = create_cursor_from_item(items[-1], sort_field)
    
    return items, next_cursor, has_more


class CursorPaginator:
    """
    Classe helper para paginação cursor-based.
    """
    
    def __init__(
        self,
        collection,
        default_limit: int = 20,
        max_limit: int = 100,
        default_sort_field: str = "created_at",
        default_sort_order: int = -1
    ):
        self.collection = collection
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.default_sort_field = default_sort_field
        self.default_sort_order = default_sort_order
    
    async def paginate(
        self,
        query: Dict[str, Any],
        limit: Optional[int] = None,
        cursor: Optional[str] = None,
        sort_field: Optional[str] = None,
        sort_order: Optional[int] = None,
        projection: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executa paginação e retorna resposta formatada.
        """
        # Aplicar defaults
        limit = min(limit or self.default_limit, self.max_limit)
        sort_field = sort_field or self.default_sort_field
        sort_order = sort_order or self.default_sort_order
        
        items, next_cursor, has_more = await paginate_cursor(
            self.collection,
            query,
            limit,
            cursor,
            sort_field,
            sort_order,
            projection
        )
        
        return {
            "items": items,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "limit": limit
        }
