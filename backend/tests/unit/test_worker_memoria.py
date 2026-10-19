"""O `powercell-worker` morria por OOM (limite de 512 MB no Render).

Não era uma fuga: eram picos sobrepostos — o email inteiro em bytes, a árvore MIME, cada anexo
descodificado só para lhe medir o tamanho, as quatro pastas IMAP em memória ao mesmo tempo, o laço
da fila e o agendador a trabalhar juntos, quatro threads IMAP, um `gather` sobre 200 caixas. Estes
testes medem cada botão a um nível em que a mutação morde (o duplo de IMAP é ao nível do protocolo,
não uma reimplementação da função).
"""
from __future__ import annotations

import asyncio
import base64
import email
import email.message
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from unittest.mock import patch

import pytest

from services import memory_guard as mg


# ──────────────────────────────────────────────────────────────────────────────
#  memory_guard
# ──────────────────────────────────────────────────────────────────────────────
class TestOsBotoes:

    @pytest.mark.parametrize("valor", ["", "abc", "0", "-3", "  "])
    def test_valor_invalido_cai_na_omissao_e_nunca_desliga_o_tecto(self, monkeypatch, valor):
        monkeypatch.setenv("IMAP_BATCH_SIZE", valor)
        assert mg.tamanho_do_lote_imap() == mg.OMISSAO_LOTE_IMAP

    def test_valor_valido_manda(self, monkeypatch):
        monkeypatch.setenv("IMAP_BATCH_SIZE", "7")
        monkeypatch.setenv("WORKER_MAX_CONCURRENCY", "2")
        monkeypatch.setenv("EMAIL_EXECUTOR_WORKERS", "1")
        assert (mg.tamanho_do_lote_imap(), mg.concorrencia_do_worker(), mg.threads_imap()) == (7, 2, 1)

    def test_o_tecto_do_email_tem_um_minimo(self, monkeypatch):
        monkeypatch.setenv("IMAP_MAX_EMAIL_BYTES", "10")  # absurdo: saltava tudo
        assert mg.tamanho_maximo_do_email() == mg.OMISSAO_EMAIL_MAXIMO

    def test_em_lotes_parte_sem_perder_nem_repetir(self):
        lotes = list(mg.em_lotes(list(range(45)), 20))
        assert [len(l) for l in lotes] == [20, 20, 5]
        assert [x for l in lotes for x in l] == list(range(45))

    def test_libertar_memoria_nunca_levanta(self):
        with patch("ctypes.CDLL", side_effect=OSError("sem glibc")):
            assert isinstance(mg.libertar_memoria(), int)


