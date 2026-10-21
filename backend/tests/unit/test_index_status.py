"""`index_status` — ponto único do estado de indexação (Lote 12, Fase 1)."""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from services import index_status as ist
from services import index_status_migration as mig
from services import process_indexing

SERVICOS = Path(__file__).resolve().parents[2] / "services"
USER = {"id": "u-index", "name": "Ivo Index"}
AGORA = "2026-10-21T10:00:00+00:00"


# ── a derivação ────────────────────────────────────────────────────────────
class TestDerivarEstado:
    @pytest.mark.parametrize(
        "doc, estado, dispensado",
        [
            ({}, "pending", False),
            ({"is_indexed": False}, "pending", False),
            ({"is_indexed": True}, "indexed", False),
            ({"skip_index": True}, "indexed", True),
            ({"assigned_indexacao_id": "u1"}, "in_review", False),
            ({"index_status": "in_review"}, "in_review", False),
            # quem indexou vence a dispensa: foi uma pessoa
            ({"is_indexed": True, "skip_index": True}, "indexed", False),
            # a dispensa vence um indexador atribuído (nunca entra em fila)
            ({"skip_index": True, "assigned_indexacao_id": "u1"}, "indexed", True),
        ],
    )
    def test_casos(self, doc, estado, dispensado):
        assert ist.derivar_estado(doc) == {"index_status": estado, "index_skipped": dispensado}

    @pytest.mark.parametrize("flag", ["true", 1, "x", "false"])
    def test_a_flag_e_estrita(self, flag):
        # `"false"` e `1` não são a flag ligada (True estrito, como o resto do projecto)
        assert ist.derivar_estado({"is_indexed": flag})["index_status"] == "pending"
        assert ist.derivar_estado({"skip_index": flag})["index_status"] == "pending"

    @pytest.mark.parametrize("lixo", [None, [], "x", 3])
    def test_nunca_levanta(self, lixo):
        assert ist.derivar_estado(lixo)["index_status"] == "pending"


class TestEstadoApos:
    def test_desligar_indexado_volta_a_fila_apesar_do_estado_antigo(self):
        # o documento diz index_status=indexed; a alteração desliga is_indexed
        r = ist.estado_apos({"is_indexed": True, "index_status": "indexed"}, {"is_indexed": False})
        assert r == {"index_status": "pending", "index_skipped": False}

    def test_ligar_skip_index_dispensa(self):
        r = ist.estado_apos({"index_status": "pending"}, {"skip_index": True})
        assert r == {"index_status": "indexed", "index_skipped": True}

    def test_desligar_skip_index_num_processo_ja_indexado_continua_indexado(self):
        # quem foi indexado por uma pessoa e perdeu a dispensa NÃO volta à fila
        r = ist.estado_apos(
            {"is_indexed": True, "skip_index": True, "index_status": "indexed"},
            {"skip_index": False},
        )
        assert r == {"index_status": "indexed", "index_skipped": False}

    def test_desligar_skip_index_num_processo_dispensado_vai_para_a_fila(self):
        r = ist.estado_apos(
            {"skip_index": True, "index_status": "indexed", "index_skipped": True},
            {"skip_index": False},
        )
        assert r == {"index_status": "pending", "index_skipped": False}

    def test_nao_muta_os_argumentos(self):
        atual, alt = {"is_indexed": True, "index_status": "indexed"}, {"is_indexed": False}
        ist.estado_apos(atual, alt)
        assert atual == {"is_indexed": True, "index_status": "indexed"}
        assert alt == {"is_indexed": False}


