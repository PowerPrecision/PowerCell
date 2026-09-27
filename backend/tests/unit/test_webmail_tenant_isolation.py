"""
Ponto 8, Fase 1 — a Parede de Betão no Webmail.

O buraco: `services/email_webmail.py` não tinha UMA ocorrência de
`network_id` nem de `tenant`, e o `resolve_ucr_mailbox_filter` devolvia
`None` em três caminhos. O chamador fazia `if ucr_filter:` — logo `None`
não era "sem empresa", era **sem filtro nenhum**. Com o `can_see_all` de
admin/ceo/diretor por cima, a Caixa Geral devolvia a colecção inteira.

Estes testes existem para que `None` nunca mais seja um valor possível
neste caminho, e para que um separador de uma empresa não consiga, por
nenhuma via, devolver um email de outra.
"""
import pytest
from unittest.mock import patch

from tests.unit.helpers_fonte import codigo_sem_comentarios
from services.tenant_network import CONDICAO_IMPOSSIVEL
from services.webmail_scope import (
    EmpresaDoWebmail,
    build_company_mailbox_condition,
    empresas_do_webmail,
    assert_empresa_no_ambito,
    build_webmail_scope,
)


# ====================================================================
# build_company_mailbox_condition — puro, e nunca `None`
# ====================================================================

class TestNuncaDevolveNone:

    def test_sem_empresa_e_sem_contas_devolve_condicao_impossivel(self):
        # O coração do defeito. `None` aqui abria a colecção inteira.
        condicao = build_company_mailbox_condition("", [])
        assert condicao is not None
        assert condicao == CONDICAO_IMPOSSIVEL

    def test_a_condicao_impossivel_nao_casa_com_nada(self):
        # Contraprova: sem isto, bastava `CONDICAO_IMPOSSIVEL` ser `{}`
        # para o teste de cima passar com a porta escancarada.
        from tests.unit.conftest import FakeAsyncCollection

        condicao = build_company_mailbox_condition(None, None)
        for doc in (
            {"id": "e1", "company_id": "domus"},
            {"id": "e2"},
            {"id": "e3", "account": "geral@power.pt"},
        ):
            assert not FakeAsyncCollection._matches(doc, condicao)

    @pytest.mark.parametrize("vazio", [None, "", "   ", "default"])
    def test_os_valores_sem_empresa_nao_viram_filtro(self, vazio):
        # `company_id="default"` é "não sei qual", não é uma empresa.
        # Deixá-lo passar como valor filtrava por um id literal
        # "default" — ou, pior, era tratado como âmbito válido.
        assert build_company_mailbox_condition(vazio, []) == CONDICAO_IMPOSSIVEL

    def test_com_empresa_filtra_pelo_carimbo(self):
        assert build_company_mailbox_condition("domus", []) == {"company_id": "domus"}


class TestPilhaPorCarimbar:
    """
    O `email_service` grava `company_id` condicionalmente
    (`if company_id:`). Há emails antigos sem carimbo cuja única prova de
    pertença é o endereço da caixa que os sincronizou.
    """

    from tests.unit.conftest import FakeAsyncCollection as _F

    def _casa(self, doc, condicao):
        from tests.unit.conftest import FakeAsyncCollection

        return FakeAsyncCollection._matches(doc, condicao)

    def test_resgata_um_email_sem_carimbo_pela_conta(self):
        condicao = build_company_mailbox_condition("domus", ["geral@domus.pt"])
        assert self._casa({"id": "e1", "account": "geral@domus.pt"}, condicao)

    def test_ignora_maiusculas_no_endereco(self):
        condicao = build_company_mailbox_condition("domus", ["geral@domus.pt"])
        assert self._casa({"id": "e1", "account": "Geral@Domus.PT"}, condicao)

    def test_o_carimbo_explicito_vence_a_deducao_pelo_endereco(self):
        # O caso que obriga o ramo a exigir "sem company_id": se o mesmo
        # endereço estiver configurado em DUAS empresas, um email
        # carimbado para a Domus não pode aparecer no separador da Power.
        condicao = build_company_mailbox_condition("power", ["partilhado@x.pt"])
        assert not self._casa(
            {"id": "e1", "account": "partilhado@x.pt", "company_id": "domus"},
            condicao,
        )

    def test_mas_o_carimbo_certo_continua_a_casar(self):
        condicao = build_company_mailbox_condition("power", ["partilhado@x.pt"])
        assert self._casa(
            {"id": "e1", "account": "partilhado@x.pt", "company_id": "power"},
            condicao,
        )

    def test_nao_resgata_a_conta_de_outra_empresa(self):
        condicao = build_company_mailbox_condition("power", ["geral@power.pt"])
        assert not self._casa({"id": "e1", "account": "geral@domus.pt"}, condicao)

    def test_um_email_de_outra_empresa_nunca_entra(self):
        condicao = build_company_mailbox_condition("power", ["geral@power.pt"])
        assert not self._casa({"id": "e1", "company_id": "domus"}, condicao)