class TestTamanhoDoAnexoSemDescodificar:

    @pytest.mark.parametrize("n", [0, 1, 2, 3, 100, 4097, 100_000])
    def test_base64_bate_com_o_tamanho_real(self, n):
        dados = bytes(range(256)) * (n // 256 + 1)
        dados = dados[:n]
        parte = MIMEApplication(dados, _subtype="pdf")
        assert mg.tamanho_do_anexo(parte) == n

    def test_nunca_descodifica(self):
        parte = MIMEApplication(b"x" * 5000, _subtype="pdf")
        with patch.object(email.message.Message, "get_payload", autospec=True,
                          side_effect=email.message.Message.get_payload) as espia:
            mg.tamanho_do_anexo(parte)
        assert all(not c.kwargs.get("decode") for c in espia.call_args_list)

    def test_texto_simples_e_o_comprimento(self):
        assert mg.tamanho_do_anexo(MIMEText("olá", "plain", "utf-8")) > 0

    def test_multipart_nao_e_um_anexo_folha(self):
        assert mg.tamanho_do_anexo(MIMEMultipart()) == 0


# ──────────────────────────────────────────────────────────────────────────────
#  O laço IMAP, com um servidor falso AO NÍVEL DO PROTOCOLO
# ──────────────────────────────────────────────────────────────────────────────
def _mensagem(i, anexo=0):
    msg = MIMEMultipart()
    msg["Message-ID"] = f"<m{i}@x.pt>"
    msg["From"] = "cliente@x.pt"
    msg["To"] = "geral@x.pt"
    msg["Subject"] = f"Assunto {i}"
    msg["Date"] = "Mon, 19 Oct 2026 10:00:00 +0000"
    msg.attach(MIMEText(f"corpo {i}", "plain", "utf-8"))
    if anexo:
        parte = MIMEApplication(b"A" * anexo, _subtype="pdf")
        parte.add_header("Content-Disposition", "attachment", filename="doc.pdf")
        msg.attach(parte)
    return msg.as_bytes()


class _ImapFalso:
    """imaplib mínimo: SEARCH devolve os números; FETCH (RFC822.SIZE) e (BODY.PEEK[])."""

    def __init__(self, mensagens):
        self.mensagens = mensagens  # {b"1": bytes}
        self.fetches = []

    def login(self, *a):
        return "OK", []

    def select(self, *a):
        return "OK", [b"1"]

    def search(self, *a):
        return "OK", [b" ".join(self.mensagens)]

    def fetch(self, num, what):
        self.fetches.append((num, what))
        dados = self.mensagens[num]
        if "RFC822.SIZE" in what:
            return "OK", [b"%s (RFC822.SIZE %d)" % (num, len(dados))]
        return "OK", [(b"%s (BODY[] {%d}" % (num, len(dados)), dados), b")"]

    def logout(self):
        return "BYE", []


def _conta():
    from services.email_service import EmailAccount

    return EmailAccount(name="t", imap_server="i", imap_port=993, smtp_server="s", smtp_port=465,
                        email="geral@x.pt", password="p")


def _correr(mensagens, **kw):
    import services.email_service as es

    falso = _ImapFalso(mensagens)
    with patch.object(es.imaplib, "IMAP4_SSL", return_value=falso):
        return es._fetch_all_from_folder_sync(_conta(), "INBOX", 30, kw.pop("max_emails", 1000)), falso


class TestOLacoDeSincronizacao:

    def test_liberta_a_memoria_no_fim_de_cada_lote(self, monkeypatch):
        import services.email_service as es

        monkeypatch.setenv("IMAP_BATCH_SIZE", "20")
        chamadas = []
        monkeypatch.setattr(es, "libertar_memoria", lambda: chamadas.append(1) or 0)
        mensagens = {b"%d" % i: _mensagem(i) for i in range(1, 46)}
        res, _ = _correr(mensagens)
        assert len(res["emails"]) == 45
        assert len(chamadas) == 2  # nos emails 20 e 40; os leves não libertam um a um

    def test_um_email_pesado_liberta_logo(self, monkeypatch):
        import services.email_service as es

        chamadas = []
        monkeypatch.setattr(es, "libertar_memoria", lambda: chamadas.append(1) or 0)
        mensagens = {b"1": _mensagem(1, anexo=2 * 1024 * 1024), b"2": _mensagem(2)}
        _correr(mensagens)
        assert len(chamadas) == 1

    def test_o_tecto_de_tamanho_salta_o_email_sem_o_descarregar(self, monkeypatch):
        monkeypatch.setenv("IMAP_MAX_EMAIL_BYTES", str(200 * 1024))
        mensagens = {b"1": _mensagem(1, anexo=400 * 1024), b"2": _mensagem(2)}
        res, falso = _correr(mensagens)
        assert [e["subject"] for e in res["emails"]] == ["Assunto 2"]
        # o email grande só foi PERGUNTADO (RFC822.SIZE); o corpo nunca foi pedido
        assert (b"1", "(BODY.PEEK[])") not in falso.fetches

    def test_o_tamanho_do_anexo_sai_sem_descodificar(self):
        mensagens = {b"1": _mensagem(1, anexo=50_000)}
        with patch.object(email.message.Message, "get_payload", autospec=True,
                          side_effect=email.message.Message.get_payload) as espia:
            res, _ = _correr(mensagens)
        assert res["emails"][0]["attachments"][0]["size"] == 50_000
        # `decode=True` é o que alocava uma cópia do anexo inteiro: só o corpo de texto o usa
        decodificados = [c for c in espia.call_args_list if c.kwargs.get("decode")]
        assert all(len(c.args) == 1 for c in decodificados)
        assert len(decodificados) <= 2  # corpo (plain) — nunca o PDF

    def test_um_email_que_rebenta_nao_impede_a_libertacao_nem_os_seguintes(self, monkeypatch):
        import services.email_service as es

        chamadas = []
        monkeypatch.setattr(es, "libertar_memoria", lambda: chamadas.append(1) or 0)
        monkeypatch.setenv("IMAP_BATCH_SIZE", "2")
        mensagens = {b"1": b"isto nao e um email", b"2": _mensagem(2)}
        res, _ = _correr(mensagens)
        assert [e["subject"] for e in res["emails"]] == ["Assunto 2"]
        assert chamadas  # o `finally` corre também na iteração que falhou/saltou


# ──────────────────────────────────────────────────────────────────────────────
#  O pico silencioso: o tecto de 15 MB nunca disparou
# ──────────────────────────────────────────────────────────────────────────────
class TestOTectoAnunciadoPeloServidor:
    """O `imaplib` devolve `[b'1 (RFC822.SIZE 4096)']` (bytes, não tuplo). O código antigo fazia
    `x[0]` sobre esse `bytes` (um `int`), `str(49)` nunca continha `RFC822.SIZE` e o tecto anti-OOM
    de 15 MB **nunca disparou** — a pré-verificação era código morto."""

    @pytest.mark.parametrize("resposta", [
        ("OK", [b"1 (RFC822.SIZE 4096)"]),                       # a forma REAL do imaplib
        ("OK", [(b"1 (RFC822.SIZE 4096 {0}", b"")]),             # com literal
        ("OK", ["1 (RFC822.SIZE 4096)"]),                        # str
    ])
    def test_le_o_tamanho_nas_formas_reais(self, resposta):
        from services.email_service import _tamanho_anunciado

        assert _tamanho_anunciado(resposta) == 4096

    @pytest.mark.parametrize("resposta", [None, (), ("OK", []), ("OK", [None]), ("OK", [b"lixo"]), ("NO", None)])
    def test_o_que_nao_vem_conta_zero_e_nunca_levanta(self, resposta):
        from services.email_service import _tamanho_anunciado

        assert _tamanho_anunciado(resposta) == 0

    def test_a_forma_real_do_imaplib_e_a_que_o_duplo_usa(self):
        """O duplo do teste anterior usava a mesma forma; se um dia divergir da do imaplib, avisa."""
        falso = _ImapFalso({b"1": _mensagem(1)})
        _, dados = falso.fetch(b"1", "(RFC822.SIZE)")
        assert isinstance(dados[0], bytes)


# ──────────────────────────────────────────────────────────────────────────────
#  Gravar por pasta
# ──────────────────────────────────────────────────────────────────────────────
class TestSincronizarPorPasta:

    @pytest.mark.asyncio
    async def test_cada_pasta_e_gravada_e_largada_antes_de_ir_buscar_a_seguinte(self, fake_async_db, monkeypatch):
        import services.email_service as es
        from unittest.mock import AsyncMock, MagicMock

        monkeypatch.setenv("ENVIRONMENT", "production")
        eventos: list[str] = []

        def _pasta(nome, n):
            return {"emails": [
                {"message_id": f"<{nome}{i}@x.pt>", "from_email": "a@x.pt", "to_emails": ["b@x.pt"],
                 "subject": f"{nome} {i}", "body": "", "body_html": "", "attachments": [],
                 "date": "2026-10-19T10:00:00+00:00", "direction": "received"} for i in range(n)
            ], "connection_error": None}

        def buscar(account, folder, days, max_emails):
            eventos.append(f"fetch:{folder}")
            return _pasta(folder, 2)

        async def inserir(_db, doc):
            eventos.append(f"gravar:{doc['subject'].split()[0]}")

        config = {"email_address": "ana@x.pt", "encrypted_password": "enc", "imap_server": "i",
                  "imap_port": 993, "smtp_server": "s", "smtp_port": 465, "resolved_company_id": "c1"}
        with patch.object(es, "_fetch_all_from_folder_sync", buscar), \
                patch.object(es, "db", fake_async_db), \
                patch.object(es, "inserir_email", inserir), \
                patch.object(es, "_ja_tenho_este_email", AsyncMock(return_value=None)), \
                patch.object(es, "pastas_candidatas", AsyncMock(return_value={
                    "sent": ["Sent"], "drafts": ["Drafts"], "trash": ["Trash"]})), \
                patch("services.encryption.encryption_service.decrypt", return_value="pw"), \
                patch("services.tenant_network.resolve_tenant_stamp", AsyncMock(return_value={})), \
                patch("services.mailbox_health.registar_sucesso", AsyncMock()), \
                patch("services.mailbox_health.registar_falha", AsyncMock()), \
                patch("services.email_realtime.notify_new_email", AsyncMock()), \
                patch("services.email_process_link.processo_da_etiqueta", AsyncMock(return_value=None)), \
                patch("services.email_client_match.resolver_processo_por_endereco",
                      AsyncMock(return_value=MagicMock(process_id=None, ambiguo=False))):
            res = await es.sync_user_emails("u1234567890", days=3, max_emails=50, resolved_config=config)

        assert res["total_synced"] == 8
        # Ordem: a pasta N é GRAVADA por inteiro antes de a N+1 ser pedida ao servidor.
        assert eventos == [
            "fetch:INBOX", "gravar:INBOX", "gravar:INBOX",
            "fetch:Sent", "gravar:Sent", "gravar:Sent",
            "fetch:Drafts", "gravar:Drafts", "gravar:Drafts",
            "fetch:Trash", "gravar:Trash", "gravar:Trash",
        ]

    def test_o_codigo_ja_nao_junta_as_quatro_pastas(self):
        import services.email_service as es
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(es.sync_user_emails)
        assert "all_emails" not in fonte
        assert fonte.count("await _gravar(") == 4


# ──────────────────────────────────────────────────────────────────────────────
#  Concorrência
# ──────────────────────────────────────────────────────────────────────────────
class TestConcorrenciaLimitada:

    @pytest.mark.asyncio
    async def test_gather_limitado_respeita_o_tecto_e_a_ordem(self, monkeypatch):
        import services.email_service as es

        em_curso = 0
        maximo = 0

        async def trabalho(i):
            nonlocal em_curso, maximo
            em_curso += 1
            maximo = max(maximo, em_curso)
            await asyncio.sleep(0.01)
            em_curso -= 1
            if i == 3:
                raise ValueError("falhou")
            return i

        monkeypatch.setenv("IMAP_SYNC_CONCURRENCY", "2")
        res = await es._gather_limitado([trabalho(i) for i in range(8)])
        assert maximo == 2
        assert [r for r in res if not isinstance(r, Exception)] == [0, 1, 2, 4, 5, 6, 7]
        assert isinstance(res[3], ValueError)  # a posição do erro é a da corrotina (mapeia por índice)

    def test_o_gather_sem_limite_saiu_da_sincronizacao_de_todas_as_caixas(self):
        import services.email_service as es
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        assert "asyncio.gather" not in codigo_da_funcao_sem_comentarios(es.sync_all_user_emails)

    def test_o_executor_imap_do_worker_tem_uma_thread(self):
        """`worker.py` define a variável ANTES de qualquer `services.*`; o executor lê-a no import."""
        import subprocess
        import sys

        codigo = (
            "import os; os.environ['EMAIL_EXECUTOR_WORKERS']='1';"
            "import services.email_service as es; print(es._email_executor._max_workers)"
        )
        saida = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                               cwd=str(__import__('pathlib').Path(__file__).resolve().parents[2]))
        assert saida.stdout.strip().splitlines()[-1] == "1", saida.stderr[-400:]

    def test_o_worker_define_o_limite_antes_de_importar_servicos(self):
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "worker.py").read_text(encoding="utf-8")
        assert fonte.index('os.environ.setdefault("EMAIL_EXECUTOR_WORKERS"') < fonte.index("from database import db")


