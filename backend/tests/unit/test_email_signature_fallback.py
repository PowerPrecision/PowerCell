"""
Assinatura de email: só a do próprio, no contexto certo (Missão de Limpeza).

O QUE ESTÁ AQUI EM JOGO
-----------------------
A assinatura é a identidade de quem envia. Um email que sai com a
assinatura de OUTRO perfil — ou com o bloco HTML do sistema — não é um
detalhe estético: diz ao cliente que falou com a empresa errada, e
assina-o com dados de contacto que não são de quem escreveu.

O DEFEITO CORRIGIDO
-------------------
A cadeia tinha cinco níveis. Os dois últimos não eram do utilizador:

  4. `ucr_any` — a assinatura de QUALQUER empresa do utilizador. Um
     consultor a escrever pela Power saía assinado pela Precision.
  5. `system_fallback` — a assinatura do sistema. Era este o HTML que
     aparecia a quem nunca configurou assinatura nenhuma.

Hoje: sem assinatura configurada, o email sai SEM assinatura.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import email_service
from services.email_service import resolve_email_signature

def _codigo_sem_comentarios(funcao) -> str:
    """Código de uma função, sem comentários nem docstrings.

    Uma guarda sobre o código-fonte que leia os comentários acaba por
    proibir a explicação do próprio defeito que previne. O leitor vive
    em `tests/unit/helpers_fonte.py` — é a terceira guarda do projecto
    a precisar dele.
    """
    from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

    return codigo_da_funcao_sem_comentarios(funcao)


ASSINATURA_POWER = "<p>Ana — Power</p>"
ASSINATURA_PRECISION = "<p>Ana — Precision</p>"
ASSINATURA_GLOBAL = "<p>Ana Martins</p>"
ASSINATURA_SISTEMA = "<div><img src='logo.png'/>PowerCell</div>"


def _db(*, utilizador=None, ucrs=None):
    """BD falsa: `users.find_one` e `user_company_roles.find_one` por filtro."""
    fake = MagicMock()
    fake.users.find_one = AsyncMock(return_value=utilizador)

    async def procurar_ucr(filtro, *_a, **_kw):
        for ucr in ucrs or []:
            if "company_id" in filtro and ucr.get("company_id") != filtro["company_id"]:
                continue
            # A consulta do antigo `ucr_any` não filtrava por empresa: pedia
            # só "um UCR qualquer com assinatura".
            if "company_id" not in filtro and not ucr.get("signature"):
                continue
            return ucr
        return None

    fake.user_company_roles.find_one = AsyncMock(side_effect=procurar_ucr)
    return fake


async def _resolver(fake_db, **kwargs):
    with patch.object(email_service, "db", fake_db):
        return await resolve_email_signature(**kwargs)


# ====================================================================
# O DEFEITO REPORTADO
# ====================================================================


class TestSemAssinaturaNaoHerdaNada:
    @pytest.mark.asyncio
    async def test_utilizador_sem_assinatura_envia_sem_assinatura(self):
        # O caso reportado: o bloco HTML do sistema aparecia por baixo do
        # texto de quem nunca configurou assinatura nenhuma.
        fake = _db(utilizador={"email_signature": None, "company": "Power"}, ucrs=[])
        assinatura, origem = await _resolver(
            fake,
            created_by="u-1",
            active_company_id="comp-power",
            system_email_signature=ASSINATURA_SISTEMA,
        )
        assert assinatura is None
        assert origem == "none"

    @pytest.mark.asyncio
    async def test_nao_herda_a_assinatura_de_outra_empresa_sua(self):
        # `ucr_any`: a Ana tem assinatura na Precision e nenhuma na Power.
        # A escrever PELA POWER, não pode sair assinada pela Precision.
        fake = _db(
            utilizador={"email_signature": None, "company": "Precision"},
            ucrs=[{"company_id": "comp-precision", "signature": ASSINATURA_PRECISION}],
        )
        assinatura, origem = await _resolver(
            fake, created_by="u-1", active_company_id="comp-power"
        )
        assert assinatura is None, f"herdou de outra empresa (origem={origem})"

    @pytest.mark.asyncio
    async def test_assinatura_vazia_conta_como_ausente(self):
        fake = _db(utilizador={"email_signature": "", "company": "Power"}, ucrs=[])
        assinatura, _ = await _resolver(
            fake,
            created_by="u-1",
            active_company_id="comp-power",
            system_email_signature=ASSINATURA_SISTEMA,
        )
        assert assinatura is None


# ====================================================================
# O QUE CONTINUA A FUNCIONAR
# ====================================================================


class TestAssinaturasLegitimas:
    @pytest.mark.asyncio
    async def test_a_da_empresa_activa_ganha(self):
        fake = _db(
            utilizador={"email_signature": ASSINATURA_GLOBAL, "company": "Power"},
            ucrs=[{"company_id": "comp-power", "signature": ASSINATURA_POWER}],
        )
        assinatura, origem = await _resolver(
            fake, created_by="u-1", active_company_id="comp-power"
        )
        assert assinatura == ASSINATURA_POWER
        assert "ucr_active" in origem

    @pytest.mark.asyncio
    async def test_a_global_do_proprio_vale_quando_o_perfil_nao_tem(self):
        fake = _db(
            utilizador={"email_signature": ASSINATURA_GLOBAL, "company": "Power"},
            ucrs=[{"company_id": "comp-power", "signature": None}],
        )
        assinatura, origem = await _resolver(
            fake, created_by="u-1", active_company_id="comp-power"
        )
        assert assinatura == ASSINATURA_GLOBAL
        assert origem == "user_global"

    @pytest.mark.asyncio
    async def test_sem_empresa_activa_a_da_empresa_por_omissao_vale(self):
        # Sem contexto escolhido não há nada a contradizer: a empresa por
        # omissão do utilizador é a melhor informação disponível.
        fake = _db(
            utilizador={"email_signature": None, "company": "comp-power"},
            ucrs=[{"company_id": "comp-power", "signature": ASSINATURA_POWER}],
        )
        assinatura, origem = await _resolver(
            fake, created_by="u-1", active_company_id=None
        )
        assert assinatura == ASSINATURA_POWER
        assert "ucr_default" in origem

    @pytest.mark.asyncio
    async def test_company_id_default_conta_como_sem_empresa_activa(self):
        fake = _db(
            utilizador={"email_signature": None, "company": "comp-power"},
            ucrs=[{"company_id": "comp-power", "signature": ASSINATURA_POWER}],
        )
        assinatura, _ = await _resolver(
            fake, created_by="u-1", active_company_id="default"
        )
        assert assinatura == ASSINATURA_POWER

    @pytest.mark.asyncio
    async def test_conta_de_sistema_usa_a_assinatura_do_sistema(self):
        # O único caso em que a assinatura do sistema É a identidade certa.
        assinatura, origem = await resolve_email_signature(
            created_by=None,
            active_company_id=None,
            is_system_account=True,
            system_email_signature=ASSINATURA_SISTEMA,
        )
        assert assinatura == ASSINATURA_SISTEMA
        assert origem == "system"


# ====================================================================
# DEGRADAÇÃO
# ====================================================================


class TestDegradacao:
    @pytest.mark.asyncio
    async def test_sem_remetente_nao_ha_assinatura(self):
        assinatura, origem = await resolve_email_signature(
            created_by=None, active_company_id="comp-power"
        )
        assert assinatura is None
        assert origem == "none"

    @pytest.mark.asyncio
    async def test_base_de_dados_em_baixo_nao_rebenta_o_envio(self):
        # Um email sem assinatura é melhor do que um email não enviado.
        fake = MagicMock()
        fake.users.find_one = AsyncMock(side_effect=RuntimeError("mongo em baixo"))
        assinatura, origem = await _resolver(
            fake, created_by="u-1", active_company_id="comp-power"
        )
        assert assinatura is None
        assert origem == "erro"

    @pytest.mark.asyncio
    async def test_utilizador_inexistente_nao_herda_nada(self):
        fake = _db(utilizador=None, ucrs=[])
        assinatura, _ = await _resolver(
            fake,
            created_by="u-fantasma",
            active_company_id="comp-power",
            system_email_signature=ASSINATURA_SISTEMA,
        )
        assert assinatura is None


# ====================================================================
# GUARDA SOBRE O CÓDIGO-FONTE
# ====================================================================


class TestSemFallbacksIndevidos:
    def test_o_envio_nao_reintroduz_o_fallback_do_sistema(self):
        # Reintroduzir `system_fallback` não parte teste nenhum de envio:
        # os emails continuam a sair. Só saem assinados por quem não os
        # escreveu — por isso a guarda é sobre o código.
        #
        # Ignora comentários e docstrings de propósito: sem isso, a própria
        # explicação de porque estes fallbacks saíram fazia o teste ficar
        # vermelho. (Mesma armadilha de `s3FileManagerTransport.test.js`.)
        codigo = _codigo_sem_comentarios(email_service.resolve_email_signature)
        assert "system_fallback" not in codigo
        assert "ucr_any" not in codigo

    def test_a_guarda_veria_o_fallback_se_ele_voltasse(self):
        # Contraprova: sem isto, um erro no despiste de comentários daria
        # um teste que passa sempre.
        def com_fallback():
            """Docstring a falar de system_fallback."""
            # comentário sobre ucr_any
            origem = "system_fallback"
            return origem

        codigo = _codigo_sem_comentarios(com_fallback)
        assert "system_fallback" in codigo
        assert "ucr_any" not in codigo


# ════════════════════════════════════════════════════════════════════
# LOTE 5, ponto 5 — "O Mistério da Assinatura"
#
# O `ProfileRoleTab` grava nos DOIS sítios: `signature` (UCR da empresa
# activa) e `email_signature` (global, "backward compat"). Mas LÊ só um:
# `active_company_signature`.
#
# Logo: configura-se a assinatura na Power → escreve nos dois. Muda-se
# para a Precision, onde o UCR não tem assinatura → a UI mostra VAZIO e
# o envio cai no nível 2, usando a global, que é a da Power.
#
# Não é só falta de transparência: é a assinatura de uma empresa a sair
# num email de outra — exactamente a fuga que o `ucr_any` do Lote 1
# fechou, a entrar de novo pela porta do campo global.
#
# A REGRA: com empresa activa, a global só vale se o utilizador NUNCA
# tiver configurado uma assinatura por empresa. Aí ela é mesmo a única
# assinatura dele, e não a de outro perfil. Quem já usa o sistema por
# empresa não herda nada de lado nenhum.
# ════════════════════════════════════════════════════════════════════
class TestGlobalNaoAtravessaEmpresas:
    @pytest.mark.asyncio
    async def test_quem_so_tem_a_global_continua_a_usa_la(self):
        """Sem regressão para quem nunca usou assinatura por empresa."""
        fake = _db(
            utilizador={"email_signature": ASSINATURA_GLOBAL, "company": "power"},
            ucrs=[],
        )
        assinatura, origem = await _resolver(
            fake, created_by="u-1", active_company_id="cmp-power",
        )
        assert assinatura == ASSINATURA_GLOBAL
        assert origem == "user_global"

    @pytest.mark.asyncio
    async def test_quem_TEM_assinatura_noutra_empresa_nao_herda_a_global(self):
        """A fuga. A global foi escrita ao gravar a da Power; usá-la na
        Precision assina um email de uma empresa com a identidade de
        outra."""
        fake = _db(
            utilizador={"email_signature": ASSINATURA_POWER, "company": "power"},
            ucrs=[{"company_id": "cmp-power", "signature": ASSINATURA_POWER}],
        )
        assinatura, origem = await _resolver(
            fake, created_by="u-1", active_company_id="cmp-precision",
        )
        assert assinatura is None, (
            "a assinatura da Power saiu num email da Precision"
        )
        assert origem == "none"

    @pytest.mark.asyncio
    async def test_a_empresa_activa_com_assinatura_propria_ganha_sempre(self):
        """Contraprova: cortar a global não pode cortar o caso normal."""
        fake = _db(
            utilizador={"email_signature": ASSINATURA_POWER, "company": "power"},
            ucrs=[
                {"company_id": "cmp-power", "signature": ASSINATURA_POWER},
                {"company_id": "cmp-precision", "signature": ASSINATURA_PRECISION},
            ],
        )
        assinatura, _ = await _resolver(
            fake, created_by="u-1", active_company_id="cmp-precision",
        )
        assert assinatura == ASSINATURA_PRECISION
