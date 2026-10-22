"""Ordenação e filtros da fila de trabalho do Index (Out 2026) — regras PURAS.

`GET /api/index/queue` passou a aceitar `sort_by`, `index_status`, `company_id` e `origin`. Tudo o que
vem do pedido é validado aqui contra listas FECHADAS: o que não existe é **422** e nunca uma lista vazia
(«não há» e «a pergunta não faz sentido» são respostas diferentes, e ninguém repara numa lista vazia).

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **Os filtros só ESTREITAM.** A condição do âmbito (dono + redes convidadas) e a dos processos activos são
   da fila e vêm primeiro; um `company_id` ou uma `origin` de outra rede devolve zero linhas, nunca as dela.
2. **A ordenação vem de uma lista fechada** (`CAMPOS_DE_ORDENACAO`): o nome do campo Mongo nunca sai do pedido.
   A mesma ordem no URL dá a mesma ordem no ecrã — por isso há SEMPRE um desempate por `id` (sem ele a
   paginação repetia ou saltava linhas entre processos com a mesma data).
3. **Cada aba tem a sua ordem por omissão** (a Fila de Espera: a entrada mais antiga primeiro; as Revisões: a
   indexação mais recente primeiro) — o que o ecrã mostrava antes desta entrega.
4. **`indexed` só ordena as Revisões** (os processos por indexar não têm data de indexação) e `index_status`
   só tem valores que a aba pode ter: `pending`/`in_review` na Fila, `indexed` nas Revisões.
5. **«Origem»**: `own` = do âmbito da rede (o que a rede é dona), `shared` = o que outra rede partilhou com ela.
   Reutiliza a condição de rede das listagens — uma segunda definição de «é de outra rede» divergiria.
6. Texto de ordenação com acentos e números: colação `pt` sem distinguir maiúsculas e com ordem NUMÉRICA
   («2» antes de «10»); sem ela «Álvaro» ficava depois de «Zé» e «PROC-10» antes de «PROC-9».
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from services.tenant_network import TenantScope, build_network_scope_condition

#: `chave do pedido → (campo Mongo, é texto?)`.
CAMPOS_DE_ORDENACAO: dict[str, tuple[str, bool]] = {
    "created": ("created_at", False),
    "indexed": ("indexed_at", False),
    "number": ("process_number", True),
    "client": ("client_name", True),
    "company": ("company_name", True),
    "status": ("index_status", True),
    "alerts": ("index_alerts_open", False),
}
SENTIDOS = {"asc": 1, "desc": -1}
ORDEM_POR_OMISSAO = {"pending": "created_asc", "reviews": "indexed_desc"}
ESTADOS_POR_ABA = {"pending": ("pending", "in_review"), "reviews": ("indexed",)}
ORIGENS = ("own", "shared")
TAMANHO_MAXIMO_DO_ID = 64
COLACAO = {"locale": "pt", "strength": 2, "numericOrdering": True}

#: Condição que nunca casa (a mesma convenção de `index_status.condicao_da_fila`).
_NADA = {"id": {"$in": []}}


def _recusar(detalhe: str) -> HTTPException:
    return HTTPException(status_code=422, detail=detalhe)


def validar_ordenacao(aba: str, sort_by: Optional[str]) -> tuple[str, int, bool, str]:
    """`(campo Mongo, sentido, é texto?, valor normalizado)`; 422 se não for uma ordem que a aba aceite."""
    valor = (sort_by or "").strip() or ORDEM_POR_OMISSAO.get(aba, "created_asc")
    chave, _, sentido = valor.rpartition("_")
    if chave not in CAMPOS_DE_ORDENACAO or sentido not in SENTIDOS:
        raise _recusar(
            "Ordenação inválida. Use «<campo>_<asc|desc>» com campo em: " + ", ".join(sorted(CAMPOS_DE_ORDENACAO)) + "."
        )
    if chave == "indexed" and aba != "reviews":
        raise _recusar("Só as Revisões Pendentes se ordenam pela data de indexação.")
    campo, texto = CAMPOS_DE_ORDENACAO[chave]
    return campo, SENTIDOS[sentido], texto, f"{chave}_{sentido}"


def ordem_mongo(campo: str, sentido: int) -> list[tuple[str, int]]:
    """A ordem pedida + o desempate por `id` (sempre ascendente): paginação estável."""
    return [(campo, sentido), ("id", 1)]


def validar_filtros(
    aba: str, *, index_status: Optional[str], company_id: Optional[str], origin: Optional[str]
) -> dict[str, Optional[str]]:
    """Os filtros normalizados (`None` = sem filtro); 422 para o que a aba não pode ter."""
    estado = (index_status or "").strip() or None
    if estado is not None and estado not in ESTADOS_POR_ABA.get(aba, ()):
        raise _recusar(
            "Estado inválido para esta lista. Valores possíveis: " + ", ".join(ESTADOS_POR_ABA.get(aba, ())) + "."
        )
    empresa = (company_id or "").strip() or None
    if empresa is not None and len(empresa) > TAMANHO_MAXIMO_DO_ID:
        raise _recusar("Empresa inválida.")
    origem = (origin or "").strip() or None
    if origem is not None and origem not in ORIGENS:
        raise _recusar("Origem inválida. Valores possíveis: " + ", ".join(ORIGENS) + ".")
    return {"index_status": estado, "company_id": empresa, "origin": origem}


def condicao_dos_filtros(aba: str, filtros: dict[str, Optional[str]], scope: TenantScope) -> Optional[dict]:
    """A condição Mongo dos filtros ligados, ou `None` se não há nenhum. Pura."""
    ramos: list[dict[str, Any]] = []
    estado = filtros.get("index_status")
    if estado:
        if aba == "pending":
            por_estado: list[dict] = [{"index_status": estado}]
            if estado == "pending":
                # o legado sem `index_status` lê-se como por indexar (é o que `condicao_da_fila` faz)
                por_estado.append({"index_status": {"$exists": False}})
            ramos.append({"$or": por_estado})
        # nas Revisões todos estão indexados: `indexed` é verdade para a lista inteira
    if filtros.get("company_id"):
        ramos.append({"company_id": filtros["company_id"]})
    origem = filtros.get("origin")
    if origem:
        propria = build_network_scope_condition(scope)
        if scope.sem_fronteira:
            # o Master na vista «Sistema» não tem fronteira: nada é «de outra rede»
            ramos.append(dict(propria) if origem == "own" else dict(_NADA))
        else:
            ramos.append(propria if origem == "own" else {"$nor": [propria]})
    if not ramos:
        return None
    return ramos[0] if len(ramos) == 1 else {"$and": ramos}


__all__ = [
    "CAMPOS_DE_ORDENACAO", "COLACAO", "ORDEM_POR_OMISSAO", "ORIGENS",
    "condicao_dos_filtros", "ordem_mongo", "validar_filtros", "validar_ordenacao",
]
