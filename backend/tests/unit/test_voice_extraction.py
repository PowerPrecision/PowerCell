"""
Testes das funções PURAS da extracção de notas de voz (Épico 7, Eixo 4).

PORQUÊ SÓ ESTAS FUNÇÕES:
    A chamada HTTP ao modelo não tem bugs interessantes — ou responde ou
    levanta. Os bugs a sério estão no que se faz com a resposta: um LLM
    devolve JSON dentro de cercas de código, inventa nomes de campos,
    trunca a meio e escreve "sexta-feira" onde se pediu uma data ISO.
    É isso que aqui se prova, sem rede e sem Mongo.

REFERÊNCIA TEMPORAL FIXA:
    Todos os testes de data injectam `AGORA` (terça-feira, 22/09/2026).
    Sem isso, um teste de "sexta-feira" passaria hoje e falharia na sexta
    seguinte — o pior tipo de teste que há.
"""
from datetime import datetime, timezone

import pytest

from services.voice_extraction import (
    ErroDeExtraccao,
    build_user_prompt,
    normalizar_extraccao,
    normalizar_prioridade,
    normalizar_tarefa,
    parse_extraction_payload,
    resolver_data_relativa,
)

# Terça-feira, 22 de Setembro de 2026, 14:30 UTC.
AGORA = datetime(2026, 9, 22, 14, 30, tzinfo=timezone.utc)


def _dia(iso: str) -> str:
    """Parte da data de um ISO, para asserções legíveis."""
    return iso[:10]


# ====================================================================
# PARSING DA RESPOSTA DO MODELO
# ====================================================================


class TestParseExtractionPayload:
    def test_json_limpo(self):
        bruto = '{"resumo_timeline": "Reunião realizada.", "tarefas_extraidas": []}'

        assert parse_extraction_payload(bruto)["resumo_timeline"] == "Reunião realizada."

    def test_json_dentro_de_cercas_de_codigo(self):
        bruto = '```json\n{"resumo_timeline": "Olá"}\n```'

        assert parse_extraction_payload(bruto)["resumo_timeline"] == "Olá"

    def test_cercas_sem_etiqueta_de_linguagem(self):
        assert parse_extraction_payload('```\n{"resumo_timeline": "Olá"}\n```')

    def test_frase_de_cortesia_antes_do_json(self):
        bruto = 'Claro! Aqui está o resultado:\n{"resumo_timeline": "Feito"}'

        assert parse_extraction_payload(bruto)["resumo_timeline"] == "Feito"

    def test_chaveta_dentro_de_uma_string_nao_parte_o_corte(self):
        # Um título com chavetas partia um `find("}")` ingénuo.
        bruto = '{"resumo_timeline": "Usar o template {cliente} no email"}'

        resultado = parse_extraction_payload(bruto)

        assert resultado["resumo_timeline"] == "Usar o template {cliente} no email"

    def test_json_truncado_a_meio_e_erro(self):
        # O modelo bateu no limite de tokens: não há objecto fechado.
        with pytest.raises(ErroDeExtraccao):
            parse_extraction_payload('{"resumo_timeline": "Reunião com o clien')

    def test_resposta_sem_json_e_erro(self):
        with pytest.raises(ErroDeExtraccao):
            parse_extraction_payload("Desculpe, não consigo ajudar com isso.")

    def test_resposta_vazia_e_erro(self):
        with pytest.raises(ErroDeExtraccao):
            parse_extraction_payload("")

    def test_json_valido_mas_lista_no_topo_e_erro(self):
        with pytest.raises(ErroDeExtraccao):
            parse_extraction_payload('[{"titulo": "x"}]')


# ====================================================================
# DATAS
# ====================================================================


