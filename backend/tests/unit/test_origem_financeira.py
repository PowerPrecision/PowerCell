"""Origem financeira do processo — orgânica vs angariação (Bloco 4, ponto 7).

A REGRA DE NEGÓCIO
==================
O cliente de um processo ou veio directamente à empresa (lead ORGÂNICA) ou
foi angariado por um utilizador específico. É a base do cálculo posterior
das comissões e só a gestão (admin, CEO, diretor) a vê e a altera.

O QUE ESTE FICHEIRO PROVA
=========================
* **Quem**: só o papel EFECTIVO de gestão. Um consultor e a Indexação
  recebem 403; o diretor só da casa DONA (um convidado vê o processo, não
  decide a quem se atribui o negócio); quem nem vê o processo recebe 404.
* **O angariador é validado**: existe, está activo e é do âmbito de quem
  decide. Um id de outra rede é recusado — atribuir comissão a quem não se
  pode ver é o buraco que as outras fronteiras já fecharam.
* **A origem NÃO está no documento do processo**: o `GET /processes/{id}`
  devolve o documento inteiro (`extra="allow"`), logo um campo lá dentro
  vazava para quem não o pode ver. A restrição é da arquitectura.
* **O rasto não revela o valor**: o histórico é lido por quem não vê a
  origem; só o trilho de auditoria (gestão) leva o valor.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (fixtures)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

BACKEND = Path(__file__).resolve().parents[2]

ANA = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "diretor"}
BRUNO = {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt", "role": "diretor"}
CARLA = {"id": "u-carla", "name": "Carla", "email": "carla@precision.pt", "role": "consultor"}
ADMIN = {"id": "u-admin", "name": "Admin", "email": "a@x.pt", "role": "admin"}
CEO = {"id": "u-ceo", "name": "CEO", "email": "c@x.pt", "role": "ceo"}
INDEXADOR = {"id": "u-ix", "name": "Xavier", "email": "x@x.pt", "role": "indexacao"}

#: Utilizadores do âmbito Power/Precision (e um da Domus + um inactivo).
UTILIZADORES = [
    {"id": "u-ana", "name": "Ana", "role": "diretor", "is_active": True,
     "company": "Power Real Estate"},
    {"id": "u-dora", "name": "Dora", "role": "consultor", "is_active": True,
     "company": "Power Real Estate"},
    {"id": "u-inativo", "name": "Inácio", "role": "consultor", "is_active": False,
     "company": "Power Real Estate"},
    # Sem `company` ele cairia na regra das contas ÓRFÃS (pertencem à rede de
    # omissão) e deixava de ser da Domus — o fixture tem de ser realista.
    {"id": "u-bruno", "name": "Bruno", "role": "diretor", "is_active": True,
     "company": "Domus"},
    # Inserido por ÚLTIMO e com o nome que vem primeiro: sem ordenação
    # explícita ele aparecia no fim da lista de candidatos.
    {"id": "u-abel", "name": "Abel", "role": "intermediario", "is_active": True,
     "company": "Power Real Estate"},
]
UCRS_EXTRA = [
    {"user_id": "u-dora", "company_id": "cmp-power", "company_name": "Power Real Estate",
     "role": "consultor", "is_default": True},
    {"user_id": "u-inativo", "company_id": "cmp-power", "company_name": "Power Real Estate",
     "role": "consultor", "is_default": True},
    {"user_id": "u-abel", "company_id": "cmp-power", "company_name": "Power Real Estate",
     "role": "intermediario", "is_default": True},
]


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.admin_users_scope as aus
    import services.audit_trail_service as ats
    import services.history as history
    import services.origem_financeira as of

    semear(fake_async_db)
    fake_async_db.processes.docs.clear()
    fake_async_db.processes.docs.extend([
        {"id": "p1", "process_number": 1, "client_name": "Silva", "status": "em_analise",
         "company_id": "cmp-power", "network_id": REDE_INCUMBENTE},
        # Power dona, Domus convidada.
        {"id": "p-partilhado", "process_number": 2, "client_name": "Souza", "status": "em_analise",
         "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
         "partner_network_ids": [REDE_DOMUS]},
        {"id": "p-domus", "process_number": 3, "client_name": "Dias", "status": "em_analise",
         "company_id": "cmp-domus", "network_id": REDE_DOMUS},
    ])
    fake_async_db.users.docs.extend(dict(u) for u in UTILIZADORES)
    fake_async_db.user_company_roles.docs.extend(dict(u) for u in UCRS_EXTRA)
    with tenant_db(fake_async_db, of, aus, history, ats):
        yield fake_async_db


async def _definir(tipo="angariacao", angariador="u-dora", user=ANA, process_id="p1", request=None):
    import services.origem_financeira as of

    return await of.run_set_origem(process_id, tipo, angariador, user, request)


async def _ler(user=ANA, process_id="p1"):
    import services.origem_financeira as of

    return await of.run_get_origem(process_id, user, None)


class TestARegraDeNegocio:
    @pytest.mark.asyncio
    async def test_sem_definir_a_origem_diz_que_nao_esta_definida(self, mundo):
        res = await _ler()
        assert res["definida"] is False
        assert res["tipo"] is None and res["angariador"] is None

    @pytest.mark.asyncio
    async def test_veio_diretamente_a_empresa(self, mundo):
        res = await _definir("organica", None)
        assert res["definida"] is True
        assert res["tipo"] == "organica"
        assert res["rotulo"] == "Veio diretamente à empresa"
        assert res["angariador"] is None

    @pytest.mark.asyncio
    async def test_angariado_por_um_utilizador_especifico(self, mundo):
        res = await _definir("angariacao", "u-dora")
        assert res["tipo"] == "angariacao"
        assert res["rotulo"] == "Foi angariado por um utilizador específico"
        assert res["angariador"] == {"id": "u-dora", "nome": "Dora", "papel": "consultor"}
        assert res["definido_por"] == "Ana"
        assert res["definido_em"]

    @pytest.mark.asyncio
    async def test_a_leitura_devolve_o_que_se_gravou(self, mundo):
        await _definir("angariacao", "u-dora")
        assert (await _ler())["angariador"]["id"] == "u-dora"

    @pytest.mark.asyncio
    async def test_organica_NAO_guarda_angariador_mesmo_que_venha_um(self, mundo):
        """O cálculo de comissões não pode ler um nome que a regra descarta."""
        await _definir("angariacao", "u-dora")
        res = await _definir("organica", "u-dora")
        assert res["angariador"] is None
        gravado = mundo.process_financial_origins.docs[0]
        assert gravado["angariador_id"] is None
        assert gravado["angariador_nome"] is None

    @pytest.mark.asyncio
    async def test_alterar_substitui_sem_duplicar(self, mundo):
        await _definir("angariacao", "u-dora")
        await _definir("angariacao", "u-ana")
        assert len(mundo.process_financial_origins.docs) == 1
        assert (await _ler())["angariador"]["id"] == "u-ana"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("tipo", ["", "outra", None, "ORGANICA "])
    async def test_um_tipo_invalido_e_recusado(self, mundo, tipo):
        if tipo == "ORGANICA ":
            # Normaliza: maiúsculas e espaços não são um erro do utilizador.
            assert (await _definir(tipo, None))["tipo"] == "organica"
            return
        with pytest.raises(HTTPException) as exc:
            await _definir(tipo, None)
        assert exc.value.status_code == 422
        assert mundo.process_financial_origins.docs == []

    @pytest.mark.asyncio
    async def test_angariacao_sem_angariador_e_recusada(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await _definir("angariacao", "  ")
        assert exc.value.status_code == 422
        assert mundo.process_financial_origins.docs == []


class TestOAngariadorEValidado:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "alvo", ["u-bruno", "u-inativo", "u-fantasma"],
        ids=["de outra rede", "inactivo", "inexistente"],
    )
    async def test_recusa(self, mundo, alvo):
        with pytest.raises(HTTPException) as exc:
            await _definir("angariacao", alvo)
        assert exc.value.status_code == 422
        assert mundo.process_financial_origins.docs == []

    @pytest.mark.asyncio
    async def test_um_pedido_recusado_nao_apaga_a_origem_anterior(self, mundo):
        await _definir("angariacao", "u-dora")
        with pytest.raises(HTTPException):
            await _definir("angariacao", "u-bruno")
        assert (await _ler())["angariador"]["id"] == "u-dora"


class TestQuemPode:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("quem", [ANA, ADMIN, CEO], ids=["diretor", "admin", "ceo"])
    async def test_a_gestao_define_e_le(self, mundo, quem):
        await _definir("organica", None, user=quem)
        assert (await _ler(user=quem))["tipo"] == "organica"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "quem", [CARLA, INDEXADOR, {"id": "u-adm", "name": "Adm", "role": "administrativo"}],
        ids=["consultor", "indexacao", "administrativo"],
    )
    async def test_os_outros_recebem_403_a_ler_e_a_escrever(self, mundo, quem):
        with pytest.raises(HTTPException) as escrever:
            await _definir("organica", None, user=quem)
        with pytest.raises(HTTPException) as ler:
            await _ler(user=quem)
        assert escrever.value.status_code == 403
        assert ler.value.status_code == 403
        assert mundo.process_financial_origins.docs == []

    @pytest.mark.asyncio
    async def test_conta_o_perfil_efectivo_e_nao_o_do_jwt(self, mundo):
        """Diretor de base a trabalhar COMO consultor: sem acesso."""
        import services.origem_financeira as of

        with patch.object(of, "resolver_papel_efectivo", AsyncMock(return_value="consultor")):
            with pytest.raises(HTTPException) as exc:
                await of.run_get_origem("p1", ANA, object())
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_o_pedido_e_passado_ao_resolvedor_do_papel(self, mundo):
        """Sem o `request` o resolvedor não vê o `X-Active-Role` e cai no cargo
        do JWT: a regra «perfil efectivo» ficava só na docstring."""
        import services.origem_financeira as of

        pedido = object()
        resolvedor = AsyncMock(return_value="diretor")
        with patch.object(of, "resolver_papel_efectivo", resolvedor):
            await of.run_get_origem("p1", ANA, pedido)
        assert resolvedor.await_args.args[1] is pedido

    @pytest.mark.asyncio
    async def test_um_consultor_a_trabalhar_COMO_diretor_tem_acesso(self, mundo):
        import services.origem_financeira as of

        with patch.object(of, "resolver_papel_efectivo", AsyncMock(return_value="diretor")):
            res = await of.run_set_origem("p1", "organica", None, {**CARLA, "id": "u-ana"}, object())
        assert res["tipo"] == "organica"

    @pytest.mark.asyncio
    async def test_quem_nao_ve_o_processo_recebe_o_mesmo_404_que_um_id_inexistente(self, mundo):
        with pytest.raises(HTTPException) as fora:
            await _ler(user=BRUNO, process_id="p1")
        with pytest.raises(HTTPException) as nada:
            await _ler(user=BRUNO, process_id="p-fantasma")
        assert fora.value.status_code == 404
        assert fora.value.detail == nada.value.detail

    @pytest.mark.asyncio
    async def test_o_diretor_da_rede_convidada_ve_o_processo_mas_nao_decide(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await _definir("organica", None, user=BRUNO, process_id="p-partilhado")
        assert exc.value.status_code == 403
        assert mundo.process_financial_origins.docs == []

    @pytest.mark.asyncio
    async def test_o_diretor_da_casa_dona_decide_no_processo_partilhado(self, mundo):
        res = await _definir("organica", None, user=ANA, process_id="p-partilhado")
        assert res["tipo"] == "organica"


class TestOCandidato:
    @pytest.mark.asyncio
    async def test_so_utilizadores_activos_do_ambito(self, mundo):
        import services.origem_financeira as of

        res = await of.run_list_candidatos("p1", ANA, None)
        ids = {c["id"] for c in res["candidatos"]}
        assert "u-dora" in ids
        assert "u-bruno" not in ids, "a Domus é uma ilha"
        assert "u-inativo" not in ids

    @pytest.mark.asyncio
    async def test_os_candidatos_vem_ordenados_por_nome(self, mundo):
        import services.origem_financeira as of

        nomes = [c["nome"] for c in (await of.run_list_candidatos("p1", ANA, None))["candidatos"]]
        assert nomes[0] == "Abel"
        assert nomes == sorted(nomes)

    @pytest.mark.asyncio
    async def test_um_consultor_nao_ve_a_lista(self, mundo):
        import services.origem_financeira as of

        with pytest.raises(HTTPException) as exc:
            await of.run_list_candidatos("p1", CARLA, None)
        assert exc.value.status_code == 403


class TestOSitioOndeVive:
    @pytest.mark.asyncio
    async def test_o_documento_do_processo_nao_ganha_nenhum_campo(self, mundo):
        """O `GET /processes/{id}` devolve o documento inteiro (`extra=allow`):
        qualquer campo novo ali vaza para quem não pode ver a origem."""
        antes = dict(next(p for p in mundo.processes.docs if p["id"] == "p1"))
        await _definir("angariacao", "u-dora")
        depois = next(p for p in mundo.processes.docs if p["id"] == "p1")
        assert depois == antes

    @pytest.mark.asyncio
    async def test_a_origem_leva_o_carimbo_do_processo(self, mundo):
        await _definir("organica", None)
        gravado = mundo.process_financial_origins.docs[0]
        assert gravado["network_id"] == REDE_INCUMBENTE
        assert gravado["company_id"] == "cmp-power"
        assert gravado["process_id"] == "p1"

    def test_nenhum_outro_modulo_escreve_a_origem_no_processo(self):
        """Guarda de fonte: só `origem_financeira.py` fala deste nome."""
        ofensores = []
        for pasta in ("services", "routes"):
            for ficheiro in (BACKEND / pasta).rglob("*.py"):
                if ficheiro.name == "origem_financeira.py":
                    continue
                texto = ficheiro.read_text(encoding="utf-8")
                for ocorrencia in re.finditer(r"origem_financeira", texto):
                    linha = texto[: ocorrencia.start()].count("\n") + 1
                    ofensores.append(f"{ficheiro.relative_to(BACKEND)}:{linha}")
        # `routes/processes.py` tem as três rotas (paths e nomes de funções).
        ofensores = [o for o in ofensores if not o.startswith("routes/processes.py")]
        assert ofensores == []


class TestORasto:
    @pytest.mark.asyncio
    async def test_o_historico_regista_que_mudou_e_NAO_para_quê(self, mundo):
        await _definir("angariacao", "u-dora")
        assert len(mundo.history.docs) == 1
        entrada = mundo.history.docs[0]
        assert entrada["field"] == "origem_financeira"
        assert entrada["new_value"] is None and entrada["old_value"] is None
        # O nome do angariador não pode estar em NENHUM campo do histórico:
        # o consultor lê o histórico do processo e não vê a origem.
        assert "Dora" not in str(entrada) and "u-dora" not in str(entrada)

    @pytest.mark.asyncio
    async def test_o_trilho_de_auditoria_leva_o_antes_e_o_depois(self, mundo):
        trilho = AsyncMock(return_value="x")
        await _definir("organica", None)
        with patch("services.audit_trail_service.log_audit_event", trilho):
            await _definir("angariacao", "u-dora")
        trilho.assert_awaited_once()
        kwargs = trilho.await_args.kwargs
        assert kwargs["old_value"] == "organica"
        assert kwargs["new_value"] == "angariacao:u-dora"
        assert kwargs["metadata"] == {"papel_efectivo": "diretor"}

    @pytest.mark.asyncio
    async def test_repetir_o_mesmo_valor_nao_deixa_rasto(self, mundo):
        await _definir("angariacao", "u-dora")
        trilho = AsyncMock(return_value="x")
        with patch("services.audit_trail_service.log_audit_event", trilho):
            await _definir("angariacao", "u-dora")
        trilho.assert_not_awaited()
        assert len(mundo.history.docs) == 1

    @pytest.mark.asyncio
    async def test_um_actor_silenciado_define_mas_nao_deixa_rasto(self, mundo):
        """Restrição de segurança do perfil Indexação: sem histórico nem auditoria."""
        import services.origem_financeira as of

        actor = {**ANA, "role": "indexacao", "effective_role": "diretor"}
        trilho = AsyncMock(return_value="x")
        with patch("services.audit_trail_service.log_audit_event", trilho), \
                patch.object(of, "resolver_papel_efectivo", AsyncMock(return_value="diretor")):
            res = await of.run_set_origem("p1", "organica", None, actor, object())
        assert res["tipo"] == "organica"
        trilho.assert_not_awaited()
        assert mundo.history.docs == []

    @pytest.mark.asyncio
    async def test_o_desligar_do_historico_de_uma_pessoa_tambem_se_aplica(self, mundo):
        await _definir("organica", None, user={**ANA, "track_history": False})
        assert mundo.history.docs == []
        assert len(mundo.process_financial_origins.docs) == 1

    @pytest.mark.asyncio
    async def test_se_o_rasto_falhar_a_operacao_nao_falha(self, mundo):
        import services.origem_financeira as of

        with patch.object(of, "log_history", AsyncMock(side_effect=RuntimeError("bd"))), \
                patch("services.audit_trail_service.log_audit_event",
                      AsyncMock(side_effect=RuntimeError("bd"))):
            res = await _definir("organica", None)
        assert res["tipo"] == "organica"


class TestALigacao:
    def _handlers(self):
        arvore = ast.parse((BACKEND / "routes" / "processes.py").read_text(encoding="utf-8"))
        return {
            n.name: n for n in arvore.body
            if isinstance(n, ast.AsyncFunctionDef) and n.name.endswith("origem_financeira")
        }

    def test_as_tres_rotas_existem_e_declaram_request(self):
        handlers = self._handlers()
        assert set(handlers) == {
            "get_origem_financeira",
            "list_candidatos_origem_financeira",
            "set_origem_financeira",
        }
        for h in handlers.values():
            assert "request" in {a.arg for a in h.args.args}, h.name

    def test_cada_rota_chama_o_servico(self):
        handlers = self._handlers()
        assert "run_get_origem" in ast.unparse(handlers["get_origem_financeira"])
        assert "run_list_candidatos" in ast.unparse(handlers["list_candidatos_origem_financeira"])
        assert "run_set_origem" in ast.unparse(handlers["set_origem_financeira"])

    def test_o_indice_unico_por_processo_esta_declarado(self):
        fonte = (BACKEND / "services" / "db_indexes.py").read_text(encoding="utf-8")
        bloco = fonte[fonte.index("origin_indexes"):]
        assert "idx_origin_process" in bloco
        assert '"unique": True' in bloco.split("idx_origin_angariador")[0]