def _carregar_worker():
    """`import worker` resolve para o PACOTE `worker/` (ARQ); o processo do Render corre o FICHEIRO
    `worker.py` como `__main__`. Carrega-se o ficheiro pelo caminho."""
    import importlib.util
    from pathlib import Path

    caminho = Path(__file__).resolve().parents[2] / "worker.py"
    spec = importlib.util.spec_from_file_location("worker_script", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TestOWorkerSoFazUmTrabalhoPesadoDeCada:

    @pytest.mark.asyncio
    async def test_o_job_do_agendador_e_a_tarefa_da_fila_nao_se_sobrepoem(self, monkeypatch):
        worker = _carregar_worker()

        monkeypatch.setenv("WORKER_MAX_CONCURRENCY", "1")
        monkeypatch.setattr(worker, "_semaforo_pesado", None)
        em_curso = 0
        maximo = 0

        async def pesado(*a, **k):
            nonlocal em_curso, maximo
            em_curso += 1
            maximo = max(maximo, em_curso)
            await asyncio.sleep(0.02)
            em_curso -= 1

        async def tarefa(_t):
            await pesado()

        with patch("services.job_executors.executar_job", pesado), patch.object(worker, "process_task", tarefa):
            async def uma_da_fila():
                async with worker._semaforo():
                    await worker.process_task({"id": "t"})

            await asyncio.gather(worker._correr_job("scheduled_tasks"), uma_da_fila(), worker._correr_job("webmail_worker_sync"))
        assert maximo == 1

    @pytest.mark.asyncio
    async def test_com_dois_o_limite_sobe(self, monkeypatch):
        worker = _carregar_worker()

        monkeypatch.setenv("WORKER_MAX_CONCURRENCY", "2")
        monkeypatch.setattr(worker, "_semaforo_pesado", None)
        em_curso = maximo = 0

        async def pesado(*a, **k):
            nonlocal em_curso, maximo
            em_curso += 1
            maximo = max(maximo, em_curso)
            await asyncio.sleep(0.02)
            em_curso -= 1

        with patch("services.job_executors.executar_job", pesado):
            await asyncio.gather(*(worker._correr_job(f"j{i}") for i in range(4)))
        assert maximo == 2

    @pytest.mark.asyncio
    async def test_a_vaga_reserva_se_antes_de_reclamar_a_tarefa(self, monkeypatch):
        """Reclamar e esperar vaga deixava a tarefa «em processamento» sem ninguém a tratar dela."""
        worker = _carregar_worker()

        monkeypatch.setattr(worker, "_semaforo_pesado", None)
        monkeypatch.setenv("WORKER_MAX_CONCURRENCY", "1")
        estado = {}

        async def reclamar(**_k):
            estado["vaga_ocupada_ao_reclamar"] = worker._semaforo().locked()
            worker.shutdown_event.set()
            return None

        worker.shutdown_event.clear()
        try:
            dormir = asyncio.sleep
            with patch.object(worker.task_queue, "get_next_task", reclamar), \
                    patch.object(worker.asyncio, "sleep", new=lambda *_a, **_k: dormir(0)):
                await worker.worker_loop()
        finally:
            worker.shutdown_event.clear()
        assert estado["vaga_ocupada_ao_reclamar"] is True


# ──────────────────────────────────────────────────────────────────────────────
#  Streaming do ZIP em massa e cursor do relatório
# ──────────────────────────────────────────────────────────────────────────────
class _CorpoS3:
    """`StreamingBody` mínimo: `read()` sem tamanho é PROIBIDO (era a leitura inteira)."""

    def __init__(self, dados, bloco_pedido=None):
        self.dados, self.fechado, self.blocos = dados, False, 0

    def iter_chunks(self, tamanho):
        for i in range(0, len(self.dados), tamanho):
            self.blocos += 1
            yield self.dados[i:i + tamanho]

    def read(self, *a):
        raise AssertionError("read() sem limite: o ficheiro inteiro em memória")

    def close(self):
        self.fechado = True


class TestZipEmMassaPorBlocos:

    def test_copia_por_blocos_fecha_o_corpo_e_o_zip_le_se(self):
        import io
        import zipfile

        import services.document_bulk_download as dbd

        dados = bytes(range(256)) * (3 * 1024 * 1024 // 256 + 5)  # ~3 MB → 4 blocos de 1 MB
        corpo = _CorpoS3(dados)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
            dbd._escrever_no_zip(z, "a.bin", corpo)
        assert corpo.fechado and corpo.blocos == 4
        with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as z:
            assert z.read("a.bin") == dados

    def test_bytes_pequenos_continuam_a_funcionar(self):
        import io
        import zipfile

        import services.document_bulk_download as dbd

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            dbd._escrever_no_zip(z, "p.txt", b"ola")
        assert zipfile.ZipFile(io.BytesIO(buffer.getvalue())).read("p.txt") == b"ola"

    def test_a_obtencao_nao_le_o_corpo_e_o_zip_nao_vive_em_bytesio(self):
        import services.document_bulk_download as dbd
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        import inspect

        fonte = codigo_sem_comentarios(inspect.getsource(dbd))
        assert '["Body"].read()' not in fonte
        assert "BytesIO" not in fonte
        assert "getvalue()" not in fonte
        assert "SpooledTemporaryFile" in fonte

    @pytest.mark.asyncio
    async def test_a_resposta_entrega_o_zip_em_blocos(self, monkeypatch):
        import io
        import zipfile
        from unittest.mock import AsyncMock

        import services.document_bulk_download as dbd

        dados = b"Z" * (2 * 1024 * 1024 + 7)
        monkeypatch.setattr(dbd, "ZIP_EM_MEMORIA_ATE", 1024)  # força o ZIP a passar para disco
        chave = "Documentação Clientes/c-1/doc.bin"
        with patch.object(dbd.s3_service, "is_configured", return_value=True), \
                patch.object(dbd, "ficheiro_no_ambito", AsyncMock(return_value=True)), \
                patch.object(dbd, "_get_s3_file_content", return_value=(_CorpoS3(dados), "application/pdf")):
            resposta = await dbd.run_bulk_download_documents({"document_ids": [chave]}, user={"id": "u"})
            partes = [p async for p in resposta.body_iterator] if hasattr(resposta.body_iterator, "__aiter__") \
                else list(resposta.body_iterator)
        assert len(partes) >= 1
        assert max(len(p) for p in partes) <= dbd.TAMANHO_DO_BLOCO
        with zipfile.ZipFile(io.BytesIO(b"".join(partes))) as z:
            assert z.read("doc.bin") == dados


class TestRelatorioDeIaPorCursor:

    def test_o_relatorio_semanal_ja_nao_traz_todos_os_processos_para_a_memoria(self):
        from services.scheduled_tasks import ScheduledTasksService
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(ScheduledTasksService._enviar_relatorio_ia_de)
        assert "to_list(None)" not in fonte
        assert "async for proc in" in fonte


class TestOAmbienteDoWorker:

    def test_o_dockerfile_do_worker_fixa_os_botoes_de_memoria(self):
        from pathlib import Path

        texto = (Path(__file__).resolve().parents[2] / "Dockerfile.worker").read_text(encoding="utf-8")
        for chave in ("MALLOC_ARENA_MAX=2", "EMAIL_EXECUTOR_WORKERS=1", "WORKER_MAX_CONCURRENCY=1",
                      "IMAP_BATCH_SIZE=20", "IMAP_MAX_EMAIL_BYTES="):
            assert chave in texto, chave


class TestObterDoS3NaoLeOCorpo:
    """Um nível ABAIXO do duplo de `_get_s3_file_content`: o cliente boto3 falso ao nível da chamada.
    A mutação «volta a ler o corpo inteiro» sobrevivia porque o `_escrever_no_zip` também aceita
    bytes — o teste tem de afirmar o que SAI de `_get_s3_file_content`."""

    def test_devolve_o_corpo_em_streaming_e_nao_os_bytes(self):
        import services.document_bulk_download as dbd

        corpo = _CorpoS3(b"x" * 10)

        class _S3:
            def get_object(self, Bucket, Key):
                return {"Body": corpo, "ContentType": "application/pdf"}

        with patch.object(dbd.s3_service, "s3_client", _S3()), patch.object(dbd.s3_service, "bucket_name", "b"):
            conteudo, tipo = dbd._get_s3_file_content("k")
        assert conteudo is corpo and tipo == "application/pdf"  # `read()` aqui levantava AssertionError
