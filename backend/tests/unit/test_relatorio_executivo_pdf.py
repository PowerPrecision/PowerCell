"""O PDF do relatório executivo (Bloco 4, ponto 16)."""
from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

import services.executive_report_pdf as pdf


def _relatorio(**extra):
    base = {
        "start_date": "2026-10-05", "end_date": "2026-10-11",
        "gerado_em": "2026-10-12T10:00:00+00:00",
        "filtros": {"user_ids": [], "papeis": []},
        "summary": {"total_phase_changes": 6, "total_processes_moved": 4,
                    "total_tasks_completed": 10, "total_tasks_pending": 4, "total_tasks_overdue": 1},
        "users": [
            {"name": "Ana Silva", "role": "consultor", "phase_changes": 5, "processes_moved": 3,
             "tasks_completed": 2, "tasks_pending": 4, "tasks_overdue": 1},
            {"name": "Zé Silenciado", "role": "diretor", "phase_changes": None, "processes_moved": None,
             "tasks_completed": 1, "tasks_pending": 0, "tasks_overdue": 0},
        ],
        "por_fase": [{"fase": "aprovado", "rotulo": "Aprovado", "n": 5}],
        "serie_diaria": [{"dia": f"2026-10-0{i}", "mudancas_de_fase": i, "tarefas_concluidas": 1} for i in range(5, 9)],
        "notas": ["Tarefa concluída conta a quem a concluiu."],
    }
    base.update(extra)
    return base


def _texto(conteudo: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(conteudo)).pages)


class TestOConteudo:
    def test_e_um_pdf_com_titulo_periodo_e_proveniencia(self):
        t = _texto(pdf.construir_pdf(_relatorio(), empresa={"nome": "Power"}, gerado_por="Cátia"))
        assert "Relatório Executivo" in t
        assert "05/10/2026" in t and "11/10/2026" in t
        assert "Gerado em 12/10/2026 por Cátia" in t
        assert "toda a equipa" in t

    def test_historico_desligado_aparece_como_traco_e_nao_zero(self):
        linhas = pdf.linhas_da_tabela(_relatorio())
        zé = next(l for l in linhas if l[0].startswith("Zé"))
        assert zé[2] == "—" and zé[3] == "—" and zé[4] == "1"

    def test_a_tabela_lista_todas_as_pessoas_mesmo_alem_do_grafico(self):
        users = [{"name": f"P{i}", "role": "consultor", "phase_changes": i, "processes_moved": i,
                  "tasks_completed": 0, "tasks_pending": 0, "tasks_overdue": 0} for i in range(30)]
        assert len(pdf.linhas_da_tabela(_relatorio(users=users))) == 31
        nomes, series = pdf.dados_do_grafico_de_pessoas(_relatorio(users=users))
        assert len(nomes) == pdf.MAX_PESSOAS_NO_GRAFICO and nomes[0] == "P29"
        assert all(len(s) == len(nomes) for s in series)

    def test_os_filtros_aplicados_ficam_escritos(self):
        t = _texto(pdf.construir_pdf(_relatorio(filtros={"user_ids": ["a", "b"], "papeis": ["consultor"]})))
        assert "2 utilizador(es)" in t and "Consultor" in t

    def test_movimentos_so_no_relatorio_semanal(self):
        sem = _texto(pdf.construir_pdf(_relatorio()))
        com = _texto(pdf.construir_pdf(_relatorio(movimentos=[
            {"em": "2026-10-06T10:00:00", "user_name": "Ana", "process_number": 12,
             "de_rotulo": "Documental", "para_rotulo": "Aprovado"}]), titulo="Relatório Semanal Executivo"))
        assert "Movimentos de fase" not in sem
        assert "Movimentos de fase" in com and "#12" in com and "Relatório Semanal Executivo" in com

    def test_periodo_longo_diz_que_omitiu_a_evolucao(self):
        t = _texto(pdf.construir_pdf(_relatorio(serie_diaria=[], serie_omitida=True)))
        assert "excede 92 dias" in t

    def test_sem_ninguem_o_pdf_sai_na_mesma(self):
        t = _texto(pdf.construir_pdf(_relatorio(users=[], por_fase=[], serie_diaria=[])))
        assert "Detalhe por colaborador" in t

    def test_nomes_com_marcas_xml_nao_partem_o_pdf(self):
        u = [{"name": "<b>Ana</b> & Rui", "role": "consultor", "phase_changes": 1, "processes_moved": 1,
              "tasks_completed": 0, "tasks_pending": 0, "tasks_overdue": 0}]
        assert _texto(pdf.construir_pdf(_relatorio(users=u))).count("Ana") >= 1

    def test_logotipo_invalido_e_ignorado(self):
        assert pdf.construir_pdf(_relatorio(), logo_bytes=b"isto nao e uma imagem")[:5] == b"%PDF-"

    def test_formatar_data(self):
        assert pdf.formatar_data("2026-10-05T10:00:00+00:00") == "05/10/2026"
        assert pdf.formatar_data("lixo") == "lixo"
        assert pdf.formatar_data(None) == "—"

    def test_nome_do_ficheiro(self):
        assert pdf.nome_do_ficheiro(_relatorio(), "relatorio-semanal") == "relatorio-semanal_2026-10-05_2026-10-11.pdf"
