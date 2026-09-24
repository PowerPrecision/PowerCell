"""
Reatribuição de tarefas (Lote 5, Secção B, ponto 10).

O QUE JÁ EXISTIA
  `run_update_task` já aceitava `assigned_to` e notificava os NOVOS
  responsáveis. O que faltava: a UI (o diálogo da tarefa mostra
  "Atribuído a" como TEXTO), e três coisas no backend.

1. A BOMBA DO LOTE 4 ESTAVA POR DESARMAR NESTE CAMINHO
     new_assignees = set(task_data.assigned_to) - set(task.get("assigned_to", []))
   `set("u1")` em Python é `{'u', '1'}` — itera os CARACTERES. O ponto 12
   do Lote 4 documentou que o `workflow_engine` gravava escalares e
   acrescentou `normalizar_assigned_to` à LEITURA; este caminho ficou de
   fora. Uma tarefa de automação reatribuída notificava letras em vez de
   pessoas, e a escrita repunha o escalar que a normalização veio tirar.

2. QUEM SAI NÃO ERA AVISADO
   O novo responsável recebe notificação; o anterior fica com a tarefa
   na lista até ao próximo refresh e sem saber que deixou de ser dele.
   Numa equipa isso é trabalho a cair no chão.

3. A REATRIBUIÇÃO NÃO DEIXAVA RASTO
   `log_history` registava "Atualizou tarefa" com o TÍTULO em old/new —
   mudar o responsável e mudar o título eram indistinguíveis no
   histórico. Quem quer saber por que é que a tarefa mudou de mãos não
   tinha onde ver.

   O rasto respeita a regra de ouro do perfil Indexação: quem regista é
   `log_history`, que já passa por `_is_stealth_user`.
"""
import pytest


class TestDiffDeResponsaveis:
    def test_um_escalar_nao_e_iterado_letra_a_letra(self):
        """`set("u1")` é `{'u','1'}` — a bomba do Lote 4, ponto 12."""
        from services.task_assignment_hygiene import diff_de_responsaveis

        diff = diff_de_responsaveis(antes="u1", depois=["u1", "u2"])
        assert diff.entraram == ["u2"]
        assert diff.sairam == []

    def test_quem_sai_e_identificado(self):
        from services.task_assignment_hygiene import diff_de_responsaveis

        diff = diff_de_responsaveis(antes=["u1", "u2"], depois=["u2"])
        assert diff.sairam == ["u1"]
        assert diff.entraram == []

    def test_uma_troca_completa_da_os_dois_lados(self):
        from services.task_assignment_hygiene import diff_de_responsaveis

        diff = diff_de_responsaveis(antes=["u1"], depois=["u2"])
        assert diff.sairam == ["u1"]
        assert diff.entraram == ["u2"]

    def test_sem_mudanca_nao_ha_diff(self):
        """Contraprova: um diff que nunca esteja vazio faria notificar
        toda a gente em cada gravação da tarefa."""
        from services.task_assignment_hygiene import diff_de_responsaveis

        diff = diff_de_responsaveis(antes=["u1", "u2"], depois=["u2", "u1"])
        assert diff.entraram == []
        assert diff.sairam == []
        assert diff.mudou is False

    def test_tirar_toda_a_gente_e_uma_mudanca(self):
        from services.task_assignment_hygiene import diff_de_responsaveis

        diff = diff_de_responsaveis(antes=["u1"], depois=[])
        assert diff.sairam == ["u1"]
        assert diff.mudou is True

    def test_none_dos_dois_lados_nao_rebenta(self):
        from services.task_assignment_hygiene import diff_de_responsaveis

        diff = diff_de_responsaveis(antes=None, depois=None)
        assert diff.entraram == [] and diff.sairam == [] and diff.mudou is False


