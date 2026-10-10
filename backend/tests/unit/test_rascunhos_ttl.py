"""
Os rascunhos de email vivem 15 dias sem serem tocados (eram 7).

PORQUÊ
  Os rascunhos automáticos (confirmação de receção de documentos, lembretes)
  esperam por uma pessoa que pode estar de férias ou ocupada; ao fim de 7
  dias desapareciam sem ninguém os ter visto. O dono do produto fixou o
  mínimo em 15.

O NÚMERO TEM DE SER UM SÓ
  O índice TTL (`db_indexes`) e o diagnóstico (`diagnostics_ttl`, que compara
  o `expireAfterSeconds` do índice com o esperado) diziam «7 dias» cada um no
  seu ficheiro. Se um subir e o outro não, o diagnóstico acusa um índice
  correcto como desactualizado. Os dois derivam da mesma constante.
"""
from __future__ import annotations

import ast
from pathlib import Path

from services import db_indexes

RAIZ = Path(__file__).resolve().parents[2]
QUINZE_DIAS = 15 * 24 * 3600


def _indice_dos_rascunhos() -> dict:
    achados = [i for i in db_indexes.TTL_INDEXES if i["name"] == "ttl_email_drafts"]
    assert len(achados) == 1
    return achados[0]


def test_o_indice_dos_rascunhos_expira_ao_fim_de_15_dias():
    assert _indice_dos_rascunhos()["seconds"] == QUINZE_DIAS == 1_296_000


def test_a_constante_diz_15_dias():
    assert db_indexes.RASCUNHOS_TTL_DIAS == 15
    assert db_indexes.RASCUNHOS_TTL_SEGUNDOS == QUINZE_DIAS


def test_so_vale_para_rascunhos_e_pelo_campo_datetime_nativo():
    """Contraprova de que mudar o prazo não mexeu no resto do índice."""
    indice = _indice_dos_rascunhos()
    assert indice["collection"] == "emails"
    assert indice["field"] == "updated_at_dt"
    assert indice["partial_filter"] == {"status": "draft"}


def test_a_descricao_nao_continua_a_dizer_7_dias():
    assert "15 dias" in _indice_dos_rascunhos()["description"]
    assert "7 dias" not in _indice_dos_rascunhos()["description"]


def test_o_diagnostico_deriva_da_mesma_constante():
    fonte = (RAIZ / "services" / "diagnostics_ttl.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    importa = any(
        isinstance(no, ast.ImportFrom) and no.module == "services.db_indexes"
        and {a.name for a in no.names} >= {"RASCUNHOS_TTL_DIAS", "RASCUNHOS_TTL_SEGUNDOS"}
        for no in ast.walk(arvore)
    )
    assert importa, "o diagnóstico tem de importar a constante, não repetir o número"
    assert "604800" not in fonte.split('"name": "emails"')[1].split("]")[0]


def test_nenhum_outro_ttl_foi_alterado():
    por_nome = {i["name"]: i["seconds"] for i in db_indexes.TTL_INDEXES}
    assert por_nome["ttl_refresh_tokens"] == 86_400
    assert por_nome["ttl_system_error_logs"] == 2_592_000
    assert por_nome["ttl_task_queue"] == 604_800