class TestResolverDataRelativa:
    def test_data_iso_e_respeitada(self):
        assert _dia(resolver_data_relativa("2026-10-15", agora=AGORA)) == "2026-10-15"

    def test_iso_com_hora_mantem_a_hora(self):
        resultado = resolver_data_relativa("2026-10-15T16:45:00", agora=AGORA)

        assert resultado.startswith("2026-10-15T16:45")

    def test_iso_sem_hora_recebe_hora_util(self):
        # Um prazo às 00:00 aparece no calendário no dia anterior em fusos
        # a oeste; 09:00 é a leitura que o consultor espera de "dia 15".
        resultado = resolver_data_relativa("2026-10-15", agora=AGORA)

        assert "T09:00" in resultado

    def test_formato_portugues_dd_mm_aaaa(self):
        assert _dia(resolver_data_relativa("15/10/2026", agora=AGORA)) == "2026-10-15"

    def test_data_impossivel_nao_e_adivinhada(self):
        assert resolver_data_relativa("31/02/2026", agora=AGORA) is None

    def test_amanha(self):
        assert _dia(resolver_data_relativa("amanhã", agora=AGORA)) == "2026-09-23"

    def test_amanha_sem_acento(self):
        # O modelo alterna entre as duas grafias; as duas têm de funcionar.
        assert _dia(resolver_data_relativa("amanha", agora=AGORA)) == "2026-09-23"

    def test_depois_de_amanha_nao_e_lido_como_amanha(self):
        assert _dia(resolver_data_relativa("depois de amanhã", agora=AGORA)) == "2026-09-24"

    def test_hoje(self):
        assert _dia(resolver_data_relativa("hoje", agora=AGORA)) == "2026-09-22"

    def test_amanha_de_manha_marca_as_nove(self):
        assert "T09:00" in resolver_data_relativa("amanhã de manhã", agora=AGORA)

    def test_amanha_a_tarde_marca_as_quinze(self):
        assert "T15:00" in resolver_data_relativa("amanhã à tarde", agora=AGORA)

    def test_hora_explicita_ganha_ao_periodo_do_dia(self):
        assert "T16:30" in resolver_data_relativa("amanhã às 16:30", agora=AGORA)

    def test_daqui_a_tres_dias(self):
        assert _dia(resolver_data_relativa("daqui a 3 dias", agora=AGORA)) == "2026-09-25"

    def test_daqui_a_duas_semanas_por_extenso(self):
        assert _dia(resolver_data_relativa("daqui a duas semanas", agora=AGORA)) == "2026-10-06"

    def test_dia_da_semana_futuro_na_mesma_semana(self):
        # Terça → a sexta seguinte é 25/09.
        assert _dia(resolver_data_relativa("sexta-feira", agora=AGORA)) == "2026-09-25"

    def test_dia_da_semana_ja_passado_vai_para_a_seguinte(self):
        # Terça → a segunda seguinte é 28/09, não a de ontem.
        assert _dia(resolver_data_relativa("segunda-feira", agora=AGORA)) == "2026-09-28"

    def test_o_proprio_dia_da_semana_vai_para_a_semana_seguinte(self):
        # Quem grava numa terça e diz "terça" não está a falar de hoje.
        assert _dia(resolver_data_relativa("terça-feira", agora=AGORA)) == "2026-09-29"

    def test_proxima_semana_cai_na_segunda(self):
        assert _dia(resolver_data_relativa("próxima semana", agora=AGORA)) == "2026-09-28"

    def test_final_do_mes(self):
        assert _dia(resolver_data_relativa("final do mês", agora=AGORA)) == "2026-09-30"

    def test_expressao_desconhecida_nao_inventa_data(self):
        # A regra do épico: sem prazo é melhor do que com prazo errado.
        assert resolver_data_relativa("quando o banco responder", agora=AGORA) is None

    def test_none_e_none(self):
        assert resolver_data_relativa(None, agora=AGORA) is None

    def test_string_vazia_e_none(self):
        assert resolver_data_relativa("   ", agora=AGORA) is None

    def test_datetime_ja_resolvido(self):
        alvo = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)

        assert resolver_data_relativa(alvo, agora=AGORA) == alvo.isoformat()


# ====================================================================
# NORMALIZAÇÃO
# ====================================================================


class TestNormalizarPrioridade:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            ("Alta", "Alta"),
            ("alta", "Alta"),
            ("urgente", "Alta"),
            ("baixa", "Baixa"),
            ("Média", "Média"),
            ("media", "Média"),
            ("normal", "Média"),
            ("", "Média"),
            (None, "Média"),
            ("catastrófica", "Média"),
        ],
    )
    def test_mapeia_para_os_valores_do_modelo(self, entrada, esperado):
        # Só "Alta"/"Média"/"Baixa" existem em `models/task.py`; qualquer
        # outra coisa gravada aqui rompia os filtros da lista de tarefas.
        assert normalizar_prioridade(entrada) == esperado


