"""Quem lê um email, quem abre os emails de um processo (Bloco 2, Lote 12).

`TestAExploracao` é o ataque, escrito para morder primeiro: antes de
`services/email_access.py` as cinco rotas legadas de anexos não tinham
guarda nenhuma, e o diretor de uma ilha passava pelo bypass de cargo sem
fronteira de rede.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import email_access as acesso
from services import webmail_scope
from tests.unit.helpers_tenant import (  # noqa: F401
    ANA, BRUNO, CARLA, REDE_DOMUS, REDE_INCUMBENTE, rede_de_omissao_incumbente, semear, tenant_db,
)

PARCEIRO = {"id": "u-parc", "email": "p@x.pt", "role": "parceiro"}
ADMIN = {"id": "u-adm", "email": "a@x.pt", "role": "admin"}
MASTER = {"id": "u-mst", "email": "m@x.pt", "role": "master"}
CEO = {"id": "u-ceo", "email": "c@x.pt", "role": "ceo"}
# Apoio administrativo da Power — para a Caixa Geral.
ADMINISTRATIVA = {"id": "u-adv", "email": "adv@power.pt", "role": "administrativo"}

E_POWER = {"id": "e-power", "company_id": "cmp-power", "from_email": "cli@x.pt",
           "to_emails": ["outro@power.pt"], "synced_for_user": "u-outro"}
E_POWER_GERAL = {"id": "e-pg", "company_id": "cmp-power", "shared_role": "geral",
                 "from_email": "cli@x.pt", "to_emails": ["geral@power.pt"]}
E_DOMUS = {"id": "e-domus", "company_id": "cmp-domus", "from_email": "cli@y.pt",
           "to_emails": ["x@domus.pt"], "synced_for_user": "u-outro"}
E_DOMUS_GERAL = {"id": "e-dg", "company_id": "cmp-domus", "shared_role": "geral",
                 "from_email": "cli@y.pt", "to_emails": ["geral@domus.pt"]}
E_LEGADO = {"id": "e-leg", "from_email": "cli@z.pt", "to_emails": ["x@y.pt"],
            "synced_for_user": "u-outro"}


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.append(
        {"user_id": "u-adv", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "administrativo", "is_default": True}
    )
    fake_async_db.user_company_roles.docs.append(
        {"user_id": "u-parc", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "parceiro", "is_default": True}
    )
    # Um processo INDEXADO da Power, para os emails ligados a processo.
    fake_async_db.processes.docs.append(
        {"id": "p-ix", "client_name": "Ana", "status": "novo", "is_indexed": True,
         "company_id": "cmp-power", "network_id": REDE_INCUMBENTE}
    )
    fake_async_db.processes.docs.append(
        {"id": "p-ix-domus", "client_name": "Rui", "status": "novo", "is_indexed": True,
         "company_id": "cmp-domus", "network_id": REDE_DOMUS}
    )
    for e in (E_POWER, E_POWER_GERAL, E_DOMUS, E_DOMUS_GERAL, E_LEGADO):
        fake_async_db.emails.docs.append(dict(e))
    return fake_async_db


async def _pode(mundo, email, user, enderecos=()):
    with tenant_db(mundo, acesso, webmail_scope), patch(
        "services.user_email_config_service.get_user_mailbox_addresses",
        AsyncMock(return_value=list(enderecos)),
    ):
        return await acesso.pode_ler_email(dict(email), user)


@pytest.mark.asyncio
class TestAExploracao:
    async def test_o_diretor_de_uma_ilha_nao_le_o_email_de_outra_rede(self, mundo):
        """O bypass de cargo era sem fronteira de rede (D-8)."""
        assert await _pode(mundo, E_POWER, BRUNO) is False

    async def test_a_gestao_de_uma_ilha_nao_abre_a_caixa_geral_alheia(self, mundo):
        assert await _pode(mundo, E_POWER_GERAL, BRUNO) is False

    async def test_a_caixa_geral_de_outra_empresa_nao_abre_com_cargo_noutra(self, mundo):
        """Ana é diretora da Power; a Caixa Geral da Domus não é dela."""
        assert await _pode(mundo, E_DOMUS_GERAL, ANA) is False

    async def test_um_parceiro_nao_entra_por_um_email_ligado_a_processo(self, mundo):
        email = {**E_POWER, "process_id": "p-ix"}
        assert await _pode(mundo, email, PARCEIRO) is False

    async def test_um_consultor_nao_le_o_email_de_um_colega_sem_processo(self, mundo):
        assert await _pode(mundo, E_POWER, CARLA) is False

    async def test_o_legado_por_carimbar_nao_e_da_ilha(self, mundo):
        assert await _pode(mundo, E_LEGADO, BRUNO) is False

    async def test_inexistente_e_alheio_respondem_ao_mesmo_404(self, mundo):
        with tenant_db(mundo, acesso, webmail_scope), patch.object(acesso, "db", mundo), patch(
            "services.user_email_config_service.get_user_mailbox_addresses",
            AsyncMock(return_value=[]),
        ):
            with pytest.raises(HTTPException) as alheio:
                await acesso.carregar_email_legivel("e-power", BRUNO)
            with pytest.raises(HTTPException) as inexistente:
                await acesso.carregar_email_legivel("nao-existe", BRUNO)
        assert alheio.value.status_code == inexistente.value.status_code == 404
        assert alheio.value.detail == inexistente.value.detail


@pytest.mark.asyncio
class TestAsRegras:
    async def test_so_o_master_atravessa_redes(self, mundo):
        """Adenda de RBAC: o Master é o único perfil global."""
        assert await _pode(mundo, E_DOMUS, MASTER) is True
        assert await _pode(mundo, E_POWER_GERAL, MASTER) is True

    async def test_admin_e_ceo_sao_locais_e_nao_atravessam_redes(self, mundo):
        assert await _pode(mundo, E_DOMUS, ADMIN) is False
        assert await _pode(mundo, E_DOMUS, CEO) is False

    async def test_o_diretor_le_dentro_da_sua_rede(self, mundo):
        assert await _pode(mundo, E_POWER, ANA) is True

    async def test_o_diretor_le_a_caixa_geral_da_sua_empresa(self, mundo):
        assert await _pode(mundo, E_POWER_GERAL, ANA) is True

    async def test_o_administrativo_le_a_caixa_geral_da_sua_empresa(self, mundo):
        """O pedido do Bloco 2: Diretor, CEO e Administrativa têm a Caixa Geral."""
        assert await _pode(mundo, E_POWER_GERAL, ADMINISTRATIVA) is True

    async def test_o_administrativo_nao_le_o_email_pessoal_de_um_colega(self, mundo):
        assert await _pode(mundo, E_POWER, ADMINISTRATIVA) is False

    async def test_o_administrativo_nao_le_a_caixa_geral_de_outra_empresa(self, mundo):
        assert await _pode(mundo, E_DOMUS_GERAL, ADMINISTRATIVA) is False

    async def test_o_consultor_nao_tem_a_caixa_geral(self, mundo):
        assert await _pode(mundo, E_POWER_GERAL, CARLA) is False

    async def test_o_que_e_seu_le_se(self, mundo):
        assert await _pode(mundo, {**E_POWER, "synced_for_user": "u-carla"}, CARLA) is True
        assert await _pode(mundo, {**E_POWER, "created_by": "u-carla"}, CARLA) is True
        assert await _pode(mundo, {**E_POWER, "synced_for_user": "carla@precision.pt"}, CARLA) is True

    async def test_a_conversa_pelos_enderecos_CONFIGURADOS(self, mundo):
        email = {**E_POWER, "to_emails": ["geral@precision.pt"]}
        assert await _pode(mundo, email, CARLA) is False
        assert await _pode(mundo, email, CARLA, enderecos=["geral@precision.pt"]) is True

    async def test_a_caixa_partilhada_do_cargo(self, mundo):
        indexacao = {"id": "u-ix", "email": "i@x.pt", "role": "indexacao"}
        email = {**E_POWER, "shared_role": "indexacao"}
        assert await _pode(mundo, email, indexacao) is True

    async def test_o_perfil_EFECTIVO_manda(self, mundo):
        """Base admin, a trabalhar como consultor, não atravessa redes."""
        como_consultor = {**ADMIN, "effective_role": "consultor"}
        assert await _pode(mundo, E_DOMUS, como_consultor) is False

    async def test_email_ligado_a_processo_visivel_le_se_na_equipa(self, mundo):
        """O separador «Emails» do processo: a conversa de um colega."""
        email = {**E_POWER, "process_id": "p-ix"}
        assert await _pode(mundo, email, ADMINISTRATIVA) is True

    async def test_email_ligado_a_processo_de_outra_rede_nao(self, mundo):
        email = {**E_DOMUS, "process_id": "p-ix-domus"}
        assert await _pode(mundo, email, ADMINISTRATIVA) is False

    async def test_o_legado_por_carimbar_pertence_a_rede_de_omissao(self, mundo):
        assert await _pode(mundo, E_LEGADO, ANA) is True

    async def test_sem_utilizador_ou_sem_email_recusa(self, mundo):
        assert await acesso.pode_ler_email(None, ANA) is False
        assert await acesso.pode_ler_email(dict(E_POWER), {}) is False


@pytest.mark.asyncio
class TestOsEmailsDeUmProcesso:
    async def test_um_processo_de_outra_rede_recusa(self, mundo):
        with tenant_db(mundo, acesso), patch(
            "services.document_visibility.db", mundo
        ):
            with pytest.raises(HTTPException) as exc:
                await acesso.exigir_processo_legivel("p-ix-domus", ANA)
        assert exc.value.status_code == 403

    async def test_um_processo_inexistente_e_404(self, mundo):
        with tenant_db(mundo, acesso), patch("services.document_visibility.db", mundo):
            with pytest.raises(HTTPException) as exc:
                await acesso.exigir_processo_legivel("nao-existe", ANA)
        assert exc.value.status_code == 404

    async def test_um_processo_da_propria_rede_devolve_o_processo(self, mundo):
        with tenant_db(mundo, acesso), patch("services.document_visibility.db", mundo):
            processo = await acesso.exigir_processo_legivel("p-ix", ANA)
        assert processo["id"] == "p-ix"


class TestAsRotasLigamAGuarda:
    """Inventário por AST de `routes/emails.py`, com contraprova."""

    CAMINHO = Path(__file__).resolve().parents[2] / "routes" / "emails.py"
    #: Rotas por email que se guardam DENTRO do serviço (o `run_get_email`
    #: precisa do `request` para o papel activo) — escritas, não esquecidas.
    GUARDADAS_NO_SERVICO = {"get_email"}

    def _rotas(self):
        arvore = ast.parse(self.CAMINHO.read_text(encoding="utf-8"))
        for no in arvore.body:
            if isinstance(no, ast.AsyncFunctionDef):
                yield no, [a.arg for a in no.args.args], ast.unparse(no)

    def test_toda_a_rota_por_processo_exige_o_processo_legivel(self):
        sem_guarda = [
            nome.name for nome, args, fonte in self._rotas()
            if "process_id" in args
            and "exigir_processo_legivel(process_id, current_user)" not in fonte
        ]
        assert sem_guarda == []

    def test_toda_a_rota_por_email_exige_o_email_legivel(self):
        sem_guarda = [
            no.name for no, args, fonte in self._rotas()
            if "email_id" in args
            and no.name not in self.GUARDADAS_NO_SERVICO
            and "carregar_email_legivel(email_id, current_user)" not in fonte
        ]
        assert sem_guarda == []

    def test_o_leitor_encontrou_mesmo_as_rotas(self):
        """Contraprova: um leitor cego também 'passaria' as duas asserções."""
        todas = list(self._rotas())
        por_processo = [n.name for n, a, _ in todas if "process_id" in a]
        por_email = [n.name for n, a, _ in todas if "email_id" in a]
        assert len(por_processo) >= 10 and len(por_email) >= 10
        assert "get_process_emails" in por_processo and "download_attachment" in por_email

    def test_o_servico_do_get_email_usa_a_guarda_central(self):
        from services import email_process_crud
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(email_process_crud.run_get_email)
        assert "exigir_leitura_do_email(" in fonte

    def test_o_download_do_webmail_usa_a_guarda_central(self):
        from services import email_mailbox_ops
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(email_mailbox_ops._assert_email_readable)
        assert "exigir_leitura_do_email(" in fonte


class TestACaixaGeralTemUmSoConjunto:
    def test_o_administrativo_tem_direito_a_caixa_geral(self):
        from services.email_config_resolver import pode_abrir_caixa_geral

        assert pode_abrir_caixa_geral("administrativo")
        for papel in ("diretor", "ceo", "admin"):
            assert pode_abrir_caixa_geral(papel)

    @pytest.mark.parametrize("papel", ["consultor", "intermediario", "indexacao", "parceiro", "cliente", "", None])
    def test_os_outros_nao(self, papel):
        from services.email_config_resolver import pode_abrir_caixa_geral

        assert not pode_abrir_caixa_geral(papel)

    def test_qualquer_cargo_UCR_valido_abre(self):
        """Webmail unificado: o perfil activo é consultor, mas é diretor noutra empresa."""
        from services.email_config_resolver import pode_abrir_caixa_geral

        assert pode_abrir_caixa_geral("consultor", {"consultor", "diretor"})
        assert not pode_abrir_caixa_geral("consultor", {"consultor"})

    def test_os_tres_nomes_sao_o_mesmo_conjunto(self):
        from services import email_config_resolver as r

        assert r.CAIXA_GERAL_INJECT_ROLES is r.CAIXA_GERAL_ROLES
        assert r.CAIXA_GERAL_ACCESS_ROLES is r.CAIXA_GERAL_ROLES

    def test_o_webmail_nao_tem_literais_do_conjunto(self):
        """Eram dois `{"admin","ceo","diretor"}` e uma lista de exclusão."""
        from services import email_webmail
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(Path(email_webmail.__file__).read_text(encoding="utf-8"))
        assert "{'admin', 'ceo', 'diretor'}" not in fonte
        assert "pode_abrir_caixa_geral(" in fonte
