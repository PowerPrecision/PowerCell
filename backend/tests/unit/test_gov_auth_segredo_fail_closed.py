"""D-3 — o `gov_token` não tem segredo por omissão, e não há recurso sem assinatura.

O QUE ESTAVA MAL
================
`gov_auth_api_helpers` fazia
`os.environ.get("GOV_AUTH_JWT_SECRET", "dev-secret-change-in-prod")` e a
variável **não estava declarada no `render.yaml`**: produção assinava
com um literal público. O `gov_token` declara `verified_by_gov: True` e
pré-preenche o formulário público, logo o segredo conhecido significava
identidades "verificadas pelo Estado" forjáveis.

O router está montado (`server.py`: `app.include_router(gov_auth_router,
prefix="/api")`), pelo que os três endpoints estavam vivos — a entrada
do registo de dívida dizia "não está em uso real" e isso era a parte
errada do diagnóstico.

O SEGUNDO DEFEITO, NO MESMO FICHEIRO
====================================
Produtor e verificador tinham ramos simétricos `except ImportError` que
criavam e ACEITAVAM um token terminado no literal `"mock-signature"`,
sem assinatura nenhuma. Nunca correu (o `PyJWT` está fixado), mas saiu
dos dois lados: manter só metade deixava um consumidor permissivo sem
produtor, que é a metade perigosa.
"""
from __future__ import annotations

import pytest

from services.gov_auth_api_helpers import (
    AMBIENTES_DE_PRODUCAO,
    _resolver_segredo,
)


class TestEmProducaoOSegredoEObrigatorio:
    @pytest.mark.parametrize("ambiente", list(AMBIENTES_DE_PRODUCAO))
    def test_sem_variavel_mata_o_arranque(self, ambiente):
        """`sys.exit(1)`, o padrão que o `config.py` já usa.

        Um valor por omissão transforma "esqueceram-se de configurar" —
        que daria erro e seria corrigido em cinco minutos — em "está a
        funcionar, e mal", que dura meses.
        """
        with pytest.raises(SystemExit) as saida:
            _resolver_segredo(ambiente, None)
        assert saida.value.code == 1

    def test_a_string_vazia_conta_como_em_falta(self):
        """Uma variável declarada e vazia é o mesmo que não a declarar."""
        with pytest.raises(SystemExit):
            _resolver_segredo("production", "")

    @pytest.mark.parametrize("ambiente", ["PRODUCTION", " Production "])
    def test_nao_se_escapa_com_maiusculas_nem_espacos(self, ambiente):
        """Senão `ENVIRONMENT=Production` desligava a guarda em silêncio."""
        with pytest.raises(SystemExit):
            _resolver_segredo(ambiente, None)

    def test_com_variavel_definida_usa_a_variavel(self):
        """Contraprova: a guarda não pode recusar o caso bom."""
        assert _resolver_segredo("production", "s3gr3d0-real") == "s3gr3d0-real"


class TestForaDeProducaoDegradaSemLiteral:
    def test_gera_um_segredo_por_instancia(self):
        segredo = _resolver_segredo("dev", None)
        assert segredo
        assert len(segredo) >= 32

    def test_dois_arranques_NAO_partilham_segredo(self):
        """A diferença que interessa face ao literal antigo.

        Um literal é um segredo conhecido em qualquer máquina que corra
        o código. Aleatório por processo, um token não sobrevive a um
        reinício — que é o que se quer de um token de 10 minutos em dev.
        """
        assert _resolver_segredo("dev", None) != _resolver_segredo("dev", None)

    def test_em_dev_a_variavel_continua_a_mandar(self):
        assert _resolver_segredo("dev", "o-meu-segredo") == "o-meu-segredo"


class TestOLiteralInseguroNaoVolta:
    """Guarda de fonte. Sem ela, um `git revert` distraído repõe o defeito."""

    def _fontes(self):
        """Código dos dois módulos, sem comentários e SEM ASPAS.

        Sem comentários porque uma guarda que os leia proíbe a
        explicação do defeito que previne. Sem aspas porque o
        `ast.unparse` normaliza `"` em `'` — comparar com aspas faria a
        asserção depender de um detalhe de formatação.
        """
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        servicos = Path(__file__).resolve().parents[2] / "services"
        fontes = {}
        for nome in ("gov_auth_api_helpers", "gov_auth_api_verify"):
            texto = (servicos / f"{nome}.py").read_text(encoding="utf-8")
            fontes[nome] = codigo_sem_comentarios(texto).replace(
                '"', ""
            ).replace("'", "")
        return fontes

    def test_nenhum_modulo_gov_traz_o_literal(self):
        for nome, fonte in self._fontes().items():
            assert "change-in-prod" not in fonte, nome
            assert "dev-secret" not in fonte, nome

    def test_nenhum_os_environ_get_com_omissao_para_o_segredo(self):
        """O defeito não era o literal em si — era o segundo argumento do
        `os.environ.get`. Proibir só o texto deixava passar qualquer
        outro valor por omissão."""
        fonte = self._fontes()["gov_auth_api_helpers"]
        assert "os.environ.get(GOV_AUTH_JWT_SECRET)" in fonte
        assert "GOV_AUTH_JWT_SECRET," not in fonte

    def test_nao_resta_aceitacao_de_token_por_assinar(self):
        for nome, fonte in self._fontes().items():
            assert "mock-signature" not in fonte, nome
            assert "ImportError" not in fonte, nome

    def test_CONTRAPROVA_o_verificador_continua_a_verificar(self):
        """Sem isto, apagar a função inteira satisfazia as guardas acima."""
        fonte = self._fontes()["gov_auth_api_verify"]
        assert "jwt.decode" in fonte
        assert "_JWT_SECRET" in fonte


class TestOCircuitoRealAssinaEVerifica:
    """Produzir e verificar com o MESMO segredo, pelas funções de produção."""

    async def test_um_token_emitido_aqui_e_aceite(self):
        from services.gov_auth_api_helpers import MOCK_CITIZEN, create_gov_jwt
        from services.gov_auth_api_verify import run_verify_gov_token

        resultado = await run_verify_gov_token(create_gov_jwt(MOCK_CITIZEN))

        assert resultado["valid"] is True
        assert resultado["gov_data"]["verified_by_gov"] is True

    async def test_um_token_FORJADO_e_recusado(self):
        """O ataque que o literal público permitia: assinar com outro
        segredo e passar por verificado pelo Estado."""
        import jwt

        from services.gov_auth_api_verify import run_verify_gov_token

        forjado = jwt.encode(
            {
                "gov_data": {"nif": "999999999", "verified_by_gov": True},
                "exp": 99999999999,
                "type": "gov_auth",
            },
            "dev-secret-change-in-prod",
            algorithm="HS256",
        )

        resultado = await run_verify_gov_token(forjado)
        assert resultado["valid"] is False

    async def test_o_token_por_assinar_ja_nao_e_aceite(self):
        """Era `<base64>.<base64>.mock-signature` e devolvia `valid: True`."""
        import base64
        import json

        from services.gov_auth_api_verify import run_verify_gov_token

        corpo = base64.urlsafe_b64encode(
            json.dumps(
                {
                    "gov_data": {"nif": "999999999", "verified_by_gov": True},
                    "exp": 99999999999,
                    "type": "gov_auth",
                }
            ).encode()
        ).decode()
        cabecalho = base64.urlsafe_b64encode(
            json.dumps({"alg": "mock"}).encode()
        ).decode()

        resultado = await run_verify_gov_token(
            f"{cabecalho}.{corpo}.mock-signature"
        )
        assert resultado["valid"] is False
