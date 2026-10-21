"""QA-9, ponto 1 — a lista de Utilizadores segue a EMPRESA escolhida e não mostra parceiros.

O QUE A QA VIU
==============
Com o Master a trabalhar na Precision aparecia gente da Domus e as contas de Parceiros misturadas na
lista de staff. Reproduzido: a Domus não vinha (a rede já estreitava), mas (1) os parceiros (contas
fantasma de role `parceiro`) vinham sempre e (2) a lista era a da REDE, logo uma colega da Power
aparecia com a Precision escolhida — a mesma queixa com outro nome.

Hoje `empresas_da_empresa_activa` estreita a LISTAGEM à empresa do `X-Company-Id` (só se o âmbito a
aceitou: o cabeçalho nunca alarga) e `sem_parceiros` tira o role `parceiro`. A gestão por id
continua a seguir a REDE e as dropdowns de atribuição mantêm o âmbito de rede.
"""
from __future__ import annotations

import pytest

from tests.unit.helpers_tenant import (  # noqa: F401
    db_tenant,  # noqa: F401  (fixture)
    tenant_db as _tenant_db,
)

MASTER = {"id": "u-master", "name": "Master", "email": "m@sistema.pt", "role": "master"}


def _pessoa(uid, role, empresa_id, empresa_nome, **extra):
    return {
        "id": uid, "name": uid, "email": f"{uid}@x.pt", "role": role, "is_active": True,
        "company": empresa_nome, **extra,
    }, {
        "user_id": uid, "company_id": empresa_id, "company_name": empresa_nome,
        "role": role, "is_default": True,
    }


@pytest.fixture
def equipa(db_tenant):  # noqa: F811
    pessoas = [
        _pessoa("u-ceo-precision", "ceo", "cmp-precision", "Precision Crédito"),
        _pessoa("u-cons-precision", "consultor", "cmp-precision", "Precision Crédito"),
        _pessoa("u-ceo-power", "ceo", "cmp-power", "Power Real Estate"),
        _pessoa("u-ceo-domus", "ceo", "cmp-domus", "Domus"),
        _pessoa("u-dir-domus", "diretor", "cmp-domus", "Domus"),
        _pessoa("u-parc", "parceiro", "cmp-precision", "Precision Crédito",
                criado_pela_rede="grupo_power_precision"),
    ]
    for doc, ucr in pessoas:
        db_tenant.users.docs.append(doc)
        db_tenant.user_company_roles.docs.append(ucr)
    # Sem empresa nenhuma: não pertence a ninguém, não pode aparecer na lista de uma empresa.
    db_tenant.users.docs.append(
        {"id": "u-orfao", "name": "Orfão", "email": "o@x.pt", "role": "consultor", "is_active": True}
    )
    db_tenant.users.docs.append({**MASTER, "is_active": True})
    return db_tenant


def _ctx(fake_db):
    from services import admin_users, admin_users_scope, users_api_list

    return _tenant_db(fake_db, admin_users_scope, admin_users, users_api_list)


def _ator(vista=None, **extra):
    ator = dict(MASTER, **extra)
    if vista:
        ator["vista_empresa_id"] = vista
    return ator


def _ids(lista):
    return {(u["id"] if isinstance(u, dict) else u.id) for u in lista}


async def _admin_lista(equipa, ator, **kw):
    from services.admin_users import run_get_users

    with _ctx(equipa):
        return _ids(await run_get_users(ator, **kw))


async def _admin_paginada(equipa, ator, **kw):
    from services.admin_users import run_get_users_paginated

    with _ctx(equipa):
        res = await run_get_users_paginated(ator, **kw)
    return _ids(res["users"])


async def _users_lista(equipa, ator, **kw):
    from services.users_api_list import run_get_users

    kw.setdefault("role", None)
    with _ctx(equipa):
        return _ids(await run_get_users(kw.pop("role"), ator, **kw))


TRES_LISTAGENS = [_admin_lista, _admin_paginada, _users_lista]