class TestCamposDosEscritores:
    def test_ao_indexar_grava_estado_e_derivado_no_mesmo_set(self):
        c = ist.campos_ao_indexar(USER, AGORA)
        assert c["index_status"] == "indexed" and c["is_indexed"] is True
        assert c["index_skipped"] is False
        assert c["indexed_at"] == AGORA and c["indexed_by"] == "u-index"

    def test_ao_reverter_um_processo_normal_volta_a_pending(self):
        c = ist.campos_ao_reverter({"is_indexed": True}, USER, AGORA)
        assert c["index_status"] == "pending" and c["is_indexed"] is False
        assert c["unindexed_at"] == AGORA

    def test_ao_reverter_um_dispensado_continua_dispensado(self):
        c = ist.campos_ao_reverter({"is_indexed": True, "skip_index": True}, USER, AGORA)
        assert c["index_status"] == "indexed" and c["index_skipped"] is True
        assert c["is_indexed"] is False

    def test_aplicar_ao_documento_novo(self):
        assert ist.aplicar_ao_documento({"skip_index": True})["index_status"] == "indexed"
        assert ist.aplicar_ao_documento({})["index_status"] == "pending"


# ── os escritores reais delegam ────────────────────────────────────────────
class TestOsEscritoresDeProducaoDelegam:
    def test_build_indexacao_update_set_leva_o_estado(self):
        s = process_indexing.build_indexacao_update_set(USER, AGORA, "analise")
        assert s["index_status"] == "indexed"
        assert s["is_indexed"] is True
        assert s["index_skipped"] is False
        assert s["status"] == "analise"
        assert s["assigned_indexacao_id"] is None  # o resto do contrato não mudou

    def test_build_unindex_update_set_respeita_a_dispensa(self):
        s = process_indexing.build_unindex_update_set(USER, AGORA, {"is_indexed": True, "skip_index": True})
        assert (s["index_status"], s["index_skipped"], s["is_indexed"]) == ("indexed", True, False)
        s2 = process_indexing.build_unindex_update_set(USER, AGORA, {"is_indexed": True})
        assert (s2["index_status"], s2["is_indexed"]) == ("pending", False)

    def test_build_unindex_sem_processo_assume_normal(self):
        assert process_indexing.build_unindex_update_set(USER, AGORA)["index_status"] == "pending"


class TestOGanchoDoRegimeCobreOsCaminhosTodos:
    @pytest.mark.asyncio
    async def test_processo_normal_nasce_pending(self):
        from services import network_triage

        async def _nao(_):
            return False

        with patch.object(network_triage, "rede_do_processo_sem_index", _nao):
            doc = {}
            assert await network_triage.aplicar_regime_de_indexacao(doc) is False
        assert doc["index_status"] == "pending" and doc["index_skipped"] is False

    @pytest.mark.asyncio
    async def test_rede_sem_index_nasce_dispensada(self):
        from services import network_triage

        async def _sim(_):
            return True

        with patch.object(network_triage, "rede_do_processo_sem_index", _sim):
            doc = {}
            assert await network_triage.aplicar_regime_de_indexacao(doc) is True
        assert doc["skip_index"] is True
        assert (doc["index_status"], doc["index_skipped"]) == ("indexed", True)

    @pytest.mark.asyncio
    async def test_skip_index_pedido_pelo_escritor_tambem_e_coberto(self):
        # `process_create` grava skip_index=True ANTES do regime: o estado tem de o ver
        from services import network_triage

        async def _nao(_):
            return False

        with patch.object(network_triage, "rede_do_processo_sem_index", _nao):
            doc = {"skip_index": True}
            await network_triage.aplicar_regime_de_indexacao(doc)
        assert (doc["index_status"], doc["index_skipped"]) == ("indexed", True)

    @pytest.mark.asyncio
    async def test_falha_a_decidir_o_regime_nao_derruba_e_deixa_estado(self):
        from services import network_triage

        async def _rebenta(_):
            raise RuntimeError("bd em baixo")

        with patch.object(network_triage, "rede_do_processo_sem_index", _rebenta):
            doc = {}
            assert await network_triage.aplicar_regime_de_indexacao(doc) is False
        assert doc["index_status"] == "pending"


