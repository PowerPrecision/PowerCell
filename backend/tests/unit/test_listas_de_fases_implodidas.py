"""As listas de nomes de fases cravadas no código foram implodidas.

ÉPICO 10, PARTE 3.

O retrato de produção mediu-as e o resultado foi este:

    stats_branches._COMPLETED_STATUSES: 0/2 nomes existem • 0 processos

Zero. O tempo médio de fecho por balcão saía de um conjunto vazio, e o
dashboard apresentava-o como um número. Este ficheiro afirma que as
listas desapareceram, que o que as substituiu vem do motor, e que
nenhum módulo novo as reintroduz.
"""
import pathlib
import re

import pytest

from services.process_status import DELETED_STATUS_VALUES, LEAD_STATUS_VALUES
from services.portal_profile import construir_query_de_processo_a_trancar
from services.workflow_phases import nomes_activos, nomes_por_macro

RAIZ = pathlib.Path(__file__).resolve().parents[2]


def fase(nome, **extra):
    base = {"id": nome, "name": nome, "label": nome.title(), "order": 1}
    base.update(extra)
    return base


MOTOR = [
    fase("clientes_espera"),
    fase("fase_documental"),
    fase("fase_bancaria"),
    fase("ch_aprovado"),
    fase("fase_escritura"),
    fase("concluidos", is_active=False),
    fase("desistencias", is_active=False),
]


# ====================================================================
# O PERFIL DO PORTAL
# ====================================================================

class TestTrancarOPerfilDoCliente:
    """A regra estava escrita à mão em DOIS sítios, com a fase inicial
    do seed cravada. Renomear a fase inicial trancava o perfil de toda a
    gente no dia do registo."""

    def test_a_recolha_de_documentos_nao_tranca(self):
        query = construir_query_de_processo_a_trancar(["p1"], MOTOR)
        excluidos = query["status"]["$nin"]
        assert "clientes_espera" in excluidos
        assert "fase_documental" in excluidos

    def test_as_fases_de_trabalho_trancam(self):
        excluidos = construir_query_de_processo_a_trancar(["p1"], MOTOR)["status"]["$nin"]
        for fase_de_trabalho in ("fase_bancaria", "ch_aprovado", "concluidos"):
            assert fase_de_trabalho not in excluidos

    def test_as_leads_e_os_perdidos_nao_trancam(self):
        excluidos = construir_query_de_processo_a_trancar(["p1"], MOTOR)["status"]["$nin"]
        assert set(LEAD_STATUS_VALUES) <= set(excluidos)
        assert "desistencias" in excluidos
        assert set(DELETED_STATUS_VALUES) <= set(excluidos)

    def test_renomear_a_fase_inicial_deixou_de_partir_a_regra(self):
        """O defeito concreto: o admin renomeia e ninguém dá por nada."""
        motor = [fase("recolha_inicial", macro_fase="novo"), fase("fase_bancaria")]
        excluidos = construir_query_de_processo_a_trancar(["p1"], motor)["status"]["$nin"]
        assert "recolha_inicial" in excluidos
        assert "fase_bancaria" not in excluidos

    def test_uma_fase_desconhecida_tranca(self):
        """Lado seguro: melhor um perfil trancado a mais do que dados a
        mudarem debaixo de uma análise a decorrer."""
        excluidos = construir_query_de_processo_a_trancar(["p1"], MOTOR)["status"]["$nin"]
        assert "fase_que_ninguem_conhece" not in excluidos

    def test_o_soft_delete_continua_excluido(self):
        query = construir_query_de_processo_a_trancar(["p1", "p2"], MOTOR)
        assert query["is_deleted"] == {"$ne": True}
        assert query["id"] == {"$in": ["p1", "p2"]}

    def test_sem_motor_so_sobram_as_leads_e_os_eliminados(self):
        """Fail-closed: sem fases, tranca em vez de abrir."""
        excluidos = construir_query_de_processo_a_trancar(["p1"], [])["status"]["$nin"]
        assert "clientes_espera" not in excluidos
        assert set(LEAD_STATUS_VALUES) <= set(excluidos)


# ====================================================================
# O BI E O RELATÓRIO MENSAL
# ====================================================================

class TestOsConjuntosDoBI:
    def test_concluido_e_so_a_fase_terminal_de_sucesso(self):
        assert nomes_por_macro(MOTOR, "concluido") == ["concluidos"]
        assert "desistencias" not in nomes_por_macro(MOTOR, "concluido")

    def test_aprovado_inclui_o_desfecho(self):
        aprovados = nomes_por_macro(MOTOR, "aprovado", "concluido")
        assert {"ch_aprovado", "fase_escritura", "concluidos"} <= set(aprovados)
        assert "clientes_espera" not in aprovados

    def test_activos_exclui_os_terminais(self):
        activos = nomes_activos(MOTOR)
        assert "concluidos" not in activos and "desistencias" not in activos
        assert "fase_bancaria" in activos

    def test_nada_do_que_o_bi_mede_e_inventado(self):
        """A propriedade que faltava, e que o retrato provou violada."""
        conhecidas = {f["name"] for f in MOTOR}
        for conjunto in (
            nomes_por_macro(MOTOR, "concluido"),
            nomes_por_macro(MOTOR, "aprovado", "concluido"),
            nomes_activos(MOTOR),
        ):
            assert set(conjunto) <= conhecidas