# ====================================================================
# Os separadores — e o 404
# ====================================================================

def _ucr(cid, papel, nome=None):
    return {
        "user_id": "u1", "company_id": cid, "role": papel,
        "company_name": nome, "is_active": True,
    }


@pytest.fixture
def db_com_ucrs(fake_async_db):
    fake_async_db.user_company_roles.docs.extend([
        _ucr("power", "consultor"),
        _ucr("precision", "diretor"),
    ])
    fake_async_db.companies.docs.extend([
        {"id": "power", "name": "Power Real Estate"},
        {"id": "precision", "name": "Precision Crédito"},
        {"id": "domus", "name": "Domus"},
    ])
    return fake_async_db


class TestEmpresasDoWebmail:

    @pytest.mark.asyncio
    async def test_devolve_so_as_empresas_do_utilizador(self, db_com_ucrs):
        import services.webmail_scope as mod

        with patch.object(mod, "db", db_com_ucrs):
            empresas = await empresas_do_webmail({"id": "u1"})

        assert [e.company_id for e in empresas] == ["power", "precision"]
        # A Domus existe na colecção e NÃO aparece: não há UCR para ela.
        assert "domus" not in [e.company_id for e in empresas]

    @pytest.mark.asyncio
    async def test_usa_o_nome_da_empresa_e_nunca_o_id_cru(self, db_com_ucrs):
        import services.webmail_scope as mod

        with patch.object(mod, "db", db_com_ucrs):
            empresas = await empresas_do_webmail({"id": "u1"})

        assert {e.company_name for e in empresas} == {
            "Power Real Estate", "Precision Crédito",
        }

    @pytest.mark.asyncio
    async def test_cai_no_id_quando_a_empresa_nao_tem_nome(self, fake_async_db):
        # Melhor um id do que um separador sem rótulo nenhum.
        import services.webmail_scope as mod

        fake_async_db.user_company_roles.docs.append(_ucr("orfa", "consultor"))
        with patch.object(mod, "db", fake_async_db):
            empresas = await empresas_do_webmail({"id": "u1"})
        assert empresas[0].company_name == "orfa"

    @pytest.mark.asyncio
    async def test_sem_utilizador_devolve_vazio(self, db_com_ucrs):
        import services.webmail_scope as mod

        with patch.object(mod, "db", db_com_ucrs):
            assert await empresas_do_webmail({}) == []
            assert await empresas_do_webmail(None) == []

    @pytest.mark.asyncio
    async def test_falha_de_io_falha_FECHADA(self, db_com_ucrs):
        # Um Webmail sem separadores mostra vazio. A alternativa — cair
        # num âmbito aberto — é como este defeito nasceu.
        import services.webmail_scope as mod

        class Partida:
            def __getattr__(self, _):
                raise RuntimeError("base em baixo")

        with patch.object(mod, "db", Partida()):
            assert await empresas_do_webmail({"id": "u1"}) == []


