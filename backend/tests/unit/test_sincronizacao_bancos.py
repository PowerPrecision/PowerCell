"""Créditos Ativos → Contas Bancárias, na ESCRITA (Lote 2, ponto 3).

O DEFEITO
=========
A regra existia dentro do `executeSave` do `pages/ProcessDetails.js`.
Corria quando um humano carregava em Gravar NAQUELA página, e só então.
Passavam ao lado:

  · a IA (`build_update_data_from_extraction`), que é quem preenche os
    créditos a partir do mapa de responsabilidades do Banco de Portugal
    — o caso mais comum de todos;
  · o `ai-apply-suggestions`, o `ai_bulk`, o motor financeiro, scripts.

É a lição do `assigned_to` noutro eixo: a regra vivia num ECRÃ e não na
escrita. E não dava erro — a lista ficava incompleta, que é o tipo de
defeito que ninguém reporta.

Havia ainda TRÊS nomes para a mesma pergunta: `bancos_creditos` usa a
chave `banco`, `creditos_ativos` (IA) usa `instituicao`, e o bloco do
frontend só conhecia o primeiro. Um banco extraído pela IA era invisível
para a sincronização E para a validação de destinatários do
`email_documentation`, que tinha a mesma cópia incompleta.

O ORÁCULO DESTES TESTES
=======================
Os escritores REAIS (`run_update_process` e
`build_update_data_from_extraction`), nunca uma lista de campos escrita
aqui — essa seria a quarta cópia. E a guarda de que o bloco do frontend
foi REMOVIDO, porque duas cópias divergem.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import financial_bank_sync as fbs  # noqa: E402
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios  # noqa: E402

RAIZ = Path(__file__).resolve().parents[3]


class TestONomeDoBancoSaiDasDuasFormas:
    """`bancos_creditos` diz `banco`; a IA diz `instituicao`."""

    def test_texto_simples(self):
        assert fbs.nome_do_banco("CGD") == "CGD"

    def test_dicionario_do_formulario(self):
        assert fbs.nome_do_banco({"banco": "Millennium", "valor": 1000}) == "Millennium"

    def test_dicionario_da_IA(self):
        """A chave que o bloco do frontend não conhecia."""
        assert fbs.nome_do_banco({"instituicao": "Novo Banco", "tipo": "Habitação"}) == "Novo Banco"

    def test_espacos_sao_aparados(self):
        assert fbs.nome_do_banco("  BPI  ") == "BPI"
        assert fbs.nome_do_banco({"banco": " Santander "}) == "Santander"

    def test_entradas_sem_nome_nao_produzem_vazios(self):
        """Um "" na lista de contas aparece no ecrã como uma etiqueta em branco."""
        assert fbs.nome_do_banco({"valor": 500}) == ""
        assert fbs.nome_do_banco(None) == ""
        assert fbs.nome_do_banco("   ") == ""


class TestAsDuasOrigensContam:
    def test_do_formulario(self):
        fd = {"bancos_creditos": [{"banco": "CGD"}, "BPI"]}
        assert fbs.nomes_de_bancos_com_credito(fd) == ["CGD", "BPI"]

    def test_da_IA(self):
        fd = {"creditos_ativos": [{"instituicao": "Millennium"}]}
        assert fbs.nomes_de_bancos_com_credito(fd) == ["Millennium"]

    def test_as_duas_ao_mesmo_tempo_sem_repetir(self):
        fd = {
            "bancos_creditos": [{"banco": "CGD"}],
            "creditos_ativos": [{"instituicao": "cgd"}, {"instituicao": "BPI"}],
        }
        assert fbs.nomes_de_bancos_com_credito(fd) == ["CGD", "BPI"]

    def test_as_duas_origens_estao_MESMO_declaradas(self):
        """Contraprova de cobertura: se uma cair da constante, os testes
        acima continuariam verdes pela outra."""
        assert set(fbs.CAMPOS_DE_CREDITOS) == {"bancos_creditos", "creditos_ativos"}


class TestASincronizacao:
    def test_o_banco_do_credito_passa_a_conta_aberta(self):
        fd = {"bancos_creditos": [{"banco": "CGD"}]}
        assert fbs.sincronizar_contas_bancarias(fd)["tem_creditos_activos"] == ["CGD"]

    def test_acrescenta_sem_apagar_o_que_ja_estava(self):
        """Uma conta inserida à mão sem crédito associado é informação
        legítima; apagá-la destruía trabalho humano em silêncio."""
        fd = {"bancos_creditos": ["BPI"], "tem_creditos_activos": ["Montepio"]}
        assert fbs.sincronizar_contas_bancarias(fd)["tem_creditos_activos"] == ["Montepio", "BPI"]

    def test_nao_duplica_quando_ja_esta_la(self):
        fd = {"bancos_creditos": ["CGD"], "tem_creditos_activos": ["CGD"]}
        assert fbs.contas_sincronizadas(fd) is None

    def test_nao_duplica_por_causa_das_maiusculas(self):
        """"CGD" e "cgd" são o mesmo banco; duas etiquetas no ecrã não."""
        fd = {"bancos_creditos": ["cgd"], "tem_creditos_activos": ["CGD"]}
        assert fbs.contas_sincronizadas(fd) is None

    def test_grava_o_nome_ORIGINAL_e_nao_a_versao_normalizada(self):
        """A comparação normaliza; o que se grava é o que o utilizador vê."""
        fd = {"bancos_creditos": ["Caixa Geral de Depósitos"]}
        assert fbs.sincronizar_contas_bancarias(fd)["tem_creditos_activos"] == [
            "Caixa Geral de Depósitos"
        ]

    def test_sem_creditos_nao_ha_alteracao(self):
        assert fbs.contas_sincronizadas({"tem_creditos_activos": ["CGD"]}) is None
        assert fbs.contas_sincronizadas({}) is None
        assert fbs.contas_sincronizadas(None) is None

    def test_None_significa_mesmo_nada_a_gravar(self):
        """Distinguir "sem alteração" de "a lista é esta" é o que impede uma
        gravação inútil (e um diff vazio na auditoria) em cada save."""
        assert fbs.contas_sincronizadas({"bancos_creditos": []}) is None

    def test_a_funcao_nao_muta_o_que_recebe(self):
        """O bloco antigo do frontend mutava o estado em sítio, e era a
        mutação — não o `setState` — que o fazia funcionar."""
        fd = {"bancos_creditos": ["CGD"]}
        resultado = fbs.sincronizar_contas_bancarias(fd)
        assert "tem_creditos_activos" not in fd
        assert resultado is not fd


class TestOBooleanoDoLegado:
    """`tem_creditos_activos` já foi um sim/não, e um booleano não carrega
    nome de banco nenhum."""

    def test_True_e_tratado_como_sem_nomes(self):
        fd = {"bancos_creditos": ["CGD"], "tem_creditos_activos": True}
        assert fbs.sincronizar_contas_bancarias(fd)["tem_creditos_activos"] == ["CGD"]

    def test_False_tambem(self):
        fd = {"bancos_creditos": ["CGD"], "tem_creditos_activos": False}
        assert fbs.sincronizar_contas_bancarias(fd)["tem_creditos_activos"] == ["CGD"]

    def test_um_booleano_nao_rebenta_a_leitura(self):
        assert fbs.contas_abertas({"tem_creditos_activos": True}) == []


class TestOsEscritoresREAISEstaoLigados:
    """Guardas de fonte com a contraprova ao lado — sem ela, apagar a
    chamada satisfaz a guarda."""

    def test_a_gravacao_do_processo_sincroniza(self):
        """A guarda aponta para `apply_staff_business_updates`, e NÃO para o
        `run_update_process`: o merge do `financial_data` vive na função
        extraída, e um guarda sobre o orquestrador passaria a verde com a
        sincronização em sítio nenhum. É a armadilha do Lote 5 (o guarda do
        Webmail apontado à função errada depois de uma extracção)."""
        from services import process_update
        fonte = codigo_da_funcao_sem_comentarios(process_update.apply_staff_business_updates)
        assert "sincronizar_contas_bancarias" in fonte
        # E o merge continua a ser feito ANTES da sincronização — sincronizar
        # o que não foi fundido perderia o que o lote traz.
        assert fonte.index("merge_nested_process_section") < fonte.index(
            "sincronizar_contas_bancarias"
        )

    def test_a_IA_sincroniza(self):
        from services import ai_document
        fonte = codigo_da_funcao_sem_comentarios(ai_document.build_update_data_from_extraction)
        assert "aplicar_a_update_data" in fonte

    def test_CONTRAPROVA_a_funcao_ligada_faz_mesmo_o_trabalho(self):
        update_data = {"financial_data": {"bancos_creditos": [{"instituicao": "BPI"}]}}
        fbs.aplicar_a_update_data(update_data)
        assert update_data["financial_data"]["tem_creditos_activos"] == ["BPI"]

    def test_um_lote_que_nao_mexe_nos_dados_financeiros_fica_intacto(self):
        """Uma actualização de etiquetas não tem de passar a mexer em contas."""
        update_data = {"labels": ["urgente"]}
        fbs.aplicar_a_update_data(update_data)
        assert update_data == {"labels": ["urgente"]}


class TestACopiaDoFrontendFoiREMOVIDA:
    """Duas cópias divergem — foi assim que a chave `instituicao` ficou de
    fora durante todo este tempo."""

    def test_o_ProcessDetails_ja_nao_tem_o_bloco(self):
        fonte = (RAIZ / "frontend" / "src" / "pages" / "ProcessDetails.js").read_text(
            encoding="utf-8"
        )
        # A atribuição é a marca do bloco antigo (o comentário que explica
        # a remoção menciona os nomes dos campos de propósito).
        assert "financialData.tem_creditos_activos = newAccounts" not in fonte
        assert "const existingAccounts" not in fonte

    def test_o_email_documentation_usa_o_ponto_unico(self):
        from services import email_documentation
        fonte = codigo_da_funcao_sem_comentarios(
            email_documentation._send_documentation_email_impl
        )
        assert "nomes_de_bancos_com_credito" in fonte

    def test_CONTRAPROVA_o_ponto_unico_apanha_a_chave_da_IA(self):
        """Era isto que a cópia local do `email_documentation` não fazia: um
        banco extraído pela IA não entrava nos `blocked_banks`."""
        assert fbs.nomes_de_bancos_com_credito(
            {"creditos_ativos": [{"instituicao": "Bankinter"}]}
        ) == ["Bankinter"]
