"""Desvio inteligente (Bloco 2, Lote 12): onde entra um ficheiro e se gasta IA.

Ordem dos testes: primeiro o DEFEITO provado (a pasta `Index` caía em
«Outros» na listagem), depois o plano puro, depois os fluxos de upload.
"""
from __future__ import annotations

import datetime as dt

import pytest

from services import document_intake as intake
from services.document_intake import (
    CATEGORIA_INDEX,
    pode_ver_o_index,
    planear_entrada,
    retirar_o_index_da_listagem,
)

RAIZ = "Documentação Clientes/cli-1"


class _Paginador:
    def __init__(self, chaves):
        self._chaves = chaves

    def paginate(self, **_kw):
        agora = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
        return [{"Contents": [
            {"Key": k, "Size": 100, "LastModified": agora} for k in self._chaves
        ]}]


class _ClienteS3:
    def __init__(self, chaves):
        self._chaves = chaves

    def get_paginator(self, _nome):
        return _Paginador(self._chaves)


def _listar(monkeypatch, chaves):
    from services import s3_storage

    monkeypatch.setattr(s3_storage.s3_service, "is_configured", lambda: True)
    monkeypatch.setattr(s3_storage.s3_service, "s3_client", _ClienteS3(chaves))
    monkeypatch.setattr(s3_storage.s3_service, "bucket_name", "bucket-de-teste")
    monkeypatch.setattr(s3_storage.s3_service, "get_presigned_url", lambda *_a, **_k: "")
    return s3_storage.s3_service.list_files("p-1", "Ana", s3_folder=RAIZ)


class TestAListagemReconheceAPastaIndex:
    def test_um_ficheiro_na_pasta_Index_aparece_em_Index_e_nao_em_Outros(self, monkeypatch):
        """O defeito provado: o `list_files` não conhecia a categoria e
        despejava a pasta `Index` em «Outros» — o consultor via ali o que
        devia estar na «pasta cofre»."""
        res = _listar(monkeypatch, [
            f"{RAIZ}/Index/cc.pdf",
            f"{RAIZ}/Outros/nota.pdf",
        ])
        assert [f["name"] for f in res["files"]["Index"]] == ["cc.pdf"]
        assert [f["name"] for f in res["files"]["Outros"]] == ["nota.pdf"]

    def test_sem_ficheiros_Index_a_chave_nao_aparece(self, monkeypatch):
        """A pasta só existe na resposta quando tem o que mostrar: as
        categorias de criação de pastas (`DEFAULT_CATEGORIES`) não mudam."""
        res = _listar(monkeypatch, [f"{RAIZ}/Outros/nota.pdf"])
        assert "Index" not in res["files"]
        assert "Index" not in res["categories"]

    def test_as_estatisticas_contam_os_ficheiros_da_Index(self, monkeypatch):
        res = _listar(monkeypatch, [f"{RAIZ}/Index/a.pdf", f"{RAIZ}/Index/b.pdf"])
        assert res["stats"]["total_files"] == 2


