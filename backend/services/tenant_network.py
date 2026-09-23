"""
====================================================================
REDES (GRUPOS EMPRESARIAIS) — isolamento multi-tenant
====================================================================
Ponto ÚNICO de resolução do âmbito de dados de um utilizador.

O MODELO
  A rede vive na EMPRESA (`companies.network_id`). Empresas com a mesma
  rede partilham visibilidade sem permissões extra (Power + Precision);
  empresas em redes diferentes estão em isolamento absoluto (Domus).
  Uma empresa SEM rede configurada é uma ilha de uma só
  (`rede_implicita`) — omissão segura: uma empresa criada hoje nasce
  isolada. Se caísse na rede de omissão, veria a pilha inteira do grupo
  incumbente, que é exactamente a fuga que isto fecha.

  O âmbito é do UTILIZADOR, não da empresa activa: a empresa activa é
  uma preferência de VISTA (o `company_id` das listagens), a rede é a
  fronteira de SEGURANÇA. Quem trabalha em duas redes vê as duas.

A REDE DE OMISSÃO (`TENANT_DEFAULT_NETWORK_ID`)
  Antes desta mudança nenhum documento era carimbado — `process_create`
  não escrevia sequer `company_id`. Essa pilha existente não tem dono
  legível, e escondê-la de toda a gente no dia do deploy seria partir os
  dados existentes. A variável de ambiente diz a que rede ela pertence:
  em produção, o grupo incumbente. Quem está nessa rede continua a
  ver tudo o que via; quem está noutra (a ilha nova) não vê nada dela.

  Com a variável POR DEFINIR (dev, CI), os documentos por carimbar são
  visíveis a todos — o comportamento de hoje, para não esvaziar as
  listagens de desenvolvimento nem a bateria — e fica um aviso no log.
  Nunca em silêncio.

  Um documento só conta como "por carimbar" quando NÃO TEM MARCA
  NENHUMA: nem `network_id`, nem `company_id`, nem `company`, nem
  `company_name`. Olhar só para o `network_id` deixaria a fuga entrar
  pela cláusula que existe para a evitar — um processo da Domus criado
  entre o carimbo na escrita e a migração tem empresa mas ainda não tem
  rede, e passaria a ser visível ao grupo incumbente.

NUNCA reconstruir esta cadeia em linha numa listagem. Foi tê-la
duplicada que produziu o incidente da conta de envio (2026-09-21); há
uma guarda sobre o código-fonte em `test_tenant_network_isolation.py`.
====================================================================
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from database import db

logger = logging.getLogger(__name__)

# Variável de ambiente (NUNCA hardcoded: dev e produção têm redes distintas).
TENANT_DEFAULT_NETWORK_ENV = "TENANT_DEFAULT_NETWORK_ID"

# Campo canónico do carimbo nos documentos de negócio.
CAMPO_REDE = "network_id"

# Onde a empresa pode estar escrita num documento (o histórico usa os três).
CAMPOS_EMPRESA: tuple[str, ...] = ("company_id", "company", "company_name")

# Valores que significam "sem empresa" — `"default"` é o sentinel que o
# frontend envia quando o utilizador não tem associações (ver `auth.py`).
VALORES_SEM_EMPRESA: tuple[Any, ...] = (None, "", "default")

# Condição que não casa com documento nenhum. É o que um âmbito fechado
# sem rede nenhuma devolve: `None` significaria "sem filtro" e reabria a
# fuga inteira em silêncio.
CONDICAO_IMPOSSIVEL: dict = {CAMPO_REDE: {"$in": []}}

_aviso_de_omissao_dado = False


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def rede_de_omissao() -> Optional[str]:
    """Rede a que pertencem os documentos sem carimbo, ou ``None``."""
    return _texto(os.getenv(TENANT_DEFAULT_NETWORK_ENV)) or None


def rede_implicita(company_id: Any) -> str:
    """Rede de uma empresa sem grupo configurado: uma ilha de uma só."""
    return f"rede:{_texto(company_id)}"


def resolve_network_id(empresa: Optional[dict], *, company_id: Any = None) -> Optional[str]:
    """`network_id` de uma empresa, ou a sua ilha implícita."""
    if empresa:
        explicita = _texto(empresa.get(CAMPO_REDE))
        if explicita:
            return explicita
        identificador = _texto(empresa.get("id")) or _texto(company_id)
    else:
        identificador = _texto(company_id)

    return rede_implicita(identificador) if identificador else None


@dataclass(frozen=True)
class TenantScope:
    """O que um utilizador pode ver, em termos de rede e de empresa."""

    network_ids: tuple[str, ...] = ()
    company_ids: tuple[str, ...] = ()
    company_names: tuple[str, ...] = ()
    # Os documentos por carimbar entram no âmbito deste utilizador?
    inclui_rede_de_omissao: bool = False


def _sem_marca_de_tenant() -> dict:
    """Documento sem NENHUMA marca de empresa ou rede (a pilha antiga).

    `{"campo": {"$in": [None, ...]}}` no Mongo casa também com o campo
    AUSENTE — é o mesmo predicado para "nulo", "vazio" e "não existe".
    """
    vazios = list(VALORES_SEM_EMPRESA)
    return {
        "$and": [
            {CAMPO_REDE: {"$in": vazios}},
            *({campo: {"$in": vazios}} for campo in CAMPOS_EMPRESA),
        ]
    }


def build_network_scope_condition(scope: TenantScope) -> dict:
    """Condição Mongo que restringe uma listagem ao âmbito do utilizador.

    Pura e testável: não toca na base de dados nem no ambiente.
    """
    ramos: list[dict] = []

    if scope.network_ids:
        ramos.append({CAMPO_REDE: {"$in": list(scope.network_ids)}})

    # O histórico grava a empresa ora por id ora por nome; aceitamos as
    # duas formas em qualquer um dos três campos.
    empresas = list(dict.fromkeys([*scope.company_ids, *scope.company_names]))
    if empresas:
        ramos.extend({campo: {"$in": empresas}} for campo in CAMPOS_EMPRESA)

    if scope.inclui_rede_de_omissao:
        ramos.append(_sem_marca_de_tenant())

    if not ramos:
        return CONDICAO_IMPOSSIVEL

    return {"$or": ramos}


async def _redes_das_empresas(company_ids: Sequence[str]) -> dict[str, Optional[str]]:
    """Mapa company_id → network_id (ilha implícita quando não há grupo)."""
    identificadores = [c for c in dict.fromkeys(_texto(c) for c in company_ids) if c]
    if not identificadores:
        return {}

    encontradas: dict[str, dict] = {}
    try:
        cursor = db.companies.find(
            {"$or": [
                {"id": {"$in": identificadores}},
                {"name": {"$in": identificadores}},
            ]},
            {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
        )
        for empresa in await cursor.to_list(200):
            for chave in (_texto(empresa.get("id")), _texto(empresa.get("name"))):
                if chave:
                    encontradas[chave] = empresa
    except Exception as exc:
        # Degradação graciosa: sem a colecção de empresas cada empresa
        # vale por si (ilha). Nunca ampliar o âmbito por causa de um erro.
        logger.warning(
            "[tenant_network] Falha a ler `companies` (%s); cada empresa "
            "passa a valer como ilha própria.", exc,
        )

    return {
        cid: resolve_network_id(encontradas.get(cid), company_id=cid)
        for cid in identificadores
    }


async def resolve_tenant_scope(user: dict) -> TenantScope:
    """Âmbito de dados de um utilizador: todas as redes a que pertence."""
    from services.auth import get_user_companies

    user_id = _texto((user or {}).get("id") or (user or {}).get("user_id"))

    associacoes: list[dict] = []
    if user_id:
        try:
            associacoes = await get_user_companies(user_id) or []
        except Exception as exc:
            logger.warning(
                "[tenant_network] Falha a ler as empresas de %s (%s).", user_id, exc,
            )

    company_ids: list[str] = []
    company_names: list[str] = []
    for assoc in associacoes:
        cid = _texto(assoc.get("company_id"))
        nome = _texto(assoc.get("company_name"))
        if cid and cid not in VALORES_SEM_EMPRESA:
            company_ids.append(cid)
        if nome:
            company_names.append(nome)

    # Recurso para contas legadas sem UCR: `user.company` é o NOME.
    legado = _texto((user or {}).get("company"))
    if not company_ids and legado and legado not in VALORES_SEM_EMPRESA:
        company_names.append(legado)
        company_ids.append(legado)

    mapa = await _redes_das_empresas([*company_ids, *company_names])
    network_ids = [rede for rede in mapa.values() if rede]

    omissao = rede_de_omissao()
    if omissao:
        # Utilizador órfão (sem empresa nenhuma) — tipicamente contas de
        # administração antigas. Cegá-las no dia do deploy não ajuda
        # ninguém; a Atribuição Rápida passa a evitar que nasçam novas.
        if not network_ids:
            logger.info(
                "[tenant_network] Utilizador %s sem empresa associada; "
                "atribuído à rede de omissão.", user_id or "?",
            )
            network_ids.append(omissao)
        inclui_omissao = omissao in network_ids
    else:
        _avisar_omissao_por_definir()
        inclui_omissao = True

    return TenantScope(
        network_ids=tuple(dict.fromkeys(network_ids)),
        company_ids=tuple(dict.fromkeys(company_ids)),
        company_names=tuple(dict.fromkeys(company_names)),
        inclui_rede_de_omissao=inclui_omissao,
    )


def _avisar_omissao_por_definir() -> None:
    """Avisa UMA vez que os documentos por carimbar estão visíveis a todos."""
    global _aviso_de_omissao_dado
    if _aviso_de_omissao_dado:
        return
    _aviso_de_omissao_dado = True
    logger.warning(
        "[tenant_network] %s por definir: os documentos sem carimbo de "
        "empresa/rede ficam visíveis a TODAS as redes (comportamento "
        "anterior ao isolamento). Em produção, defina-a com a rede do "
        "grupo incumbente.", TENANT_DEFAULT_NETWORK_ENV,
    )


async def build_tenant_condition(user: dict) -> dict:
    """Atalho: âmbito do utilizador já convertido em condição Mongo."""
    return build_network_scope_condition(await resolve_tenant_scope(user))


async def resolve_tenant_stamp(
    user: dict,
    *,
    active_company_id: Any = None,
) -> Optional[dict]:
    """Carimbo a gravar num documento novo, ou ``None``.

    Devolve ``None`` quando não há contexto de empresa: carimbar uma rede
    errada é pior do que não carimbar, porque o documento passaria a ser
    visível à rede errada para sempre. Sem carimbo, ele cai na pilha por
    carimbar, que a migração resolve depois.
    """
    cid = _texto(active_company_id) or _texto((user or {}).get("active_company_id"))
    if cid in VALORES_SEM_EMPRESA:
        cid = ""

    nome = ""
    if not cid:
        nome = _texto((user or {}).get("company"))
        if nome in VALORES_SEM_EMPRESA:
            nome = ""
        if not nome:
            return None

    chave = cid or nome
    empresa = None
    try:
        empresa = await db.companies.find_one(
            {"$or": [{"id": chave}, {"name": chave}]},
            {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
        )
    except Exception as exc:
        logger.warning("[tenant_network] Falha a ler a empresa %s (%s).", chave, exc)

    rede = resolve_network_id(empresa, company_id=chave)
    if not rede:
        return None

    carimbo = {
        "company_id": _texto(empresa.get("id")) if empresa else cid,
        "company_name": _texto(empresa.get("name")) if empresa else nome,
        CAMPO_REDE: rede,
    }
    return {chave_: valor for chave_, valor in carimbo.items() if valor}
