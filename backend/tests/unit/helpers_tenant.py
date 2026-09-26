"""
Cenário partilhado do isolamento multi-tenant: duas redes, três empresas.

PORQUE É QUE ISTO SAIU DO FICHEIRO DE TESTES
  O cenário nasceu em `test_tenant_network_isolation.py` (Lote 4, ponto
  10) e o Dashboard precisa exactamente do mesmo: as mesmas empresas, os
  mesmos UCRs, o mesmo processo legado por carimbar. Copiá-lo para o
  segundo ficheiro dava duas versões da mesma realidade a divergir — e a
  primeira vez que alguém acrescentasse uma empresa a um deles, metade
  dos testes de isolamento passava a provar outra coisa.

  A Carla existe de propósito: trabalha nas duas redes, e é ela que
  distingue "isolamento" de "uma empresa só".
"""
from __future__ import annotations

import contextlib
from unittest.mock import patch

import pytest

REDE_INCUMBENTE = "grupo_power_precision"
REDE_DOMUS = "grupo_domus"

EMPRESAS = [
    {"id": "cmp-power", "name": "Power Real Estate", "network_id": REDE_INCUMBENTE},
    {"id": "cmp-precision", "name": "Precision Crédito", "network_id": REDE_INCUMBENTE},
    {"id": "cmp-domus", "name": "Domus", "network_id": REDE_DOMUS},
]

UCRS = [
    {"user_id": "u-ana", "company_id": "cmp-power", "company_name": "Power Real Estate",
     "role": "diretor", "is_default": True},
    {"user_id": "u-bruno", "company_id": "cmp-domus", "company_name": "Domus",
     "role": "diretor", "is_default": True},
    # Carla trabalha nas duas redes — não é fuga, são os dois empregos dela.
    {"user_id": "u-carla", "company_id": "cmp-precision", "company_name": "Precision Crédito",
     "role": "consultor", "is_default": True},
    {"user_id": "u-carla", "company_id": "cmp-domus", "company_name": "Domus",
     "role": "consultor", "is_default": False},
]

ANA = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "diretor"}
BRUNO = {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt", "role": "diretor"}
CARLA = {"id": "u-carla", "name": "Carla", "email": "carla@precision.pt", "role": "consultor"}
ORFAO = {"id": "u-orfao", "name": "Orfão", "email": "orfao@sistema.pt", "role": "admin"}

PROCESSOS = [
    {"id": "p-power", "client_name": "Cliente da Power", "status": "novo",
     "company_id": "cmp-power", "network_id": REDE_INCUMBENTE},
    {"id": "p-domus", "client_name": "Cliente da Domus", "status": "novo",
     "company_id": "cmp-domus", "network_id": REDE_DOMUS},
    # O processo que já lá estava antes desta mudança: sem carimbo nenhum.
    {"id": "p-legado", "client_name": "Cliente Antigo", "status": "novo"},
    # Carimbado com empresa mas ainda sem rede (criado entre a camada 3 e
    # a migração). NÃO é "sem marca de tenant" — ver teste dedicado.
    {"id": "p-domus-sem-rede", "client_name": "Outro da Domus", "status": "novo",
     "company_id": "cmp-domus"},
]

CLIENTES = [
    {"id": "c-power", "nome": "Silva da Power", "network_id": REDE_INCUMBENTE,
     "company_id": "cmp-power", "contacto": {}, "dados_pessoais": {"nif": "111111111"}},
    {"id": "c-domus", "nome": "Silva da Domus", "network_id": REDE_DOMUS,
     "company_id": "cmp-domus", "contacto": {}, "dados_pessoais": {"nif": "222222222"}},
    {"id": "c-legado", "nome": "Silva Antigo", "contacto": {},
     "dados_pessoais": {"nif": "333333333"}},
]


def semear(fake_db):
    """Semeia o cenário na base de dados falsa."""
    for empresa in EMPRESAS:
        fake_db.companies.docs.append(dict(empresa))
    for ucr in UCRS:
        fake_db.user_company_roles.docs.append(dict(ucr))
    for proc in PROCESSOS:
        fake_db.processes.docs.append(dict(proc))
    for cli in CLIENTES:
        fake_db.clients.docs.append(dict(cli))
    return fake_db


def casa(doc: dict, condicao: dict) -> bool:
    """Aplica uma condição Mongo a um documento com o matcher da fake."""
    from tests.unit.conftest import FakeAsyncCollection

    return FakeAsyncCollection._matches(doc, condicao)


def por_id(docs):
    return {d["id"] for d in docs}


def tenant_db(fake_db, *modulos_extra):
    """Patcha a BD em TODA a cadeia de resolução do âmbito.

    `tenant_network` importa `db` no topo (referência própria), mas
    delega a lista de empresas válidas em `auth.get_user_companies`, que
    faz `from database import db` DENTRO da função. Patchar só um dos
    dois deixa metade da cadeia a falar com o proxy real — e o resultado
    passa ou falha conforme a ORDEM de recolha do pytest (ver AGENTS.md).

    ÉPICO 10, PONTO 1 — a cadeia cresceu: `workflow_phases` também
    importa `db` no topo, e o quadro passou a perguntar-lhe que fases
    estão fechadas. Sem este patch o `carregar_fases` falava com o proxy
    real, a excepção era engolida (degradação graciosa), devolvia `[]` e
    o quadro vinha SEM COLUNAS — um teste vermelho a apontar para o
    isolamento quando o problema era o `db`.

    DASHBOARD, PONTO 1 — e cresceu outra vez: `stats_scope`,
    `admin_users_scope` e os módulos de estatísticas importam `db` no
    topo cada um. **Uma cadeia nova de `db` entra aqui**, por nome, via
    `modulos_extra`.
    """
    import services.tenant_network as tn
    import services.workflow_phases as wp

    @contextlib.contextmanager
    def _ctx():
        with contextlib.ExitStack() as pilha:
            pilha.enter_context(patch.object(tn, "db", fake_db))
            pilha.enter_context(patch.object(wp, "db", fake_db))
            pilha.enter_context(patch("database.db", fake_db))
            for modulo in modulos_extra:
                pilha.enter_context(patch.object(modulo, "db", fake_db))
            yield

    return _ctx()


@pytest.fixture
def db_tenant(fake_async_db):
    return semear(fake_async_db)


@pytest.fixture
def rede_de_omissao_incumbente(monkeypatch):
    """Produção: a pilha por carimbar pertence ao grupo incumbente."""
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    yield REDE_INCUMBENTE
