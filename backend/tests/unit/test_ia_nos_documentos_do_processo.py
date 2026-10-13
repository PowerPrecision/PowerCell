"""
IA sobre os documentos de um processo: gestão OU atribuído, dentro da fronteira de rede
(QA, Out 2026).

O botão «Analisar» não aparecia à equipa da rede satélite (Precision/Domus) num processo
PARTILHADO: o gate era `require_roles([MASTER, ADMIN, CEO, DIRETOR])`, que decide pelo
cargo e não vê o processo — o consultor/intermediário que a distribuição B2B atribuiu ao
processo na rede de destino nunca podia usar a ferramenta. Não havia nenhuma condição
«só a rede primária» (nem no ecrã nem no servidor): a causa era o cargo.

O que se afirma:
  · a regra pura (gestão, atribuído, fronteira de rede ANTES do bypass);
  · cada uma das três rotas aplica a guarda (comportamento, com o serviço real);
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

    def test_o_consultor_atribuido_da_rede_satelite_pode(self):
        assert pode_usar_ia("consultor", _u("u-consultor-precision"),
                            PROCESSO_PARTILHADO, scope=AMBITO_PRECISION)

    def test_o_intermediario_atribuido_da_rede_satelite_pode(self):
        assert pode_usar_ia("intermediario", _u("u-interm-precision", "intermediario"),
                            PROCESSO_PARTILHADO, scope=AMBITO_PRECISION)

    def test_o_atribuido_so_por_campo_legado_tambem_pode(self):
        # `collect_assigned_ids` é o ponto único — uma lista à mão aqui divergiria dos escritores.
        processo = {"id": "p", "network_id": REDE_POWER, "partner_network_ids": [REDE_PRECISION],
                    "consultant_id": "u-legado"}
        assert pode_usar_ia("consultor", _u("u-legado"), processo, scope=AMBITO_PRECISION)

    def test_o_consultor_NAO_atribuido_nao_pode(self):
        assert not pode_usar_ia("consultor", _u("u-outro"), PROCESSO_PARTILHADO,
                                scope=AMBITO_PRECISION)

    @pytest.mark.parametrize("papel", ["administrativo", "indexacao", "parceiro"])
    def test_outros_cargos_nao_atribuidos_nao_podem(self, papel):
        # A abertura é a quem trata do processo, não a todo o staff.
        assert not pode_usar_ia(papel, _u("u-x", papel), PROCESSO_PARTILHADO,
                                scope=AMBITO_PRECISION)

    def test_o_dono_continua_a_poder(self):
        assert pode_usar_ia("diretor", _u("u-d", "diretor"), PROCESSO_PARTILHADO,
                            scope=AMBITO_POWER)

    def test_a_fronteira_de_rede_vem_ANTES_do_bypass_de_cargo(self):
        # Um diretor da Domus (ilha) não ganha acesso por ser diretor.
        assert not pode_usar_ia("diretor", _u("u-d", "diretor"), PROCESSO_PARTILHADO,
                                scope=AMBITO_DOMUS)

    def test_atribuido_numa_rede_sem_partilha_nao_passa_a_fronteira(self):
        # Contraprova da partilha: sem a Precision convidada, o mesmo consultor fica de fora.
        sem_partilha = {**PROCESSO_PARTILHADO, "partner_network_ids": []}
        assert not pode_usar_ia("consultor", _u("u-consultor-precision"), sem_partilha,
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
    async def test_exigir_deixa_passar_o_atribuido(self):
        with patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            await exigir_ia_no_processo(
                _pedido(), _u("u-consultor-precision"), PROCESSO_PARTILHADO
            )

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
    async def test_ai_analyze_deixa_o_atribuido_chegar_ao_trabalho(self):
        from services import document_ai_analyze as mod

        ler = AsyncMock(return_value=[])
        with patch.object(mod, "db", self._bd()), \
             patch.object(mod, "_read_upload_files", ler), \
             patch.object(mod, "run_analysis_on_documents", AsyncMock(return_value={"success": True})), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            resultado = await mod.run_ai_analyze_documents(
                "proc-1", [], user=_u("u-consultor-precision"), request=_pedido()
            )
        assert resultado == {"success": True}
        ler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rename_all_recusa_o_nao_atribuido(self):
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
    async def test_rename_all_deixa_o_atribuido_passar_a_guarda(self):
        from services import document_rename_smart as mod

        bd = self._bd()
        bd.document_metadata.find = MagicMock(
            return_value=MagicMock(to_list=AsyncMock(return_value=[]))
        )
        with patch.object(mod, "db", bd), \
             patch.object(acesso, "_ambito_do_utilizador", AsyncMock(return_value=AMBITO_PRECISION)), \
             patch.object(acesso, "get_effective_role_async", AsyncMock(return_value="consultor")):
            resultado = await mod.run_rename_all_documents_smart(
                "proc-1", user=_u("u-consultor-precision"), request=_pedido()
            )
        assert resultado["total"] == 0

    @pytest.mark.asyncio
    async def test_extract_recusa_o_nao_atribuido_antes_de_tocar_no_s3(self):
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
                    user=_u("u-outro"), request=_pedido(),
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
    async def test_se_a_pergunta_falha_o_ecra_nao_oferece_o_botao(self):
        from services.process_detail import anexar_permissao_de_ia

        processo: dict = {}
        with patch(
            "services.document_ai_access.pode_usar_ia_no_processo",
            AsyncMock(side_effect=RuntimeError("bd em baixo")),
        ):
            await anexar_permissao_de_ia(processo, _u("u-1"), _pedido())
        assert processo["pode_usar_ia_documentos"] is False

    def test_o_detalhe_chama_a_flag_e_a_rota_passa_o_pedido(self):
        from routes import processes as rota
        from services import process_detail
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        corpo = codigo_da_funcao_sem_comentarios(process_detail.run_get_process_detail)
        assert "anexar_permissao_de_ia(process, user, request)" in corpo
        assert "request=request" in codigo_da_funcao_sem_comentarios(rota.get_process)


class TestAsRotasJaNaoFiltramPorCargo:
    """O `require_roles` só decide pelo cargo — a causa do botão em falta. As três rotas
    passam a `require_staff` e a decisão vive no serviço (que vê o processo)."""

    @pytest.mark.parametrize(
        "modulo, funcao",
        [
            ("routes.documents", "ai_analyze_documents"),
            ("routes.documents", "rename_all_documents_smart"),
            ("routes.document_extraction", "extract_document_data"),
        ],
    )
    def test_sem_require_roles_e_com_o_pedido_passado_ao_servico(self, modulo, funcao):
        import importlib

        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        mod = importlib.import_module(modulo)
        fn = getattr(mod, funcao)
        assert "request: Request" in __import__("inspect").getsource(fn).replace("\n", " ")
        corpo = codigo_da_funcao_sem_comentarios(fn)
        assert "request=request" in corpo
        assert "require_roles" not in __import__("inspect").getsource(fn).split('"""')[0]
