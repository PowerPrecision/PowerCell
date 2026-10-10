"""Ao adicionar um cliente a um processo: «este cliente já tem um processo activo?»

O PEDIDO (Bloco 1, ponto 5)
===========================
«Ao adicionar um cliente a um processo, verificar se esse cliente já tem
algum processo activo associado e mostrar uma caixa de aviso/confirmação a
perguntar se quer continuar.»

AS TRÊS DECISÕES QUE ESTES TESTES FIXAM
=======================================
1. **«Activo» é o do motor**: `nomes_terminais(carregar_fases())`, não uma
   lista escrita à mão (a D-6) — um processo numa fase que o administrador
   marcou como terminal NÃO conta;
2. **O cliente pode estar em TRÊS sítios do processo**: `client_id` (1.º
   titular), `second_client_id` (2.º titular) e `client_ids` (co-titulares
   N:M). Procurar só no primeiro é o defeito do ponto 6 do mesmo bloco;
3. **A resposta respeita a rede**: um cliente — e os processos dele — que
   não são do âmbito de quem pergunta respondem 404 / não se contam. Um
   «já tem um processo activo» que atravesse redes confirma a existência de
   um cliente na ilha ao lado.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

ANA = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "diretor"}
BRUNO = {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt", "role": "diretor"}


def _proc(id, **kw):
    base = {
        "id": id,
        "process_number": 100,
        "status": "em_analise",
        "client_id": "c-power",
        "client_name": "Silva da Power",
        "company_id": "cmp-power",
        "network_id": REDE_INCUMBENTE,
        "consultor_names": ["Ana"],
        "created_at": "2026-10-01T10:00:00Z",
    }
    base.update(kw)
    return base


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.client_active_processes as cap

    semear(fake_async_db)
    # O cenário partilhado já traz processos de teste; aqui parte-se do zero.
    fake_async_db.processes.docs.clear()
    with tenant_db(fake_async_db, cap):
        yield fake_async_db


async def _activos(client_id="c-power", user=ANA, **kw):
    import services.client_active_processes as cap

    return await cap.processos_activos_do_cliente(client_id, user, **kw)


def _ids(res):
    return {p["id"] for p in res["processos"]}


# ════════════════════════════════════════════════════════════════════
class TestOndeOClienteEstaNoProcesso:
    @pytest.mark.asyncio
    async def test_primeiro_titular(self, mundo):
        mundo.processes.docs.append(_proc("p1"))
        res = await _activos()
        assert _ids(res) == {"p1"} and res["total"] == 1
        assert res["processos"][0]["titular"] == "titular1"

    @pytest.mark.asyncio
    async def test_segundo_titular_e_o_defeito_do_ponto_6(self, mundo):
        """Só como 2.º titular: procurar apenas por `client_id` não o vê."""
        mundo.processes.docs.append(_proc("p2", client_id="c-outro", second_client_id="c-power"))
        res = await _activos()
        assert _ids(res) == {"p2"}
        assert res["processos"][0]["titular"] == "titular2"

    @pytest.mark.asyncio
    async def test_co_titular_da_lista_n_m(self, mundo):
        mundo.processes.docs.append(_proc("p3", client_id="c-outro", client_ids=["c-outro", "c-power"]))
        res = await _activos()
        assert _ids(res) == {"p3"}
        assert res["processos"][0]["titular"] == "co_titular"

    @pytest.mark.asyncio
    async def test_processo_ligado_pelo_process_ids_do_cliente(self, mundo):
        """`link-process` põe o processo em `clients.process_ids`."""
        next(c for c in mundo.clients.docs if c["id"] == "c-power")["process_ids"] = ["p4"]
        mundo.processes.docs.append(_proc("p4", client_id="c-outro"))
        res = await _activos()
        assert _ids(res) == {"p4"}

    @pytest.mark.asyncio
    async def test_o_mesmo_processo_nao_conta_duas_vezes(self, mundo):
        next(c for c in mundo.clients.docs if c["id"] == "c-power")["process_ids"] = ["p1"]
        mundo.processes.docs.append(_proc("p1", client_ids=["c-power"]))
        res = await _activos()
        assert res["total"] == 1 and len(res["processos"]) == 1

    @pytest.mark.asyncio
    async def test_sem_processos_diz_zero(self, mundo):
        res = await _activos()
        assert res["total"] == 0 and res["processos"] == []
        assert res["client_name"] == "Silva da Power"


class TestOQueConstaComoActivo:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("estado", ["concluido", "concluidos", "cancelado", "desistencia", "eliminado", "arquivo", "perdido"])
    async def test_os_estados_terminais_nao_contam(self, mundo, estado):
        mundo.processes.docs.append(_proc("p1", status=estado))
        assert (await _activos())["total"] == 0

    @pytest.mark.asyncio
    async def test_um_processo_eliminado_por_flag_nao_conta(self, mundo):
        mundo.processes.docs.append(_proc("p1", is_deleted=True))
        assert (await _activos())["total"] == 0

    @pytest.mark.asyncio
    async def test_uma_fase_que_o_administrador_marcou_terminal_nao_conta(self, mundo):
        """O motor manda: nenhuma lista escrita à mão sabe desta fase."""
        mundo.workflow_statuses.docs.extend([
            {"name": "em_analise", "label": "Em análise", "order": 1, "is_active": True},
            {"name": "recusado_pelo_banco", "label": "Recusado", "order": 9, "is_active": False},
        ])
        mundo.processes.docs.extend([
            _proc("p1", status="recusado_pelo_banco"),
            _proc("p2", status="em_analise"),
        ])
        assert _ids(await _activos()) == {"p2"}

    @pytest.mark.asyncio
    async def test_o_processo_a_que_se_esta_a_adicionar_o_cliente_nao_conta(self, mundo):
        """Adicionar à P e avisar «já tem a P» seria ruído."""
        mundo.processes.docs.extend([_proc("pP"), _proc("pOutro")])
        res = await _activos(exclude_process_id="pP")
        assert _ids(res) == {"pOutro"}

    @pytest.mark.asyncio
    async def test_o_total_e_real_e_a_lista_tem_tecto(self, mundo):
        for i in range(25):
            mundo.processes.docs.append(_proc(f"p{i:02d}", process_number=i))
        res = await _activos()
        assert res["total"] == 25
        assert len(res["processos"]) == 20


class TestARede:
    @pytest.mark.asyncio
    async def test_um_cliente_de_outra_rede_da_404(self, mundo):
        mundo.processes.docs.append(_proc("p1"))
        with pytest.raises(HTTPException) as exc:
            await _activos(user=BRUNO)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_um_cliente_inexistente_da_o_MESMO_404(self, mundo):
        """Distinguir «não existe» de «não é teu» confirmava o id."""
        with pytest.raises(HTTPException) as exc_fora:
            await _activos(user=BRUNO)
        with pytest.raises(HTTPException) as exc_nada:
            await _activos(client_id="c-fantasma")
        assert exc_fora.value.detail == exc_nada.value.detail

    @pytest.mark.asyncio
    async def test_processos_de_outra_rede_nao_se_contam(self, mundo):
        """O cliente é da Power mas há um processo dele carimbado na Domus."""
        mundo.processes.docs.extend([
            _proc("p-meu"),
            _proc("p-domus", company_id="cmp-domus", network_id=REDE_DOMUS),
        ])
        res = await _activos()
        assert _ids(res) == {"p-meu"} and res["total"] == 1

    @pytest.mark.asyncio
    async def test_um_processo_partilhado_connosco_conta(self, mundo):
        """A partilha (D-25) abre o processo à rede convidada: é activo para ela."""
        mundo.processes.docs.append(_proc(
            "p-partilhado", company_id="cmp-domus", network_id=REDE_DOMUS,
            partner_network_ids=[REDE_INCUMBENTE],
        ))
        assert _ids(await _activos()) == {"p-partilhado"}

    @pytest.mark.asyncio
    async def test_um_processo_legado_por_carimbar_conta_para_o_grupo_incumbente(self, mundo):
        mundo.processes.docs.append({
            "id": "p-antigo", "status": "em_analise", "client_id": "c-power",
            "client_name": "Silva da Power", "process_number": 1,
        })
        assert _ids(await _activos()) == {"p-antigo"}


class TestOQueSaiParaOEcra:
    @pytest.mark.asyncio
    async def test_so_os_campos_que_o_aviso_precisa(self, mundo):
        """O aviso diz QUAL processo — nunca despeja o documento (NIF,
        telefone, IBAN, palavras-passe de portais...)."""
        mundo.processes.docs.append(_proc(
            "p1", personal_data={"nif": "123456789"}, financial_data={"iban": "PT50"},
            client_email="a@x.pt", titular2_data={"nif": "987654321"},
        ))
        res = await _activos()
        assert set(res["processos"][0]) <= {
            "id", "process_number", "status", "status_label", "titular",
            "consultor_names", "created_at",
        }
        assert "123456789" not in str(res) and "PT50" not in str(res)

    @pytest.mark.asyncio
    async def test_a_fase_vem_com_o_rotulo_do_motor(self, mundo):
        mundo.workflow_statuses.docs.append(
            {"name": "em_analise", "label": "Em Análise Bancária", "order": 1, "is_active": True}
        )
        mundo.processes.docs.append(_proc("p1"))
        assert (await _activos())["processos"][0]["status_label"] == "Em Análise Bancária"

    @pytest.mark.asyncio
    async def test_sem_rotulo_cai_para_o_nome_da_fase(self, mundo):
        mundo.processes.docs.append(_proc("p1", status="fase_sem_rotulo"))
        assert (await _activos())["processos"][0]["status_label"] == "fase_sem_rotulo"

    @pytest.mark.asyncio
    async def test_os_mais_recentes_primeiro(self, mundo):
        mundo.processes.docs.extend([
            _proc("velho", created_at="2026-01-01T00:00:00Z"),
            _proc("novo", created_at="2026-10-01T00:00:00Z"),
        ])
        res = await _activos()
        assert [p["id"] for p in res["processos"]] == ["novo", "velho"]


class TestOEndpointAntigoTambemRespeitaARede:
    """`GET /clients/{id}/processes` devolvia os processos DESENCRIPTADOS de
    qualquer cliente a qualquer sessão: zero `network`, zero posse."""

    @pytest.mark.asyncio
    async def test_um_utilizador_de_outra_rede_da_404(self, mundo):
        import services.client_process_ops as ops

        mundo.processes.docs.append(_proc("p1"))
        with pytest.raises(HTTPException) as exc:
            from unittest.mock import patch
            with patch.object(ops, "db", mundo):
                await ops.run_get_client_processes("c-power", BRUNO)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_so_devolve_os_processos_do_ambito(self, mundo):
        import services.client_process_ops as ops
        from unittest.mock import patch

        next(c for c in mundo.clients.docs if c["id"] == "c-power")["process_ids"] = ["p-meu", "p-domus"]
        mundo.processes.docs.extend([
            _proc("p-meu"),
            _proc("p-domus", company_id="cmp-domus", network_id=REDE_DOMUS),
        ])
        with patch.object(ops, "db", mundo):
            res = await ops.run_get_client_processes("c-power", ANA)
        assert {p["id"] for p in res["processes"]} == {"p-meu"}


BACKEND = Path(__file__).resolve().parents[2]


class TestALigacao:
    def test_a_rota_existe_e_recebe_o_request(self):
        arvore = ast.parse((BACKEND / "routes" / "clients.py").read_text(encoding="utf-8"))
        no = next(
            n for n in arvore.body
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_client_active_processes"
        )
        assert "request" in {a.arg for a in no.args.args}
        assert "exclude_process_id" in {a.arg for a in no.args.args}

    def test_a_rota_fica_antes_da_generica_com_id(self):
        """`/{client_id}/active-processes` não colide, mas o princípio da casa
        (estáticas antes de `/{client_id}`) mantém-se."""
        fonte = (BACKEND / "routes" / "clients.py").read_text(encoding="utf-8")
        assert fonte.index('"/{client_id}/active-processes"') < fonte.index('@router.delete("/{client_id}")')

    def test_o_servico_usa_o_ambito_de_processos_e_nao_o_generico(self):
        arvore = ast.parse((BACKEND / "services" / "client_active_processes.py").read_text(encoding="utf-8"))
        chamadas = {
            n.func.id for n in ast.walk(arvore)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }
        assert "build_tenant_process_condition" in chamadas