class TestAExploracao:
    """O ataque: o que a QA viu, escrito para morder primeiro."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("listar", TRES_LISTAGENS)
    async def test_com_a_precision_escolhida_so_aparece_a_precision(self, equipa, listar):
        ids = await listar(equipa, _ator("cmp-precision"))
        assert {"u-ceo-precision", "u-cons-precision"} <= ids
        assert "u-ceo-domus" not in ids and "u-dir-domus" not in ids  # outra rede
        assert "u-ceo-power" not in ids  # mesma rede, outra empresa
        assert "u-orfao" not in ids

    @pytest.mark.asyncio
    @pytest.mark.parametrize("listar", TRES_LISTAGENS)
    async def test_os_parceiros_nao_aparecem_na_lista_de_staff(self, equipa, listar):
        for vista in (None, "cmp-precision"):
            assert "u-parc" not in await listar(equipa, _ator(vista))

    @pytest.mark.asyncio
    @pytest.mark.parametrize("listar", TRES_LISTAGENS)
    async def test_um_ceo_local_com_cabecalho_forjado_nao_alarga(self, equipa, listar):
        ceo = {"id": "u-ceo-precision", "name": "x", "role": "ceo", "vista_empresa_id": "cmp-domus"}
        ids = await listar(equipa, ceo)
        assert "u-ceo-domus" not in ids and "u-dir-domus" not in ids


class TestContraprovas:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("listar", TRES_LISTAGENS)
    async def test_a_domus_escolhida_ve_so_a_domus(self, equipa, listar):
        ids = await listar(equipa, _ator("cmp-domus"))
        assert {"u-ceo-domus", "u-dir-domus"} <= ids
        assert "u-ceo-precision" not in ids and "u-ceo-power" not in ids

    @pytest.mark.asyncio
    @pytest.mark.parametrize("listar", TRES_LISTAGENS)
    async def test_sem_empresa_escolhida_o_master_continua_a_ver_tudo_menos_parceiros(
        self, equipa, listar
    ):
        ids = await listar(equipa, _ator())
        assert {"u-ceo-precision", "u-ceo-power", "u-ceo-domus", "u-dir-domus"} <= ids
        assert "u-parc" not in ids

    @pytest.mark.asyncio
    @pytest.mark.parametrize("listar", [_admin_lista, _admin_paginada, _users_lista])
    async def test_pedir_explicitamente_role_parceiro_continua_a_funcionar(self, equipa, listar):
        ids = await listar(equipa, _ator("cmp-precision"), role="parceiro")
        assert ids == {"u-parc"}

    @pytest.mark.asyncio
    async def test_a_dropdown_de_atribuicao_segue_a_empresa_escolhida(self, equipa):
        """INVERTIDO em P5. Antes mantinha o âmbito de REDE («a Power e a Precision partilham-na»);
        mas uma dropdown responde a «quem trabalha nesta empresa?»: com a Precision escolhida não
        aparece gente da Power nem da Domus, mesmo que as empresas partilhem a rede."""
        ids = await _admin_lista(equipa, _ator("cmp-precision"), for_assignment=True)
        assert "u-ceo-precision" in ids
        assert "u-ceo-power" not in ids and "u-ceo-domus" not in ids


class TestSemParceiros:

    def test_junta_a_exclusao_a_uma_query_existente(self):
        from services.admin_users_scope import sem_parceiros

        q = sem_parceiros({"is_active": True})
        assert q["$and"][0] == {"is_active": True}
        assert set(q["$and"][1]["role"]["$nin"]) == {"parceiro", "partner"}

    def test_query_vazia_devolve_so_a_exclusao(self):
        from services.admin_users_scope import sem_parceiros

        assert "$nin" in sem_parceiros({})["role"]

    def test_role_parceiro_pedido_nao_exclui(self):
        from services.admin_users_scope import sem_parceiros

        assert sem_parceiros({"a": 1}, "Parceiro") == {"a": 1}
        assert sem_parceiros({}, "partner") == {}