class TestAssertEmpresaNoAmbito:

    @pytest.mark.asyncio
    async def test_aceita_uma_empresa_do_utilizador(self, db_com_ucrs):
        import services.webmail_scope as mod

        with patch.object(mod, "db", db_com_ucrs):
            empresa = await assert_empresa_no_ambito({"id": "u1"}, "power")
        assert empresa.company_id == "power"

    @pytest.mark.asyncio
    async def test_recusa_uma_empresa_de_outra_rede_com_404(self, db_com_ucrs):
        # 404 e não 403: um 403 confirmaria que o id "domus" existe.
        from fastapi import HTTPException
        import services.webmail_scope as mod

        with patch.object(mod, "db", db_com_ucrs):
            with pytest.raises(HTTPException) as exc:
                await assert_empresa_no_ambito({"id": "u1"}, "domus")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_recusa_empresa_vazia_com_404(self, db_com_ucrs):
        from fastapi import HTTPException
        import services.webmail_scope as mod

        with patch.object(mod, "db", db_com_ucrs):
            for vazio in ("", None, "   "):
                with pytest.raises(HTTPException) as exc:
                    await assert_empresa_no_ambito({"id": "u1"}, vazio)
                assert exc.value.status_code == 404


# ====================================================================
# build_webmail_scope — a Caixa Geral não atravessa empresas
# ====================================================================

class TestCaixaGeralPorEmpresa:

    @pytest.mark.asyncio
    async def test_a_caixa_geral_de_um_separador_e_so_daquela_empresa(
        self, db_com_ucrs,
    ):
        # A regra de tolerância zero: o admin da Domus no separador da
        # Domus vê `geral@domus.pt` e NUNCA `geral@power.pt`.
        import services.webmail_scope as mod

        async def caixa(cid):
            return {"email_address": f"geral@{cid}.pt"}

        with patch.object(mod, "db", db_com_ucrs), \
             patch("services.email_config_resolver.load_caixa_geral_config", caixa):
            condicao = await build_webmail_scope(
                {"id": "u1"}, "precision", box="general",
            )

        from tests.unit.conftest import FakeAsyncCollection as F

        # Comportamento, não o texto da query: um `re.escape` a mais ou a
        # menos muda a string e não muda o que a caixa mostra.
        assert F._matches({"id": "e1", "account": "geral@precision.pt"}, condicao)
        assert not F._matches({"id": "e2", "account": "geral@power.pt"}, condicao)
        assert not F._matches({"id": "e3", "company_id": "power"}, condicao)

    @pytest.mark.asyncio
    async def test_a_caixa_pessoal_usa_as_contas_daquela_empresa(
        self, db_com_ucrs,
    ):
        import services.webmail_scope as mod

        db_com_ucrs.user_email_configs.docs.extend([
            {"user_id": "u1", "company_id": "power", "is_configured": True,
             "email_address": "ana@power.pt"},
            {"user_id": "u1", "company_id": "precision", "is_configured": True,
             "email_address": "ana@precision.pt"},
        ])
        with patch.object(mod, "db", db_com_ucrs):
            condicao = await build_webmail_scope({"id": "u1"}, "power", box="personal")

        from tests.unit.conftest import FakeAsyncCollection as F

        assert F._matches({"id": "e1", "account": "ana@power.pt"}, condicao)
        assert not F._matches({"id": "e2", "account": "ana@precision.pt"}, condicao)

    @pytest.mark.asyncio
    async def test_empresa_fora_do_ambito_rebenta_antes_de_haver_query(
        self, db_com_ucrs,
    ):
        from fastapi import HTTPException
        import services.webmail_scope as mod

        with patch.object(mod, "db", db_com_ucrs):
            with pytest.raises(HTTPException) as exc:
                await build_webmail_scope({"id": "u1"}, "domus", box="general")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_sem_contas_configuradas_fica_so_o_carimbo(self, db_com_ucrs):
        # Degradação: continua a haver filtro (o `company_id`), nunca a
        # ausência dele.
        import services.webmail_scope as mod

        with patch.object(mod, "db", db_com_ucrs):
            condicao = await build_webmail_scope({"id": "u1"}, "power", box="personal")
        assert condicao == {"company_id": "power"}


# ====================================================================
# Guarda sobre o código-fonte
# ====================================================================

class TestONoneNaoVolta:

    def test_o_modulo_nunca_devolve_none_no_construtor(self):
        from pathlib import Path
        import services.webmail_scope as mod

        fonte = codigo_sem_comentarios(
            Path(mod.__file__).read_text()
        )
        inicio = fonte.index("def build_company_mailbox_condition")
        corpo = fonte[inicio:fonte.index("async def build_webmail_scope")]
        assert "return None" not in corpo
        assert "CONDICAO_IMPOSSIVEL" in corpo


# ====================================================================
# O ENDPOINT, a sério — a prova que interessa
# ====================================================================