class TestPlanoDeEntrada:
    def test_processo_por_indexar_vai_para_Index_e_para_a_fila_da_IA(self):
        plano = planear_entrada({"is_indexed": False}, "Financeiros")
        assert plano.categoria == CATEGORIA_INDEX
        assert plano.categoria_pedida == "Financeiros"
        assert plano.passa_pela_ia is True

    def test_processo_indexado_guarda_na_categoria_pedida_sem_IA(self):
        plano = planear_entrada({"is_indexed": True}, "Financeiros")
        assert plano.categoria == "Financeiros"
        assert plano.passa_pela_ia is False

    def test_via_verde_conta_como_ja_indexado(self):
        """`skip_index` nunca será marcado como indexado: sem esta cláusula
        os ficheiros acumulavam-se na Index para sempre."""
        plano = planear_entrada({"skip_index": True}, "Imóvel")
        assert plano.categoria == "Imóvel"
        assert plano.passa_pela_ia is False

    @pytest.mark.parametrize("pedida", ["", "auto", "Auto", "Outros", "other", None, "  "])
    def test_indexado_e_sem_escolha_dá_Outros_sem_IA(self, pedida):
        plano = planear_entrada({"is_indexed": True}, pedida)
        assert plano.categoria == "Outros"
        assert plano.passa_pela_ia is False

    @pytest.mark.parametrize("valor", ["true", 1, "yes", None, "False"])
    def test_so_o_booleano_verdadeiro_conta_como_indexado(self, valor):
        """Um texto «true» ou um 1 não é a marca de indexação: falha fechada
        para o lado de ENTRAR na fila (gastar IA a mais nota-se; perder um
        ficheiro numa pasta errada, não)."""
        plano = planear_entrada({"is_indexed": valor}, "Financeiros")
        assert plano.categoria == CATEGORIA_INDEX

    def test_processo_inexistente_trata_se_como_por_indexar(self):
        assert planear_entrada(None, "Outros").categoria == CATEGORIA_INDEX

    def test_a_descricao_para_o_ecra_diz_onde_foi_parar_e_porque(self):
        d = intake.descricao_para_o_utilizador(planear_entrada({}, "Financeiros"))
        assert d["fila_ia"] is True
        assert d["categoria_pedida"] == "Financeiros"
        assert d["categoria_final"] == "Index"
        assert d["aviso"]
        d2 = intake.descricao_para_o_utilizador(planear_entrada({"is_indexed": True}, "Financeiros"))
        assert d2["fila_ia"] is False and d2["aviso"] is None


class TestAParedeDaPastaIndex:
    LISTAGEM = {
        "files": {
            "Index": [{"name": "cc.pdf", "size": 100}],
            "Outros": [{"name": "n.pdf", "size": 10}],
        },
        "stats": {"total_files": 2, "total_size": 110, "total_size_formatted": "110 B"},
    }

    @pytest.mark.parametrize("papel", ["admin", "ceo", "diretor", "indexacao"])
    def test_quem_vê_a_Index_recebe_a_listagem_inteira(self, papel):
        res = retirar_o_index_da_listagem(self.LISTAGEM, {"role": papel})
        assert "Index" in res["files"]

    @pytest.mark.parametrize("papel", ["consultor", "intermediario", "administrativo", "parceiro"])
    def test_os_outros_perfis_nao_recebem_a_Index_e_o_total_desce(self, papel):
        res = retirar_o_index_da_listagem(self.LISTAGEM, {"role": papel})
        assert "Index" not in res["files"]
        assert res["stats"]["total_files"] == 1
        assert res["stats"]["total_size"] == 10

    def test_o_perfil_EFECTIVO_manda_nao_o_do_token(self):
        """Quem tem base consultor e entra COMO diretor vê; o inverso não."""
        assert pode_ver_o_index({"role": "consultor", "effective_role": "diretor"})
        assert not pode_ver_o_index({"role": "admin", "effective_role": "consultor"})

    def test_a_listagem_original_nao_e_mutada(self):
        retirar_o_index_da_listagem(self.LISTAGEM, {"role": "consultor"})
        assert "Index" in self.LISTAGEM["files"]

    def test_sem_utilizador_falha_fechado(self):
        assert not pode_ver_o_index(None)
        assert "Index" not in retirar_o_index_da_listagem(self.LISTAGEM, None)["files"]


class TestOsFicheirosEmIndexacaoContamSeSemSeMostrarem:
    def test_quem_nao_vê_a_Index_sabe_quantos_aguardam(self):
        res = retirar_o_index_da_listagem(TestAParedeDaPastaIndex.LISTAGEM, {"role": "consultor"})
        assert res["em_indexacao"] == 1

    def test_quem_vê_não_recebe_o_contador_porque_tem_a_lista(self):
        res = retirar_o_index_da_listagem(TestAParedeDaPastaIndex.LISTAGEM, {"role": "admin"})
        assert "em_indexacao" not in res