class TestOCaminhoDeEscritaNormaliza:
    def test_a_actualizacao_grava_lista(self):
        """O Lote 4 normalizou a LEITURA e pôs o motor de automação a
        gravar lista. Este caminho gravava o que lhe dessem."""
        from pathlib import Path
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(
            Path(__file__).resolve().parents[2]
            .joinpath("services", "task_api_crud.py").read_text()
        )
        assert 'update_data[assigned_to] = task_data.assigned_to' not in fonte.replace(
            "'", ""
        ).replace('"', "")
        assert "normalizar_assigned_to" in fonte

    def test_deixou_de_fazer_diff_com_set_cru(self):
        from pathlib import Path
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(
            Path(__file__).resolve().parents[2]
            .joinpath("services", "task_api_crud.py").read_text()
        )
        assert "set(task_data.assigned_to)" not in fonte
        assert "diff_de_responsaveis" in fonte

    def test_contraprova_a_funcao_do_diff_faz_alguma_coisa(self):
        """Sem isto, apagar o corpo satisfazia as duas guardas acima."""
        from services.task_assignment_hygiene import diff_de_responsaveis

        assert diff_de_responsaveis(antes=["a"], depois=["b"]).entraram == ["b"]


class TestNotificacaoDeQuemSai:
    @pytest.mark.asyncio
    async def test_avisa_o_responsavel_anterior(self, fake_async_db, monkeypatch):
        from services import task_api_crud as mod
        from models.task import TaskUpdate

        await fake_async_db.tasks.insert_one(_tarefa(assigned_to=["u1"]))
        avisados = []

        async def notificar(**kwargs):
            avisados.append((kwargs.get("user_id"), kwargs.get("notification_type")))

        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(mod, "send_realtime_notification", notificar)
        monkeypatch.setattr(mod, "enrich_task", lambda t: _devolver(t))

        await mod.run_update_task(
            "t1", TaskUpdate(assigned_to=["u2"]), {"id": "admin", "name": "Ana"},
        )

        assert ("u2", "task_assigned") in avisados
        tipos_de_u1 = [t for (u, t) in avisados if u == "u1"]
        assert tipos_de_u1, "quem sai da tarefa não foi avisado"

    @pytest.mark.asyncio
    async def test_nao_avisa_quem_se_atribui_a_si_proprio(self, fake_async_db, monkeypatch):
        """Contraprova do desenho existente: notificar-se a si mesmo é
        ruído, e era assim antes."""
        from services import task_api_crud as mod
        from models.task import TaskUpdate

        await fake_async_db.tasks.insert_one(_tarefa(assigned_to=[]))
        avisados = []

        async def notificar(**kwargs):
            avisados.append(kwargs.get("user_id"))

        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(mod, "send_realtime_notification", notificar)
        monkeypatch.setattr(mod, "enrich_task", lambda t: _devolver(t))

        await mod.run_update_task(
            "t1", TaskUpdate(assigned_to=["eu"]), {"id": "eu", "name": "Ana"},
        )
        assert avisados == []

    @pytest.mark.asyncio
    async def test_grava_a_lista_normalizada(self, fake_async_db, monkeypatch):
        from services import task_api_crud as mod
        from models.task import TaskUpdate

        # `assigned_to` ESCALAR: é o que o motor de automação gravava
        # antes do Lote 4 e o que faz `set(...)` iterar caracteres.
        await fake_async_db.tasks.insert_one(_tarefa(assigned_to="u1"))
        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(mod, "send_realtime_notification", _nada)
        monkeypatch.setattr(mod, "enrich_task", lambda t: _devolver(t))

        await mod.run_update_task(
            "t1", TaskUpdate(assigned_to=["u1", "u1", "", "u2"]), {"id": "a", "name": "A"},
        )
        guardada = await fake_async_db.tasks.find_one({"id": "t1"})
        assert guardada["assigned_to"] == ["u1", "u2"]


def _tarefa(**extra):
    """Documento de tarefa com os campos que o `TaskResponse` exige."""
    base = {
        "id": "t1",
        "title": "Pedir IRS",
        "assigned_to": [],
        "process_id": None,
        "created_by": "admin",
        "created_at": "2026-09-01T10:00:00+00:00",
    }
    base.update(extra)
    return base


