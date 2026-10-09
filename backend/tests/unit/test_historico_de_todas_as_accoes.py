"""«Todas as acções vão para o histórico — excepto as da Indexação» (Bloco 3, ponto 21).

O INVENTÁRIO QUE FALTAVA
  A regra do silêncio estava no sítio certo (`history._is_stealth_user`, ponto
  único). Faltava a outra metade: que as acções sobre um processo chegassem
  sequer ao histórico. A leitura dos escritores encontrou, entre outras:
    * `DELETE /processes/{id}` só escrevia em `process_activities`, que nenhum
      ecrã lê — eliminar um processo não deixava rasto visível;
    * o `send_email` NÃO regista histórico (a nota do código que o dizia estava
      errada): a documentação enviada ao banco e os emails do webmail não
      apareciam na trilha;
    * ligações, pasta externa, emails monitorizados, link do Portal, links
      temporários, cancelar visita, restaurar, renomear/mover ficheiros e
      aplicar sugestões da IA à ficha.

COMO SE FECHA
  Um inventário por AST sobre as rotas de escrita COM `{process_id}` no
  caminho: cada uma chega a um registo (transitivamente, pelo grafo de
  chamadas dos serviços) ou está numa lista de excepções com o MOTIVO. Uma
  rota nova que não registe nada falha por omissão.
"""
from __future__ import annotations

import ast
import functools
import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services import history as history_mod

BACKEND = Path(__file__).resolve().parents[2]

# ─────────────────────────────────────────────────────────────────────
# 1. O inventário das rotas
# ─────────────────────────────────────────────────────────────────────

REGISTA = re.compile(
    r"log_history|log_audit_event|db\.history\.insert|_log_history|"
    r"log_mark_indexed_history|_registar_envio_no_historico|registar_historico"
)

#: Rotas de escrita com `{process_id}` que, de propósito, NÃO escrevem no
#: histórico — cada uma com o motivo. A lista só encolhe por boas razões.
SEM_HISTORICO = {
    ("admin_encryption.py", "verify_process_encryption"): "leitura (verifica a encriptação, não altera)",
    ("admin_encryption.py", "encrypt_single_process"): "manutenção de infraestrutura (Admin); a ficha não muda de valor",
    ("ai_analysis.py", "generate_analysis"): "gera uma análise guardada à parte; não altera a ficha",
    ("alerts.py", "create_deed_reminder_endpoint"): "alerta automático: vive no calendário e nas notificações",
    ("document_extraction.py", "extract_document_data"): "só propõe; quem escreve é o `ai-apply-suggestions` (regista)",
    ("documents.py", "categorize_document"): "etiquetagem de metadados pela IA; o ficheiro não muda",
    ("documents.py", "categorize_all_documents"): "etiquetagem de metadados pela IA; o ficheiro não muda",
    ("documents.py", "ai_analyze_documents"): "análise; só propõe",
    ("emails.py", "sync_process_emails"): "sincronização automática da caixa",
    ("templates.py", "get_document_request_template"): "POST que só renderiza um modelo (não grava)",
}

#: Alvos cujo registo vive num serviço que o grafo por nome não alcança, e que
#: são confirmados à mão pelos testes de comportamento mais abaixo.
CONFIRMADOS_POR_TESTE = {
    ("emails.py", "send_documentation_email"),
}


@functools.lru_cache(maxsize=1)
def _servicos():
    """nome da função → lista de (corpo, nomes referidos)."""
    funcs: dict[str, list] = {}
    for caminho in (BACKEND / "services").glob("*.py"):
        fonte = caminho.read_text()
        if "def " not in fonte:
            continue
        for no in ast.walk(ast.parse(fonte)):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                corpo = ast.get_source_segment(fonte, no) or ""
                nomes = {n.id for n in ast.walk(no) if isinstance(n, ast.Name)}
                nomes |= {n.attr for n in ast.walk(no) if isinstance(n, ast.Attribute)}
                funcs.setdefault(no.name, []).append((corpo, nomes))
    return funcs


def _alcanca_registo(nome: str, vistos=None, profundidade=0) -> bool:
    vistos = vistos if vistos is not None else set()
    if nome in vistos or profundidade > 6:
        return False
    vistos.add(nome)
    for corpo, nomes in _servicos().get(nome, []):
        if REGISTA.search(corpo):
            return True
        if any(n in _servicos() and n != nome and _alcanca_registo(n, vistos, profundidade + 1)
               for n in nomes):
            return True
    return False