def _email(eid, **extra):
    doc = {
        "id": eid,
        "direction": "received",
        "is_archived": False,
        "status": "received",
        "subject": f"Assunto {eid}",
        "from_email": "cliente@exemplo.pt",
        "to_email": "geral@power.pt",
        "created_at": "2026-09-20T10:00:00",
        "date": "2026-09-20T10:00:00",
        # A caixa `general` exige a marca de caixa partilhada — sem ela
        # o email não é da Caixa Geral de empresa nenhuma.
        "is_general": True,
    }
    doc.update(extra)
    return doc


class TestAListagemNaoAtravessaEmpresas:
    """
    O teste que justifica a Fase 1 inteira: com o separador de uma
    empresa, a listagem não pode devolver um email de outra — nem sequer
    para um admin, nem sequer na Caixa Geral.
    """

    async def _listar(self, fake_db, *, company_id, box, papel="admin"):
        import services.email_webmail as mod

        async def papel_efectivo(_request, _user):
            return papel

        async def caixa_geral(cid):
            return {"email_address": f"geral@{cid}.pt"}

        async def sem_contas(_user_id):
            return []

        async def sem_cargos(_request, _user):
            return {papel}

        with patch.object(mod, "db", fake_db), \
             patch("services.webmail_scope.db", fake_db), \
             patch("services.auth.get_effective_role_async", papel_efectivo), \
             patch("services.email_config_resolver.load_caixa_geral_config", caixa_geral), \
             patch.object(mod, "_resolve_conversation_emails", sem_contas), \
             patch.object(mod, "_user_ucr_roles", sem_cargos):
            from services.email_webmail import run_webmail_list

            return await run_webmail_list(
                None, {"id": "u1", "email": "ana@power.pt", "role": papel},
                folder="inbox", box=box, company_id=company_id,
            )

    @pytest.fixture
    def base(self, db_com_ucrs):
        db_com_ucrs.emails.docs.extend([
            _email("meu", company_id="power"),
            _email("do-lado", company_id="domus"),
            _email("sem-carimbo-meu", account="geral@power.pt"),
            _email("sem-carimbo-do-lado", account="geral@domus.pt"),
        ])
        return db_com_ucrs

    @pytest.mark.asyncio
    async def test_a_caixa_geral_do_separador_so_traz_a_propria_empresa(self, base):
        resultado = await self._listar(base, company_id="power", box="general")
        ids = {e["id"] for e in resultado.get("emails", [])}

        assert "meu" in ids
        assert "sem-carimbo-meu" in ids
        # Tolerância zero: nem o carimbado nem o por carimbar da Domus.
        assert "do-lado" not in ids
        assert "sem-carimbo-do-lado" not in ids

    @pytest.mark.asyncio
    async def test_o_separador_da_outra_empresa_devolve_404(self, base):
        # `domus` não está nos UCRs deste utilizador.
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await self._listar(base, company_id="domus", box="general")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_um_separador_sem_contas_nem_carimbos_nao_abre_a_caixa(
        self, db_com_ucrs,
    ):
        # O cenário exacto do defeito: âmbito vazio. Antes devolvia
        # `None` → `query = {}` → a colecção inteira.
        db_com_ucrs.emails.docs.extend([
            _email("do-lado", company_id="domus"),
            _email("orfao"),
        ])

        async def sem_caixa(_cid):
            return None

        import services.email_webmail as mod

        async def papel_efectivo(_r, _u):
            return "admin"

        async def sem_contas(_uid):
            return []

        async def cargos(_r, _u):
            return {"admin"}

        with patch.object(mod, "db", db_com_ucrs), \
             patch("services.webmail_scope.db", db_com_ucrs), \
             patch("services.auth.get_effective_role_async", papel_efectivo), \
             patch("services.email_config_resolver.load_caixa_geral_config", sem_caixa), \
             patch.object(mod, "_resolve_conversation_emails", sem_contas), \
             patch.object(mod, "_user_ucr_roles", cargos):
            from services.email_webmail import run_webmail_list

            resultado = await run_webmail_list(
                None, {"id": "u1", "email": "ana@power.pt", "role": "admin"},
                folder="inbox", box="general", company_id="power",
            )

        assert [e["id"] for e in resultado.get("emails", [])] == []