async def _nada(**_kwargs):
    return None


async def _devolver(t):
    return {**t, "assigned_to_names": []}


class TestRastoDaReatribuicao:
    """O ramo do histórico só corre com `process_id`.

    Os testes acima usavam todos `process_id: None` e por isso nunca o
    exercitavam — a bateria ficou verde sobre código que rebentava em
    produção (`get_user_names` não estava importado). Foi o flake8 que o
    denunciou, não os testes. Uma tarefa de processo é o caso NORMAL:
    tem de estar coberto.
    """

    @pytest.mark.asyncio
    async def test_a_mudanca_de_maos_fica_registada(self, fake_async_db, monkeypatch):
        from services import task_api_crud as mod
        from models.task import TaskUpdate

        await fake_async_db.tasks.insert_one(
            _tarefa(assigned_to=["u1"], process_id="p1")
        )
        registos = []

        async def registar(process_id, user, accao, campo, antes, depois):
            registos.append((accao, campo, antes, depois))

        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(mod, "send_realtime_notification", _nada)
        monkeypatch.setattr(mod, "enrich_task", lambda t: _devolver(t))
        monkeypatch.setattr(mod, "log_history", registar)
        monkeypatch.setattr(
            mod, "get_user_names", _nomes({"u1": "Ana", "u2": "Bruno"})
        )

        await mod.run_update_task(
            "t1", TaskUpdate(assigned_to=["u2"]), {"id": "admin", "name": "Chefe"},
        )

        assert registos, "a reatribuição não deixou rasto"
        accao, _campo, antes, depois = registos[0]
        assert accao == "Reatribuiu tarefa"
        assert antes == "Ana" and depois == "Bruno"

    @pytest.mark.asyncio
    async def test_mudar_so_o_titulo_continua_a_registar_uma_edicao(
        self, fake_async_db, monkeypatch
    ):
        """Contraprova: se TUDO passasse a ser "Reatribuiu tarefa", o
        histórico ficava tão pouco informativo como antes."""
        from services import task_api_crud as mod
        from models.task import TaskUpdate

        await fake_async_db.tasks.insert_one(
            _tarefa(assigned_to=["u1"], process_id="p1")
        )
        registos = []

        async def registar(process_id, user, accao, campo, antes, depois):
            registos.append(accao)

        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(mod, "send_realtime_notification", _nada)
        monkeypatch.setattr(mod, "enrich_task", lambda t: _devolver(t))
        monkeypatch.setattr(mod, "log_history", registar)

        await mod.run_update_task(
            "t1", TaskUpdate(title="Outro título"), {"id": "admin", "name": "Chefe"},
        )
        assert registos == ["Atualizou tarefa"]

    @pytest.mark.asyncio
    async def test_gravar_sem_mexer_nos_responsaveis_nao_e_reatribuicao(
        self, fake_async_db, monkeypatch
    ):
        from services import task_api_crud as mod
        from models.task import TaskUpdate

        await fake_async_db.tasks.insert_one(
            _tarefa(assigned_to=["u1"], process_id="p1")
        )
        registos = []

        async def registar(process_id, user, accao, campo, antes, depois):
            registos.append(accao)

        monkeypatch.setattr(mod, "db", fake_async_db)
        monkeypatch.setattr(mod, "send_realtime_notification", _nada)
        monkeypatch.setattr(mod, "enrich_task", lambda t: _devolver(t))
        monkeypatch.setattr(mod, "log_history", registar)
        monkeypatch.setattr(mod, "get_user_names", _nomes({"u1": "Ana"}))

        await mod.run_update_task(
            "t1", TaskUpdate(assigned_to=["u1"]), {"id": "admin", "name": "Chefe"},
        )
        assert registos == ["Atualizou tarefa"]


def _nomes(mapa):
    async def _get(ids):
        return {i: mapa.get(i, i) for i in ids}

    return _get