@functools.lru_cache(maxsize=1)
def _rotas_de_escrita_com_process_id():
    rotas = {}
    for caminho in sorted((BACKEND / "routes").glob("*.py")):
        fonte = caminho.read_text()
        for no in ast.walk(ast.parse(fonte)):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in no.decorator_list:
                if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                        and d.func.attr in ("post", "put", "patch", "delete")
                        and d.args and isinstance(d.args[0], ast.Constant)
                        and "process_id" in str(d.args[0].value)):
                    corpo = ast.get_source_segment(fonte, no) or ""
                    chamadas = set(re.findall(r"\b([A-Za-z_]\w*)\(", corpo))
                    regista = bool(REGISTA.search(corpo)) or any(
                        _alcanca_registo(c) for c in chamadas
                    )
                    rotas[(caminho.name, no.name)] = regista
    return rotas


class TestNenhumaRotaDeEscritaDoProcessoFicaSemRasto:
    def test_o_detector_le_mesmo_as_rotas(self):
        rotas = _rotas_de_escrita_com_process_id()
        assert len(rotas) >= 40
        # Contraprovas nos dois sentidos: uma que sempre registou e uma que não.
        assert rotas[("processes.py", "update_process")] is True
        assert rotas[("alerts.py", "create_deed_reminder_endpoint")] is False

    def test_cada_rota_regista_ou_esta_justificada(self):
        sem_registo = {k for k, regista in _rotas_de_escrita_com_process_id().items() if not regista}
        por_resolver = sem_registo - set(SEM_HISTORICO) - CONFIRMADOS_POR_TESTE
        assert not por_resolver, (
            "Rota de escrita do processo sem histórico e sem justificação: "
            f"{sorted(por_resolver)}"
        )

    def test_as_excepcoes_so_apontam_para_rotas_que_existem_e_ainda_nao_registam(self):
        """Uma justificação que sobrevive à correcção é lixo; uma que aponta
        para uma rota que já não existe, também."""
        rotas = _rotas_de_escrita_com_process_id()
        for chave in SEM_HISTORICO:
            assert chave in rotas, f"{chave}: a rota já não existe"
            assert rotas[chave] is False, f"{chave}: já regista — retire a excepção"

    @pytest.mark.parametrize("rota", [
        ("processes.py", "delete_process"),
        ("processes.py", "generate_magic_link"),
        ("processes.py", "send_magic_link_email"),
        ("processes.py", "send_portal_message_staff"),
        ("restore.py", "restore_process"),
        ("emails.py", "add_monitored_email"),
        ("emails.py", "remove_monitored_email"),
        ("onedrive.py", "save_process_folder_url"),
        ("onedrive.py", "remove_process_folder_url"),
        ("onedrive.py", "add_process_link"),
        ("onedrive.py", "update_process_link"),
        ("onedrive.py", "delete_process_link"),
        ("onedrive.py", "generate_document_checklist"),
        ("storage.py", "save_process_folder_url"),
        ("storage.py", "delete_process_folder_url"),
        ("storage.py", "generate_document_checklist"),
        ("documents.py", "apply_ai_suggestions"),
        ("documents.py", "confirm_process_data"),
        ("documents.py", "resolve_data_conflict"),
        ("documents.py", "rename_document_smart"),
        ("documents.py", "rename_all_documents_smart"),
        ("documents.py", "organize_files_in_folders"),
        ("documents.py", "organize_documents_after_analysis"),
        ("clients.py", "unlink_process_from_client"),
    ])
    def test_os_buracos_encontrados_estao_fechados(self, rota):
        assert _rotas_de_escrita_com_process_id()[rota] is True


# ─────────────────────────────────────────────────────────────────────
# 2. Comportamento: o que fica escrito e o silêncio da Indexação
# ─────────────────────────────────────────────────────────────────────

INDEXACAO = {"id": "u-ix", "name": "Rui", "role": "indexacao"}
CONSULTOR = {"id": "u-co", "name": "Carla", "role": "consultor"}
CONSULTOR_EM_EXERCICIO_DE_INDEXACAO = {
    "id": "u-co", "name": "Carla", "role": "consultor", "effective_role": "indexacao",
}
SILENCIADO = {"id": "u-si", "name": "Sílvia", "role": "consultor", "track_history": False}


