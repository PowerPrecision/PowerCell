"""O resolvedor de fases — o ponto único dos NOMES.

Épico 10, Parte 3. Ver `services/workflow_phases.py`.

O `workflow_lookup` já era o ponto único das FLAGS de propósito. Este é o
dos nomes: que fase é esta que está gravada, e que fases são terminais.
"""
import pytest

from services.process_status import INACTIVE_STATUSES
from services.workflow_phases import (
    FASE_DESCONHECIDA,
    Resolucao,
    construir_tabela_de_aliases,
    nomes_activos,
    nomes_das_fases,
    nomes_terminais,
    normalizar_para_gralha,
    resolver_muitos,
    resolver_nome,
)


def fase(nome, **extra):
    base = {"id": nome, "name": nome, "label": nome.title(), "order": 1}
    base.update(extra)
    return base


SEED = [
    fase("clientes_espera"),
    fase("fase_documental"),
    fase("fase_bancaria"),
    fase("ch_aprovado"),
    fase("fase_escritura"),
    fase("escritura_agendada"),
    fase("concluidos", is_active=False),
    fase("desistencias", is_active=False),
]


# ====================================================================
# A ORDEM DA RESOLUÇÃO
# ====================================================================

class TestResolverNome:
    def test_exacto_nao_traduz_nada(self):
        r = resolver_nome("clientes_espera", SEED)
        assert r == Resolucao("clientes_espera", "clientes_espera", "exacto")
        assert r.resolvida and not r.traduzida

    @pytest.mark.parametrize("gravado", [
        "Clientes_Espera", "clientes_espera ", " clientes_espera",
        "CLIENTES_ESPERA", "clientes-espera",
    ])
    def test_gralha_cai_na_fase_certa(self, gravado):
        r = resolver_nome(gravado, SEED)
        assert r.fase == "clientes_espera"
        assert r.motivo == "gralha"
        assert r.traduzida

    def test_alias_legitimo_do_produto(self):
        """`escriturado` é o nome que `concluidos` tinha noutra versão."""
        r = resolver_nome("escriturado", SEED)
        assert r.fase == "concluidos"
        assert r.motivo == "alias"

    def test_o_alias_do_singular_legado(self):
        r = resolver_nome("concluido", SEED)
        assert r.fase == "concluidos"
        assert r.motivo == "alias"

    def test_cpcv_vai_para_a_escritura_e_nao_para_a_documental(self):
        """A tabela do produto diz `cpcv -> fase_escritura`.

        Um CPCV acontece depois do crédito aprovado, antes da escritura.
        Mandá-lo para a fase documental moveria o processo para TRÁS no
        funil — de quase-fechado para o início do trabalho.
        """
        r = resolver_nome("cpcv", SEED)
        assert r.fase == "fase_escritura"
        assert r.motivo == "alias"

    def test_desconhecido_nao_e_adivinhado(self):
        r = resolver_nome("fase_inventada", SEED)
        assert r.fase is None
        assert r.motivo == "desconhecido"
        assert not r.resolvida

    @pytest.mark.parametrize("vazio", [None, ""])
    def test_sem_status_e_desconhecido_e_nao_rebenta(self, vazio):
        r = resolver_nome(vazio, SEED)
        assert r.fase is None and r.motivo == "desconhecido"

    def test_sem_fases_nenhumas_nada_resolve(self):
        """Fail-closed: uma leitura falhada não inventa fases."""
        assert resolver_nome("clientes_espera", []).motivo == "desconhecido"


