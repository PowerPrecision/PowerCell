"""As contas configuradas do Webmail são as do utilizador, não as do servidor.

O QUE ESTAVA MAL (P0, Set 2026)
===============================
    async def run_get_configured_accounts(current_user: dict):
        accounts = get_email_accounts()   # ← lê variáveis de ambiente
        return [...]                       # ← current_user NUNCA é usado

Recebia o utilizador e ignorava-o. O `get_email_accounts()` devolve as
contas `power` e `precision` a partir de variáveis de ambiente, sem
noção nenhuma de empresa — logo um utilizador da **Domus**, que é uma
ilha, via `geral@powerealestate.pt` no seu Webmail.

A LIÇÃO, OUTRA VEZ E CONTRA MIM
===============================
Quando avaliei a D-8 (`db.emails` sem carimbo de rede) disse que não era
uma fuga activa, apoiado no `test_webmail_tenant_isolation.py`. Essa
parte continua certa: o construtor do FILTRO DE LISTAGEM é escrupuloso.
Mas eu verifiquei o filtro e não o **inventário das superfícies** — a
listagem de CONTAS é outra superfície, e não tinha filtro nenhum. É
exactamente a lição do Lote 5, cometida enquanto a citava.

A REGRA DERIVA DO QUE JÁ EXISTE
===============================
O âmbito sai de `webmail_scope.empresas_do_webmail`, a MESMA função que
decide os separadores do Webmail. Uma segunda regra aqui divergiria da
dos separadores, e a que divergisse não daria erro — mostraria uma conta
a mais. A Caixa Geral só entra quando o utilizador tem papel de gestão
NESSA empresa (`tem_caixa_geral`), que é a regra que já existe.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from services import email_webmail as modulo
from services.webmail_scope import EmpresaDoWebmail

POWER = EmpresaDoWebmail(
    company_id="cid-power", company_name="Power", papeis=frozenset({"diretor"}),
)
DOMUS = EmpresaDoWebmail(
    company_id="cid-domus", company_name="Domus", papeis=frozenset({"consultor"}),
)


class _Conta:
    """Duplo mínimo de `EmailAccount` — só o que o handler lê."""

    def __init__(self, name, email):
        self.name = name
        self.email = email
        self.imap_server = f"imap.{name}.pt"
        self.smtp_server = f"smtp.{name}.pt"


CONTAS_DO_SERVIDOR = [
    _Conta("power", "geral@powerealestate.pt"),
    _Conta("precision", "geral@precisioncredito.pt"),
    _Conta("domus", "geral@domus.pt"),
]


async def _listar(empresas, enderecos):
    """Corre o handler real com o âmbito falseado ao nível do scope."""
    with patch.object(modulo, "get_email_accounts", lambda: list(CONTAS_DO_SERVIDOR)), \
            patch.object(
                modulo, "empresas_do_webmail", AsyncMock(return_value=empresas)
            ), \
            patch.object(
                modulo, "contas_pessoais_da_empresa",
                AsyncMock(side_effect=lambda uid, cid: set(enderecos.get(cid, set()))),
            ), \
            patch.object(
                modulo, "conta_da_caixa_geral",
                AsyncMock(side_effect=lambda cid: set(enderecos.get(f"geral:{cid}", set()))),
            ):
        resultado = await modulo.run_get_configured_accounts(
            {"id": "u-1", "email": "alguem@x.pt"}
        )
    return {c["email"] for c in resultado}


class TestADomusNaoVeAsContasDaPower:
    async def test_o_caso_relatado_em_producao(self):
        emails = await _listar(
            [DOMUS], {"cid-domus": {"consultor@domus.pt"}},
        )
        assert "geral@powerealestate.pt" not in emails

    async def test_CONTRAPROVA_continua_a_ver_a_dela(self):
        """Sem isto, devolver sempre `[]` passava o teste de cima."""
        emails = await _listar(
            [DOMUS], {"cid-domus": {"geral@domus.pt"}},
        )
        assert emails == {"geral@domus.pt"}

    async def test_quem_tem_as_DUAS_empresas_ve_as_duas(self):
        """Power e Precision partilham rede e colaboram — não se cortam."""
        emails = await _listar(
            [POWER, DOMUS],
            {
                "geral:cid-power": {"geral@powerealestate.pt"},
                "cid-domus": {"geral@domus.pt"},
            },
        )
        assert emails == {"geral@powerealestate.pt", "geral@domus.pt"}


class TestACaixaGeralSegueARegraQueJaExiste:
    async def test_sem_papel_de_gestao_a_caixa_geral_NAO_entra(self):
        """`tem_caixa_geral` é `False` para um consultor.

        A regra não é nova: é a do `webmail_scope`. Reescrevê-la aqui
        faria duas regras a decidir o mesmo, e a que divergisse mostrava
        uma conta a mais.
        """
        emails = await _listar(
            [DOMUS], {"geral:cid-domus": {"geral@domus.pt"}},
        )
        assert emails == set()

    async def test_com_papel_de_gestao_entra(self):
        emails = await _listar(
            [POWER], {"geral:cid-power": {"geral@powerealestate.pt"}},
        )
        assert emails == {"geral@powerealestate.pt"}


class TestFalhaFechada:
    async def test_sem_empresas_nao_devolve_nada(self):
        """Um Webmail sem separadores mostra vazio, não mostra tudo.

        `empresas_do_webmail` já devolve `[]` quando o I/O falha; o que
        este teste garante é que o `[]` não é lido como "sem restrição".
        """
        assert await _listar([], {}) == set()

    async def test_o_endereco_compara_se_sem_maiusculas(self):
        emails = await _listar(
            [DOMUS], {"cid-domus": {"GERAL@DOMUS.PT"}},
        )
        assert emails == {"geral@domus.pt"}


class TestGuardaDeFonte:
    def test_o_handler_usa_mesmo_o_utilizador(self):
        """O defeito era um parâmetro recebido e ignorado — a forma de
        erro que nenhum teste de conteúdo apanha."""
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(modulo.run_get_configured_accounts)
        assert "current_user" in fonte
        assert "_enderecos_no_ambito_do_utilizador(current_user)" in fonte

    def test_o_ambito_deriva_do_webmail_scope(self):
        """E não de uma segunda regra escrita aqui.

        A cadeia é verificada nos DOIS elos — o handler chama o helper, o
        helper chama o `webmail_scope` — porque uma guarda sobre um elo
        só é satisfeita apagando o outro.
        """
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(
            modulo._enderecos_no_ambito_do_utilizador
        )
        assert "empresas_do_webmail(current_user)" in fonte
        assert "tem_caixa_geral" in fonte