@pytest.fixture
async def mundo(fake_async_db):
    await fake_async_db.processes.insert_one(
        {"id": "p-1", "client_name": "Joana", "status": "fase_bancaria",
         "monitored_emails": ["a@x.pt"], "onedrive_links": [{"id": "l1", "name": "A"}]}
    )
    with patch.object(history_mod, "db", fake_async_db):
        yield fake_async_db


async def _historico(db):
    return await db.history.find({"process_id": "p-1"}).to_list(50)


ACCOES = []  # (rotulo, coroutine-factory, texto esperado na acção)


def _acoes():
    from services import (
        document_ocr_data,
        email_process_crud,
        onedrive_folder_url,
        onedrive_links,
        process_delete,
        storage_api_folder,
    )

    class _Obj:  # `LinkCreate` mínimo
        def __init__(self, **kw):
            self.__dict__.update(kw)

    return [
        ("eliminar", process_delete, lambda u: process_delete.soft_delete_process("p-1", u), "Eliminou o processo"),
        ("email monitorizado +", email_process_crud,
         lambda u: email_process_crud.run_add_monitored_email("p-1", "novo@x.pt", u),
         "Adicionou email monitorizado"),
        ("email monitorizado -", email_process_crud,
         lambda u: email_process_crud.run_remove_monitored_email("p-1", "a@x.pt", u),
         "Removeu email monitorizado"),
        ("confirmar dados", document_ocr_data,
         lambda u: document_ocr_data.run_confirm_process_data("p-1", {"confirmed": True}, user=u),
         "Confirmou os dados do processo"),
        ("desbloquear dados", document_ocr_data,
         lambda u: document_ocr_data.run_confirm_process_data("p-1", {"confirmed": False}, user=u),
         "Desbloqueou os dados do processo"),
        ("pasta externa", onedrive_folder_url,
         lambda u: onedrive_folder_url.run_save_process_folder_url("p-1", "https://drive.google.com/x", u),
         "Definiu a pasta externa"),
        ("ligação +", onedrive_links,
         lambda u: onedrive_links.run_add_process_link(
             "p-1", _Obj(name="Dossier", url="https://exemplo.pt/x", description=None), u),
         "Adicionou ligação"),
        ("ligação -", onedrive_links,
         lambda u: onedrive_links.run_delete_process_link("p-1", "l1", u),
         "Removeu ligação"),
        ("pasta externa (storage)", storage_api_folder,
         lambda u: storage_api_folder.run_save_process_folder_url("p-1", "https://exemplo.pt/pasta", u),
         "Definiu a pasta externa"),
    ]


def _patch_dbs(modulos, db):
    from contextlib import ExitStack

    pilha = ExitStack()
    for m in modulos:
        pilha.enter_context(patch.object(m, "db", db))
    return pilha


@pytest.fixture
def mundo_com_servicos(mundo):
    # `process_delete` e afins fazem `from database import db`.
    mods = {m for _, m, _, _ in _acoes()}
    with _patch_dbs(mods, mundo):
        yield mundo


@pytest.mark.parametrize("indice", range(9))
class TestCadaAccaoDeixaRastoEACalaIndexacao:
    async def test_um_consultor_deixa_uma_entrada(self, mundo_com_servicos, indice):
        _, _, executar, texto = _acoes()[indice]
        await executar(CONSULTOR)
        entradas = await _historico(mundo_com_servicos)
        assert len(entradas) == 1, entradas
        assert texto in entradas[0]["action"]
        assert entradas[0]["user_id"] == "u-co"

    async def test_a_indexacao_nao_deixa_rasto(self, mundo_com_servicos, indice):
        _, _, executar, _ = _acoes()[indice]
        await executar(INDEXACAO)
        assert await _historico(mundo_com_servicos) == []

    async def test_quem_entra_COMO_indexacao_tambem_nao_deixa_rasto(self, mundo_com_servicos, indice):
        """O perfil activo conta — é assim que o produto quer que se troque de chapéu."""
        _, _, executar, _ = _acoes()[indice]
        await executar(CONSULTOR_EM_EXERCICIO_DE_INDEXACAO)
        assert await _historico(mundo_com_servicos) == []

    async def test_o_registo_desligado_por_pessoa_tambem_cala(self, mundo_com_servicos, indice):
        _, _, executar, _ = _acoes()[indice]
        await executar(SILENCIADO)
        assert await _historico(mundo_com_servicos) == []


