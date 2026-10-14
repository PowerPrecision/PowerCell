"""D-13 passo 1 e D-15 — as medições são só de leitura e classificam o que dizem.

Parte PURA (o que corre no `backend-fast`, sem Mongo). A semântica de tipos do Mongo
(datetime vs texto ISO) prova-se contra um mongod real em
`tests/integration/test_medicoes_de_dados_mongo.py`.
"""
from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from services import birthdate_exposure_audit as b
from services import db_storage_audit as d

RAIZ = Path(__file__).resolve().parents[2]
AGORA = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


# ───────────────────────────── D-13: pura ─────────────────────────────

class TestLinhaDeCollstats:
    def test_traduz_os_tamanhos(self):
        l = d.linha_de_collstats("history", {"count": 10, "size": 5000, "totalIndexSize": 700, "storageSize": 9000})
        assert (l.documentos, l.bytes_dados, l.bytes_indices, l.bytes_armazenados) == (10, 5000, 700, 9000)
        assert l.bytes_totais == 5700
        assert l.media_por_documento == 500

    def test_colecao_inexistente_nao_e_zero_bytes(self):
        l = d.linha_de_collstats("nao_existe", None)
        assert l.existe is False
        assert l.aviso

    def test_lixo_nos_stats_vira_zero_e_nunca_levanta(self):
        l = d.linha_de_collstats("x", {"count": None, "size": "abc", "totalIndexSize": -5})
        assert (l.documentos, l.bytes_dados, l.bytes_indices) == (0, 0, 0)

    def test_media_com_zero_documentos_nao_divide_por_zero(self):
        assert d.linha_de_collstats("x", {"count": 0, "size": 0}).media_por_documento == 0


class TestCondicoesDeIdade:
    def test_cobre_os_dois_tipos_de_data(self):
        cond = d.condicao_mais_antigo_que("created_at", AGORA, 90)
        ramos = cond["$or"]
        assert len(ramos) == 2
        limites = [list(r["created_at"].values())[0] for r in ramos]
        assert {type(x) for x in limites} == {datetime, str}

    def test_o_corte_em_texto_e_o_mesmo_instante_do_datetime(self):
        limite, limite_iso = d.corte_em(AGORA, 90)
        assert limite == AGORA - timedelta(days=90)
        assert datetime.fromisoformat(limite_iso) == limite

    def test_datetime_sem_fuso_conta_como_utc(self):
        _, iso = d.corte_em(datetime(2026, 10, 14, 12, 0), 1)
        assert iso.endswith("+00:00")

    def test_formato_do_texto_ordena_como_o_isoformat_gravado(self):
        # `datetime.now(timezone.utc).isoformat()` é o que as colecções gravam; a comparação
        # lexicográfica só serve se o corte tiver o MESMO formato.
        gravado = (AGORA - timedelta(days=200)).isoformat()
        _, corte = d.corte_em(AGORA, 90)
        assert gravado < corte
        recente = (AGORA - timedelta(days=5)).isoformat()
        assert not recente < corte

    def test_sem_data_exclui_datas_e_texto(self):
        cond = d.condicao_sem_data("x")
        tipos = {list(r["x"].values())[0] for r in cond["$nor"]}
        assert tipos == {"date", "string"}


class TestEscolherCampo:
    def test_primeiro_candidato_com_documentos(self):
        assert d.escolher_campo_de_data({"a": 0, "b": 3, "c": 9}, ["a", "b", "c"]) == "b"

    def test_nenhum_com_documentos_devolve_none(self):
        assert d.escolher_campo_de_data({"a": 0}, ["a", "b"]) is None

    def test_todas_as_colecoes_tem_candidatos(self):
        assert all(c for c in d.COLECCOES_MEDIDAS.values())


def _linha(nome, dados, antigos_365=None, docs=100, sem_data=0):
    l = d.LinhaDaColeccao(nome=nome, documentos=docs, bytes_dados=dados, sem_data=sem_data)
    if antigos_365 is not None:
        l.mais_antigos_que[365] = antigos_365
    return l


class TestPontosDeAtencao:
    def test_ordena_por_peso(self):
        ls = [_linha("a", 10), _linha("b", 1000), _linha("c", 100)]
        assert [l.nome for l in d.ordenar_por_peso(ls)] == ["b", "c", "a"]

    def test_pesada_e_antiga_e_ponto_de_atencao(self):
        ls = [_linha("history", 9000, antigos_365=80), _linha("pequena", 100, antigos_365=100)]
        assert [n for n, _ in d.pontos_de_atencao(ls)] == ["history"]

    def test_pesada_mas_recente_nao_e(self):
        ls = [_linha("emails", 9000, antigos_365=5), _linha("x", 100)]
        assert d.pontos_de_atencao(ls) == []

    def test_pesada_sem_data_diz_que_a_idade_nao_se_mede(self):
        ls = [_linha("emails", 9000, sem_data=100), _linha("x", 100)]
        (nome, motivo), = d.pontos_de_atencao(ls)
        assert nome == "emails" and "não se mede" in motivo

    def test_inexistente_nunca_e_candidata(self):
        ls = [d.linha_de_collstats("nao_existe", None), _linha("x", 100, antigos_365=100)]
        assert "nao_existe" not in [n for n, _ in d.pontos_de_atencao(ls)]

    def test_fatia_so_conta_documentos_com_data(self):
        l = _linha("x", 1, antigos_365=30, docs=100, sem_data=40)
        assert l.fatia_mais_antiga_que(365) == pytest.approx(0.5)

    def test_fatia_sem_medicao_e_none_e_nao_zero(self):
        assert _linha("x", 1).fatia_mais_antiga_que(365) is None

    def test_formatar_bytes(self):
        assert d.formatar_bytes(512) == "512 B"
        assert d.formatar_bytes(2048) == "2.0 KB"
        assert d.formatar_bytes(5 * 1024 ** 3) == "5.0 GB"


