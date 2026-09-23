"""
Bateria e2e — Nota de voz do consultor: áudio → IA → BD → tempo real.

Exercita a cadeia COMPLETA do Épico 7 num único fluxo por teste, em vez de
validar cada peça isoladamente:

    upload de áudio (endpoint)
        → arquivo do áudio (S3)
        → tarefa de acompanhamento (TaskLog)
        → transcrição (ASR)
        → extracção de resumo + tarefas (LLM)
        → resumo na timeline (`db.activities`)
        → tarefas em `db.tasks` (pelo caminho canónico, com notificação)
        → eventos `task_*` no canal Redis → WebSocket do DONO da tarefa

CAMINHOS COBERTOS:
  1. Caminho feliz — tudo responde.
  2. Transcrição em baixo — a tarefa falha com motivo legível e nada fica
     escrito a meio.
  3. LLM em baixo — degradação graciosa: a transcrição NÃO se perde, entra
     na timeline, e não se inventam tarefas.
  4. LLM a devolver lixo — o mesmo, sem rebentar.
  5. S3 em baixo — a nota processa na mesma (o arquivo é acessório).
  6. Tempo real — os envelopes levam o `user_id` de quem gravou e o
     `process_id` certo, e o terminal traz o que o cliente precisa para se
     actualizar sem refresh.
  7. Guardas do endpoint — papel sem acesso, processo inexistente, formato
     recusado, ficheiro vazio e gravação demasiado grande.

SEM MONGO E SEM REDE: usa a `FakeAsyncDatabase` de `tests/unit/conftest.py`
e duplos explícitos (`FakeASRService`/`FakeLLMService`), pelo que corre em
qualquer job. Nenhuma API paga é contactada.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import (
    task_api_crud,
    task_api_helpers,
    task_log_service,
    voice_note_api,
    voice_note_engine,
)
from services.voice_extraction import ErroDeExtraccao
from services.voice_transcription import ErroDeTranscricao, ResultadoTranscricao
from tests.unit.conftest import FakeAsyncDatabase

pytestmark = pytest.mark.integration


# ====================================================================
# CENÁRIO BASE
# ====================================================================

CONSULTOR = {
    "id": "u-consultor",
    "name": "Carla Consultora",
    "role": "consultor",
    "email": "carla@precisioncredito.pt",
}
OUTRO_UTILIZADOR = {"id": "u-intruso", "name": "Intruso", "role": "consultor"}

PROCESS_ID = "proc-ch-voz"
AUDIO = b"RIFF-um-webm-qualquer" * 64

TRANSCRICAO = (
    "Reunião com a cliente. Ficou combinado que envia os recibos de "
    "vencimento até sexta-feira. Tenho de pedir a avaliação do imóvel ao "
    "banco amanhã de manhã."
)

EXTRACCAO = {
    "resumo_timeline": (
        "Reunião com a cliente: entrega os recibos de vencimento até sexta "
        "e o consultor pede a avaliação do imóvel ao banco."
    ),
    "tarefas_extraidas": [
        {
            "titulo": "Pedir avaliação do imóvel ao banco",
            "descricao": "Combinado na reunião.",
            "due_date": "2026-09-23T09:00:00+00:00",
            "prioridade": "Alta",
        },
        {
            "titulo": "Receber recibos de vencimento da cliente",
            "descricao": "",
            "due_date": "2026-09-25T09:00:00+00:00",
            "prioridade": "Média",
        },
    ],
    "provider": "fake",
    "modelo": "fake",
}


# ====================================================================
# DUPLOS EXPLÍCITOS (o "não faças chamadas reais a APIs pagas" do briefing)
# ====================================================================


class FakeASRService:
    """Motor de transcrição falso, com resposta programável.

    Regista as chamadas para que os testes possam provar QUE FOI CHAMADO e
    com que bytes — sem isso, um teste passaria mesmo que o pipeline
    saltasse a transcrição por completo.
    """

    def __init__(self, texto=TRANSCRICAO, erro=None):
        self.texto = texto
        self.erro = erro
        self.chamadas = []

    async def __call__(self, conteudo, *, filename="", mime_type="", **kwargs):
        self.chamadas.append(
            {"bytes": len(conteudo), "filename": filename, "mime_type": mime_type}
        )
        if self.erro:
            raise self.erro
        return ResultadoTranscricao(texto=self.texto, provider="fake", modelo="fake")


class FakeLLMService:
    """Extractor falso; devolve a estrutura já normalizada ou levanta."""

    def __init__(self, resultado=None, erro=None):
        self.resultado = resultado if resultado is not None else dict(EXTRACCAO)
        self.erro = erro
        self.chamadas = []

    async def __call__(self, transcricao, *, contexto=None, **kwargs):
        self.chamadas.append({"transcricao": transcricao, "contexto": contexto})
        if self.erro:
            raise self.erro
        return self.resultado


class FakeS3:
    """Arquivo de áudio falso. `configurado=False` simula S3 em baixo."""

    def __init__(self, configurado=True, explode=False):
        self.configurado = configurado
        self.explode = explode
        self.uploads = []

    def is_configured(self):
        return self.configurado

    def upload_file(self, ficheiro, client_id, client_name, category, filename, content_type):
        if self.explode:
            raise RuntimeError("S3 indisponível")
        self.uploads.append({"category": category, "filename": filename})
        return f"{client_name}/{category}/{filename}"


class FicheiroFalso:
    """Substituto do `UploadFile` do FastAPI (só o que o handler usa)."""

    def __init__(self, conteudo=AUDIO, filename="nota.webm", content_type="audio/webm"):
        self._conteudo = conteudo
        self.filename = filename
        self.content_type = content_type

    async def read(self):
        return self._conteudo


# ====================================================================
# ARNÊS
# ====================================================================


class Arnes:
    """Monta os patches partilhados e expõe os espiões.

    O `db` é patchado módulo a módulo (não só em `database.db`): cada
    serviço faz `from database import db` no topo e fica com a SUA
    referência ao proxy — patchar apenas `database.db` deixaria o resultado
    dependente da ordem em que o pytest recolhe os ficheiros.
    """

    def __init__(self, *, asr=None, llm=None, s3=None):
        self.db = FakeAsyncDatabase()
        self.asr = asr or FakeASRService()
        self.llm = llm or FakeLLMService()
        self.s3 = s3 or FakeS3()
        self.eventos = []
        self.notificacoes = []
        self._patches = []

    async def _publish(self, event_type, payload, *, user_id, company_id=None, **kwargs):
        self.eventos.append(
            {"tipo": event_type, "payload": payload, "user_id": user_id}
        )
        return True

    async def _notificar(self, **kwargs):
        self.notificacoes.append(kwargs)
        return True

    def _correr_em_serie(self, coro, *, name=None):
        """`spawn_background_task` síncrono: o teste espera pelo pipeline.

        Em produção a corrida é fire-and-forget; aqui precisamos do
        resultado para o poder afirmar.
        """
        self.tarefa_background = asyncio.get_event_loop().create_task(coro)
        return self.tarefa_background

    async def __aenter__(self):
        await self.db.processes.insert_one(
            {
                "id": PROCESS_ID,
                "client_name": "Ana Martins",
                "process_ref": "PROC-012",
                "process_number": 12,
            }
        )
        await self.db.users.insert_one({"id": CONSULTOR["id"], "name": CONSULTOR["name"]})

        self._patches = [
            patch("database.db", self.db),
            patch.object(voice_note_api, "db", self.db),
            patch.object(voice_note_engine, "db", self.db),
            patch.object(task_log_service, "db", self.db),
            patch.object(task_api_crud, "db", self.db),
            patch.object(task_api_helpers, "db", self.db),
            patch("services.s3_storage.s3_service", self.s3),
            patch("services.voice_transcription.transcrever_audio", self.asr),
            patch("services.voice_extraction.extrair_accoes", self.llm),
            patch("services.task_events.publish_event", self._publish),
            patch("services.history.log_history", AsyncMock()),
            patch.object(task_api_crud, "log_history", AsyncMock()),
            patch.object(task_api_crud, "send_realtime_notification", self._notificar),
            patch.object(voice_note_api, "spawn_background_task", self._correr_em_serie),
        ]
        for p in self._patches:
            p.start()
        return self

    async def __aexit__(self, *exc):
        for p in reversed(self._patches):
            p.stop()
        return False

    # ── Atalhos de leitura ────────────────────────────────────────────

    async def gravar_nota(self, ficheiro=None, user=None):
        """Faz o upload e espera que o pipeline de background termine."""
        resposta = await voice_note_api.run_create_voice_note(
            PROCESS_ID, ficheiro or FicheiroFalso(), user or CONSULTOR
        )
        await self.tarefa_background
        return resposta

    async def atividades(self):
        return await self.db.activities.find({}, {"_id": 0}).to_list(100)

    async def tarefas(self):
        return await self.db.tasks.find({}, {"_id": 0}).to_list(100)

    async def nota(self, nota_id):
        return await self.db.voice_notes.find_one({"id": nota_id}, {"_id": 0})

    def eventos_de(self, tipo):
        return [e for e in self.eventos if e["tipo"] == tipo]


# ====================================================================
# 1. CAMINHO FELIZ
# ====================================================================


class TestCaminhoFeliz:
    @pytest.mark.asyncio
    async def test_o_audio_chega_ao_motor_de_transcricao(self):
        async with Arnes() as arnes:
            await arnes.gravar_nota()

        assert arnes.asr.chamadas == [
            {"bytes": len(AUDIO), "filename": "nota.webm", "mime_type": "audio/webm"}
        ]

    @pytest.mark.asyncio
    async def test_a_transcricao_chega_ao_llm_com_contexto_do_processo(self):
        async with Arnes() as arnes:
            await arnes.gravar_nota()

        assert len(arnes.llm.chamadas) == 1
        chamada = arnes.llm.chamadas[0]
        assert chamada["transcricao"] == TRANSCRICAO
        # Sem o nome do cliente e a data de hoje, o modelo não resolve
        # "sexta-feira" nem trata a cliente pelo nome.
        assert chamada["contexto"]["client_name"] == "Ana Martins"
        assert chamada["contexto"]["process_ref"] == "PROC-012"
        assert chamada["contexto"]["hoje"]

    @pytest.mark.asyncio
    async def test_o_resumo_entra_na_timeline_do_processo(self):
        async with Arnes() as arnes:
            await arnes.gravar_nota()

            atividades = await arnes.atividades()

        assert len(atividades) == 1
        atividade = atividades[0]
        assert atividade["comment"] == EXTRACCAO["resumo_timeline"]
        assert atividade["process_id"] == PROCESS_ID
        # O autor é quem falou, não "Sistema".
        assert atividade["user_id"] == CONSULTOR["id"]
        assert atividade["user_name"] == CONSULTOR["name"]
        # A proveniência permite à timeline distinguir nota ditada de nota
        # escrita — e permite desfazer em bloco o que a IA criou.
        assert atividade["origin"] == "voice_note"

    @pytest.mark.asyncio
    async def test_as_tarefas_extraidas_sao_criadas_e_atribuidas_a_quem_gravou(self):
        async with Arnes() as arnes:
            await arnes.gravar_nota()

            tarefas = await arnes.tarefas()

        assert len(tarefas) == 2
        for tarefa in tarefas:
            assert tarefa["assigned_to"] == [CONSULTOR["id"]]
            assert tarefa["process_id"] == PROCESS_ID

    @pytest.mark.asyncio
    async def test_as_tarefas_nascem_pelo_caminho_canonico(self):
        # A prova de que passaram por `run_create_task` e não por um
        # `insert_one` paralelo: só esse caminho prefixa a referência do
        # processo no título.
        async with Arnes() as arnes:
            await arnes.gravar_nota()

            titulos = [t["title"] for t in await arnes.tarefas()]

        # `run_create_task` prefixa a referência do processo E o nome do
        # cliente — é essa dupla marca que distingue o caminho canónico de
        # um `insert_one` paralelo.
        assert all("[PROC-012]" in titulo for titulo in titulos), titulos
        assert all("[Ana Martins]" in titulo for titulo in titulos), titulos

    @pytest.mark.asyncio
    async def test_prazos_e_prioridades_chegam_intactos(self):
        async with Arnes() as arnes:
            await arnes.gravar_nota()

            tarefas = {t["title"]: t for t in await arnes.tarefas()}

        avaliacao = next(t for k, t in tarefas.items() if "avaliação" in k)
        assert avaliacao["due_date"] == "2026-09-23T09:00:00+00:00"
        assert avaliacao["priority"] == "Alta"

    @pytest.mark.asyncio
    async def test_a_tarefa_ditada_deixa_rasto_da_origem(self):
        async with Arnes() as arnes:
            resposta = await arnes.gravar_nota()

            tarefas = await arnes.tarefas()

        assert all(
            resposta["voice_note_id"] in (t.get("description") or "") for t in tarefas
        )

    @pytest.mark.asyncio
    async def test_o_audio_e_arquivado_no_s3_do_processo(self):
        async with Arnes() as arnes:
            await arnes.gravar_nota()

        assert arnes.s3.uploads == [{"category": "Notas de Voz", "filename": "nota.webm"}]

    @pytest.mark.asyncio
    async def test_a_nota_fica_registada_como_concluida(self):
        async with Arnes() as arnes:
            resposta = await arnes.gravar_nota()

            nota = await arnes.nota(resposta["voice_note_id"])

        assert nota["status"] == "completed"
        assert nota["transcription"] == TRANSCRICAO
        assert len(nota["task_ids"]) == 2

    @pytest.mark.asyncio
    async def test_o_endpoint_responde_antes_de_o_trabalho_estar_feito(self):
        # O contrato do Eixo 3: o consultor não espera pela IA. A resposta
        # traz o `task_id` com que o frontend segue o progresso.
        async with Arnes() as arnes:
            resposta = await voice_note_api.run_create_voice_note(
                PROCESS_ID, FicheiroFalso(), CONSULTOR
            )

            assert resposta["status"] == "processing"
            assert resposta["task_id"]
            # Nesta altura o pipeline ainda não correu.
            assert await arnes.atividades() == []

            await arnes.tarefa_background


# ====================================================================
# 2. TEMPO REAL
# ====================================================================


class TestTempoReal:
    @pytest.mark.asyncio
    async def test_a_nota_gera_eventos_do_arranque_ao_fim(self):
        async with Arnes() as arnes:
            await arnes.gravar_nota()

        assert arnes.eventos_de("task_started"), "sem evento de arranque"
        assert arnes.eventos_de("task_progress"), "sem eventos de progresso"
        assert len(arnes.eventos_de("task_completed")) == 1

    @pytest.mark.asyncio
    async def test_os_eventos_vao_so_para_quem_gravou(self):
        # Tenant-safety: o envelope é por destinatário. Um evento sem dono
        # certo apareceria no ecrã de outro consultor.
        async with Arnes() as arnes:
            await arnes.gravar_nota()

        destinatarios = {e["user_id"] for e in arnes.eventos}
        assert destinatarios == {CONSULTOR["id"]}
        assert OUTRO_UTILIZADOR["id"] not in destinatarios

    @pytest.mark.asyncio
    async def test_o_evento_terminal_traz_o_que_o_frontend_precisa(self):
        async with Arnes() as arnes:
            resposta = await arnes.gravar_nota()

        terminal = arnes.eventos_de("task_completed")[0]["payload"]
        assert terminal["process_id"] == PROCESS_ID
        resultado = terminal["result"]
        # Sem estes campos o cliente não sabe o que invalidar e volta a
        # depender de um refresh — que é exactamente o que o épico remove.
        assert resultado["voice_note_id"] == resposta["voice_note_id"]
        assert resultado["activity_id"]
        assert len(resultado["task_ids"]) == 2

    @pytest.mark.asyncio
    async def test_o_progresso_avanca_de_forma_monotona(self):
        async with Arnes() as arnes:
            await arnes.gravar_nota()

        valores = [
            e["payload"]["progress"]
            for e in arnes.eventos
            if "progress" in e["payload"]
        ]
        assert valores == sorted(valores), valores
        assert valores[-1] == 100


# ====================================================================
# 3. FALHAS
# ====================================================================


class TestTranscricaoEmBaixo:
    @pytest.mark.asyncio
    async def test_a_tarefa_falha_com_motivo_legivel(self):
        asr = FakeASRService(erro=ErroDeTranscricao("serviço indisponível"))

        async with Arnes(asr=asr) as arnes:
            await arnes.gravar_nota()

        falhas = arnes.eventos_de("task_failed")
        assert len(falhas) == 1
        assert "serviço indisponível" in falhas[0]["payload"]["error"]

    @pytest.mark.asyncio
    async def test_nada_fica_escrito_a_meio(self):
        asr = FakeASRService(erro=ErroDeTranscricao("serviço indisponível"))

        async with Arnes(asr=asr) as arnes:
            resposta = await arnes.gravar_nota()

            assert await arnes.atividades() == []
            assert await arnes.tarefas() == []
            assert (await arnes.nota(resposta["voice_note_id"]))["status"] == "failed"

    @pytest.mark.asyncio
    async def test_o_llm_nao_chega_a_ser_chamado(self):
        asr = FakeASRService(erro=ErroDeTranscricao("x"))

        async with Arnes(asr=asr) as arnes:
            await arnes.gravar_nota()

        assert arnes.llm.chamadas == []

    @pytest.mark.asyncio
    async def test_uma_excepcao_inesperada_tambem_e_contida(self):
        # Um provider pode levantar o que quiser (timeout, erro de rede).
        asr = FakeASRService(erro=RuntimeError("boom"))

        async with Arnes(asr=asr) as arnes:
            await arnes.gravar_nota()

        assert arnes.eventos_de("task_failed")


class TestLLMEmBaixo:
    @pytest.mark.asyncio
    async def test_a_transcricao_nao_se_perde(self):
        # Degradação graciosa: o consultor falou, o texto existe — não pode
        # desaparecer por o extractor estar em baixo.
        llm = FakeLLMService(erro=ErroDeExtraccao("modelo indisponível"))

        async with Arnes(llm=llm) as arnes:
            await arnes.gravar_nota()

            atividades = await arnes.atividades()

        assert len(atividades) == 1
        assert atividades[0]["comment"] == TRANSCRICAO

    @pytest.mark.asyncio
    async def test_nao_se_inventam_tarefas(self):
        llm = FakeLLMService(erro=ErroDeExtraccao("modelo indisponível"))

        async with Arnes(llm=llm) as arnes:
            await arnes.gravar_nota()

            assert await arnes.tarefas() == []

    @pytest.mark.asyncio
    async def test_a_tarefa_conclui_com_aviso_em_vez_de_falhar(self):
        llm = FakeLLMService(erro=ErroDeExtraccao("modelo indisponível"))

        async with Arnes(llm=llm) as arnes:
            resposta = await arnes.gravar_nota()

            nota = await arnes.nota(resposta["voice_note_id"])

        assert nota["status"] == "partial"
        assert nota["warning"]
        terminal = arnes.eventos_de("task_completed")[0]["payload"]
        assert terminal["result"]["aviso"]

    @pytest.mark.asyncio
    async def test_resposta_vazia_do_llm_cai_na_transcricao(self):
        # O modelo respondeu, mas sem resumo: não se grava uma nota em branco.
        llm = FakeLLMService(resultado={"resumo_timeline": "   ", "tarefas_extraidas": []})

        async with Arnes(llm=llm) as arnes:
            await arnes.gravar_nota()

            atividades = await arnes.atividades()

        assert atividades[0]["comment"] == TRANSCRICAO


class TestS3EmBaixo:
    @pytest.mark.asyncio
    async def test_a_nota_processa_na_mesma(self):
        # O arquivo do áudio é acessório: serve para reouvir, não é uma
        # dependência do processamento.
        async with Arnes(s3=FakeS3(explode=True)) as arnes:
            resposta = await arnes.gravar_nota()

            assert resposta["s3_path"] is None
            assert len(await arnes.atividades()) == 1
            assert len(await arnes.tarefas()) == 2

    @pytest.mark.asyncio
    async def test_s3_nao_configurado_nao_e_erro(self):
        async with Arnes(s3=FakeS3(configurado=False)) as arnes:
            resposta = await arnes.gravar_nota()

            assert resposta["s3_path"] is None
            assert len(await arnes.atividades()) == 1


# ====================================================================
# 4. GUARDAS DO ENDPOINT
# ====================================================================


class TestGuardasDoEndpoint:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("papel", ["cliente", "parceiro"])
    async def test_papeis_sem_acesso_sao_recusados(self, papel):
        async with Arnes():
            with pytest.raises(HTTPException) as erro:
                await voice_note_api.run_create_voice_note(
                    PROCESS_ID, FicheiroFalso(), {**CONSULTOR, "role": papel}
                )

        assert erro.value.status_code == 403

    @pytest.mark.asyncio
    async def test_processo_inexistente_da_404(self):
        async with Arnes():
            with pytest.raises(HTTPException) as erro:
                await voice_note_api.run_create_voice_note(
                    "proc-que-nao-existe", FicheiroFalso(), CONSULTOR
                )

        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_formato_nao_suportado_e_recusado_antes_de_ler_o_ficheiro(self):
        async with Arnes() as arnes:
            with pytest.raises(HTTPException) as erro:
                await voice_note_api.run_create_voice_note(
                    PROCESS_ID,
                    FicheiroFalso(content_type="application/pdf", filename="x.pdf"),
                    CONSULTOR,
                )

        assert erro.value.status_code == 400
        # Nem sequer se contactou o motor de transcrição.
        assert arnes.asr.chamadas == []

    @pytest.mark.asyncio
    async def test_ficheiro_vazio_e_recusado(self):
        async with Arnes():
            with pytest.raises(HTTPException) as erro:
                await voice_note_api.run_create_voice_note(
                    PROCESS_ID, FicheiroFalso(conteudo=b""), CONSULTOR
                )

        assert erro.value.status_code == 400

    @pytest.mark.asyncio
    async def test_gravacao_demasiado_grande_e_recusada(self):
        # Sem limite, um upload grande basta para esgotar a memória do worker.
        grande = FicheiroFalso(conteudo=b"x" * (2 * 1024 * 1024))

        async with Arnes():
            with patch.dict("os.environ", {"VOICE_NOTE_MAX_MB": "1"}):
                with pytest.raises(HTTPException) as erro:
                    await voice_note_api.run_create_voice_note(
                        PROCESS_ID, grande, CONSULTOR
                    )

        assert erro.value.status_code == 413

    @pytest.mark.asyncio
    async def test_codecs_do_mediarecorder_sao_aceites(self):
        # O browser envia "audio/webm;codecs=opus"; recusá-lo tornaria a
        # gravação no browser inutilizável.
        async with Arnes() as arnes:
            await arnes.gravar_nota(
                FicheiroFalso(content_type="audio/webm;codecs=opus")
            )

        assert len(arnes.asr.chamadas) == 1