class TestOsValoresPessoaisNaoVaoParaOHistorico:
    async def test_aplicar_sugestoes_da_ia_regista_nomes_de_campos_e_nunca_valores(self, mundo):
        from services import document_ai_analyze as daa

        with patch.object(daa, "db", mundo), \
             patch("services.process_service.can_edit_process_data", return_value=(True, "")):
            await daa.run_apply_ai_suggestions(
                "p-1",
                {"nif": "123456789", "iban": "PT50000201231234567890154", "target_titular": "titular1"},
                user=CONSULTOR,
            )
        (entrada,) = await _historico(mundo)
        texto = " ".join(str(v) for v in entrada.values())
        assert "123456789" not in texto and "PT50" not in texto
        assert "Aplicou sugestões da IA" in entrada["action"]

    async def test_o_perfil_do_cliente_regista_nomes_de_campos_e_nunca_valores(self, mundo):
        from services import portal_profile
        from services.portal_profile import ClientProfileUpdate

        # Processo ainda em recolha: o perfil está destrancado.
        await mundo.processes.update_one({"id": "p-1"}, {"$set": {"status": None}})
        await mundo.clients.insert_one({"id": "c-1", "process_ids": ["p-1"], "nome": "Joana"})
        editaveis = {"dados_pessoais": {"morada"}, "contacto": {"telefone"}}
        with patch.object(portal_profile, "db", mundo), \
             patch.object(portal_profile, "carregar_campos_editaveis", AsyncMock(return_value=editaveis)):
            resposta = await portal_profile.run_update_client_profile(
                ClientProfileUpdate(
                    dados_pessoais={"morada": "Rua Secreta 1"},
                    contacto={"telefone": "912345678"},
                ),
                {"client_id": "c-1"},
            )
        assert resposta["updated_fields"], resposta
        entradas = await _historico(mundo)
        assert len(entradas) == 1
        texto = " ".join(str(v) for v in entradas[0].values())
        assert "Rua Secreta" not in texto and "912345678" not in texto
        assert "Cliente atualizou o perfil" in entradas[0]["action"]
        assert "morada" in entradas[0]["new_value"] and "telefone" in entradas[0]["new_value"]
        assert entradas[0]["user_id"] == "c-1"  # o autor é o cliente


class TestOEnvioDeEmailFicaNoHistorico:
    """O `send_email` não regista (a nota que o dizia estava errada)."""

    def _registo(self, **extra):
        from services.email_send_queue import build_pending_send_record

        base = dict(
            account="geral", to_emails=["a@x.pt", "b@x.pt"], subject="Documentos", body="x",
            body_html=None, cc_emails=["c@x.pt"], process_id="p-1", from_box=None,
            from_email=None, company_id=None, created_by="u-co",
            created_by_email="c@x.pt", attachment_ids=[],
        )
        base.update(extra)
        return build_pending_send_record(**base)

    async def test_um_envio_com_processo_deixa_uma_entrada(self, mundo):
        from services.email_send_queue import _registar_envio_no_historico

        await _registar_envio_no_historico(self._registo(created_by_name="Carla"))
        (entrada,) = await _historico(mundo)
        assert entrada["action"] == "Enviou email"
        assert entrada["user_name"] == "Carla"
        assert "Documentos" in entrada["new_value"] and "3 destinatário" in entrada["new_value"]

    async def test_sem_processo_nao_regista(self, mundo):
        from services.email_send_queue import _registar_envio_no_historico

        await mundo.history.delete_many({})
        await _registar_envio_no_historico(self._registo(process_id=None))
        assert await mundo.history.count_documents({}) == 0

    async def test_o_silencio_foi_decidido_ao_enfileirar_e_vale_no_envio(self, mundo):
        """O envio real corre depois, num job sem sessão: o `actor_silenciado`
        guardado no registo é o que o cala."""
        from services.email_send_queue import _registar_envio_no_historico

        await _registar_envio_no_historico(self._registo(actor_silenciado=True))
        assert await _historico(mundo) == []

    def test_quem_enfileira_calcula_o_silencio_pelo_ponto_unico(self):
        from services.email_process_crud import _utilizador_silenciado

        assert _utilizador_silenciado(INDEXACAO) is True
        assert _utilizador_silenciado(CONSULTOR_EM_EXERCICIO_DE_INDEXACAO) is True
        assert _utilizador_silenciado(SILENCIADO) is True
        assert _utilizador_silenciado(CONSULTOR) is False

    def test_o_enfileiramento_passa_o_silencio_ao_registo(self):
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios((BACKEND / "services" / "email_process_crud.py").read_text())
        assert "actor_silenciado=_utilizador_silenciado(current_user)" in fonte

    async def test_um_erro_ao_registar_nunca_derruba_o_envio(self, mundo, caplog):
        from services.email_send_queue import _registar_envio_no_historico

        with patch("services.history.log_history", AsyncMock(side_effect=RuntimeError("mongo caiu"))):
            await _registar_envio_no_historico(self._registo())
        assert "mongo caiu" in caplog.text

    def test_o_executor_chama_o_registo_depois_de_enviar(self):
        from services.email_send_queue import execute_pending_email_send
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(execute_pending_email_send)
        assert fonte.index("_registar_envio_no_historico") > fonte.index("_finalize_attachments")