# ── transições assíncronas ─────────────────────────────────────────────────
class TestReivindicarEDevolver:
    @pytest.mark.asyncio
    async def test_claim_e_devolver(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "p1", "index_status": "pending"})
        with patch.object(ist, "db", fake_async_db):
            r = await ist.reivindicar("p1")
            assert r == {"alterado": True, "estado": "in_review"}
            # idempotente
            assert (await ist.reivindicar("p1"))["alterado"] is False
            assert (await ist.devolver_a_fila("p1"))["alterado"] is True
            assert (await ist.devolver_a_fila("p1"))["alterado"] is False
        doc = await fake_async_db.processes.find_one({"id": "p1"})
        assert doc["index_status"] == "pending"

    @pytest.mark.asyncio
    async def test_claim_nunca_toca_num_indexado_nem_dispensado(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "i", "is_indexed": True, "index_status": "indexed"})
        await fake_async_db.processes.insert_one(
            {"id": "d", "skip_index": True, "index_status": "indexed", "index_skipped": True}
        )
        with patch.object(ist, "db", fake_async_db):
            ri = await ist.reivindicar("i")
            rd = await ist.reivindicar("d")
        assert ri == {"alterado": False, "estado": "indexed"}
        assert rd == {"alterado": False, "estado": "indexed"}
        assert (await fake_async_db.processes.find_one({"id": "i"}))["index_status"] == "indexed"
        assert (await fake_async_db.processes.find_one({"id": "d"}))["index_status"] == "indexed"

    @pytest.mark.asyncio
    async def test_devolver_nao_desfaz_um_indexado(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "i", "is_indexed": True, "index_status": "indexed"})
        with patch.object(ist, "db", fake_async_db):
            assert (await ist.devolver_a_fila("i"))["alterado"] is False
        assert (await fake_async_db.processes.find_one({"id": "i"}))["index_status"] == "indexed"

    @pytest.mark.asyncio
    async def test_processo_eliminado_nao_e_reivindicado(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "x", "is_deleted": True, "index_status": "pending"})
        with patch.object(ist, "db", fake_async_db):
            assert (await ist.reivindicar("x"))["alterado"] is False


class TestContadores:
    @pytest.mark.asyncio
    async def test_grava_e_trunca_a_zero(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "p1"})
        with patch.object(ist, "db", fake_async_db):
            await ist.gravar_contadores("p1", has_pending_review=True, index_alerts_open=-3)
        d = await fake_async_db.processes.find_one({"id": "p1"})
        assert d["has_pending_review"] is True and d["index_alerts_open"] == 0

    @pytest.mark.asyncio
    async def test_nunca_propaga(self):
        class Rebenta:
            class processes:
                @staticmethod
                async def update_one(*a, **k):
                    raise RuntimeError("bd em baixo")

        with patch.object(ist, "db", Rebenta):
            await ist.gravar_contadores("p1", has_pending_review=True)  # não levanta

    @pytest.mark.asyncio
    async def test_sem_nada_para_gravar_nao_toca_na_bd(self):
        class Proibida:
            def __getattr__(self, _):
                raise AssertionError("não devia tocar na BD")

        with patch.object(ist, "db", Proibida()):
            await ist.gravar_contadores("p1")


# ── a condição da fila ─────────────────────────────────────────────────────
class TestCondicaoDaFila:
    def test_aba_desconhecida_e_impossivel_nunca_vazia(self):
        c = ist.condicao_da_fila("qualquer")
        assert c != {} and c == {"id": {"$in": []}}

    def test_pending_tolera_legado_sem_index_status(self):
        c = ist.condicao_da_fila("pending")
        ramos = c["$and"]
        assert {"is_indexed": {"$ne": True}} in ramos
        assert {"skip_index": {"$ne": True}} in ramos
        assert {"$or": [
            {"index_status": {"$in": ["pending", "in_review"]}},
            {"index_status": {"$exists": False}},
        ]} in ramos

    def test_reviews_exige_indexado_por_pessoa_e_revisao(self):
        assert ist.condicao_da_fila("reviews") == {"is_indexed": True, "has_pending_review": True}


# ── ponto único (guarda por AST) ───────────────────────────────────────────
def _e_projeccao(valor: ast.AST) -> bool:
    """`{"campo": 1}` é uma PROJECÇÃO (leitura), não uma escrita."""
    return isinstance(valor, ast.Constant) and valor.value in (0, 1) and not isinstance(valor.value, bool)


