"""
Processo FECHADO — o que o D-34 deixou de fora e agora fecha (Out 2026).

O QUE ESTAVA ABERTO
  Em `TECHNICAL_DEBT.md` (D-34) ficaram quatro superfícies de fora porque
  «não editam o processo»: o envio de emails (e os modelos de pedido de
  documentos), a análise/extracção de documentos por IA e o `link-process`.
  Num processo «Concluído» ainda se podia mandar um email ao cliente, gerar
  uma análise de IA que se gravava no processo e voltar a ligar um cliente.

COMO SE TESTA  (a mesma forma do `test_processo_fechado_rotas_secundarias.py`)
  * o ATAQUE primeiro: cada superfície tentada nos routers REAIS por Master,
    Admin, CEO e Diretor — sem excepção por cargo;
  * as que não levam `{process_id}` no caminho (o `process_id` vai no corpo ou
    na query) testam-se ao nível do serviço, com a contraprova de que num
    processo ABERTO continuam a funcionar;
  * a leitura nunca fecha (ver a análise já feita, ver o email recebido);
  * «fechado» nunca é um oráculo sobre um processo de outra rede.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from services import process_closed_guard as guarda
from services.auth import get_current_user
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
from tests.unit.helpers_tenant import (  # noqa: F401
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)
from tests.unit.test_processo_fechado_rotas_secundarias import (
    ABERTO, FECHADO, FECHADO_DA_DOMUS, PERFIS, _cenario, _fechou,
)


@pytest.fixture
def app_e_cliente(fake_async_db, rede_de_omissao_incumbente):
    import routes.ai_analysis as ai_analysis
    import routes.document_extraction as extraccao
    import routes.emails as emails
    import routes.templates as templates
    import services.auth as auth_mod
    import services.process_scope_guard as psg
    import services.workflow_phases as wp

    _cenario(fake_async_db)
    atual = {"user": PERFIS["master"]}
    app = FastAPI()
    for modulo in (emails, templates, ai_analysis, extraccao):
        app.include_router(modulo.router)
    app.dependency_overrides[get_current_user] = lambda: atual["user"]
    # Os papéis dos routers de IA/modelos: o ataque é à guarda do processo, não às papéis.
    from services.auth import require_roles  # noqa: F401

    with tenant_db(fake_async_db, guarda, auth_mod, psg, wp):
        cliente = TestClient(app, raise_server_exceptions=False)
        cliente.definir_utilizador = lambda u: atual.update(user=u)
        yield cliente


TENTATIVAS = {
    "enviar_documentacao_aos_balcoes": ("POST", "/emails/send-documentation/{pid}", {}),
    "monitorizar_um_email": ("POST", "/emails/monitored/{pid}", {"email": "x@y.pt"}),
    "deixar_de_monitorizar": ("DELETE", "/emails/monitored/{pid}/x@y.pt", None),
    "modelo_de_pedido_de_documentos": ("POST", "/templates/process/{pid}/document-request", {}),
    "gerar_analise_de_ia": ("POST", "/processes/{pid}/analyze", None),
    "extrair_dados_de_um_documento_por_ia": (
        "POST", "/processes/{pid}/documents/extract", {"file_path": "Documentação Clientes/x.pdf"},
    ),
}


class TestAsSuperficiesRecusamUmProcessoFechado:
    @pytest.mark.parametrize("perfil", sorted(PERFIS))
    @pytest.mark.parametrize("tentativa", sorted(TENTATIVAS))
    def test_fechado_e_403_para_todos_os_perfis(self, app_e_cliente, tentativa, perfil):
        metodo, caminho, corpo = TENTATIVAS[tentativa]
        app_e_cliente.definir_utilizador(PERFIS[perfil])
        resposta = app_e_cliente.request(metodo, caminho.format(pid=FECHADO), json=corpo)
        assert _fechou(resposta), f"{perfil}/{tentativa} → {resposta.status_code} {resposta.text[:120]}"

    @pytest.mark.parametrize("tentativa", sorted(TENTATIVAS))
    def test_aberto_a_guarda_nao_atrapalha(self, app_e_cliente, tentativa):
        """Contraprova: uma guarda que recusasse sempre passava o teste de cima."""
        metodo, caminho, corpo = TENTATIVAS[tentativa]
        resposta = app_e_cliente.request(metodo, caminho.format(pid=ABERTO), json=corpo)
        assert not _fechou(resposta), f"{tentativa} → {resposta.text[:120]}"

    @pytest.mark.parametrize("caminho", [
        "/emails/preview-documentation/{pid}", "/emails/timeline/{pid}",
        "/emails/process/{pid}", "/emails/stats/{pid}", "/emails/monitored/{pid}",
        "/processes/{pid}/analyze",
    ])
    def test_a_leitura_nunca_fecha(self, app_e_cliente, caminho):
        """Ver o que já existe (a análise feita, o email recebido) não é escrever."""
        assert not _fechou(app_e_cliente.get(caminho.format(pid=FECHADO)))

    def test_recolher_correio_recebido_continua_a_poder(self, app_e_cliente):
        """É a única excepção do fecho: não altera o processo nem fala com o cliente."""
        assert not _fechou(app_e_cliente.post(f"/emails/sync/{FECHADO}"))

    def test_outra_rede_nao_ve_o_estado_sem_oraculo(self, app_e_cliente):
        app_e_cliente.definir_utilizador(PERFIS["diretor"])  # Power
        resposta = app_e_cliente.post(f"/processes/{FECHADO_DA_DOMUS}/analyze")
        assert not _fechou(resposta)


# ====================================================================
# O ENVIO COM O `process_id` NO CORPO — escapa à dependência de router
# ====================================================================

def _pedido_de_envio(process_id):
    from models.email import EmailSendRequest

    return EmailSendRequest(
        to_emails=["cliente@x.pt"], subject="Assunto", body="Olá", process_id=process_id,
    )


@pytest.fixture
def servicos(fake_async_db, rede_de_omissao_incumbente):
    import services.email_process_crud as epc
    import services.workflow_phases as wp

    _cenario(fake_async_db)
    # Nada pode ficar em fila: um processo ABERTO segue o envio normal e o
    # temporizador de «desfazer» chegaria a sair para a rede.
    with tenant_db(fake_async_db, guarda, epc, wp), \
            patch("services.email_send_queue.schedule_pending_email_send", AsyncMock()), \
            patch("services.email_service.send_email", AsyncMock()):
        yield epc, fake_async_db


class TestEnviarUmEmailParaUmProcessoFechado:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", sorted(PERFIS))
    async def test_o_envio_e_403_e_nada_sai(self, servicos, perfil):
        epc, _bd = servicos
        enviar = AsyncMock()
        with patch("services.email_service.send_email", enviar):
            with pytest.raises(HTTPException) as exc:
                await epc.run_send_email(
                    _pedido_de_envio(FECHADO), MagicMock(headers={}), PERFIS[perfil],
                )
        assert exc.value.status_code == 403 and "fechado" in exc.value.detail
        enviar.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_guarda_corre_antes_de_qualquer_outra_coisa(self):
        """Antes de resolver a empresa, a conta de envio ou o ramo da fila."""
        import services.email_process_crud as epc

        codigo = codigo_da_funcao_sem_comentarios(epc.run_send_email)
        assert "exigir_processo_aberto_por_id" in codigo
        assert codigo.index("exigir_processo_aberto_por_id") < codigo.index("get_active_company_id_async")
        assert codigo.index("exigir_processo_aberto_por_id") < codigo.index("db.shared_role_email_configs")

    @pytest.mark.asyncio
    async def test_sem_processo_a_guarda_nao_corre(self, servicos):
        """Um email avulso (sem `process_id`) nunca foi sobre um processo."""
        epc, _bd = servicos
        guarda_chamada = AsyncMock()
        with patch.object(guarda, "exigir_processo_aberto_por_id", guarda_chamada):
            try:
                await epc.run_send_email(
                    _pedido_de_envio(None), MagicMock(headers={}), PERFIS["master"],
                )
            except Exception:
                pass  # o resto do envio não é o assunto aqui
        guarda_chamada.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_num_processo_aberto_a_guarda_deixa_passar(self, servicos):
        epc, _bd = servicos
        try:
            await epc.run_send_email(
                _pedido_de_envio(ABERTO), MagicMock(headers={}), PERFIS["master"],
            )
        except HTTPException as exc:
            assert "fechado" not in str(exc.detail)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_um_processo_de_outra_rede_nao_responde_fechado(self, servicos):
        epc, _bd = servicos
        try:
            await epc.run_send_email(
                _pedido_de_envio(FECHADO_DA_DOMUS), MagicMock(headers={}), PERFIS["diretor"],
            )
        except HTTPException as exc:
            assert "fechado" not in str(exc.detail)
        except Exception:
            pass


# ====================================================================
# RASCUNHOS — o rascunho de um processo fechado não se envia nem se cria
# ====================================================================

@pytest.fixture
def rascunhos(fake_async_db, rede_de_omissao_incumbente):
    import services.email_templates_drafts as etd
    import services.workflow_phases as wp

    _cenario(fake_async_db)
    fake_async_db.emails.docs.extend([
        {"id": "d-fechado", "is_auto_draft": True, "process_id": FECHADO, "status": "draft"},
        {"id": "d-aberto", "is_auto_draft": True, "process_id": ABERTO, "status": "draft"},
        {"id": "d-domus", "is_auto_draft": True, "process_id": FECHADO_DA_DOMUS, "status": "draft"},
    ])
    with tenant_db(fake_async_db, guarda, etd, wp), \
            patch.object(etd, "_exigir_rascunho_legivel", AsyncMock()):
        yield etd, fake_async_db


class TestRascunhosDeUmProcessoFechado:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", sorted(PERFIS))
    async def test_enviar_o_rascunho_e_403_e_nada_sai(self, rascunhos, perfil):
        etd, _bd = rascunhos
        enviar = AsyncMock(return_value={"success": True})
        with patch.object(etd, "send_draft", enviar):
            with pytest.raises(HTTPException) as exc:
                await etd.run_send_auto_draft("d-fechado", PERFIS[perfil])
        assert exc.value.status_code == 403 and "fechado" in exc.value.detail
        enviar.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_enviar_o_rascunho_de_um_processo_aberto_continua_a_poder(self, rascunhos):
        etd, _bd = rascunhos
        enviar = AsyncMock(return_value={"success": True})
        with patch.object(etd, "send_draft", enviar):
            await etd.run_send_auto_draft("d-aberto", PERFIS["master"])
        enviar.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_descartar_o_rascunho_continua_a_poder(self, rascunhos):
        """É a saída de quem não quer o rascunho pendente: só o ENVIO fecha."""
        etd, _bd = rascunhos
        descartar = AsyncMock(return_value={"success": True})
        with patch.object(etd, "discard_draft", descartar):
            await etd.run_delete_auto_draft("d-fechado", PERFIS["master"])
        descartar.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_um_rascunho_de_outra_rede_nao_responde_fechado(self, rascunhos):
        etd, _bd = rascunhos
        enviar = AsyncMock(return_value={"success": True})
        with patch.object(etd, "send_draft", enviar):
            await etd.run_send_auto_draft("d-domus", PERFIS["diretor"])
        enviar.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", sorted(PERFIS))
    async def test_criar_um_rascunho_num_processo_fechado_e_403(self, rascunhos, perfil):
        etd, _bd = rascunhos
        criar = AsyncMock(return_value={"success": True})
        with patch("services.email_access.exigir_processo_legivel", AsyncMock()), \
                patch.object(etd, "create_missing_doc_draft", criar):
            with pytest.raises(HTTPException) as exc:
                await etd.run_manually_create_draft(
                    {"process_id": FECHADO, "doc_type": "irs"}, PERFIS[perfil],
                )
        assert exc.value.status_code == 403 and "fechado" in exc.value.detail
        criar.assert_not_awaited()

    def test_o_envio_chama_a_guarda_antes_de_enviar(self):
        import services.email_templates_drafts as etd

        codigo = codigo_da_funcao_sem_comentarios(etd.run_send_auto_draft)
        assert codigo.index("_exigir_processo_do_rascunho_aberto") < codigo.index("send_draft")

    def test_a_visibilidade_vem_antes_do_estado(self):
        import services.email_templates_drafts as etd

        codigo = codigo_da_funcao_sem_comentarios(etd.run_send_auto_draft)
        assert codigo.index("_exigir_rascunho_legivel") < codigo.index("_exigir_processo_do_rascunho_aberto")


# ====================================================================
# LINK-PROCESS — ligar também exige reabrir
# ====================================================================

@pytest.fixture
def ligacoes(fake_async_db, rede_de_omissao_incumbente):
    import services.client_process_ops as ops
    import services.workflow_phases as wp

    _cenario(fake_async_db)
    fake_async_db.clients.docs[0]["process_ids"] = []
    with tenant_db(fake_async_db, guarda, ops, wp):
        yield ops, fake_async_db


class TestLigarUmProcessoFechado:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("perfil", sorted(PERFIS))
    async def test_ligar_e_403_e_a_relacao_nao_nasce(self, ligacoes, perfil):
        ops, bd = ligacoes
        with pytest.raises(HTTPException) as exc:
            await ops.run_link_process_to_client("c-power", FECHADO, PERFIS[perfil])
        assert exc.value.status_code == 403 and "fechado" in exc.value.detail
        cliente = next(d for d in bd.clients.docs if d["id"] == "c-power")
        processo = next(d for d in bd.processes.docs if d["id"] == FECHADO)
        assert FECHADO not in cliente.get("process_ids", [])
        assert processo.get("client_id") != "c-power"

    @pytest.mark.asyncio
    async def test_num_processo_aberto_continua_a_poder(self, ligacoes):
        ops, bd = ligacoes
        with patch("services.history.log_history", AsyncMock()):
            resultado = await ops.run_link_process_to_client("c-power", ABERTO, PERFIS["master"])
        assert resultado["success"] is True
        assert next(d for d in bd.processes.docs if d["id"] == ABERTO)["client_id"] == "c-power"

    @pytest.mark.asyncio
    async def test_um_processo_de_outra_rede_nao_responde_fechado(self, ligacoes):
        ops, _bd = ligacoes
        with patch("services.history.log_history", AsyncMock()):
            try:
                await ops.run_link_process_to_client("c-power", FECHADO_DA_DOMUS, PERFIS["diretor"])
            except HTTPException as exc:
                assert "fechado" not in str(exc.detail)

    def test_o_servico_chama_a_guarda_antes_de_escrever(self):
        import services.client_process_ops as ops

        codigo = codigo_da_funcao_sem_comentarios(ops.run_link_process_to_client)
        assert codigo.index("exigir_processo_aberto_por_id") < codigo.index("update_one")
        # ...e antes do atalho «já está ligado», que devolvia sucesso sem perguntar.
        assert codigo.index("exigir_processo_aberto_por_id") < codigo.index("já vinculado")


# ====================================================================
# O INVENTÁRIO — um router novo com escrita em `{process_id}` não pode escapar
# ====================================================================

class TestOsRoutersDaComunicacaoELevamAGuarda:
    @pytest.mark.parametrize("modulo", [
        "routes.emails", "routes.templates", "routes.ai_analysis", "routes.document_extraction",
    ])
    def test_o_router_leva_a_dependencia(self, modulo):
        import importlib

        router = importlib.import_module(modulo).router
        assert guarda.exigir_processo_editavel in [d.dependency for d in router.dependencies]