class TestAParedeNasListagensSemList_files:
    DOCS = [
        {"s3_path": "Documentação Clientes/c/Index/cc.pdf"},
        {"s3_path": "Documentação Clientes/c/Financeiros/irs.pdf"},
        {"s3_path": "Documentação Clientes/c/Outros/x.pdf", "in_index_queue": True},
        {"s3_path": "Documentação Clientes/Indexador/y.pdf"},
    ]

    def test_a_chave_compara_o_segmento_e_nao_o_texto(self):
        assert intake.chave_esta_na_index("Documentação Clientes/c/Index/cc.pdf")
        assert intake.chave_esta_na_index("a/b/index/x.pdf")
        assert not intake.chave_esta_na_index("Documentação Clientes/Indexador/y.pdf")
        assert not intake.chave_esta_na_index("Index")
        assert not intake.chave_esta_na_index(None)

    def test_quem_nao_vê_perde_a_Index_e_o_que_esta_na_fila(self):
        res = intake.retirar_documentos_da_index(self.DOCS, {"role": "consultor"})
        assert [d["s3_path"] for d in res] == [
            "Documentação Clientes/c/Financeiros/irs.pdf",
            "Documentação Clientes/Indexador/y.pdf",
        ]

    def test_quem_vê_recebe_tudo(self):
        assert intake.retirar_documentos_da_index(self.DOCS, {"role": "diretor"}) == self.DOCS


# ---------------------------------------------------------------------
# Upload multipart — a decisão chega à pasta e à IA
# ---------------------------------------------------------------------
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from fastapi import BackgroundTasks  # noqa: E402

from services import document_upload  # noqa: E402


@pytest.fixture
def upload_env(fake_async_db):
    """O upload multipart com as fronteiras externas falseadas.

    Falseia SÓ o que sai do processo (S3, resolução do processo, conversão,
    histórico, pedido do Portal); a decisão do desvio e o registo da fila são
    os REAIS. As asserções são sobre os PARÂMETROS que saem — a pasta que
    segue para o S3 e as tarefas agendadas —, nunca sobre um duplo que
    reimplementa a decisão.
    """

    def montar(processo: dict, *, categoria="Financeiros"):
        s3 = MagicMock()
        s3.is_configured.return_value = True
        s3.upload_file.return_value = "Documentação Clientes/cli-1/Index/f.pdf"
        s3.get_presigned_url.return_value = "https://x"
        triagem = AsyncMock(return_value={"success": True, "category": "Imóvel"})
        tarefas = BackgroundTasks()
        patches = [
            patch.object(document_upload, "s3_service", s3),
            patch.object(document_upload, "db", fake_async_db),
            patch.object(intake, "db", fake_async_db),
            patch.object(
                document_upload, "resolve_process_from_flexible_id",
                AsyncMock(return_value=(processo, processo.get("id", "p-1"))),
            ),
            patch.object(
                document_upload, "_validate_and_maybe_convert",
                AsyncMock(return_value=(b"%PDF-1.4", "f.pdf", "application/pdf", False, False, False, {})),
            ),
            patch.object(document_upload, "log_history", AsyncMock()),
            patch.object(document_upload, "assert_can_upload_to_process", AsyncMock()),
            patch.object(
                document_upload, "_auto_fulfill_portal_request",
                AsyncMock(return_value={"fulfilled": 0}),
            ),
            patch("services.document_categorization.categorize_document_with_ai", triagem),
        ]
        return s3, tarefas, triagem, patches, categoria

    return montar


async def _enviar(env, processo, categoria="Financeiros"):
    s3, tarefas, triagem, patches, _ = env(processo, categoria=categoria)
    for p in patches:
        p.start()
    try:
        res = await document_upload.run_upload_file_s3(
            "p-1", file_content=b"%PDF-1.4", original_filename="f.pdf",
            content_type="application/pdf", category=categoria, empresa_nif=None,
            custom_filename=None, user={"id": "u1", "role": "consultor"},
            background_tasks=tarefas,
        )
    finally:
        for p in patches:
            p.stop()
    return res, s3, tarefas, triagem