class TestNormalizarTarefa:
    def test_tarefa_completa(self):
        resultado = normalizar_tarefa(
            {
                "titulo": "Pedir avaliação do imóvel",
                "descricao": "Contactar o banco",
                "data_sugerida": "amanhã",
                "prioridade": "Alta",
            },
            agora=AGORA,
        )

        assert resultado["titulo"] == "Pedir avaliação do imóvel"
        assert _dia(resultado["due_date"]) == "2026-09-23"
        assert resultado["prioridade"] == "Alta"

    def test_sem_titulo_e_descartada(self):
        assert normalizar_tarefa({"descricao": "só descrição"}, agora=AGORA) is None

    def test_titulo_so_com_espacos_e_descartada(self):
        assert normalizar_tarefa({"titulo": "   "}, agora=AGORA) is None

    def test_entrada_que_nao_e_objecto_e_descartada(self):
        assert normalizar_tarefa("Ligar ao cliente", agora=AGORA) is None

    def test_nomes_de_campo_alternativos_do_modelo(self):
        # O prompt pede `titulo`/`data_sugerida`, mas o modelo improvisa.
        resultado = normalizar_tarefa(
            {"title": "Enviar simulação", "prazo": "amanhã", "priority": "alta"},
            agora=AGORA,
        )

        assert resultado["titulo"] == "Enviar simulação"
        assert _dia(resultado["due_date"]) == "2026-09-23"
        assert resultado["prioridade"] == "Alta"

    def test_guarda_a_expressao_original_da_data(self):
        # Quando não se consegue resolver, o consultor ainda vê o que disse.
        resultado = normalizar_tarefa(
            {"titulo": "Ligar", "data_sugerida": "quando o banco responder"},
            agora=AGORA,
        )

        assert resultado["due_date"] is None
        assert resultado["data_original"] == "quando o banco responder"

    def test_titulo_demasiado_longo_e_cortado(self):
        resultado = normalizar_tarefa({"titulo": "x" * 500}, agora=AGORA)

        assert len(resultado["titulo"]) == 200

    def test_espacos_e_quebras_de_linha_sao_colapsados(self):
        resultado = normalizar_tarefa(
            {"titulo": "Pedir\n\n  recibos   de vencimento"}, agora=AGORA
        )

        assert resultado["titulo"] == "Pedir recibos de vencimento"


class TestNormalizarExtraccao:
    def test_extraccao_tipica(self):
        resultado = normalizar_extraccao(
            {
                "resumo_timeline": "Cliente envia recibos.",
                "tarefas_extraidas": [
                    {"titulo": "Pedir recibos", "data_sugerida": "sexta-feira"},
                    {"titulo": "Marcar avaliação", "data_sugerida": "amanhã"},
                ],
            },
            agora=AGORA,
        )

        assert resultado["resumo_timeline"] == "Cliente envia recibos."
        assert len(resultado["tarefas_extraidas"]) == 2

    def test_tarefas_invalidas_sao_filtradas_sem_derrubar_as_boas(self):
        resultado = normalizar_extraccao(
            {
                "resumo_timeline": "Resumo",
                "tarefas_extraidas": [
                    "isto é uma string",
                    {"descricao": "sem título"},
                    {"titulo": "Esta é válida"},
                    None,
                ],
            },
            agora=AGORA,
        )

        assert [t["titulo"] for t in resultado["tarefas_extraidas"]] == ["Esta é válida"]

    def test_lista_em_falta_da_lista_vazia(self):
        resultado = normalizar_extraccao({"resumo_timeline": "Só resumo"}, agora=AGORA)

        assert resultado["tarefas_extraidas"] == []

    def test_lista_com_tipo_errado_nao_rebenta(self):
        resultado = normalizar_extraccao(
            {"resumo_timeline": "R", "tarefas_extraidas": "não é uma lista"},
            agora=AGORA,
        )

        assert resultado["tarefas_extraidas"] == []

    def test_excesso_de_tarefas_e_travado(self):
        # Um modelo a delirar não pode encher a lista do consultor.
        resultado = normalizar_extraccao(
            {
                "resumo_timeline": "R",
                "tarefas_extraidas": [{"titulo": f"T{i}"} for i in range(50)],
            },
            agora=AGORA,
        )

        assert len(resultado["tarefas_extraidas"]) == 10

    def test_payload_que_nao_e_objecto_da_forma_vazia(self):
        resultado = normalizar_extraccao(["lixo"], agora=AGORA)

        assert resultado == {"resumo_timeline": "", "tarefas_extraidas": []}

    def test_resumo_demasiado_longo_e_cortado(self):
        resultado = normalizar_extraccao(
            {"resumo_timeline": "a" * 5000}, agora=AGORA
        )

        assert len(resultado["resumo_timeline"]) == 1500


# ====================================================================
# PROMPT
# ====================================================================


class TestBuildUserPrompt:
    def test_inclui_a_transcricao(self):
        prompt = build_user_prompt("Ficou combinado enviar os recibos.")

        assert "Ficou combinado enviar os recibos." in prompt

    def test_contexto_entra_no_cabecalho(self):
        prompt = build_user_prompt(
            "texto",
            contexto={
                "hoje": "2026-09-22 (Tuesday)",
                "client_name": "Ana Martins",
                "process_ref": "PROC-012",
            },
        )

        assert "Ana Martins" in prompt
        assert "PROC-012" in prompt
        # A data de hoje é o que permite ao modelo resolver "sexta-feira".
        assert "2026-09-22" in prompt

    def test_sem_contexto_nao_deixa_cabecalho_vazio(self):
        prompt = build_user_prompt("texto")

        assert prompt.startswith("Transcrição da nota de voz:")
