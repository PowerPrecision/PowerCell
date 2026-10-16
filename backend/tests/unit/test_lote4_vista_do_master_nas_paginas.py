"""
Lote 4, ponto 1 (Out 2026) — a empresa que o Master escolhe no cabeçalho vale em TODAS as páginas.

O PEDIDO
  «O Master altera a empresa no cabeçalho (`X-Company-Id`), mas várias páginas
  ignoram o contexto e misturam dados de todas as redes: Rascunhos, Dashboard de
  Validades, Performance de Balcões, Análise e Estatísticas, Relatório Semanal,
  Desempenho da Equipa, Explorador de Ficheiros, Clientes Registados e Registo de
  Clientes.»

AS CAUSAS (três, não uma)
  1. Backend: estatísticas, relatório executivo/desempenho, a Pool (Registo de
     Clientes) e o Explorador resolviam o âmbito pelo `resolve_tenant_scope`, que é
     «tudo» para o Master. A VISTA (`resolve_vista_scope`) só estava nos atalhos de
     listagem `build_tenant_condition`/`build_tenant_process_condition`.
  2. Frontend: Validades, Balcões, Clientes Registados e a pesquisa global usavam
     `fetch` cru, que NÃO leva o `X-Company-Id` — o servidor nem sabia que havia uma
     empresa escolhida.
  3. Os Rascunhos vivem no `localStorage` com uma chave única por browser.
  Além disso, o filtro de consultores do Dashboard de Validades listava todos os
  consultores do sistema.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.unit.helpers_fonte import codigo_sem_comentarios
from tests.unit.helpers_tenant import (  # noqa: F401  (fixtures)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    casa,
    db_tenant,
    por_id,
    rede_de_omissao_incumbente,
    tenant_db,
)

RAIZ = Path(__file__).resolve().parents[2]
FRONTEND = RAIZ.parent / "frontend" / "src"

MASTER = {"id": "u-master", "name": "Master", "email": "m@sistema.pt", "role": "master"}


def _sessao(vista: str | None = None, *, efectivo: str = "master") -> dict:
    sessao = {**MASTER, "effective_role": efectivo, "is_active": True}
    if vista:
        sessao["vista_empresa_id"] = vista
    return sessao


@pytest.fixture
def mundo(db_tenant, rede_de_omissao_incumbente):  # noqa: F811
    db_tenant.users.docs.append(dict(MASTER))
    return db_tenant


# ════════════════════════════════════════════════════════════════════
#  REGISTO DE CLIENTES (a Pool)
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestARegistoDeClientesSegueAEmpresaEscolhida:
    async def _ids(self, mundo, user):
        from services.tenant_network import build_tenant_pool_condition

        with tenant_db(mundo):
            condicao = await build_tenant_pool_condition(user)
        return {c["id"] for c in mundo.clients.docs if casa(c, condicao)}

    async def test_a_exploracao_domus_escolhida_nao_ve_clientes_da_power(self, mundo):
        ids = await self._ids(mundo, _sessao("cmp-domus"))
        assert "c-power" not in ids
        assert "c-domus" in ids

    async def test_power_escolhida_nao_ve_clientes_da_domus(self, mundo):
        ids = await self._ids(mundo, _sessao("cmp-power"))
        assert "c-domus" not in ids
        assert "c-power" in ids

    async def test_sem_empresa_escolhida_continua_global(self, mundo):
        ids = await self._ids(mundo, _sessao())
        assert {"c-power", "c-domus"} <= ids


# ════════════════════════════════════════════════════════════════════
#  ESTATÍSTICAS (Análise e Estatísticas, Balcões)
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestAsEstatisticasSeguemAEmpresaEscolhida:
    async def _ambito(self, mundo, user):
        from services import stats_scope

        with tenant_db(mundo):
            return await stats_scope.resolver_ambito(user)

    async def test_a_condicao_so_apanha_processos_da_rede_escolhida(self, mundo):
        ambito = await self._ambito(mundo, _sessao("cmp-domus"))
        assert por_id(p for p in mundo.processes.docs if casa(p, ambito.condicao)) == {
            "p-domus", "p-domus-sem-rede",
        }

    async def test_o_global_continua_a_apanhar_tudo(self, mundo):
        ambito = await self._ambito(mundo, _sessao())
        assert {"p-power", "p-domus", "p-legado"} <= por_id(
            p for p in mundo.processes.docs if casa(p, ambito.condicao)
        )

    async def test_a_chave_de_cache_muda_com_a_empresa_escolhida(self, mundo):
        """Sem isto a Domus serviria os números do Redis calculados para o Sistema."""
        global_ = await self._ambito(mundo, _sessao())
        domus = await self._ambito(mundo, _sessao("cmp-domus"))
        power = await self._ambito(mundo, _sessao("cmp-power"))
        assert len({global_.sufixo, domus.sufixo, power.sufixo}) == 3


# ════════════════════════════════════════════════════════════════════
#  RELATÓRIO SEMANAL / DESEMPENHO DA EQUIPA
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestORelatorioExecutivoSegueAEmpresaEscolhida:
    async def _ambito(self, mundo, user):
        import services.admin_users_scope as aus
        from services import executive_report

        with tenant_db(mundo, aus):
            return await executive_report.resolver_ambito(user)

    async def test_domus_escolhida_o_relatorio_e_da_rede_domus(self, mundo):
        ambito = await self._ambito(mundo, _sessao("cmp-domus"))
        assert ambito.redes == (REDE_DOMUS,)
        assert ambito.scope.sem_fronteira is False

    async def test_sem_empresa_escolhida_e_o_consolidado(self, mundo):
        ambito = await self._ambito(mundo, _sessao())
        assert ambito.scope.sem_fronteira is True

    async def test_a_chave_de_cache_do_relatorio_muda_com_a_empresa(self, mundo):
        global_ = await self._ambito(mundo, _sessao())
        domus = await self._ambito(mundo, _sessao("cmp-domus"))
        assert global_.chave != domus.chave


# ════════════════════════════════════════════════════════════════════
#  EXPLORADOR DE FICHEIROS
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOExploradorSegueAEmpresaEscolhida:
    async def _ambito(self, mundo, user, *, vista):
        from types import SimpleNamespace

        from services import s3_explorer_scope

        pedido = SimpleNamespace(headers={}, state=SimpleNamespace())
        with tenant_db(mundo):
            return await s3_explorer_scope.ambito_do_utilizador(pedido, user, vista=vista)

    async def test_ao_listar_com_empresa_escolhida_o_ambito_estreita(self, mundo):
        scope, papel = await self._ambito(mundo, _sessao("cmp-domus"), vista=True)
        assert scope.network_ids == (REDE_DOMUS,)
        assert scope.sem_fronteira is False

    async def test_e_o_master_perde_a_reconciliacao_so_enquanto_a_vista_esta_estreita(self, mundo):
        from services.s3_explorer_scope import PAPEL_DA_VISTA, PastaDoExplorador, pode_ver

        scope, papel = await self._ambito(mundo, _sessao("cmp-domus"), vista=True)
        assert papel == PAPEL_DA_VISTA
        orfa = PastaDoExplorador(caminho="Documentação Clientes/x/", orfa=True)
        assert pode_ver(orfa, scope, role=papel) is False, "uma pasta órfã apareceu na vista da Domus"

    async def test_as_pastas_de_outra_rede_ficam_de_fora_da_vista(self, mundo):
        from services.s3_explorer_scope import PastaDoExplorador, pode_ver

        scope, papel = await self._ambito(mundo, _sessao("cmp-domus"), vista=True)
        da_power = PastaDoExplorador(
            caminho="Documentação Clientes/p/", network_ids=frozenset({REDE_INCUMBENTE}), company_ids=frozenset({"cmp-power"}),
        )
        da_domus = PastaDoExplorador(
            caminho="Documentação Clientes/d/", network_ids=frozenset({REDE_DOMUS}), company_ids=frozenset({"cmp-domus"}),
        )
        assert pode_ver(da_power, scope, role=papel) is False
        assert pode_ver(da_domus, scope, role=papel) is True

    async def test_sem_empresa_escolhida_o_master_continua_a_reconciliar(self, mundo):
        from services.s3_explorer_scope import PastaDoExplorador, pode_ver

        scope, papel = await self._ambito(mundo, _sessao(), vista=True)
        assert scope.sem_fronteira is True
        orfa = PastaDoExplorador(caminho="Documentação Clientes/x/", orfa=True)
        assert pode_ver(orfa, scope, role=papel) is True

    async def test_as_operacoes_por_caminho_tambem_ficam_na_empresa_escolhida(self, mundo):
        """INVERTIDO no Lote 7.1 (contexto estrito).

        Antes: «mover/renomear/apagar por caminho não podem 404 para o Master por causa do
        cabeçalho» (`sem_fronteira is True`). Agora a empresa escolhida é a fronteira do pedido,
        para listar e para mexer por caminho: um Master a trabalhar como Domus não mexe nas pastas
        da Power (a interface obriga a trocar de empresa), e as órfãs só se reconciliam na vista
        «Sistema».
        """
        from services.s3_explorer_scope import PastaDoExplorador, pode_ver

        scope, papel = await self._ambito(mundo, _sessao("cmp-domus"), vista=False)
        assert scope.sem_fronteira is False
        assert tuple(scope.network_ids) == (REDE_DOMUS,)
        da_power = PastaDoExplorador(
            caminho="Documentação Clientes/p/", network_ids=frozenset({REDE_INCUMBENTE}), company_ids=frozenset({"cmp-power"}),
        )
        orfa = PastaDoExplorador(caminho="Documentação Clientes/x/", orfa=True)
        assert pode_ver(da_power, scope, role=papel) is False
        assert pode_ver(orfa, scope, role=papel) is False

    async def test_contraprova_sem_empresa_escolhida_as_operacoes_continuam_globais(self, mundo):
        scope, _ = await self._ambito(mundo, _sessao(), vista=False)
        assert scope.sem_fronteira is True

    def test_a_listagem_do_servico_pede_a_vista_e_as_outras_nao(self):
        fonte = codigo_sem_comentarios((RAIZ / "services" / "admin_s3_explorer.py").read_text(encoding="utf-8"))
        assert fonte.count("ambito_do_utilizador(request, user, vista=True)") == 1
        assert fonte.count("ambito_do_utilizador(request, user)") >= 4


# ════════════════════════════════════════════════════════════════════
#  DASHBOARD DE VALIDADES: o filtro de consultores
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOFiltroDeConsultoresDasValidades:
    async def test_so_lista_consultores_da_empresa_escolhida(self, mundo):
        import services.admin_users_scope as aus
        from services import document_expiring_dashboard as dash

        mundo.users.docs.extend([
            {"id": "u-cons-power", "name": "Cons Power", "role": "consultor"},
            {"id": "u-cons-domus", "name": "Cons Domus", "role": "consultor"},
        ])
        mundo.user_company_roles.docs.extend([
            {"user_id": "u-cons-power", "company_id": "cmp-power", "company_name": "Power Real Estate",
             "role": "consultor"},
            {"user_id": "u-cons-domus", "company_id": "cmp-domus", "company_name": "Domus",
             "role": "consultor"},
        ])
        with tenant_db(mundo, dash, aus):
            resultado = await dash.run_get_expiring_documents_dashboard(
                days_ahead=30, urgency=None, consultor_id=None, search=None,
                user=_sessao("cmp-domus"),
            )
        ids = {c["id"] for c in resultado["consultors_filter"]}
        assert "u-cons-domus" in ids
        assert "u-cons-power" not in ids, "o filtro listou um consultor de outra rede"

    async def test_sem_empresa_escolhida_o_master_ve_todos(self, mundo):
        import services.admin_users_scope as aus
        from services import document_expiring_dashboard as dash

        mundo.users.docs.extend([
            {"id": "u-cons-power", "name": "Cons Power", "role": "consultor"},
            {"id": "u-cons-domus", "name": "Cons Domus", "role": "consultor"},
        ])
        with tenant_db(mundo, dash, aus):
            resultado = await dash.run_get_expiring_documents_dashboard(
                days_ahead=30, urgency=None, consultor_id=None, search=None, user=_sessao(),
            )
        assert {"u-cons-power", "u-cons-domus"} <= {c["id"] for c in resultado["consultors_filter"]}


# ════════════════════════════════════════════════════════════════════
#  FRONTEND: nenhuma destas páginas fala sem o contexto de empresa
# ════════════════════════════════════════════════════════════════════
PAGINAS_COM_FETCH = (
    "pages/ExpiringDocumentsDashboard.jsx",
    "pages/BranchPerformancePage.js",
    "pages/ClientsPage.js",
    "components/admin/ClientSearchTab.js",
)


class TestOFrontendLevaOContextoDeEmpresa:
    @pytest.mark.parametrize("ficheiro", PAGINAS_COM_FETCH)
    def test_todo_fetch_leva_os_cabecalhos_de_contexto(self, ficheiro):
        fonte = (FRONTEND / ficheiro).read_text(encoding="utf-8")
        chamadas = len(re.findall(r"\bfetch\(", fonte))
        assert chamadas >= 1, "o leitor não encontrou nenhum fetch: a guarda está cega"
        assert fonte.count("...cabecalhosDeContexto()") >= chamadas, (
            f"{ficheiro}: há {chamadas} fetch cru e só "
            f"{fonte.count('...cabecalhosDeContexto()')} com X-Company-Id"
        )

    def test_a_pagina_de_rascunhos_ja_nao_usa_a_chave_unica(self):
        fonte = (FRONTEND / "pages" / "DraftsPage.js").read_text(encoding="utf-8")
        assert "DRAFTS_STORAGE_KEY" not in fonte
        assert "chaveDosRascunhos(" in fonte