@pytest.mark.asyncio
class TestOUploadSegueOPlano:
    async def test_processo_por_indexar_grava_na_Index_e_agenda_UMA_categorizacao(self, upload_env, fake_async_db):
        processo = {"id": "p-1", "client_name": "Ana", "is_indexed": False}
        res, s3, tarefas, triagem = await _enviar(upload_env, processo)

        # A pasta que SEGUE para o S3 — não o que a resposta diz.
        assert s3.upload_file.call_args.args[3] == "Index"
        assert res["category"] == "Index"
        assert res["intake"]["fila_ia"] is True
        assert res["intake"]["categoria_pedida"] == "Financeiros"
        # Uma só tarefa de IA agendada, e nenhuma triagem SÍNCRONA à entrada.
        assert len(tarefas.tasks) == 1
        triagem.assert_not_called()
        # A fila é visível desde o primeiro segundo.
        meta = await fake_async_db.document_metadata.find_one({"s3_path": res["path"]})
        assert meta["in_index_queue"] is True and meta["is_categorized"] is False

    async def test_processo_indexado_guarda_na_categoria_pedida_e_nao_gasta_IA(self, upload_env, fake_async_db):
        processo = {"id": "p-1", "client_name": "Ana", "is_indexed": True}
        res, s3, tarefas, triagem = await _enviar(upload_env, processo)

        assert s3.upload_file.call_args.args[3] == "Financeiros"
        assert res["category"] == "Financeiros"
        assert res["intake"]["fila_ia"] is False
        assert len(tarefas.tasks) == 0
        triagem.assert_not_called()
        assert await fake_async_db.document_metadata.find_one({"s3_path": res["path"]}) is None

    async def test_indexado_e_pedido_Auto_nao_chama_o_modelo_para_escolher_pasta(self, upload_env):
        """Era a triagem à entrada: «Outros»/«Auto» chamava o modelo."""
        processo = {"id": "p-1", "client_name": "Ana", "is_indexed": True}
        res, s3, tarefas, triagem = await _enviar(upload_env, processo, categoria="Auto")
        assert s3.upload_file.call_args.args[3] == "Outros"
        triagem.assert_not_called()
        assert len(tarefas.tasks) == 0

    async def test_via_verde_nao_entra_na_fila(self, upload_env):
        processo = {"id": "p-1", "client_name": "Ana", "skip_index": True}
        res, s3, tarefas, _ = await _enviar(upload_env, processo, categoria="Imóvel")
        assert s3.upload_file.call_args.args[3] == "Imóvel"
        assert len(tarefas.tasks) == 0

    async def test_o_pedido_do_portal_tenta_casar_com_a_categoria_PEDIDA(self, upload_env):
        """O ficheiro fica na Index, mas o cliente pediu um «Financeiros»:
        com a categoria `Index` o pedido nunca casava e ficava pendente."""
        processo = {"id": "p-1", "client_name": "Ana", "is_indexed": False}
        s3, tarefas, triagem, patches, _ = upload_env(processo)
        fulfill = None
        for p in patches:
            m = p.start()
            if getattr(p, "attribute", "") == "_auto_fulfill_portal_request":
                fulfill = m
        try:
            await document_upload.run_upload_file_s3(
                "p-1", file_content=b"%PDF-1.4", original_filename="f.pdf",
                content_type="application/pdf", category="Financeiros", empresa_nif=None,
                custom_filename=None, user={"id": "u1", "role": "consultor"},
                background_tasks=tarefas,
            )
        finally:
            for p in patches:
                p.stop()
        assert fulfill.call_args.args[1]["category"] == "Financeiros"


# ---------------------------------------------------------------------
# Upload directo (URL pré-assinado + confirmação)
# ---------------------------------------------------------------------
from services import document_direct_upload as directo  # noqa: E402

_VEREDICTO = MagicMock(tipo_detectado="application/pdf", tamanho=1234)
_PROC_DIRECTO = {
    "id": "p-1", "client_name": "Ana Cliente",
    "s3_folder": "Documentação Clientes/cli-1",
}