class TestOMotorGanhaSempreAoAlias:
    """A regra que fez a timeline mentir no Lote 5, P0."""

    def test_uma_fase_chamada_cpcv_nao_e_traduzida(self):
        """Basta o admin criar `cpcv` para a tradução ter de calar-se."""
        fases = SEED + [fase("cpcv")]
        r = resolver_nome("cpcv", fases)
        assert r.fase == "cpcv"
        assert r.motivo == "exacto"

    def test_alias_cujo_destino_nao_existe_nao_resolve(self):
        """O destino tem de existir NO MOTOR."""
        r = resolver_nome("escriturado", [fase("clientes_espera")])
        assert r.motivo == "desconhecido"

    def test_dois_destinos_configurados_e_ambiguidade(self):
        fases = [fase("concluido"), fase("concluidos")]
        assert resolver_nome("escriturado", fases).motivo == "desconhecido"

    def test_gralha_ambigua_tambem_recusa(self):
        fases = [fase("escritura"), fase("Escritura")]
        assert resolver_nome("escritura ", fases).motivo == "desconhecido"

    def test_a_gralha_vence_o_alias(self):
        """`Concluidos ` é a mesma fase mal escrita, não um nome antigo.

        Sem esta ordem, um nome que fosse simultaneamente gralha de uma
        fase e alias de outra resolveria para a errada.
        """
        r = resolver_nome("Concluidos ", SEED)
        assert r.motivo == "gralha" and r.fase == "concluidos"


class TestResolverMuitos:
    def test_resolve_o_conjunto_distinto(self):
        r = resolver_muitos(
            ["clientes_espera", "clientes_espera", "escriturado", None], SEED,
        )
        assert r["clientes_espera"].motivo == "exacto"
        assert r["escriturado"].fase == "concluidos"
        assert r[""].motivo == "desconhecido"

    def test_concorda_sempre_com_o_resolver_um_a_um(self):
        valores = ["clientes_espera", "escriturado", "Concluidos ", "xpto", ""]
        muitos = resolver_muitos(valores, SEED)
        for valor in valores:
            assert muitos[valor or ""] == resolver_nome(valor, SEED)


# ====================================================================
# TERMINAIS — o que substitui as listas cravadas
# ====================================================================

class TestNomesTerminais:
    def test_a_flag_do_motor_manda(self):
        terminais = nomes_terminais(SEED)
        assert "concluidos" in terminais and "desistencias" in terminais
        assert "clientes_espera" not in terminais

    def test_uma_fase_marcada_activa_nao_e_terminal_mesmo_na_lista_legada(self):
        """O admin reabriu `concluidos`? Então não é terminal.

        É o ponto todo de a verdade ser a flag: a lista legada não pode
        vencer uma decisão explícita do administrador.
        """
        fases = [fase("concluidos", is_active=True)]
        assert nomes_terminais(fases) == sorted(
            set(INACTIVE_STATUSES) - {"concluidos"}
        )

    def test_fase_sem_flag_cai_na_lista_legada(self):
        """Instalação que ainda não correu o backfill das flags."""
        fases = [fase("concluidos"), fase("clientes_espera")]
        terminais = nomes_terminais(fases)
        assert "concluidos" in terminais
        assert "clientes_espera" not in terminais

    def test_o_residuo_legado_que_nao_e_fase_continua_terminal(self):
        """`perdido`, `cancelado`, `arquivo`: existem em dados, não no motor.

        São os 125 processos do retrato de produção. Deixá-los de fora
        fá-los-ia aparecer como ACTIVOS, que é pior do que órfãos.
        """
        terminais = set(nomes_terminais(SEED))
        assert {"perdido", "cancelado", "arquivo"} <= terminais

    def test_sem_fases_sobra_o_residuo_e_nao_o_vazio(self):
        """Fail-closed: sem motor, o filtro fica restritivo, não permissivo."""
        assert set(nomes_terminais([])) == set(INACTIVE_STATUSES)

    def test_activos_e_o_complemento_dentro_do_motor(self):
        activos = nomes_activos(SEED)
        assert "clientes_espera" in activos
        assert "concluidos" not in activos
        assert set(activos) & set(nomes_terminais(SEED)) == set()

    def test_activos_nunca_inventa_uma_fase_que_o_motor_nao_tem(self):
        """A contraprova do resíduo: ele conta como terminal, não como fase."""
        assert "perdido" not in nomes_activos(SEED)


# ====================================================================
# DETALHES
# ====================================================================

