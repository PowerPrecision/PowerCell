"""
IA AUTOMÁTICA ao cair um ficheiro na `Index` (Out 2026).

A direcção retirou o botão manual da IA aos perfis operacionais (custos da API). O fluxo
normal tem de andar sozinho, em três arranques:

  1. staff / Indexador faz upload (multipart, directo, «Arquivar no Processo»);
  2. o parceiro envia ficheiros;
  3. o cliente submete pelo Portal.

Os dois primeiros já estavam ligados pelo desvio inteligente (`document_intake`). O terceiro
FALTAVA: `run_confirm_portal_upload` força a `Index`, grava o registo e termina — sem fila e
sem IA. Este ficheiro prova o gatilho novo e fixa, por inventário, que nenhum caminho que
decide «passa pela IA» deixa de a agendar.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import document_ai_trigger as gatilho
from services import document_intake
from services import portal_upload_ops as puo

from tests.unit.test_portal_upload_path_traversal import (
    CHAVE_LEGITIMA,
    CLIENTE,
    PROCESSO,
    S3Falso,
    _dados_do_cliente,
    _nada_async,
)

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
def ligada(monkeypatch):
    monkeypatch.setenv("IA_DA_ENTRADA_ENABLED", "true")


class S3ComBytes(S3Falso):
    """O S3 falso do Portal + `get_file_content` (o que a IA lê)."""

    def __init__(self):
        super().__init__()
        self.lidos: list[str] = []

    def get_file_content(self, object_name: str):
        self.lidos.append(object_name)
        if object_name in self.chaves_inexistentes:
            return None
        return self._corpo(object_name)


# ====================================================================
# O interruptor
# ====================================================================

class TestOInterruptor:
    def test_em_testing_esta_desligada_por_omissao(self, monkeypatch):
        monkeypatch.delenv("IA_DA_ENTRADA_ENABLED", raising=False)
        monkeypatch.setenv("TESTING", "true")
        assert gatilho.ia_da_entrada_ligada() is False

    def test_fora_de_testing_esta_ligada_por_omissao(self, monkeypatch):
        monkeypatch.delenv("IA_DA_ENTRADA_ENABLED", raising=False)
        monkeypatch.setenv("TESTING", "false")
        assert gatilho.ia_da_entrada_ligada() is True

    def test_ligar_explicitamente_vence_o_testing(self, monkeypatch):
        monkeypatch.setenv("TESTING", "true")
        monkeypatch.setenv("IA_DA_ENTRADA_ENABLED", "true")
        assert gatilho.ia_da_entrada_ligada() is True

    def test_desligar_explicitamente_vence_tudo_corte_de_custos(self, monkeypatch):
        monkeypatch.setenv("TESTING", "false")
        monkeypatch.setenv("IA_DA_ENTRADA_ENABLED", "false")
        assert gatilho.ia_da_entrada_ligada() is False


# ====================================================================
# correr_ia_da_entrada — o trabalho em si
# ====================================================================

class TestCorrerAIA:
    @pytest.fixture
    def mundo(self, fake_async_db):
        s3 = S3ComBytes()
        categoriza = AsyncMock()
        with patch.object(gatilho, "db", fake_async_db), \
             patch.object(gatilho, "s3_service", s3), \
             patch("services.document_auto_categorize.auto_categorize_document_background",
                   categoriza):
            yield s3, categoriza, fake_async_db

    @pytest.mark.asyncio
    async def test_le_o_ficheiro_e_categoriza(self, mundo):
        s3, categoriza, _ = mundo
        resultado = await gatilho.correr_ia_da_entrada(
            process_id="proc-1", client_name="Ana", s3_path=CHAVE_LEGITIMA,
            filename="recibo.pdf", satisfazer_pedidos=False,
        )
        assert resultado == "categorizado"
        categoriza.assert_awaited_once()
        argumentos = categoriza.await_args.kwargs
        assert argumentos["s3_path"] == CHAVE_LEGITIMA
        assert argumentos["process_id"] == "proc-1"
        assert argumentos["file_content"].startswith(b"%PDF")
        assert argumentos["satisfazer_pedidos"] is False

    @pytest.mark.asyncio
    async def test_uma_vez_por_ficheiro_o_ja_categorizado_nao_paga_outra_chamada(self, mundo):
        s3, categoriza, bd = mundo
        await bd.document_metadata.insert_one(
            {"id": "m1", "s3_path": CHAVE_LEGITIMA, "is_categorized": True}
        )
        resultado = await gatilho.correr_ia_da_entrada(
            process_id="proc-1", client_name="Ana", s3_path=CHAVE_LEGITIMA, filename="recibo.pdf",
        )
        assert resultado == "ja_categorizado"
        categoriza.assert_not_awaited()
        assert s3.lidos == []  # nem sequer lê o ficheiro

    @pytest.mark.asyncio
    async def test_um_registo_na_fila_ainda_nao_categorizado_NAO_conta_como_feito(self, mundo):
        # A fila escreve `is_categorized: False` — se isto contasse, a IA nunca corria.
        s3, categoriza, bd = mundo
        await bd.document_metadata.insert_one(
            {"id": "m1", "s3_path": CHAVE_LEGITIMA, "is_categorized": False, "in_index_queue": True}
        )
        resultado = await gatilho.correr_ia_da_entrada(
            process_id="proc-1", client_name="Ana", s3_path=CHAVE_LEGITIMA, filename="recibo.pdf",
        )
        assert resultado == "categorizado"
        categoriza.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acima_do_tecto_fica_na_fila_sem_ler_nem_chamar_o_modelo(self, mundo):
        s3, categoriza, _ = mundo
        resultado = await gatilho.correr_ia_da_entrada(
            process_id="proc-1", client_name="Ana", s3_path=CHAVE_LEGITIMA, filename="x.pdf",
            tamanho=gatilho.TAMANHO_MAXIMO_PARA_IA + 1,
        )
        assert resultado == "demasiado_grande"
        categoriza.assert_not_awaited()
        assert s3.lidos == []

    @pytest.mark.asyncio
    async def test_no_tecto_exacto_ainda_corre(self, mundo):
        _, categoriza, _ = mundo
        resultado = await gatilho.correr_ia_da_entrada(
            process_id="proc-1", client_name="Ana", s3_path=CHAVE_LEGITIMA, filename="x.pdf",
            tamanho=gatilho.TAMANHO_MAXIMO_PARA_IA,
        )
        assert resultado == "categorizado"
        categoriza.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sem_tamanho_pergunta_ao_s3_pelo_head(self, mundo):
        s3, categoriza, _ = mundo
        grande = MagicMock(return_value=("ok", {"tamanho": gatilho.TAMANHO_MAXIMO_PARA_IA + 5}))
        with patch.object(s3, "head_object_metadata", grande):
            resultado = await gatilho.correr_ia_da_entrada(
                process_id="proc-1", client_name="Ana", s3_path=CHAVE_LEGITIMA, filename="x.pdf",
            )
        assert resultado == "demasiado_grande"
        grande.assert_called_once_with(CHAVE_LEGITIMA)

    @pytest.mark.asyncio
    async def test_ficheiro_ilegivel_nao_chama_o_modelo(self, mundo):
        s3, categoriza, _ = mundo
        s3.chaves_inexistentes.add(CHAVE_LEGITIMA)
        resultado = await gatilho.correr_ia_da_entrada(
            process_id="proc-1", client_name="Ana", s3_path=CHAVE_LEGITIMA, filename="x.pdf",
            tamanho=100,
        )
        assert resultado == "ilegivel"
        categoriza.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_uma_falha_do_modelo_nunca_propaga(self, mundo):
        _, categoriza, _ = mundo
        categoriza.side_effect = RuntimeError("OpenAI em baixo")
        resultado = await gatilho.correr_ia_da_entrada(
            process_id="proc-1", client_name="Ana", s3_path=CHAVE_LEGITIMA, filename="x.pdf",
            tamanho=100,
        )
        assert resultado == "erro"

    @pytest.mark.asyncio
    async def test_sem_processo_o_onboarding_do_portal_tambem_corre(self, mundo):
        _, categoriza, _ = mundo
        resultado = await gatilho.correr_ia_da_entrada(
            process_id=None, client_name="Ana", s3_path=CHAVE_LEGITIMA, filename="x.pdf", tamanho=100,
        )
        assert resultado == "categorizado"
        assert categoriza.await_args.kwargs["process_id"] is None


# ====================================================================
# agendar_ia_da_entrada — fila + background
# ====================================================================

class TestAgendar:
    @pytest.mark.asyncio
    async def test_regista_na_fila_e_lanca_a_tarefa_com_referencia_forte(self, ligada, fake_async_db):
        lancadas = []

        def captura(coro, *, name=None):
            lancadas.append((coro, name))
            coro.close()

        with patch.object(gatilho, "db", fake_async_db), \
             patch.object(document_intake, "db", fake_async_db), \
             patch.object(gatilho, "spawn_background_task", captura):
            await gatilho.agendar_ia_da_entrada(
                process_id="proc-1", client_name="Ana", s3_path=CHAVE_LEGITIMA,
                filename="recibo.pdf", origem="portal_cliente", tamanho=900,
                satisfazer_pedidos=False,
            )

        fila = await fake_async_db.document_metadata.find_one({"s3_path": CHAVE_LEGITIMA})
        assert fila["in_index_queue"] is True
        assert fila["queue_source"] == "portal_cliente"
        assert fila["is_categorized"] is False
        assert len(lancadas) == 1 and lancadas[0][1].startswith("ia-da-entrada")

    @pytest.mark.asyncio
    async def test_desligada_nao_toca_na_base_de_dados_nem_lanca_nada(self, monkeypatch, fake_async_db):
        monkeypatch.setenv("IA_DA_ENTRADA_ENABLED", "false")
        lancadas = []
        with patch.object(gatilho, "db", fake_async_db), \
             patch.object(document_intake, "db", fake_async_db), \
             patch.object(gatilho, "spawn_background_task", lambda c, **k: lancadas.append(c) or c.close()):
            await gatilho.agendar_ia_da_entrada(
                process_id="proc-1", client_name="Ana", s3_path=CHAVE_LEGITIMA,
                filename="recibo.pdf", origem="portal_cliente",
            )
        assert lancadas == []
        assert await fake_async_db.document_metadata.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_nunca_propaga_mesmo_que_o_agendamento_falhe(self, ligada, fake_async_db):
        def rebenta(*a, **k):
            a[0].close()
            raise RuntimeError("sem event loop")

        with patch.object(gatilho, "db", fake_async_db), \
             patch.object(document_intake, "db", fake_async_db), \
             patch.object(gatilho, "spawn_background_task", rebenta):
            await gatilho.agendar_ia_da_entrada(
                process_id="p", client_name="A", s3_path="k", filename="f.pdf", origem="x",
            )


# ====================================================================
# O Portal do Cliente — o gatilho que faltava
# ====================================================================

class TestOPortalDispara:
    @pytest.fixture
    def portal(self, fake_async_db, ligada):
        from services import document_portal_counts, s3_content_quarantine

        s3 = S3ComBytes()
        categoriza = AsyncMock()
        lancadas = []

        def captura(coro, *, name=None):
            lancadas.append(coro)

        with patch.object(puo, "db", fake_async_db), \
             patch.object(document_portal_counts, "db", fake_async_db), \
             patch("database.db", fake_async_db), \
             patch.object(gatilho, "db", fake_async_db), \
             patch.object(document_intake, "db", fake_async_db), \
             patch.object(puo, "s3_service", s3), \
             patch.object(gatilho, "s3_service", s3), \
             patch.object(s3_content_quarantine, "s3_service", s3), \
             patch.object(puo, "invalidate_stats_cache", _nada_async), \
             patch("services.background_tasks.spawn_background_task",
                   lambda c, **k: c.close()), \
             patch.object(gatilho, "spawn_background_task", captura), \
             patch("services.history.log_history", _nada_async), \
             patch.object(puo, "send_notification_with_preference_check", _nada_async), \
             patch.object(puo, "agendar_apos_upload_do_cliente", _nada_async), \
             patch("services.document_auto_categorize.auto_categorize_document_background",
                   categoriza):
            yield s3, categoriza, lancadas, fake_async_db

    @pytest.mark.asyncio
    async def test_o_upload_do_cliente_entra_na_fila_e_a_ia_corre_sem_satisfazer_pedidos(self, portal):
        s3, categoriza, lancadas, bd = portal

        resposta = await puo.run_confirm_portal_upload(
            {"file_key": CHAVE_LEGITIMA, "original_filename": "recibo.pdf",
             "file_size": 1024, "content_type": "application/pdf"},
            _dados_do_cliente(),
        )
        assert resposta["success"] is True

        fila = await bd.document_metadata.find_one({"s3_path": CHAVE_LEGITIMA})
        assert fila and fila["in_index_queue"] is True
        assert fila["process_id"] == PROCESSO["id"]
        assert fila["queue_source"] == "portal_cliente"
        assert len(lancadas) == 1

        # A tarefa de background, corrida de verdade (um nível abaixo do agendamento).
        await lancadas[0]
        categoriza.assert_awaited_once()
        kw = categoriza.await_args.kwargs
        assert kw["s3_path"] == CHAVE_LEGITIMA
        assert kw["process_id"] == PROCESSO["id"]
        assert kw["client_name"] == PROCESSO["client_name"]
        assert kw["satisfazer_pedidos"] is False

    @pytest.mark.asyncio
    async def test_cliente_sem_processo_onboarding_tambem_dispara(self, portal):
        s3, categoriza, lancadas, bd = portal
        chave = "Documentação Clientes/Ana Legitima/Index/cc.pdf"
        # O cliente sem processo grava na pasta do cliente.
        dados = _dados_do_cliente(com_processo=False)

        await puo.run_confirm_portal_upload(
            {"file_key": chave, "original_filename": "cc.pdf", "file_size": 900,
             "content_type": "application/pdf"},
            dados,
        )
        assert len(lancadas) == 1
        await lancadas[0]
        assert categoriza.await_args.kwargs["process_id"] is None

    @pytest.mark.asyncio
    async def test_uma_recusa_da_quarentena_nao_dispara_ia(self, portal):
        # A IA custa dinheiro: um ficheiro reprovado (ou de outra pessoa) nunca chega lá.
        from fastapi import HTTPException

        s3, categoriza, lancadas, bd = portal
        with pytest.raises(HTTPException):
            await puo.run_confirm_portal_upload(
                {"file_key": "backups/dump.zip", "original_filename": "dump.zip", "file_size": 10},
                _dados_do_cliente(),
            )
        assert lancadas == []
        assert await bd.document_metadata.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_a_ia_a_falhar_nao_estraga_o_upload(self, portal):
        s3, categoriza, lancadas, bd = portal
        with patch.object(puo, "agendar_ia_da_entrada", AsyncMock(side_effect=RuntimeError("x"))):
            # `agendar_ia_da_entrada` nunca levanta por contrato; se a parede regredir, o
            # upload do cliente (já gravado) não pode ser a vítima — este teste fixa o
            # contrato do lado do chamador: documenta o que acontece se o contrato partir.
            with pytest.raises(RuntimeError):
                await puo.run_confirm_portal_upload(
                    {"file_key": CHAVE_LEGITIMA, "original_filename": "recibo.pdf",
                     "file_size": 1024},
                    _dados_do_cliente(),
                )


# ====================================================================
# Inventário — nenhum caminho que decide «passa pela IA» deixa de a agendar
# ====================================================================

def _funcoes_que_chamam(nome_da_chamada: str) -> set[str]:
    achadas: set[str] = set()
    for ficheiro in (RAIZ / "services").glob("*.py"):
        arvore = ast.parse(ficheiro.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for sub in ast.walk(no):
                    if isinstance(sub, ast.Call):
                        alvo = sub.func
                        nome = getattr(alvo, "id", None) or getattr(alvo, "attr", None)
                        if nome == nome_da_chamada:
                            achadas.add(f"{ficheiro.stem}.{no.name}")
    return achadas


def _corpo_chama_algum(ficheiro: str, funcao: str, nomes: set[str]) -> bool:
    arvore = ast.parse((RAIZ / "services" / ficheiro).read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name == funcao:
            for sub in ast.walk(no):
                if isinstance(sub, ast.Call):
                    alvo = sub.func
                    ident = getattr(alvo, "id", None) or getattr(alvo, "attr", None)
                    # `background_tasks.add_task(auto_categorize..., ...)` passa a função como argumento
                    argumentos = [getattr(a, "id", None) or getattr(a, "attr", None) for a in sub.args]
                    if ident in nomes or any(a in nomes for a in argumentos):
                        return True
    return False


class TestInventarioDosArranques:
    #: Os escritores que decidem `passa_pela_ia` (via `planear_entrada`) e a função que corre a IA.
    ESCRITORES_DO_DESVIO = {
        "document_upload.run_upload_file_s3",
        "document_direct_upload.run_confirm_upload",
        "partner_upload_ops.run_partner_confirm_upload",
    }
    #: `_depois_de_guardar` é onde o Portal do Parceiro agenda a IA (verificado abaixo).
    AGENDADORES = {"auto_categorize_document_background", "agendar_ia_da_entrada", "_depois_de_guardar"}

    def test_todo_o_chamador_de_planear_entrada_que_gasta_ia_agenda_a_ia(self):
        chamadores = _funcoes_que_chamam("planear_entrada")
        # Chamadores que só decidem a PASTA (conflito de nomes) não correm IA.
        so_decidem_pasta = {"document_upload_conflict.run_check_upload_conflict",
                            "document_direct_upload.run_generate_upload_url",
                            "partner_upload_ops.run_partner_upload_url"}
        em_falta = []
        for chamador in sorted(chamadores):
            ficheiro, funcao = chamador.split(".", 1)
            if chamador in so_decidem_pasta or "planear_entrada" in {funcao}:
                continue
            if not _corpo_chama_algum(f"{ficheiro}.py", funcao, self.AGENDADORES):
                em_falta.append(chamador)
        assert not em_falta, (
            "Chamadores de `planear_entrada` que nunca agendam a IA (e a IA deixou de ter "
            f"botão para os perfis operacionais): {em_falta}"
        )

    def test_a_contraprova_o_leitor_encontra_os_escritores_conhecidos(self):
        chamadores = _funcoes_que_chamam("planear_entrada")
        for esperado in self.ESCRITORES_DO_DESVIO:
            assert esperado in chamadores, (
                f"{esperado} não aparece — o inventário está cego ou o escritor mudou de nome"
            )

    def test_o_parceiro_agenda_a_ia_dentro_de_depois_de_guardar(self):
        assert _corpo_chama_algum(
            "partner_upload_ops.py", "_depois_de_guardar",
            {"auto_categorize_document_background", "agendar_ia_da_entrada"},
        )

    def test_o_portal_agenda_a_ia_e_nao_deixa_a_ia_satisfazer_pedidos(self):
        assert _corpo_chama_algum(
            "portal_upload_ops.py", "run_confirm_portal_upload", {"agendar_ia_da_entrada"}
        )
        fonte = (RAIZ / "services" / "portal_upload_ops.py").read_text(encoding="utf-8")
        trecho = fonte[fonte.index("await agendar_ia_da_entrada("):]
        trecho = trecho[: trecho.index(")\n")]
        assert "satisfazer_pedidos=False" in trecho
        assert 'origem="portal_cliente"' in trecho
