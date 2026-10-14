"""
Lote 5 — D-4 FECHADA: UMA implementação do travão de força bruta, uma política POR PORTA.

O DEFEITO
  Duas implementações independentes da mesma ideia para as duas portas do mesmo Portal (`portal_brute_force`
  para o login por email, `portal_security` para o `verify`): uma correcção feita numa não chegava à outra, e
  foi essa dispersão que levou a declarar inexistente a segunda.

O QUE SE AFIRMA
  1. cada porta MANTÉM os seus números — é isto que distingue uma consolidação de uma alteração de política
     (apertar o login para 5 bloqueia quem erra um código de 6 caracteres cinco vezes; alargar o verify para
     8/10 abre a porta que tem o espaço de busca mais pequeno);
  2. medido no COMPORTAMENTO, não nas constantes: o N-ésimo erro bloqueia o N+1-ésimo pedido;
  3. as portas não gastam as tentativas umas das outras (colecções e chaves próprias);
  4. já só existe uma implementação: nenhum módulo fora do ponto único conta tentativas à mão.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException

from services import portal_brute_force as pbf

RAIZ = Path(__file__).resolve().parents[2]


async def _falhar(bd, ambito, identidade, vezes):
    for _ in range(vezes):
        await pbf.registar_falha(bd, ambito, identidade)


async def _bloqueado(bd, ambito, identidade) -> bool:
    try:
        await pbf.exigir_sem_bloqueio(bd, ambito, identidade)
    except HTTPException as erro:
        assert erro.status_code == 429
        return True
    return False


class TestCadaPortaMantemOsSeusNumeros:
    def test_a_tabela_diz_o_que_sempre_disse(self):
        assert (pbf.POLITICA_DO_LOGIN.tentativas, pbf.POLITICA_DO_LOGIN.minutos_de_bloqueio) == (8, 10)
        assert (pbf.POLITICA_DO_VERIFY.tentativas, pbf.POLITICA_DO_VERIFY.minutos_de_bloqueio) == (5, 15)
        assert pbf.POLITICA_DO_LOGIN.colecao == "portal_login_attempts"
        assert pbf.POLITICA_DO_VERIFY.colecao == "portal_verify_attempts"

    def test_um_ambito_sem_entrada_herda_a_politica_do_login(self):
        """O login do Parceiro e a confirmação por password não declaravam política: ficam como estavam."""
        for ambito in ("confirmar_password", "parceiro_login", "qualquer_outro"):
            assert pbf.politica_de(ambito) is pbf.POLITICA_DO_LOGIN

    @pytest.mark.asyncio
    async def test_o_verify_bloqueia_depois_de_5_erros_e_nao_de_4(self, fake_async_db):
        await _falhar(fake_async_db, pbf.AMBITO_DO_VERIFY, "cli-1", 4)
        assert not await _bloqueado(fake_async_db, pbf.AMBITO_DO_VERIFY, "cli-1")
        await _falhar(fake_async_db, pbf.AMBITO_DO_VERIFY, "cli-1", 1)
        assert await _bloqueado(fake_async_db, pbf.AMBITO_DO_VERIFY, "cli-1")

    @pytest.mark.asyncio
    async def test_o_login_bloqueia_depois_de_8_erros_e_nao_de_5(self, fake_async_db):
        await _falhar(fake_async_db, pbf.AMBITO_DO_LOGIN, "a@x.pt", 5)
        assert not await _bloqueado(fake_async_db, pbf.AMBITO_DO_LOGIN, "a@x.pt"), "o login NÃO foi apertado"
        await _falhar(fake_async_db, pbf.AMBITO_DO_LOGIN, "a@x.pt", 3)
        assert await _bloqueado(fake_async_db, pbf.AMBITO_DO_LOGIN, "a@x.pt")

    @pytest.mark.asyncio
    async def test_o_bloqueio_dura_o_que_cada_porta_diz(self, fake_async_db):
        for ambito, identidade, vezes, minutos in (
            (pbf.AMBITO_DO_VERIFY, "cli-2", 5, 15), (pbf.AMBITO_DO_LOGIN, "b@x.pt", 8, 10),
        ):
            await _falhar(fake_async_db, ambito, identidade, vezes)
            with pytest.raises(HTTPException) as erro:
                await pbf.exigir_sem_bloqueio(fake_async_db, ambito, identidade)
            esperado = minutos * 60
            assert abs(int(erro.value.headers["Retry-After"]) - esperado) <= 5


class TestOFormatoDoErroEOHistoricoDeCadaPorta:
    @pytest.mark.asyncio
    async def test_o_verify_responde_com_detalhe_em_texto(self, fake_async_db):
        await _falhar(fake_async_db, pbf.AMBITO_DO_VERIFY, "cli-3", 5)
        with pytest.raises(HTTPException) as erro:
            await pbf.exigir_sem_bloqueio(fake_async_db, pbf.AMBITO_DO_VERIFY, "cli-3")
        assert isinstance(erro.value.detail, str)
        assert "Tente novamente em" in erro.value.detail

    @pytest.mark.asyncio
    async def test_o_login_responde_com_o_dicionario_de_sempre(self, fake_async_db):
        await _falhar(fake_async_db, pbf.AMBITO_DO_LOGIN, "c@x.pt", 8)
        with pytest.raises(HTTPException) as erro:
            await pbf.exigir_sem_bloqueio(fake_async_db, pbf.AMBITO_DO_LOGIN, "c@x.pt")
        assert isinstance(erro.value.detail, dict)
        assert erro.value.detail["retry_after_minutes"] >= 1

    @pytest.mark.asyncio
    async def test_a_chave_do_verify_continua_a_ser_a_dos_registos_ja_gravados(self, fake_async_db):
        """Os registos antigos (TTL de 30 min) têm `_id = portal_verify:<client_id>`: mudar a chave
        desbloqueava quem estivesse bloqueado no momento do deploy."""
        await _falhar(fake_async_db, pbf.AMBITO_DO_VERIFY, "cli-4", 1)
        assert any(d["_id"] == "portal_verify:cli-4" for d in fake_async_db.portal_verify_attempts.docs)


class TestAsPortasNaoGastamAsTentativasUmasDasOutras:
    @pytest.mark.asyncio
    async def test_esgotar_o_verify_nao_bloqueia_o_login_do_mesmo_identificador(self, fake_async_db):
        await _falhar(fake_async_db, pbf.AMBITO_DO_VERIFY, "x@x.pt", 5)
        assert await _bloqueado(fake_async_db, pbf.AMBITO_DO_VERIFY, "x@x.pt")
        assert not await _bloqueado(fake_async_db, pbf.AMBITO_DO_LOGIN, "x@x.pt")

    @pytest.mark.asyncio
    async def test_cada_porta_escreve_na_sua_colecao(self, fake_async_db):
        await _falhar(fake_async_db, pbf.AMBITO_DO_VERIFY, "cli-5", 1)
        await _falhar(fake_async_db, pbf.AMBITO_DO_LOGIN, "d@x.pt", 1)
        assert [d["_id"] for d in fake_async_db.portal_verify_attempts.docs] == ["portal_verify:cli-5"]
        assert [d["_id"] for d in fake_async_db.portal_login_attempts.docs] == ["portal_login:d@x.pt"]

    @pytest.mark.asyncio
    async def test_o_sucesso_limpa_so_a_porta_certa(self, fake_async_db):
        await _falhar(fake_async_db, pbf.AMBITO_DO_VERIFY, "e", 2)
        await _falhar(fake_async_db, pbf.AMBITO_DO_LOGIN, "e", 2)
        await pbf.limpar(fake_async_db, pbf.AMBITO_DO_VERIFY, "e")
        assert fake_async_db.portal_verify_attempts.docs == []
        assert len(fake_async_db.portal_login_attempts.docs) == 1


class TestJaSoHaUmaImplementacao:
    ESCRITAS_PERMITIDAS = {"services/portal_brute_force.py"}

    @staticmethod
    def _quem_conta_tentativas():
        """Módulos que escrevem os registos de tentativas: tocam em `portal_*_attempts` OU fazem `$inc` de `attempts`."""
        achados = set()
        for pasta in ("services", "routes"):
            for ficheiro in (RAIZ / pasta).glob("*.py"):
                arvore = ast.parse(ficheiro.read_text(encoding="utf-8"))
                for no in ast.walk(arvore):
                    if isinstance(no, ast.Attribute) and no.attr in ("portal_verify_attempts", "portal_login_attempts"):
                        achados.add(f"{pasta}/{ficheiro.name}")
                    if isinstance(no, ast.Constant) and no.value == "attempts":
                        achados.add(f"{pasta}/{ficheiro.name}")
        return achados

    def test_o_leitor_le_mesmo(self):
        assert "services/portal_brute_force.py" in self._quem_conta_tentativas()

    def test_nenhum_modulo_fora_do_ponto_unico_conta_tentativas_a_mao(self):
        # `portal_attempts_ttl` migra os registos (backfill do TTL) — não conta tentativas.
        fora = self._quem_conta_tentativas() - self.ESCRITAS_PERMITIDAS - {"services/portal_attempts_ttl.py"}
        assert not fora, f"Segunda implementação do travão em: {sorted(fora)} — use `portal_brute_force`."

    def test_a_funcao_antiga_foi_apagada_e_nao_desligada(self):
        from services import portal_security

        assert not hasattr(portal_security, "_record_failed_attempt")