# ─────────────────────────────────────────────────────────────────────
# 3. As acções sem `{process_id}` no caminho (o inventário não as vê)
# ─────────────────────────────────────────────────────────────────────

def _funcao(modulo: str, nome: str):
    import importlib

    return getattr(importlib.import_module(f"services.{modulo}"), nome)


class TestAsAccoesForaDoInventarioDeRotas:
    """O `process_id` vem no corpo, na visita ou no cliente: o inventário por
    caminho não as alcança, por isso cada uma é afirmada pela fonte (com
    contraprova: o sítio certo chama mesmo o registo)."""

    @pytest.mark.parametrize("modulo,nome", [
        ("temp_link_api_staff", "run_create_temp_link"),
        ("temp_link_api_staff", "run_cancel_temp_link"),
        ("temp_link_api_staff", "run_delete_temp_link"),
        ("visit_update_cancel", "run_cancel_visit"),
        ("client_process_ops", "run_link_process_to_client"),
        ("client_process_ops", "run_unlink_process_from_client"),
        ("client_process_ops", "run_create_process_for_client"),
        ("portal_magic_link", "send_magic_link_to_client"),
        ("process_portal_messages", "run_send_portal_message_staff"),
        ("restore_api_process", "run_restore_process"),
        ("portal_profile", "run_update_client_profile"),
        ("document_rename_smart", "run_rename_document_smart"),
        ("document_rename_smart", "run_rename_all_documents_smart"),
        ("document_ai_analyze", "run_apply_ai_suggestions"),
        ("document_ai_analyze", "run_organize_files_in_folders"),
        ("document_ai_analyze", "run_organize_documents_after_analysis"),
        ("document_ocr_data", "run_resolve_data_conflict"),
        ("email_documentation", "_send_documentation_email_impl"),
    ])
    def test_chama_mesmo_o_registo(self, modulo, nome):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(_funcao(modulo, nome))
        # A CHAMADA, não o nome: o `import` sozinho também contém «log_history»
        # e deixava passar uma chamada apagada (mutação que sobreviveu).
        assert "await log_history(" in fonte, f"{modulo}.{nome} deixou de registar no histórico"

    @pytest.mark.parametrize("modulo,nome", [
        ("temp_link_api_staff", "run_create_temp_link"),
        ("visit_update_cancel", "run_cancel_visit"),
        ("client_process_ops", "run_link_process_to_client"),
        ("process_portal_messages", "run_send_portal_message_staff"),
        ("document_rename_smart", "run_rename_all_documents_smart"),
    ])
    def test_nunca_escreve_na_colecao_a_mao(self, modulo, nome):
        """Um `db.history.insert_one` à mão contorna o interruptor da Indexação."""
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(_funcao(modulo, nome))
        assert "db.history" not in fonte

    def test_o_lote_de_renomear_nao_regista_um_por_ficheiro(self):
        """O histórico diz o que aconteceu sem se afogar em N linhas iguais."""
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(_funcao("document_rename_smart", "run_rename_all_documents_smart"))
        assert fonte.count("log_history(") == 1
