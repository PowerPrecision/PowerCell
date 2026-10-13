"""
IA MANUAL sobre os documentos de um processo: SÓ os altos perfis, dentro da fronteira de rede
(decisão da direcção, Out 2026 — controlo de custos da API).

HISTÓRICO
  Numa iteração anterior abriu-se a ferramenta a «gestão OU atribuído» (a equipa da rede
  satélite num processo partilhado não via o botão porque o gate era o cargo). A direcção
  revogou-o: cada clique é uma chamada paga ao modelo, e o fluxo normal já não depende do
  clique (a IA corre sozinha ao cair na `Index`: `test_ia_automatica_na_index.py`).
  Os testes que afirmavam que o ATRIBUÍDO podia foram INVERTIDOS, não apagados: agora provam
  que estar atribuído não abre nada.

O que se afirma:
  · a regra pura (Master/Admin/CEO/Diretor sim; atribuído NÃO; fronteira de rede ANTES do bypass);
  · as três rotas só abrem aos altos perfis (guardas reais da aplicação) e o serviço aplica
    a fronteira (comportamento, com o serviço real);
  · a flag que o detalhe devolve ao ecrã vem da MESMA função que recusa.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from services import document_ai_access as acesso
from services.document_ai_access import (
    DETALHE_SEM_PERMISSAO_DE_IA,
    exigir_ia_no_processo,
    pode_usar_ia,
    pode_usar_ia_no_processo,
)
from services.tenant_network import TenantScope

REDE_POWER = "rede-power"
REDE_PRECISION = "rede-precision"
REDE_DOMUS = "rede-domus"

#: Processo da Power partilhado com a Precision (rede de destino) e atribuído a dois da Precision.
PROCESSO_PARTILHADO = {
    "id": "proc-1",
    "network_id": REDE_POWER,
    "partner_network_ids": [REDE_PRECISION],
    "assigned_consultor_ids": ["u-consultor-precision"],
    "assigned_consultor_id": "u-consultor-precision",
    "consultant_id": "u-consultor-precision",
    "assigned_mediador_ids": ["u-interm-precision"],
    "assigned_mediador_id": "u-interm-precision",
}

AMBITO_PRECISION = TenantScope(network_ids=(REDE_PRECISION,))
AMBITO_POWER = TenantScope(network_ids=(REDE_POWER,))
AMBITO_DOMUS = TenantScope(network_ids=(REDE_DOMUS,))


def _u(uid: str, role: str = "consultor") -> dict:
    return {"id": uid, "role": role}


class TestARegraPura:
    @pytest.mark.parametrize("papel", ["master", "admin", "ceo", "diretor"])
    def test_a_gestao_da_rede_satelite_pode(self, papel):
        assert pode_usar_ia(papel, _u("u-gestor", papel), PROCESSO_PARTILHADO,
                            scope=AMBITO_PRECISION)

    def test_o_consultor_atribuido_NAO_pode(self):
        # Invertido: estar atribuído já não abre a ferramenta manual.
        assert not pode_usar_ia("consultor", _u("u-consultor-precision"),
                                PROCESSO_PARTILHADO, scope=AMBITO_PRECISION)

    def test_o_intermediario_atribuido_NAO_pode(self):
        assert not pode_usar_ia("intermediario", _u("u-interm-precision", "intermediario"),
                                PROCESSO_PARTILHADO, scope=AMBITO_PRECISION)

    def test_o_atribuido_por_campo_legado_tambem_NAO_pode(self):
        processo = {"id": "p", "network_id": REDE_POWER, "partner_network_ids": [REDE_PRECISION],
                    "consultant_id": "u-legado"}
        assert not pode_usar_ia("consultor", _u("u-legado"), processo, scope=AMBITO_PRECISION)

    @pytest.mark.parametrize("papel", ["consultor", "intermediario", "administrativo",
                                       "indexacao", "parceiro"])
    def test_nenhum_cargo_operacional_pode_seja_qual_for_a_atribuicao(self, papel):
        # Mesmo atribuído por TODOS os campos: o uid está em todas as listas.
        uid = "u-x"
        processo = {**PROCESSO_PARTILHADO,
                    "assigned_consultor_ids": [uid], "assigned_consultor_id": uid,
                    "consultant_id": uid, "assigned_mediador_ids": [uid],
                    "assigned_mediador_id": uid}
        assert not pode_usar_ia(papel, _u(uid, papel), processo, scope=AMBITO_PRECISION)

    def test_a_lista_de_gestao_sao_exactamente_os_quatro_altos_perfis(self):
        assert [str(p.value if hasattr(p, "value") else p) for p in acesso.PAPEIS_DE_GESTAO_DA_IA] \
            == ["master", "admin", "ceo", "diretor"]

    def test_o_dono_continua_a_poder(self):
        assert pode_usar_ia("diretor", _u("u-d", "diretor"), PROCESSO_PARTILHADO,
                            scope=AMBITO_POWER)

    def test_a_fronteira_de_rede_vem_ANTES_do_bypass_de_cargo(self):
        # Um diretor da Domus (ilha) não ganha acesso por ser diretor.
        assert not pode_usar_ia("diretor", _u("u-d", "diretor"), PROCESSO_PARTILHADO,
                                scope=AMBITO_DOMUS)

    def test_a_gestao_sem_partilha_tambem_fica_fora_da_fronteira(self):
        # Contraprova da partilha: sem a Precision convidada, nem o admin da Precision passa.
        sem_partilha = {**PROCESSO_PARTILHADO, "partner_network_ids": []}
        assert not pode_usar_ia("admin", _u("u-a", "admin"), sem_partilha,
                                scope=AMBITO_PRECISION)

    def test_ambito_vazio_recusa_tudo(self):
        assert not pode_usar_ia("admin", _u("u-a", "admin"), PROCESSO_PARTILHADO,
                                scope=TenantScope())

    def test_sem_scope_a_pura_nao_aplica_fronteira(self):
        assert pode_usar_ia("admin", _u("u-a", "admin"), PROCESSO_PARTILHADO, scope=None)


def _pedido(papel_activo: str | None = None):
    req = MagicMock()
    req.headers = {"X-Active-Role": papel_activo} if papel_activo else {}
    req.state = MagicMock(spec=[])
    return req


class TestAsVariantesAsync:
    @pytest.mark.asyncio
    async def test_o_perfil_ACTIVO_decide_nao_o_cargo_base(self):
        # Atribuído? Não. Cargo base consultor. Com o chapéu de diretor da Precision, pode.
        utilizador = _u("u-multi", "consultor")
        with patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="diretor")):
            assert await pode_usar_ia_no_processo(_pedido("diretor"), utilizador, PROCESSO_PARTILHADO)
        with patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            assert not await pode_usar_ia_no_processo(_pedido("consultor"), utilizador, PROCESSO_PARTILHADO)

    @pytest.mark.asyncio
    async def test_exigir_levanta_403_com_o_motivo(self):
        with patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            with pytest.raises(HTTPException) as erro:
                await exigir_ia_no_processo(_pedido(), _u("u-outro"), PROCESSO_PARTILHADO)
        assert erro.value.status_code == 403
        assert erro.value.detail == DETALHE_SEM_PERMISSAO_DE_IA

    @pytest.mark.asyncio
    async def test_exigir_recusa_o_atribuido(self):
        with patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            with pytest.raises(HTTPException) as erro:
                await exigir_ia_no_processo(
                    _pedido(), _u("u-consultor-precision"), PROCESSO_PARTILHADO
                )
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_exigir_deixa_passar_o_diretor(self):
        with patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="diretor")):
            await exigir_ia_no_processo(_pedido(), _u("u-d", "diretor"), PROCESSO_PARTILHADO)

    @pytest.mark.asyncio
    async def test_falha_a_resolver_o_ambito_recusa(self):
        # `_ambito_do_utilizador` falha FECHADO (TenantScope vazio): nem o admin passa.
        with patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=TenantScope())), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="admin")):
            assert not await pode_usar_ia_no_processo(
                _pedido(), _u("u-a", "admin"), PROCESSO_PARTILHADO
            )


class TestAsTresRotasAplicamAGuarda:
    """Comportamento com o serviço real: o consultor NÃO atribuído é recusado (403) e
    o ATRIBUÍDO chega ao trabalho. A guarda corre ANTES de qualquer leitura/IA."""

    def _bd(self):
        bd = MagicMock()
        bd.processes.find_one = AsyncMock(return_value=dict(PROCESSO_PARTILHADO))
        return bd

    @pytest.mark.asyncio
    async def test_ai_analyze_recusa_o_nao_atribuido_antes_de_ler_os_ficheiros(self):
        from services import document_ai_analyze as mod

        ler = AsyncMock()
        with patch.object(mod, "db", self._bd()), \
             patch.object(mod, "_read_upload_files", ler), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            with pytest.raises(HTTPException) as erro:
                await mod.run_ai_analyze_documents(
                    "proc-1", [], user=_u("u-outro"), request=_pedido()
                )
        assert erro.value.status_code == 403
        ler.assert_not_called()

    @pytest.mark.asyncio
    async def test_ai_analyze_recusa_o_ATRIBUIDO_e_deixa_o_diretor_chegar_ao_trabalho(self):
        from services import document_ai_analyze as mod

        ler = AsyncMock(return_value=[])
        with patch.object(mod, "db", self._bd()), \
             patch.object(mod, "_read_upload_files", ler), \
             patch.object(mod, "run_analysis_on_documents", AsyncMock(return_value={"success": True})), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            with pytest.raises(HTTPException) as erro:
                await mod.run_ai_analyze_documents(
                    "proc-1", [], user=_u("u-consultor-precision"), request=_pedido()
                )
        assert erro.value.status_code == 403
        ler.assert_not_called()
        with patch.object(mod, "db", self._bd()), \
             patch.object(mod, "_read_upload_files", ler), \
             patch.object(mod, "run_analysis_on_documents", AsyncMock(return_value={"success": True})), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="diretor")):
            resultado = await mod.run_ai_analyze_documents(
                "proc-1", [], user=_u("u-d", "diretor"), request=_pedido()
            )
        assert resultado == {"success": True}
        ler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rename_all_recusa_o_nao_gestor(self):
        from services import document_rename_smart as mod

        with patch.object(mod, "db", self._bd()), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            with pytest.raises(HTTPException) as erro:
                await mod.run_rename_all_documents_smart(
                    "proc-1", user=_u("u-outro"), request=_pedido()
                )
        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_rename_all_recusa_o_atribuido_e_deixa_o_diretor_passar(self):
        from services import document_rename_smart as mod

        bd = self._bd()
        bd.document_metadata.find = MagicMock(
            return_value=MagicMock(to_list=AsyncMock(return_value=[]))
        )
        with patch.object(mod, "db", bd), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            with pytest.raises(HTTPException) as erro:
                await mod.run_rename_all_documents_smart(
                    "proc-1", user=_u("u-consultor-precision"), request=_pedido()
                )
        assert erro.value.status_code == 403
        with patch.object(mod, "db", bd), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="diretor")):
            resultado = await mod.run_rename_all_documents_smart(
                "proc-1", user=_u("u-d", "diretor"), request=_pedido()
            )
        assert resultado["total"] == 0

    @pytest.mark.asyncio
    async def test_extract_recusa_o_atribuido_antes_de_tocar_no_s3(self):
        from services import document_vision_extract as mod

        # As guardas de caminho/posse ficam neutras de propósito: o 403 que se afirma tem de
        # ser o da IA (o detalhe), e não o de um caminho que não pertence ao processo.
        ler = AsyncMock()
        with patch.object(mod, "db", self._bd()), \
             patch.object(mod, "assert_path_within_document_root", lambda *_: None), \
             patch.object(mod, "assert_s3_file_belongs_to_process", lambda *_: None), \
             patch.object(mod, "ler_ficheiro_do_s3", ler), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            with pytest.raises(HTTPException) as erro:
                await mod.run_extract_document_data(
                    "proc-1", "Documentação Clientes/x/y.pdf",
                    user=_u("u-consultor-precision"), request=_pedido(),
                )
        assert erro.value.status_code == 403
        assert erro.value.detail == DETALHE_SEM_PERMISSAO_DE_IA
        ler.assert_not_called()


class TestADecisaoDoEcraVemDoServidor:
    @pytest.mark.asyncio
    async def test_o_detalhe_do_processo_leva_a_flag_calculada_pela_mesma_funcao(self):
        from services.process_detail import anexar_permissao_de_ia

        processo: dict = {}
        with patch(
            "services.document_ai_access.pode_usar_ia_no_processo",
            AsyncMock(return_value=True),
        ) as pergunta:
            await anexar_permissao_de_ia(processo, _u("u-1"), _pedido())
        assert processo["pode_usar_ia_documentos"] is True
        pergunta.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_se_a_pergunta_falha_o_campo_fica_por_preencher_e_o_ecra_decide_pelo_cargo(self):
        from services.process_detail import anexar_permissao_de_ia

        processo: dict = {}
        with patch(
            "services.document_ai_access.pode_usar_ia_no_processo",
            AsyncMock(side_effect=RuntimeError("bd em baixo")),
        ):
            await anexar_permissao_de_ia(processo, _u("u-1"), _pedido())
        # Nem `False` (tiraria o botão à gestão por um soluço) nem `True`.
        assert "pode_usar_ia_documentos" not in processo

    def test_o_detalhe_chama_a_flag_e_a_rota_passa_o_pedido(self):
        from routes import processes as rota
        from services import process_detail
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        corpo = codigo_da_funcao_sem_comentarios(process_detail.run_get_process_detail)
        assert "anexar_permissao_de_ia(process, user, request)" in corpo
        assert "request=request" in codigo_da_funcao_sem_comentarios(rota.get_process)


class TestAsRotasSoAbremAosAltosPerfis:
    """As três rotas reais (as guardas que o FastAPI monta) só deixam passar os altos perfis.
    Antes da revogação eram `require_staff` e a decisão vivia só no serviço; a direcção quer
    a recusa também à porta — um consultor nem chega a ler os ficheiros enviados."""

    CAMINHOS = (
        ("/api/documents/ai-analyze/{process_id}", "POST"),
        ("/api/documents/rename-all-smart/{process_id}", "POST"),
        ("/api/processes/{process_id}/documents/extract", "POST"),
    )

    @staticmethod
    def _guardas_de_papel(rota):
        achadas = []

        def percorrer(dependant):
            for dep in dependant.dependencies:
                if hasattr(dep.call, "allowed_roles"):
                    achadas.append(dep.call)
                percorrer(dep)

        percorrer(rota.dependant)
        return achadas

    @pytest.mark.parametrize("caminho, metodo", CAMINHOS)
    def test_a_rota_existe_e_so_admite_os_altos_perfis(self, caminho, metodo):
        import os

        os.environ.setdefault("TESTING", "true")
        import server

        rotas = [r for r in server.app.routes
                 if getattr(r, "path", None) == caminho and metodo in (r.methods or ())]
        assert rotas, f"rota {metodo} {caminho} desapareceu"
        permitidos = set()
        for guarda in self._guardas_de_papel(rotas[0]):
            permitidos |= {str(getattr(p, "value", p)).lower() for p in guarda.allowed_roles}
        assert permitidos == {"master", "admin", "ceo", "diretor"}, (
            f"{caminho} admite {sorted(permitidos)}"
        )

    @pytest.mark.parametrize("modulo, funcao", [
        ("routes.documents", "ai_analyze_documents"),
        ("routes.documents", "rename_all_documents_smart"),
        ("routes.document_extraction", "extract_document_data"),
    ])
    def test_o_pedido_continua_a_chegar_ao_servico(self, modulo, funcao):
        import importlib
        import inspect

        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fn = getattr(importlib.import_module(modulo), funcao)
        assert "request: Request" in inspect.getsource(fn).replace("\n", " ")
        assert "request=request" in codigo_da_funcao_sem_comentarios(fn)