def _chaves_de_dicts_com(nome: str, fonte: str) -> list[int]:
    """Linhas onde um dict literal ESCREVE `nome` (chave com valor), ou há `x["nome"] = …`.

    Uma projecção (`{"nome": 1}`) lê, não escreve: não conta.
    """
    arvore = ast.parse(fonte)
    linhas: list[int] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Dict):
            for k, v in zip(no.keys, no.values):
                if isinstance(k, ast.Constant) and k.value == nome and not _e_projeccao(v):
                    linhas.append(no.lineno)
        elif isinstance(no, ast.Assign):
            for alvo in no.targets:
                if (
                    isinstance(alvo, ast.Subscript)
                    and isinstance(alvo.slice, ast.Constant)
                    and alvo.slice.value == nome
                ):
                    linhas.append(no.lineno)
    return linhas


class TestUmSoEscritor:
    #: Quem pode ESCREVER `index_status`: o próprio módulo (e o `$set` da migração vem dele).
    PERMITIDOS = {"index_status.py"}

    def test_ninguem_fora_do_modulo_escreve_index_status_a_mao(self):
        intrusos = []
        for ficheiro in sorted(SERVICOS.glob("*.py")):
            if ficheiro.name in self.PERMITIDOS:
                continue
            if _chaves_de_dicts_com("index_status", ficheiro.read_text(encoding="utf-8")):
                intrusos.append(ficheiro.name)
        assert intrusos == [], f"escritores de index_status à margem do ponto único: {intrusos}"

    def test_contraprova_o_leitor_ve_o_proprio_modulo(self):
        fonte = (SERVICOS / "index_status.py").read_text(encoding="utf-8")
        assert _chaves_de_dicts_com("index_status", fonte), "o leitor ficou cego"

    def test_contraprova_apanha_um_escritor_a_mao(self):
        assert _chaves_de_dicts_com("index_status", 'x = {"index_status": "indexed"}')
        assert _chaves_de_dicts_com("index_status", 'doc["index_status"] = "indexed"')
        # …mas uma projecção não é uma escrita
        assert not _chaves_de_dicts_com("index_status", 'p = {"index_status": 1}')

    def test_os_dois_construtores_de_process_indexing_nao_escrevem_is_indexed_a_mao(self):
        fonte = (SERVICOS / "process_indexing.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        for no in ast.walk(arvore):
            if isinstance(no, ast.FunctionDef) and no.name in {
                "build_indexacao_update_set",
                "build_unindex_update_set",
            }:
                assert not _chaves_de_dicts_com("is_indexed", ast.unparse(no)), no.name
                corpo = ast.unparse(no)
                assert "campos_ao_indexar" in corpo or "campos_ao_reverter" in corpo, no.name

    def test_os_escritores_de_skip_index_chamam_o_estado(self):
        # contraprova de ligação: apagar a chamada parte este teste
        assert "aplicar_ao_documento(process_doc)" in (SERVICOS / "network_triage.py").read_text(encoding="utf-8")
        assert "estado_apos(processo, atualizacao)" in (SERVICOS / "network_triage.py").read_text(encoding="utf-8")
        assert "estado_apos(process, update_data)" in (SERVICOS / "process_update.py").read_text(encoding="utf-8")


# ── migração ───────────────────────────────────────────────────────────────
class TestMigracao:
    DOCS = [
        {"id": "a", "is_indexed": True},
        {"id": "b", "is_indexed": False},
        {"id": "c"},
        {"id": "d", "skip_index": True},
        {"id": "e", "assigned_indexacao_id": "u1"},
        {"id": "f", "is_indexed": True, "index_status": "indexed", "index_skipped": False},  # já certo
    ]

    def test_plano_por_processo(self):
        assert mig.plano_do_processo(self.DOCS[0]) == {"index_status": "indexed", "index_skipped": False}
        assert mig.plano_do_processo(self.DOCS[3]) == {"index_status": "indexed", "index_skipped": True}
        assert mig.plano_do_processo(self.DOCS[4]) == {"index_status": "in_review", "index_skipped": False}
        assert mig.plano_do_processo(self.DOCS[5]) is None

    def test_resumo(self):
        r = mig.resumo(self.DOCS)
        assert r["total"] == 6 and r["a_escrever"] == 5
        assert r["por_estado"] == {"indexed": 1, "pending": 2, "indexed+dispensado": 1, "in_review": 1}

    @pytest.mark.asyncio
    async def test_aplicar_e_idempotente(self, fake_async_db):
        for d in self.DOCS:
            await fake_async_db.processes.insert_one(dict(d))
        docs = await mig.ler_processos(fake_async_db)
        assert await mig.aplicar(fake_async_db, docs) == 5
        docs = await mig.ler_processos(fake_async_db)
        assert mig.resumo(docs)["a_escrever"] == 0
        assert await mig.aplicar(fake_async_db, docs) == 0  # a 2.ª passagem escreve 0

    @pytest.mark.asyncio
    async def test_nao_pisa_um_processo_que_mudou_entretanto(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "p", "is_indexed": False})
        lidos = await mig.ler_processos(fake_async_db)
        # outro escritor indexa-o depois da leitura
        await fake_async_db.processes.update_one({"id": "p"}, {"$set": {"is_indexed": True}})
        assert await mig.aplicar(fake_async_db, lidos) == 0
        d = await fake_async_db.processes.find_one({"id": "p"})
        assert "index_status" not in d  # não foi gravado «pending» por cima de um indexado

    @pytest.mark.asyncio
    async def test_so_toca_em_estado_nunca_noutros_campos(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "p", "is_indexed": True, "skip_index": True, "x": 1})
        await mig.aplicar(fake_async_db, await mig.ler_processos(fake_async_db))
        d = await fake_async_db.processes.find_one({"id": "p"})
        assert d["is_indexed"] is True and d["skip_index"] is True and d["x"] == 1

    @pytest.mark.asyncio
    async def test_eliminados_ficam_de_fora(self, fake_async_db):
        await fake_async_db.processes.insert_one({"id": "z", "is_deleted": True})
        assert await mig.ler_processos(fake_async_db) == []

    def test_o_script_nao_tem_derivacao_propria(self):
        fonte = (SERVICOS / "index_status_migration.py").read_text(encoding="utf-8")
        assert "derivar_estado" in fonte
        assert '"is_indexed": True' not in fonte