# ====================================================================
# GUARDA: AS LISTAS NÃO VOLTAM
# ====================================================================

# Nomes de fases reais e fantasma. Três ou mais literais num módulo é o
# sinal de uma lista a renascer.
NOMES_DE_FASES = {
    "clientes_espera", "fase_documental", "fase_documental_ii",
    "enviado_bruno", "enviado_luis", "enviado_bcp_rui", "entradas_precision",
    "fase_bancaria", "fase_visitas", "ch_aprovado", "fase_escritura",
    "escritura_agendada", "concluidos", "desistencias",
    "documentacao", "pre_aprovacao", "credito_aprovado", "pedido_avaliacao",
    "cpcv", "minuta",
}

# Os únicos sítios com direito a nomes de fases, e porquê.
COM_DIREITO = {
    # O mapa de macro-fases e a tabela de aliases: é aqui que vivem.
    "workflow_phases.py",
    # A medição — compara o código com a realidade; precisa dos dois.
    "workflow_status_coverage.py",
    # Semeia as flags de propósito uma vez, em instalações antigas.
    "workflow_lookup.py",
    # Semeadores: criam as fases por omissão de uma instalação nova.
    "admin_workflow.py",
    "admin_dev_ops.py",
}


def _sem_comentarios(fonte: str) -> str:
    """Sem isto, o comentário que EXPLICA a lista implodida faria a
    guarda ficar vermelha — e a saída óbvia seria apagar a explicação."""
    fonte = re.sub(r'"""[\s\S]*?"""', "", fonte)
    fonte = re.sub(r"'''[\s\S]*?'''", "", fonte)
    return re.sub(r"#.*", "", fonte)


def _modulos_de_servico():
    return sorted((RAIZ / "backend" / "services").rglob("*.py")) or \
        sorted((RAIZ / "services").rglob("*.py"))


@pytest.mark.parametrize(
    "caminho", _modulos_de_servico(), ids=lambda c: c.name,
)
def test_nenhum_servico_novo_crava_uma_lista_de_fases(caminho):
    if caminho.name in COM_DIREITO:
        pytest.skip("sítio com direito a nomes de fases")
    fonte = _sem_comentarios(caminho.read_text(encoding="utf-8"))
    achados = sorted(
        n for n in NOMES_DE_FASES
        if f'"{n}"' in fonte or f"'{n}'" in fonte
    )
    assert len(achados) < 3, (
        f"{caminho.name} tem {len(achados)} nomes de fases cravados "
        f"({achados}). As fases são configuráveis: usar "
        f"`workflow_phases` (nomes_activos / nomes_terminais / "
        f"nomes_por_macro) em vez de uma lista."
    )


class TestContraprovaDaGuarda:
    """Sem isto, a guarda passaria com os módulos todos vazios."""

    def test_o_mapa_de_macro_fases_existe_mesmo(self):
        from services.workflow_phases import MACRO_FASE_POR_OMISSAO

        assert len(MACRO_FASE_POR_OMISSAO) > 20

    def test_a_guarda_apanharia_uma_lista_a_renascer(self):
        fonte = _sem_comentarios(
            'ACTIVOS = ["clientes_espera", "fase_bancaria", "ch_aprovado"]'
        )
        achados = [n for n in NOMES_DE_FASES if f'"{n}"' in fonte]
        assert len(achados) >= 3

    def test_a_guarda_ignora_a_explicacao_em_comentario(self):
        fonte = _sem_comentarios(
            '# eram "clientes_espera", "fase_bancaria" e "ch_aprovado"\nx = 1'
        )
        assert [n for n in NOMES_DE_FASES if f'"{n}"' in fonte] == []

    @pytest.mark.parametrize("modulo", [
        "stats_branches.py", "scheduled_tasks.py", "portal_status.py",
        "portal_profile.py", "alerts.py",
    ])
    def test_os_modulos_varridos_ficaram_mesmo_limpos(self, modulo):
        """Os cinco que esta parte varreu, nomeados um a um."""
        caminho = next(
            c for c in _modulos_de_servico() if c.name == modulo
        )
        fonte = _sem_comentarios(caminho.read_text(encoding="utf-8"))
        achados = [n for n in NOMES_DE_FASES if f'"{n}"' in fonte or f"'{n}'" in fonte]
        assert len(achados) < 3, f"{modulo}: {achados}"