async def _gerar_url(processo, categoria):
    s3 = MagicMock()
    s3.is_configured.return_value = True
    s3.generate_upload_presigned_url.return_value = {
        "upload_url": "https://u", "file_key": "k", "expires_at": "x", "expires_in_seconds": 300,
    }
    db_falso = MagicMock()
    db_falso.processes.find_one = AsyncMock(return_value=processo)
    with patch.object(directo, "s3_service", s3), patch.object(directo, "db", db_falso), \
            patch.object(directo, "assert_can_upload_to_process", AsyncMock()):
        res = await directo.run_generate_upload_url(
            {"process_id": "p-1", "filename": "f.pdf", "content_type": "application/pdf",
             "category": categoria},
            user={"email": "a@b.pt"},
        )
    return res, s3


async def _confirmar(fake_db, processo, categoria="Financeiros"):
    s3 = MagicMock()
    s3.get_file_content.return_value = b"%PDF-1.4"
    tarefas = BackgroundTasks()
    triagem = AsyncMock(return_value={"success": True, "category": "Imóvel"})
    fulfill = AsyncMock(return_value={"fulfilled": 0})
    db_falso = MagicMock()
    db_falso.processes.find_one = AsyncMock(return_value=processo)
    with patch.object(directo, "s3_service", s3), \
            patch.object(directo, "db", db_falso), \
            patch.object(intake, "db", fake_db), \
            patch.object(directo, "exigir_conteudo_valido", AsyncMock(return_value=_VEREDICTO)), \
            patch.object(directo, "log_history", AsyncMock()), \
            patch.object(directo, "assert_can_upload_to_process", AsyncMock()), \
            patch.object(directo, "_auto_fulfill_portal_request", fulfill), \
            patch("services.document_categorization.categorize_document_with_ai", triagem):
        res = await directo.run_confirm_upload(
            {"process_id": "p-1",
             "file_key": "Documentação Clientes/cli-1/Index/f.pdf",
             "original_filename": "f.pdf", "category": categoria},
            background_tasks=tarefas, user={"id": "u1", "name": "Ana"},
        )
    return res, tarefas, triagem, fulfill


@pytest.mark.asyncio
class TestOUploadDirectoSegueOPlano:
    async def test_o_URL_pre_assinado_e_pedido_para_a_pasta_Index_se_por_indexar(self):
        """A pasta fica presa à chave do PUT: decide-se ao GERAR o URL."""
        res, s3 = await _gerar_url({**_PROC_DIRECTO, "is_indexed": False}, "Financeiros")
        assert s3.generate_upload_presigned_url.call_args.kwargs["category"] == "Index"
        assert res["intake"]["fila_ia"] is True

    async def test_o_URL_pre_assinado_respeita_a_categoria_se_ja_indexado(self):
        res, s3 = await _gerar_url({**_PROC_DIRECTO, "is_indexed": True}, "Financeiros")
        assert s3.generate_upload_presigned_url.call_args.kwargs["category"] == "Financeiros"
        assert res["intake"]["fila_ia"] is False

    async def test_confirmar_por_indexar_entra_na_fila_e_agenda_uma_IA(self, fake_async_db):
        res, tarefas, triagem, fulfill = await _confirmar(
            fake_async_db, {**_PROC_DIRECTO, "is_indexed": False}
        )
        assert res["category"] == "Index"
        assert len(tarefas.tasks) == 1
        triagem.assert_not_called()
        meta = await fake_async_db.document_metadata.find_one({"s3_path": res["s3_path"]})
        assert meta["in_index_queue"] is True
        assert fulfill.call_args.args[1]["category"] == "Financeiros"

    async def test_confirmar_ja_indexado_nao_gasta_IA_nem_le_o_ficheiro(self, fake_async_db):
        res, tarefas, triagem, _ = await _confirmar(
            fake_async_db, {**_PROC_DIRECTO, "is_indexed": True}
        )
        assert res["category"] == "Financeiros"
        assert res["auto_categorization"] == "dispensada"
        assert len(tarefas.tasks) == 0
        triagem.assert_not_called()
        assert await fake_async_db.document_metadata.find_one({"s3_path": res["s3_path"]}) is None


