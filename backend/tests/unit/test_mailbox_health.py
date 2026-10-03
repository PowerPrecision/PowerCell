"""A saúde da caixa de correio, persistida (Lote 7, ponto 4).

A auditoria perguntava: «se a password do IMAP expirar, o sistema lida com o
erro de forma graciosa (avisando na UI) ou rebenta em silêncio?»

A resposta era **as duas coisas, em caminhos diferentes**: a sincronização
MANUAL falha o job e o ecrã mostra um toast; a AUTOMÁTICA — de 10 em 10
minutos, a que mantém a caixa fresca — morria num `logger.warning`. A caixa
deixava de receber email, o ecrã mostrava a lista antiga sem um único aviso, e
o ciclo voltava a falhar para sempre. Não havia **nada persistido**.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services.mailbox_health import (
    CLASSE_AUTENTICACAO,
    CLASSE_DESCONHECIDA,
    CLASSE_LIMITE,
    CLASSE_REDE,
    classificar_falha,
    construir_estado_de_falha,
    construir_estado_de_sucesso,
    exige_accao_do_utilizador,
    registar_falha,
    registar_sucesso,
    resumo_para_o_ecra,
)


class TestAClassificacao:
    def test_a_mensagem_real_do_IMAP_e_autenticacao(self):
        """A mensagem que o `_fetch_all_from_folder_sync` produz."""
        assert classificar_falha(
            "Autenticação IMAP falhou para a@b.pt — verifique email/password "
            "nas Configurações do Perfil"
        ) == CLASSE_AUTENTICACAO

    @pytest.mark.parametrize("mensagem", [
        "AUTHENTICATIONFAILED",
        "535 Incorrect authentication data",
        "LOGIN failed",
        "invalid credentials",
    ])
    def test_as_variantes_do_servidor_tambem(self, mensagem):
        assert classificar_falha(mensagem) == CLASSE_AUTENTICACAO

    def test_o_LIMITE_vence_a_autenticacao_e_isso_e_deliberado(self):
        """«too many login attempts» tem as duas palavras.

        Tratá-lo como password errada mandava o utilizador mudar uma password
        que está certa — e a conta resolve-se sozinha. A ordem das
        verificações é a correcção.
        """
        assert classificar_falha(
            "Too many login attempts, temporarily refused"
        ) == CLASSE_LIMITE

    @pytest.mark.parametrize("mensagem", [
        "Ligação IMAP falhou para a@b.pt — servidor inatingível (mail.x:993)",
        "connection refused",
        "timed out",
        "getaddrinfo failed",
    ])
    def test_a_rede_e_rede(self, mensagem):
        assert classificar_falha(mensagem) == CLASSE_REDE

    @pytest.mark.parametrize("mensagem", ["", None, "   ", "coisa esquisita"])
    def test_o_que_nao_se_reconhece_e_desconhecido_e_nao_autenticacao(self, mensagem):
        """Fail-SOFT na classificação, de propósito.

        Classificar o desconhecido como autenticação mandaria pessoas mudar
        passwords que estão certas — e um aviso falso ensina a ignorar os
        verdadeiros.
        """
        assert classificar_falha(mensagem) == CLASSE_DESCONHECIDA

    def test_so_a_autenticacao_exige_accao_do_utilizador(self):
        assert exige_accao_do_utilizador(CLASSE_AUTENTICACAO) is True
        for outra in (CLASSE_LIMITE, CLASSE_REDE, CLASSE_DESCONHECIDA):
            assert exige_accao_do_utilizador(outra) is False, (
                "avisar de tudo com a mesma força ensina a ignorar o aviso "
                "(é o `desactivado ≠ em baixo` do painel de sinais vitais)"
            )


class TestOEstadoGravado:
    def test_a_falha_conta_as_consecutivas_e_PRESERVA_o_desde(self):
        """`desde` responde «há quanto tempo está parado».

        Reescrevê-lo a cada ciclo fazia um problema de três dias parecer
        acabado de acontecer, e é precisamente esse número que distingue um
        soluço de uma caixa parada.
        """
        estado = construir_estado_de_falha(
            "AUTHENTICATIONFAILED",
            falhas_anteriores=7,
            desde="2026-09-30T10:00:00+00:00",
        )
        assert estado["sync_failures"] == 8
        assert estado["sync_failing_since"] == "2026-09-30T10:00:00+00:00"
        assert estado["sync_requires_action"] is True

    def test_a_primeira_falha_inaugura_o_desde(self):
        estado = construir_estado_de_falha("AUTHENTICATIONFAILED")
        assert estado["sync_failures"] == 1
        assert estado["sync_failing_since"]

    def test_a_mensagem_tecnica_e_truncada(self):
        estado = construir_estado_de_falha("x" * 5000)
        assert len(estado["sync_error_message"]) <= 500

    def test_o_sucesso_LIMPA_o_erro(self):
        """Sem isto, o aviso ficava no ecrã depois de a password ser corrigida.

        E um aviso que não desaparece é indistinguível de um aviso falso.
        """
        estado = construir_estado_de_sucesso()
        assert estado["sync_status"] == "ok"
        assert estado["sync_error_class"] is None
        assert estado["sync_error_user_message"] is None
        assert estado["sync_requires_action"] is False
        assert estado["sync_failures"] == 0
        assert estado["sync_failing_since"] is None
        assert estado["last_sync_ok_at"]

    def test_a_mensagem_do_ecra_diz_O_QUE_FAZER(self):
        """Um «IMAP error 535» não diz a ninguém que tem de mudar a password."""
        estado = construir_estado_de_falha("535 Incorrect authentication data")
        texto = estado["sync_error_user_message"].lower()
        assert "password" in texto
        assert "perfil" in texto


class TestAPersistencia:
    @pytest.mark.asyncio
    async def test_a_falha_e_gravada_na_config_certa(self, fake_async_db):
        from services import mailbox_health

        await fake_async_db.user_email_configs.insert_one({
            "id": "cfg-1", "user_id": "u1", "company_id": "emp-1",
            "email_address": "a@b.pt", "is_configured": True,
        })
        with patch.object(mailbox_health, "db", fake_async_db):
            await registar_falha("u1", "AUTHENTICATIONFAILED", account_id="cfg-1")

        cfg = await fake_async_db.user_email_configs.find_one({"id": "cfg-1"})
        assert cfg["sync_status"] == "failed"
        assert cfg["sync_error_class"] == CLASSE_AUTENTICACAO
        assert cfg["sync_requires_action"] is True

    @pytest.mark.asyncio
    async def test_falhas_consecutivas_acumulam_e_o_desde_nao_salta(
        self, fake_async_db,
    ):
        from services import mailbox_health

        await fake_async_db.user_email_configs.insert_one({
            "id": "cfg-1", "user_id": "u1", "email_address": "a@b.pt",
        })
        with patch.object(mailbox_health, "db", fake_async_db):
            await registar_falha("u1", "AUTHENTICATIONFAILED", account_id="cfg-1")
            primeiro = (await fake_async_db.user_email_configs.find_one(
                {"id": "cfg-1"}))["sync_failing_since"]
            await registar_falha("u1", "AUTHENTICATIONFAILED", account_id="cfg-1")

        cfg = await fake_async_db.user_email_configs.find_one({"id": "cfg-1"})
        assert cfg["sync_failures"] == 2
        assert cfg["sync_failing_since"] == primeiro

    @pytest.mark.asyncio
    async def test_o_sucesso_limpa_o_que_a_falha_gravou(self, fake_async_db):
        from services import mailbox_health

        await fake_async_db.user_email_configs.insert_one({
            "id": "cfg-1", "user_id": "u1", "email_address": "a@b.pt",
        })
        with patch.object(mailbox_health, "db", fake_async_db):
            await registar_falha("u1", "AUTHENTICATIONFAILED", account_id="cfg-1")
            await registar_sucesso("u1", account_id="cfg-1")

        cfg = await fake_async_db.user_email_configs.find_one({"id": "cfg-1"})
        assert cfg["sync_status"] == "ok"
        assert cfg["sync_requires_action"] is False
        assert cfg["sync_failures"] == 0

    @pytest.mark.asyncio
    async def test_prefere_o_account_id_a_marcar_a_conta_errada(
        self, fake_async_db,
    ):
        """Um utilizador pode ter várias contas na mesma empresa.

        Marcar a errada punha o aviso na caixa que está a funcionar — pior do
        que não avisar, porque manda procurar no sítio errado.
        """
        from services import mailbox_health

        for cid in ("cfg-1", "cfg-2"):
            await fake_async_db.user_email_configs.insert_one({
                "id": cid, "user_id": "u1", "company_id": "emp-1",
                "email_address": f"{cid}@b.pt",
            })
        with patch.object(mailbox_health, "db", fake_async_db):
            await registar_falha(
                "u1", "AUTHENTICATIONFAILED",
                company_id="emp-1", account_id="cfg-2",
            )

        assert (await fake_async_db.user_email_configs.find_one(
            {"id": "cfg-1"})).get("sync_status") is None
        assert (await fake_async_db.user_email_configs.find_one(
            {"id": "cfg-2"})).get("sync_status") == "failed"

    @pytest.mark.asyncio
    async def test_gravar_o_estado_NUNCA_propaga(self, fake_async_db):
        """Observa, não intercepta — a regra do `job_heartbeat`.

        Uma excepção aqui subia para um ciclo de fundo que estava a correr
        bem, e transformava um aviso num ciclo falhado.
        """
        from services import mailbox_health

        class _Explode:
            def __getitem__(self, _nome):
                raise RuntimeError("Mongo em baixo")

        with patch.object(mailbox_health, "db", _Explode()):
            await registar_falha("u1", "AUTHENTICATIONFAILED")
            await registar_sucesso("u1")

    @pytest.mark.asyncio
    async def test_sem_utilizador_nao_marca_nada(self, fake_async_db):
        """Senão um `user_id` vazio marcava a primeira config da colecção."""
        from services import mailbox_health

        await fake_async_db.user_email_configs.insert_one({
            "id": "cfg-1", "user_id": "u1", "email_address": "a@b.pt",
        })
        with patch.object(mailbox_health, "db", fake_async_db):
            await registar_falha("", "AUTHENTICATIONFAILED")
            await registar_falha(None, "AUTHENTICATIONFAILED")

        cfg = await fake_async_db.user_email_configs.find_one({"id": "cfg-1"})
        assert cfg.get("sync_status") is None


class TestOResumoParaOEcra:
    def test_nao_expoe_a_mensagem_TECNICA_do_servidor(self):
        """Pode trazer o host e o código do erro.

        O ecrã recebe a mensagem que diz o que fazer; a técnica fica na
        config, para quem diagnostica.
        """
        estado = construir_estado_de_falha(
            "IMAP mail.interno.exemplo.pt:993 535 auth data"
        )
        resumo = resumo_para_o_ecra(estado)
        assert "mail.interno.exemplo.pt" not in str(resumo)
        assert resumo["sync_message"]
        assert resumo["sync_requires_action"] is True

    def test_uma_config_sem_estado_nao_mente_que_esta_bem(self):
        """«desconhecido» e não «ok»: nunca sincronizou ainda."""
        resumo = resumo_para_o_ecra({})
        assert resumo["sync_status"] == "desconhecido"
        assert resumo["sync_requires_action"] is False

    def test_resiste_a_None(self):
        assert resumo_para_o_ecra(None)["sync_status"] == "desconhecido"


class TestALigacaoNoCodigo:
    """Guardas: o estado tem de continuar a ser gravado nos DOIS caminhos."""

    def _fonte(self, nome):
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        caminho = Path(__file__).resolve().parents[2] / "services" / nome
        return codigo_sem_comentarios(caminho.read_text(encoding="utf-8"))

    def test_a_sincronizacao_pessoal_grava_falha_E_sucesso(self):
        fonte = self._fonte("email_service.py")
        assert "registar_falha(" in fonte, (
            "a sincronização automática voltou a morrer num logger.warning"
        )
        assert "registar_sucesso(" in fonte, (
            "sem limpar o erro, o aviso fica no ecrã para sempre"
        )

    def test_a_saude_vai_no_contrato_da_UI(self):
        fonte = self._fonte("user_email_config_service.py")
        assert "_saude_da_caixa(" in fonte

    def test_o_job_de_sync_nao_usa_create_task_cru(self):
        """Uma task crua pode ser recolhida pelo GC e o job fica em `pending`.

        O ecrã desiste com "Sincronização a demorar demasiado" — um erro que
        aponta para o servidor de email quando a causa é o garbage collector.
        """
        fonte = self._fonte("email_webmail.py")
        assert "asyncio.create_task(" not in fonte
        assert "spawn_background_task(" in fonte