class TestOEnumEFechado:
    """Sobreviveu a uma mutação (M8): o enum fechado era desenho e
    comentário, e nunca afirmação.

    É o ponto todo do agrupamento aprovado: texto livre criaria um grupo
    novo com uma gralha e o funil partia-se em silêncio — a lição do
    Campo de Rede (Lote 5, ponto 2)."""

    def test_uma_macro_fase_inventada_e_ignorada(self):
        from services.workflow_phases import macro_da_fase

        assert macro_da_fase(fase("concluidos", macro_fase="inventado")) == "concluido"

    def test_e_ignorada_mesmo_sem_omissao_a_que_recorrer(self):
        from services.workflow_phases import macro_da_fase

        assert macro_da_fase(fase("fase_nova", macro_fase="Aprovado")) is None

    def test_a_fase_com_macro_invalida_nao_entra_em_grupo_nenhum(self):
        from services.workflow_phases import nomes_por_macro

        fases = [fase("fase_nova", macro_fase="quase_aprovado")]
        for macro in ("novo", "analise", "aprovado", "concluido", "perdido"):
            assert nomes_por_macro(fases, macro) == []

    def test_contraprova_uma_macro_valida_ganha_a_omissao(self):
        from services.workflow_phases import macro_da_fase

        assert macro_da_fase(fase("concluidos", macro_fase="perdido")) == "perdido"

    @pytest.mark.parametrize("valida", ["novo", "analise", "aprovado",
                                        "concluido", "perdido"])
    def test_todas_as_do_enum_sao_aceites(self, valida):
        from services.workflow_phases import macro_da_fase

        assert macro_da_fase(fase("seja_qual_for", macro_fase=valida)) == valida


class TestQuemReconcilia:
    """Sobreviveu a uma mutação (M10): o papel desconhecido.

    A propriedade que interessa não é "o admin vê" — é que quem NÃO se
    consegue identificar não vê. Uma resolução de papel falhada não pode
    abrir o que a bem sucedida fecharia (Gestor S3, Passo 3)."""

    from models.auth import UserRole as _UR

    @pytest.mark.parametrize("papel", [None, "", "  ", "desconhecido", 0, []])
    def test_papel_que_nao_se_resolve_nao_reconcilia(self, papel):
        from services.workflow_phases import pode_ver_desconhecidas

        assert pode_ver_desconhecidas(papel) is False

    @pytest.mark.parametrize("papel", ["admin", "ceo", _UR.ADMIN, _UR.CEO])
    def test_quem_reconcilia(self, papel):
        from services.workflow_phases import pode_ver_desconhecidas

        assert pode_ver_desconhecidas(papel) is True

    @pytest.mark.parametrize("papel", ["diretor", "consultor", "intermediario",
                                       "indexacao", "administrativo",
                                       "parceiro", "cliente"])
    def test_quem_nao_reconcilia(self, papel):
        from services.workflow_phases import pode_ver_desconhecidas

        assert pode_ver_desconhecidas(papel) is False

    def test_o_enum_embrulhado_do_python_311(self):
        """`str(UserRole.ADMIN)` devolve `'UserRole.ADMIN'`, não `'admin'`."""
        from services.workflow_phases import pode_ver_desconhecidas

        assert pode_ver_desconhecidas("UserRoleEnum.ADMIN") is True
        assert pode_ver_desconhecidas("UserRoleEnum.CONSULTOR") is False


class TestDetalhes:
    def test_nomes_das_fases_ignora_lixo(self):
        assert nomes_das_fases([fase("x"), {"id": "sem_nome"}, "lixo", None]) == ["x"]

    def test_a_ordem_do_motor_e_preservada(self):
        fases = [fase("terceira"), fase("primeira"), fase("segunda")]
        assert nomes_das_fases(fases) == ["terceira", "primeira", "segunda"]

    def test_a_tabela_de_aliases_e_simetrica(self):
        tabela = construir_tabela_de_aliases()
        for nome, outros in tabela.items():
            for outro in outros:
                assert nome in tabela[outro]

    def test_normalizar_none(self):
        assert normalizar_para_gralha(None) == ""

    def test_a_fase_desconhecida_nao_colide_com_nome_nenhum(self):
        """A chave da coluna de órfãos não pode ser um nome plausível."""
        assert FASE_DESCONHECIDA.startswith("__")
        assert FASE_DESCONHECIDA not in nomes_das_fases(SEED)