# ---------------------------------------------------------------------
# A parede chega às rotas (comportamento + ligação)
# ---------------------------------------------------------------------
from services import document_queries  # noqa: E402


@pytest.mark.asyncio
class TestAParedeChegaAosMetadados:
    async def _semear(self, fake):
        await fake.processes.insert_one({"id": "p-1", "client_name": "Ana"})
        await fake.document_metadata.insert_one({
            "id": "m1", "process_id": "p-1", "filename": "cc.pdf",
            "s3_path": "Documentação Clientes/c/Index/cc.pdf", "in_index_queue": True,
        })
        await fake.document_metadata.insert_one({
            "id": "m2", "process_id": "p-1", "filename": "irs.pdf",
            "s3_path": "Documentação Clientes/c/Financeiros/irs.pdf",
        })

    async def test_o_consultor_nao_recebe_a_Index_nem_o_URL_pre_assinado(self, fake_async_db):
        await self._semear(fake_async_db)
        s3 = MagicMock()
        s3.get_presigned_url.side_effect = lambda k: f"https://assinado/{k}"
        with patch.object(document_queries, "db", fake_async_db), \
                patch.object(document_queries, "s3_service", s3):
            res = await document_queries.run_get_document_metadata("p-1", user={"role": "consultor"})
        assert [d["filename"] for d in res["documents"]] == ["irs.pdf"]
        assinados = [c.args[0] for c in s3.get_presigned_url.call_args_list]
        assert not any("/Index/" in k for k in assinados)

    async def test_o_diretor_recebe_tudo(self, fake_async_db):
        await self._semear(fake_async_db)
        s3 = MagicMock()
        s3.get_presigned_url.return_value = "https://x"
        with patch.object(document_queries, "db", fake_async_db), \
                patch.object(document_queries, "s3_service", s3):
            res = await document_queries.run_get_document_metadata("p-1", user={"role": "diretor"})
        assert len(res["documents"]) == 2


class TestAsRotasLigamAParede:
    def _fonte(self, nome_funcao):
        from routes import documents as rota
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        return codigo_da_funcao_sem_comentarios(getattr(rota, nome_funcao))

    def test_a_listagem_do_cliente_passa_pela_parede(self):
        assert "retirar_o_index_da_listagem(files, user)" in self._fonte("list_client_files")

    @pytest.mark.parametrize("funcao", ["get_process_documents", "get_document_metadata", "search_documents"])
    def test_as_outras_tres_passam_o_utilizador(self, funcao):
        assert "user=user" in self._fonte(funcao)


@pytest.mark.asyncio
class TestOConflitoVerificaOndeOFicheiroVaiFicar:
    async def _verificar(self, processo):
        from services import document_upload_conflict as conflito

        existe = MagicMock(return_value=False)
        s3 = MagicMock()
        s3.file_exists = existe
        db_falso = MagicMock()
        db_falso.processes.find_one = AsyncMock(return_value=processo)
        with patch.object(conflito, "s3_service", s3), patch.object(conflito, "db", db_falso), \
                patch.object(conflito, "assert_can_upload_to_process", AsyncMock()):
            res = await conflito.run_check_upload_conflict(
                {"process_id": "p-1", "filenames": ["a.pdf"], "category": "Financeiros"},
                user={"id": "u1", "role": "diretor"},
            )
        return res, [c.args[0] for c in existe.call_args_list]

    async def test_por_indexar_verifica_a_pasta_Index(self):
        res, consultas = await self._verificar({"id": "p-1", "s3_folder": "Documentação Clientes/c"})
        assert consultas == ["Documentação Clientes/c/Index/a.pdf"]
        assert res["category"] == "Index"

    async def test_indexado_verifica_a_pasta_pedida(self):
        res, consultas = await self._verificar(
            {"id": "p-1", "s3_folder": "Documentação Clientes/c", "is_indexed": True}
        )
        assert consultas == ["Documentação Clientes/c/Financeiros/a.pdf"]