# ───────────────────────────── D-15: pura ─────────────────────────────

class TestEstadoDoValor:
    @pytest.mark.parametrize("valor,estado", [
        (None, b.VAZIO), ("", b.VAZIO), ("   ", b.VAZIO),
        ("1990-03-04", b.ISO), ("1990-03-04T00:00:00", b.ISO),
        (datetime(1990, 3, 4), b.ISO),
        ("25/03/1988", b.OUTRO), ("abc", b.OUTRO), (1990, b.OUTRO),
    ])
    def test_classificacao(self, valor, estado):
        assert b.estado_do_valor(valor) == estado

    def test_valor_encriptado_e_cifrado(self):
        from services.encryption import EncryptionService
        assert b.estado_do_valor(EncryptionService.ENCRYPTION_PREFIX + "xyz") == b.CIFRADO


class TestAuditoria:
    def test_conta_escalares_e_listas(self):
        docs = [
            {"personal_data": {"birth_date": "1990-01-01"}, "co_buyers": [{"data_nascimento": "1985-05-05"}, {"data_nascimento": ""}]},
            {"personal_data": {"data_nascimento": "25/03/1988"}},
            {},
        ]
        r = b.auditar("processes", docs)
        resumo = b.resumir(r)
        assert resumo["documentos"] == {"processes": 3}
        assert resumo["com_data_em_claro"] == {"processes": 1}
        assert resumo["total_em_claro"] == 2        # escalar + co_buyer
        assert resumo["total_outro"] == 1
        assert "co_buyers[].data_nascimento" in resumo["por_colecao"]["processes"]

    def test_resumo_omite_caminhos_sem_nenhum_valor(self):
        r = b.auditar("clients", [{}, {}])
        assert b.resumir(r)["por_colecao"] == {}

    def test_projeccao_traz_todos_os_caminhos_que_a_auditoria_le(self):
        proj = b.projeccao("processes")
        for c in b.caminhos_de_uma_colecao("processes"):
            assert c in proj
        assert "co_buyers.data_nascimento" in proj

    def test_os_nomes_de_campo_vem_da_regra_sub35(self):
        from services.sub35 import CAMPOS_DE_NASCIMENTO
        assert b.CAMPOS_DE_NASCIMENTO is CAMPOS_DE_NASCIMENTO

    def test_o_relatorio_nunca_guarda_valores(self):
        r = b.auditar("clients", [{"dados_pessoais": {"birth_date": "1990-01-01"}}])
        assert "1990" not in repr(b.resumir(r))


# ─────────────────── os dois scripts são só de leitura ────────────────────

ESCRITAS = {"insert_one", "insert_many", "update_one", "update_many", "replace_one", "delete_one",
            "delete_many", "drop", "create_index", "bulk_write", "find_one_and_update",
            "find_one_and_delete", "find_one_and_replace", "drop_collection", "rename"}


def _chamadas(caminho: Path) -> set[str]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    return {n.func.attr for n in ast.walk(arvore)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}


@pytest.mark.parametrize("ficheiro", [
    "scripts/medir_colecoes.py",
    "scripts/medir_datas_de_nascimento.py",
    "services/db_storage_audit.py",
    "services/birthdate_exposure_audit.py",
])
def test_nenhuma_escrita(ficheiro):
    assert _chamadas(RAIZ / ficheiro) & ESCRITAS == set()


@pytest.mark.parametrize("ficheiro", ["scripts/medir_colecoes.py", "scripts/medir_datas_de_nascimento.py"])
def test_corre_contra_producao_de_proposito(ficheiro):
    """Sem `require_non_production_db`: a pergunta está nos dados reais."""
    assert "require_non_production_db" not in (RAIZ / ficheiro).read_text(encoding="utf-8").split('"""')[2]


def test_contraprova_o_detector_de_escritas_detecta():
    arvore = ast.parse("db.x.insert_one({})")
    achadas = {n.func.attr for n in ast.walk(arvore) if isinstance(n, ast.Call)}
    assert achadas & ESCRITAS


def test_o_script_da_d13_so_mede_colecoes_declaradas():
    texto = (RAIZ / "scripts/medir_colecoes.py").read_text(encoding="utf-8")
    assert "COLECCOES_MEDIDAS" in texto
