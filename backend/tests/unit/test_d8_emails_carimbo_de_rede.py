"""
D-8 — os emails nascem com `network_id`.

REGRAS PROVADAS
  * uma candidata é uma resposta; duas diferentes NÃO se resolvem (nem por
    maioria nem por prioridade): fica por carimbar, com aviso;
  * o processo é uma fonte; a empresa do email é outra; sem nenhuma não se
    carimba (meio carimbo é pior do que nenhum);
  * nunca se sobrepõe um carimbo que o escritor já tenha posto;
  * o carimbo NUNCA derruba a escrita (falha → email por carimbar);
  * TODOS os escritores passam pelo ponto único (inventário por AST, com
    contraprova), e o backfill usa a MESMA função de produção.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services import email_tenant_stamp as et
from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_DOMUS,
    REDE_INCUMBENTE,
    semear,
)

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
def db(fake_async_db):
    semear(fake_async_db)
    fake_async_db.companies.docs.append({"id": "cmp-ilha", "name": "Sem Grupo"})  # sem network_id
    fake_async_db.processes.docs.extend([
        {"id": "p-com-empresa", "company_id": "cmp-domus"},  # entre o carimbo e a migração
        {"id": "p-sem-nada"},
    ])
    return fake_async_db


def _email(**campos):
    return {"id": "e1", "subject": "x", **campos}


class TestAPuraDoConsenso:
    def test_uma_candidata_e_uma_resposta(self):
        assert et.rede_consensual_do_email("r1") == "r1"
        assert et.rede_consensual_do_email("r1", "r1", None, " r1 ") == "r1"

    def test_duas_diferentes_nao_se_resolvem(self):
        assert et.rede_consensual_do_email("r1", "r2") is None
        assert et.rede_consensual_do_email("r1", "r1", "r2") is None  # nem por maioria

    def test_nenhuma_nao_e_uma_resposta(self):
        assert et.rede_consensual_do_email() is None
        assert et.rede_consensual_do_email(None, "", "  ") is None


@pytest.mark.asyncio
class TestOndeVemARede:
    async def test_do_processo(self, db):
        assert await et.resolver_rede_do_email(db, _email(process_id="p-domus")) == REDE_DOMUS

    async def test_do_processo_que_so_tem_empresa(self, db):
        assert await et.resolver_rede_do_email(db, _email(process_id="p-com-empresa")) == REDE_DOMUS

    async def test_da_empresa_do_email_por_id(self, db):
        assert await et.resolver_rede_do_email(db, _email(company_id="cmp-power")) == REDE_INCUMBENTE

    async def test_da_empresa_do_email_por_nome(self, db):
        assert await et.resolver_rede_do_email(db, _email(company_id="Domus")) == REDE_DOMUS

    async def test_empresa_sem_grupo_e_uma_ilha_de_uma_so(self, db):
        assert await et.resolver_rede_do_email(db, _email(company_id="cmp-ilha")) == "rede:cmp-ilha"

    async def test_processo_e_empresa_que_concordam(self, db):
        e = _email(process_id="p-power", company_id="cmp-precision")  # mesma rede, empresas diferentes
        assert await et.resolver_rede_do_email(db, e) == REDE_INCUMBENTE

    async def test_processo_e_empresa_que_discordam_nao_carimba_e_avisa(self, db, caplog):
        e = _email(process_id="p-power", company_id="cmp-domus")
        with caplog.at_level("WARNING"):
            assert await et.resolver_rede_do_email(db, e) is None
        assert "não se carimba" in caplog.text

    async def test_sem_processo_nem_empresa_nao_carimba(self, db):
        assert await et.resolver_rede_do_email(db, _email()) is None

    @pytest.mark.parametrize("empresa", ["default", "", None])
    async def test_empresa_sentinela_nao_conta(self, db, empresa):
        assert await et.resolver_rede_do_email(db, _email(company_id=empresa)) is None

    async def test_processo_inexistente_nao_conta(self, db):
        assert await et.resolver_rede_do_email(db, _email(process_id="nao-existe")) is None

    async def test_processo_legado_sem_nada_nao_carimba(self, db):
        assert await et.resolver_rede_do_email(db, _email(process_id="p-sem-nada")) is None

    async def test_o_memo_evita_repetir_consultas(self, db):
        memo: dict = {}
        with patch.object(db.processes, "find_one", wraps=db.processes.find_one) as fp:
            for _ in range(3):
                await et.resolver_rede_do_email(db, _email(process_id="p-domus"), memo=memo)
        assert fp.call_count == 1


@pytest.mark.asyncio
class TestInserir:
    async def test_carimba_e_insere(self, db):
        doc = _email(process_id="p-domus")
        await et.inserir_email(db, doc)
        assert db.emails.docs[0]["network_id"] == REDE_DOMUS

    async def test_nao_sobrepoe_um_carimbo_ja_posto(self, db):
        doc = _email(process_id="p-domus", network_id="rede-do-escritor")
        await et.inserir_email(db, doc)
        assert db.emails.docs[0]["network_id"] == "rede-do-escritor"

    async def test_sem_rede_dedutivel_insere_sem_carimbo(self, db):
        await et.inserir_email(db, _email())
        assert "network_id" not in db.emails.docs[0]

    async def test_uma_falha_a_resolver_nunca_perde_o_email(self, db, caplog):
        with patch.object(et, "resolver_rede_do_email", AsyncMock(side_effect=RuntimeError("base em baixo"))), \
             caplog.at_level("WARNING"):
            await et.inserir_email(db, _email(process_id="p-domus"))
        assert len(db.emails.docs) == 1
        assert "network_id" not in db.emails.docs[0]
        assert "fica por carimbar" in caplog.text  # nunca em silêncio


# ═══════════════════════════════════════════════════════════════════
#  OS ESCRITORES REAIS
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
async def test_o_registo_manual_de_um_email_sai_carimbado(db):
    """Fim a fim por um escritor real (`run_create_email_record`)."""
    import services.email_process_crud as epc
    from models.email import EmailCreate

    with patch.object(epc, "db", db), patch.object(epc, "enrich_email", AsyncMock(side_effect=lambda e: e)):
        await epc.run_create_email_record(
            EmailCreate(process_id="p-domus", direction="sent", from_email="a@domus.pt",
                        to_emails=["c@x.pt"], subject="Olá", body="corpo", status="sent"),
            {"id": "u-bruno", "name": "Bruno"},
        )
    assert db.emails.docs[0]["network_id"] == REDE_DOMUS


def _chamadas_a_inserir_email(ficheiro: Path) -> list[tuple[str, ast.Call]]:
    arvore = ast.parse(ficheiro.read_text(encoding="utf-8"))
    achados = []
    for funcao in ast.walk(arvore):
        if isinstance(funcao, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for no in ast.walk(funcao):
                if isinstance(no, ast.Call) and getattr(no.func, "id", "") == "inserir_email":
                    achados.append((funcao.name, no))
    return achados


class TestTodosOsEscritoresPassamPeloPontoUnico:
    def test_nenhum_insert_one_em_db_emails_fora_do_ponto_unico(self):
        ofensores = []
        for pasta in ("services", "routes", "scripts"):
            for ficheiro in (BACKEND / pasta).rglob("*.py"):
                if ficheiro.name == "email_tenant_stamp.py":
                    continue
                arvore = ast.parse(ficheiro.read_text(encoding="utf-8"))
                for no in ast.walk(arvore):
                    if (
                        isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                        and no.func.attr in {"insert_one", "insert_many"}
                        and isinstance(no.func.value, ast.Attribute) and no.func.value.attr == "emails"
                    ):
                        ofensores.append(f"{ficheiro.relative_to(BACKEND)}:{no.lineno}")
        assert ofensores == []

    def test_contraprova_os_oito_escritores_existem_e_passam_o_handle_do_modulo(self):
        """Sem isto, apagar as chamadas satisfazia a guarda acima."""
        esperados = {
            "services/email_service.py": 5,
            "services/email_process_crud.py": 1,
            "services/gmail_api_service.py": 1,
            "services/email_draft_service.py": 1,
        }
        for rel, quantos in esperados.items():
            chamadas = _chamadas_a_inserir_email(BACKEND / rel)
            assert len(chamadas) == quantos, (rel, len(chamadas))
            for _, chamada in chamadas:
                # O `db` do PRÓPRIO módulo (o que os testes patcham), não um import novo.
                assert isinstance(chamada.args[0], ast.Name) and chamada.args[0].id == "db"

    def test_o_backfill_usa_a_funcao_de_producao(self):
        fonte = (BACKEND / "scripts" / "backfill_email_network_id.py").read_text(encoding="utf-8")
        assert "resolver_rede_do_email" in fonte
        # só escreve onde ainda falta (idempotente) e só o `network_id`
        assert '{"$set": {"network_id": rede}}' in fonte


# ═══════════════════════════════════════════════════════════════════
#  O BACKFILL
# ═══════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestBackfill:
    @pytest.fixture
    def com_emails(self, db):
        db.emails.docs.extend([
            {"id": "e-processo", "process_id": "p-domus"},
            {"id": "e-empresa", "company_id": "cmp-power"},
            {"id": "e-conflito", "process_id": "p-power", "company_id": "cmp-domus"},
            {"id": "e-geral"},  # caixa partilhada, sem processo nem empresa
            {"id": "e-ja", "process_id": "p-power", "network_id": "rede-existente"},
        ])
        return db

    async def test_omissao_le_e_conta_e_nao_escreve(self, com_emails):
        from scripts.backfill_email_network_id import carimbar_emails

        contagens = await carimbar_emails(com_emails, aplicar=False)
        assert contagens == {"vistos": 4, "carimbados": 2, "por_resolver": 2, "ja_carimbados_entretanto": 0}
        assert all("network_id" not in e for e in com_emails.emails.docs if e["id"] != "e-ja")

    async def test_aplicar_carimba_so_o_inequivoco(self, com_emails):
        from scripts.backfill_email_network_id import carimbar_emails

        await carimbar_emails(com_emails, aplicar=True)
        por_id = {e["id"]: e for e in com_emails.emails.docs}
        assert por_id["e-processo"]["network_id"] == REDE_DOMUS
        assert por_id["e-empresa"]["network_id"] == REDE_INCUMBENTE
        assert "network_id" not in por_id["e-conflito"]      # duas candidatas: não se adivinha
        assert "network_id" not in por_id["e-geral"]
        assert por_id["e-ja"]["network_id"] == "rede-existente"  # nunca sobrepõe

    async def test_a_segunda_passagem_escreve_zero(self, com_emails):
        from scripts.backfill_email_network_id import carimbar_emails

        await carimbar_emails(com_emails, aplicar=True)
        segunda = await carimbar_emails(com_emails, aplicar=True)
        assert segunda["carimbados"] == 0
        assert segunda["vistos"] == 2  # só os dois que ficaram por resolver
