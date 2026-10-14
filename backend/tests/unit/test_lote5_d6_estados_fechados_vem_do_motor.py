"""
Lote 5 — D-6 FECHADA: quem define «fechado» é a flag `is_active` da fase no MOTOR de workflow.

O DEFEITO
  `INACTIVE_STATUSES` é uma lista cravada em código que sobrevivia como recurso e continuava a ser o
  caminho de `client_list_search` e de mais quatro módulos. Uma fase nova marcada como terminal no painel
  de administração não era reconhecida como fechada nesses caminhos: os números de «carteira activa»
  divergiam do quadro, sem erro nenhum.

O QUE SE AFIRMA
  1. COMPORTAMENTO: uma fase terminal PERSONALIZADA da rede dona fecha o processo na listagem de clientes
     (contagem de activos, `is_active` do cliente e separador Histórico) — e a mesma fase noutra rede,
     onde é activa, não o fecha (cada processo fecha pelo workflow da rede DONA);
  2. INVENTÁRIO: os módulos que ainda mencionam `INACTIVE_STATUSES` são exactamente os que o fazem de
     propósito (definição, recurso explícito quando o motor não é injectado, medição) — um módulo novo
     que o leia falha por omissão, com contraprova de que o leitor lê mesmo.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE, rede_de_omissao_incumbente, semear, tenant_db  # noqa: F401
from tests.unit.test_lote4_clientes_registados_historico import ANA, _cli, _proc

RAIZ = Path(__file__).resolve().parents[2]


def _fase(nome, rede, activa, ordem):
    return {"id": f"{rede}-{nome}", "name": nome, "label": nome, "color": "#000", "order": ordem,
            "is_active": activa, "network_id": rede}


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.client_list_search as cls
    import services.client_list_titulares as clt

    semear(fake_async_db)
    fake_async_db.processes.docs.clear()
    fake_async_db.clients.docs.clear()
    # Workflow PRÓPRIO da rede incumbente: «arrumado_x» é terminal. Nome que NÃO consta da lista legada.
    fake_async_db.workflow_statuses.docs.extend([
        _fase("em_analise", REDE_INCUMBENTE, True, 1),
        _fase("arrumado_x", REDE_INCUMBENTE, False, 2),
    ])
    fake_async_db.clients.docs.extend([_cli("c-arrumado", "Arrumado"), _cli("c-curso", "Em Curso")])
    fake_async_db.processes.docs.extend([
        _proc("p1", "c-arrumado", "Arrumado", status="arrumado_x"),
        _proc("p2", "c-curso", "Em Curso", status="em_analise"),
    ])
    with tenant_db(fake_async_db, cls, clt):
        yield fake_async_db


async def _listar(**kw):
    import services.client_list_search as cls

    kw.setdefault("limit", 100)
    kw.setdefault("exclude_deleted", True)
    return await cls.run_list_clients(ANA, **kw)


@pytest.mark.asyncio
class TestUmaFaseTerminalPersonalizadaFechaOProcesso:
    async def test_a_exploracao_o_nome_nao_esta_na_lista_legada(self):
        from services.process_status import INACTIVE_STATUSES

        assert "arrumado_x" not in INACTIVE_STATUSES, "sem isto o teste não distingue o motor da lista"

    async def test_nao_conta_como_processo_activo(self, mundo):
        res = await _listar(show_all=True, historico=True)
        arrumado = next(c for c in res["clients"] if c["id"] == "c-arrumado")
        assert arrumado["active_processes_count"] == 0
        assert arrumado["is_active"] is False

    async def test_vai_para_o_historico_e_sai_do_ecra_de_trabalho(self, mundo):
        trabalho = {c["id"] for c in (await _listar(show_all=True))["clients"]}
        historico = {c["id"] for c in (await _listar(show_all=True, historico=True))["clients"]}
        assert "c-arrumado" not in trabalho
        assert "c-arrumado" in historico

    async def test_contraprova_o_processo_em_fase_activa_continua_activo(self, mundo):
        res = await _listar(show_all=True)
        curso = next(c for c in res["clients"] if c["id"] == "c-curso")
        assert curso["active_processes_count"] == 1
        assert curso["is_active"] is True

    async def test_a_mesma_fase_noutra_rede_onde_e_activa_nao_fecha_o_processo(self, mundo):
        """Cada processo fecha pelo workflow da rede DONA, não pelo de quem olha."""
        mundo.workflow_statuses.docs.extend([_fase("arrumado_x", REDE_DOMUS, True, 1)])
        mundo.clients.docs.append(_cli("c-domus", "Cliente Domus", network_id=REDE_DOMUS))
        mundo.processes.docs.append(_proc("p9", "c-domus", "Cliente Domus", status="arrumado_x", network_id=REDE_DOMUS))
        # Partilhado com a rede de ANA: o processo continua a significar em casa o que significa em casa.
        mundo.processes.docs[-1]["partner_network_ids"] = [REDE_INCUMBENTE]
        res = await _listar(show_all=True)
        domus = next(c for c in res["clients"] if c["id"] == "c-domus")  # visível pela partilha
        assert domus["active_processes_count"] == 1, "é activa no workflow da rede dona (Domus)"


class TestInventarioDoUsoDaListaLegada:
    #: módulo → porque é que continua a mencionar a lista.
    PERMITIDOS = {
        "services/process_status.py": "a definição",
        "services/workflow_phases.py": "o recurso de `nomes_terminais` para fases sem flag e nomes que não são fases",
        "services/workflow_status_coverage.py": "mede a cobertura da lista contra o motor",
        "services/process_list_filters.py": "recurso quando o chamador não injecta `terminais=`",
        "services/my_clients_api_helpers.py": "recurso quando o chamador não injecta `terminais=`",
        "services/process_update.py": "recurso quando o chamador não injecta `terminais=`",
        "services/client_list_search.py": "recurso SÓ quando o motor não se deixa ler (com aviso no log)",
    }

    @staticmethod
    def _modulos_que_leem():
        achados = set()
        for pasta in ("services", "routes"):
            for ficheiro in (RAIZ / pasta).glob("*.py"):
                arvore = ast.parse(ficheiro.read_text(encoding="utf-8"))
                for no in ast.walk(arvore):
                    if isinstance(no, ast.Name) and no.id == "INACTIVE_STATUSES":
                        achados.add(f"{pasta}/{ficheiro.name}")
                    if isinstance(no, ast.ImportFrom) and any(a.name == "INACTIVE_STATUSES" for a in no.names):
                        achados.add(f"{pasta}/{ficheiro.name}")
        return achados

    def test_o_leitor_le_mesmo(self):
        assert "services/process_status.py" in self._modulos_que_leem()
        assert "services/workflow_phases.py" in self._modulos_que_leem()

    def test_so_leem_a_lista_legada_os_modulos_que_o_fazem_de_proposito(self):
        extra = self._modulos_que_leem() - set(self.PERMITIDOS)
        assert not extra, (
            f"Módulo(s) novo(s) a ler `INACTIVE_STATUSES` sem passar pelo motor: {sorted(extra)}. "
            "Use `nomes_terminais(await fases_do_utilizador(user))` / `so_processos_com_fase_activa`."
        )

    def test_nenhuma_excepcao_ficou_a_mais(self):
        sobra = set(self.PERMITIDOS) - self._modulos_que_leem()
        assert not sobra, f"Excepções sem uso (apague-as da lista): {sorted(sobra)}"