class TestIndicesDeclarados:
    def test_estao_em_db_indexes(self):
        from services.db_indexes import INDEX_DEFINITIONS

        def nomes(col):
            return {i["name"] for i in INDEX_DEFINITIONS.get(col, [])}

        assert {"idx_index_fila", "idx_index_revisoes"} <= nomes("processes")
        assert {"idx_prof_meta_processo", "idx_prof_meta_rede_nif"} <= nomes("process_professional_metadata")
        assert "idx_employers_nif" in nomes("employers")
        assert "idx_index_alerts_processo" in nomes("process_index_alerts")
        assert "idx_index_job_activo_unico" in nomes("task_logs")

    def test_unicidade_onde_a_regra_a_exige(self):
        from services.db_indexes import INDEX_DEFINITIONS

        por_nome = {i["name"]: i for lista in INDEX_DEFINITIONS.values() for i in lista}
        assert por_nome["idx_prof_meta_processo"]["unique"] is True
        assert por_nome["idx_employers_nif"]["unique"] is True
        job = por_nome["idx_index_job_activo_unico"]
        assert job["unique"] is True
        assert job["partialFilterExpression"] == {"index_job_key": {"$type": "string"}}

    def test_a_fila_abre_pela_rede(self):
        from services.db_indexes import INDEX_DEFINITIONS

        por_nome = {i["name"]: i for i in INDEX_DEFINITIONS["processes"]}
        assert por_nome["idx_index_fila"]["keys"][0] == ("network_id", 1)
        assert por_nome["idx_index_revisoes"]["keys"][0] == ("network_id", 1)
