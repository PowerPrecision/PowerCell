"""D-31 (fecho) — `/task-logs/{id}`, `/documents/client/{client_id}/*` e `/portal/{client_id}/verify`.

O QUE ESTAVA ABERTO
===================
`get_current_user` autoriza o VERBO, não o OBJECTO. A D-31 fechou clientes,
tarefas, restauro e rascunhos e deixou escritas, por nome, as três superfícies
que este ficheiro cobre:

* `/task-logs/{id}` — o registo de uma tarefa assíncrona leva o `process_name`
  (o nome do cliente). A excepção era `role in [master, admin, ceo]`: o cargo da
  conta, sem pergunta de rede. Admin e CEO são LOCAIS desde a adenda de RBAC, e
  o CEO da Domus lia, cancelava e apagava os registos da Power. E o 403 para
  quem não é dono confirmava o id;
* `/documents/client/{client_id}/*` — o id é «flexível» (processo, cliente ou
  `client_id` de um processo). Havia guarda de VISIBILIDADE nuns handlers
  (D-26, com 403) e **nenhuma** noutros: o `init-folders` nem recebia o
  utilizador;
* `/portal/{client_id}/verify` — pública: não há utilizador nem rede em
  contexto, a guarda é a credencial. O que se afirma aqui é que não há ORÁCULO.

COMO SE TESTA
=============
Os routers REAIS, pedidos por HTTP, com os `run_*` substituídos por sentinelas:
o ataque exige que o handler NUNCA seja chamado (um 404 que viesse do handler
provava o contrário). Onde o serviço é o objecto (task-logs), chama-se o
serviço e afirma-se o efeito na base de dados.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (fixtures)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    db_tenant,
    rede_de_omissao_incumbente,
    tenant_db,
)

# ── Pessoas ──────────────────────────────────────────────────────────────
ANA = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "diretor"}
PEDRO = {"id": "u-pedro", "name": "Pedro", "email": "pedro@precision.pt", "role": "consultor"}
BRUNO = {"id": "u-bruno", "name": "Bruno", "email": "bruno@domus.pt", "role": "diretor"}
NUNO = {"id": "u-nuno", "name": "Nuno", "email": "nuno@domus.pt", "role": "consultor"}
ADMIN_POWER = {"id": "u-adm-power", "name": "Admin Power", "email": "a@power.pt", "role": "admin"}
CEO_DOMUS = {"id": "u-ceo-domus", "name": "CEO Domus", "email": "ceo@domus.pt", "role": "ceo"}
MASTER = {"id": "u-master", "name": "Master", "email": "m@sistema.pt", "role": "master"}

EMPRESA_DE = {
    "u-ana": "Power Real Estate", "u-pedro": "Precision Crédito",
    "u-bruno": "Domus", "u-nuno": "Domus",
    "u-adm-power": "Power Real Estate", "u-ceo-domus": "Domus",
}
UCR_DE = {
    "u-pedro": ("cmp-precision", "Precision Crédito"),
    "u-nuno": ("cmp-domus", "Domus"),
    "u-adm-power": ("cmp-power", "Power Real Estate"),
    "u-ceo-domus": ("cmp-domus", "Domus"),
}


def _sessao(pessoa: dict) -> dict:
    """O utilizador como o `get_current_user` o entrega."""
    return {**pessoa, "effective_role": pessoa["role"], "is_active": True}


def _semear_pessoas(fake_db) -> None:
    for pessoa in (ANA, PEDRO, BRUNO, NUNO, ADMIN_POWER, CEO_DOMUS, MASTER):
        fake_db.users.docs.append({
            **pessoa, "is_active": True,
            **({"company": EMPRESA_DE[pessoa["id"]]} if pessoa["id"] in EMPRESA_DE else {}),
        })
    for uid, (cid, nome) in UCR_DE.items():
        fake_db.user_company_roles.docs.append({
            "user_id": uid, "company_id": cid, "company_name": nome,
            "role": next(p["role"] for p in (PEDRO, NUNO, ADMIN_POWER, CEO_DOMUS) if p["id"] == uid),
            "is_default": True,
        })


# ════════════════════════════════════════════════════════════════════
#  1 · /task-logs/{id}
# ════════════════════════════════════════════════════════════════════
def _registo(task_id: str, dono: str, *, estado: str = "completed") -> dict:
    return {
        "id": task_id, "task_id": task_id, "user_id": dono,
        "task_type": "PDF_GEN", "status": estado, "title": f"Trabalho {task_id}",
        "process_name": f"Cliente de {dono}",
        "created_at": "2026-10-11T10:00:00+00:00", "progress": 100,
    }


@pytest.fixture
def logs(db_tenant, rede_de_omissao_incumbente):  # noqa: F811
    _semear_pessoas(db_tenant)
    db_tenant.task_logs.docs.extend([
        _registo("tl-pedro", "u-pedro"),
        _registo("tl-nuno", "u-nuno"),
        _registo("tl-pedro-pendente", "u-pedro", estado="pending"),
        _registo("tl-nuno-pendente", "u-nuno", estado="pending"),
        _registo("tl-orfao", "u-que-ja-nao-existe"),
    ])
    return db_tenant


def _ctx_logs(fake_db):
    from services import (
        admin_users_scope,
        task_log_service,
        task_logs_api_actions,
        user_management_scope,
    )

    return tenant_db(
        fake_db, admin_users_scope, user_management_scope,
        task_logs_api_actions, task_log_service,
    )


async def _chamar(logs, nome: str, tarefa: str, pessoa: dict):
    from services import task_logs_api_actions as acoes

    with _ctx_logs(logs):
        return await getattr(acoes, nome)(tarefa, _sessao(pessoa))


ACCOES = ["run_get_task_details", "run_acknowledge_task", "run_cancel_task", "run_delete_task"]


class TestOsRegistosDeTarefasAtravessavamRedes:
    """`TestAExploracao` deste ficheiro: o CEO da Domus contra a Power."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("accao", ACCOES)
    async def test_o_CEO_da_Domus_nao_toca_num_registo_da_Power(self, logs, accao):
        with pytest.raises(HTTPException) as erro:
            await _chamar(logs, accao, "tl-pedro", CEO_DOMUS)
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize("accao", ACCOES)
    async def test_o_admin_da_Power_nao_toca_num_registo_da_Domus(self, logs, accao):
        with pytest.raises(HTTPException) as erro:
            await _chamar(logs, accao, "tl-nuno", ADMIN_POWER)
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_o_ataque_nao_deixa_efeito_na_base_de_dados(self, logs):
        """Apagar e cancelar de fora da rede não mexe em nada."""
        with pytest.raises(HTTPException):
            await _chamar(logs, "run_delete_task", "tl-pedro", CEO_DOMUS)
        with pytest.raises(HTTPException):
            await _chamar(logs, "run_cancel_task", "tl-pedro-pendente", CEO_DOMUS)

        por_id = {d["id"]: d for d in logs.task_logs.docs}
        assert "tl-pedro" in por_id
        assert por_id["tl-pedro-pendente"]["status"] == "pending"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("accao", ACCOES)
    async def test_um_colega_que_nao_e_dono_nem_gestor_recebe_404_e_nao_403(self, logs, accao):
        """O 403 antigo confirmava que o id existe."""
        with pytest.raises(HTTPException) as erro:
            await _chamar(logs, accao, "tl-pedro", ANA)
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_alheio_e_inexistente_respondem_o_mesmo(self, logs):
        with pytest.raises(HTTPException) as alheio:
            await _chamar(logs, "run_get_task_details", "tl-pedro", CEO_DOMUS)
        with pytest.raises(HTTPException) as inexistente:
            await _chamar(logs, "run_get_task_details", "tl-nunca-existiu", CEO_DOMUS)
        assert (alheio.value.status_code, alheio.value.detail) == (
            inexistente.value.status_code, inexistente.value.detail,
        )

    @pytest.mark.asyncio
    async def test_um_registo_de_dono_que_ja_nao_existe_so_o_master_ve(self, logs):
        with pytest.raises(HTTPException) as erro:
            await _chamar(logs, "run_get_task_details", "tl-orfao", ADMIN_POWER)
        assert erro.value.status_code == 404
        assert (await _chamar(logs, "run_get_task_details", "tl-orfao", MASTER)).id == "tl-orfao"


class TestOQueContinuaPermitidoNosRegistos:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("accao", ["run_get_task_details"])
    async def test_o_dono_ve_o_seu(self, logs, accao):
        assert (await _chamar(logs, accao, "tl-pedro", PEDRO)).user_id == "u-pedro"

    @pytest.mark.asyncio
    async def test_o_admin_da_Power_ve_o_do_Pedro_da_Precision_mesma_rede(self, logs):
        assert (await _chamar(logs, "run_get_task_details", "tl-pedro", ADMIN_POWER)).id == "tl-pedro"

    @pytest.mark.asyncio
    async def test_o_CEO_da_Domus_ve_os_da_sua_rede(self, logs):
        assert (await _chamar(logs, "run_get_task_details", "tl-nuno", CEO_DOMUS)).id == "tl-nuno"

    @pytest.mark.asyncio
    async def test_o_Master_ve_qualquer_um(self, logs):
        for tarefa in ("tl-pedro", "tl-nuno"):
            assert (await _chamar(logs, "run_get_task_details", tarefa, MASTER)).id == tarefa

    @pytest.mark.asyncio
    async def test_o_gestor_do_ambito_elimina_e_o_efeito_e_real(self, logs):
        resposta = await _chamar(logs, "run_delete_task", "tl-pedro", ADMIN_POWER)
        assert resposta["success"] is True
        assert "tl-pedro" not in {d["id"] for d in logs.task_logs.docs}

    @pytest.mark.asyncio
    async def test_o_dono_confirma_o_seu(self, logs):
        resposta = await _chamar(logs, "run_acknowledge_task", "tl-pedro", PEDRO)
        assert resposta["success"] is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("quem", [ADMIN_POWER, MASTER])
    async def test_confirmar_e_so_do_dono_nem_o_gestor_nem_o_Master(self, logs, quem):
        with pytest.raises(HTTPException) as erro:
            await _chamar(logs, "run_acknowledge_task", "tl-pedro", quem)
        assert erro.value.status_code == 404


class TestOsRegistosDeTarefasEstaoLigados:
    @pytest.mark.asyncio
    async def test_todos_os_handlers_passam_pela_mesma_guarda(self):
        """Guarda de fonte COM contraprova: nenhum `run_*` volta a ter a
        excepção por cargo escrita à mão."""
        from services import task_logs_api_actions as acoes
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        for nome in ACCOES:
            fonte = codigo_da_funcao_sem_comentarios(getattr(acoes, nome))
            assert "_carregar_acessivel" in fonte, nome
            assert '"admin", "ceo"' not in fonte, nome
            assert "403" not in fonte, nome

        # Contraprova: o leitor lê mesmo, e a guarda é a que decide o âmbito.
        guarda = codigo_da_funcao_sem_comentarios(acoes._carregar_acessivel)
        assert "carregar_utilizador_gerivel" in guarda
        assert "utilizador_e_global" in guarda

    @pytest.mark.asyncio
    async def test_a_rota_entrega_o_utilizador_ao_servico(self, logs):
        from routes import task_logs as rotas

        with _ctx_logs(logs):
            with pytest.raises(HTTPException) as erro:
                await rotas.get_task_details("tl-pedro", user=_sessao(CEO_DOMUS))
            assert erro.value.status_code == 404
            assert (await rotas.get_task_details("tl-nuno", user=_sessao(CEO_DOMUS))).id == "tl-nuno"


# ════════════════════════════════════════════════════════════════════
#  2 · /documents/client/{client_id}/*  (o id é «flexível»)
# ════════════════════════════════════════════════════════════════════
import contextlib  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PASTA_PW = "Documentação Clientes/c-pw/processos/p-pw"
PASTA_DM = "Documentação Clientes/c-dm/processos/p-dm"

DETALHE = {"sentinela": "handler chamado"}

#: Quem entra no ataque. Todos com sessão (o `get_current_user` é substituído).
SESSOES = {
    "ana": _sessao({"id": "u-ana", "name": "Ana", "role": "diretor"}),             # Power
    "bruno": _sessao({"id": "u-bruno", "name": "Bruno", "role": "diretor"}),       # Domus
    "carla": _sessao({"id": "u-carla", "name": "Carla", "role": "consultor"}),     # Precision + Domus
    "master": _sessao(MASTER),
    "ceo_domus": _sessao(CEO_DOMUS),
}

#: Os ids com que se chega à MESMA pasta de documentos da Power.
IDS_DA_POWER = [
    pytest.param("p-pw", id="processo"),
    pytest.param("c-pw", id="cliente"),
    pytest.param("cli-sem-ficha", id="client_id-so-no-processo"),
]


def _cenario_docs(fake_db) -> None:
    from tests.unit.helpers_tenant import semear

    semear(fake_db)
    _semear_pessoas(fake_db)
    fake_db.user_company_roles.docs.extend([
        {"user_id": "u-bruno", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "diretor", "is_default": True},
    ])
    fake_db.clients.docs.extend([
        {"id": "c-pw", "nome": "Cliente da Power", "network_id": REDE_INCUMBENTE,
         "company_id": "cmp-power", "process_ids": ["p-pw"], "s3_folder": "Documentação Clientes/c-pw"},
        {"id": "c-dm", "nome": "Cliente da Domus", "network_id": REDE_DOMUS,
         "company_id": "cmp-domus", "process_ids": ["p-dm"], "s3_folder": "Documentação Clientes/c-dm"},
        {"id": "c-pool", "nome": "Registo Público", "lead_status": "new"},
        # Carimbado Domus, mas o vínculo aponta para um processo da POWER
        # (homónimo / vínculo antigo): o handler abriria a pasta da Power.
        {"id": "c-cruzado", "nome": "Vínculo Cruzado", "network_id": REDE_DOMUS,
         "company_id": "cmp-domus", "process_ids": ["p-pw"]},
        {"id": "c-part", "nome": "Do Processo Partilhado", "network_id": REDE_INCUMBENTE,
         "company_id": "cmp-power", "process_ids": ["p-part"]},
    ])
    fake_db.processes.docs.extend([
        {"id": "p-pw", "is_indexed": True, "client_id": "c-pw", "status": "novo", "network_id": REDE_INCUMBENTE,
         "company_id": "cmp-power", "s3_folder": PASTA_PW},
        {"id": "p-dm", "is_indexed": True, "client_id": "c-dm", "status": "novo", "network_id": REDE_DOMUS,
         "company_id": "cmp-domus", "s3_folder": PASTA_DM},
        # Partilhado pela Power com a Domus (D-25): a Domus vê.
        {"id": "p-part", "is_indexed": True, "client_id": "c-part", "status": "novo", "network_id": REDE_INCUMBENTE,
         "company_id": "cmp-power", "partner_network_ids": [REDE_DOMUS],
         "s3_folder": "Documentação Clientes/c-part/processos/p-part"},
        # Partilhado e SEM ficha de cliente: só o ramo do PROCESSO o pode abrir
        # (com a ficha, o ramo do cliente abria-o e escondia o defeito).
        {"id": "p-part-so", "is_indexed": True, "client_id": "cli-part-so", "status": "novo",
         "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
         "partner_network_ids": [REDE_DOMUS],
         "s3_folder": "Documentação Clientes/Pasta_Partilhada"},
        # O cliente só existe como `client_id` do processo — sem ficha.
        {"id": "p-sf", "is_indexed": True, "client_id": "cli-sem-ficha", "status": "novo", "network_id": REDE_INCUMBENTE,
         "company_id": "cmp-power"},
    ])


HANDLERS_DE_DOCUMENTOS = [
    "run_upload_file_s3", "run_initialize_folders", "run_get_download_url",
    "run_delete_file_s3", "run_bulk_delete_files",
]


@pytest.fixture
def docs(fake_async_db, rede_de_omissao_incumbente):
    import routes.documents as rd
    import services.auth as auth_mod
    import services.by_id_scope as guard
    import services.document_process_resolve as dpr
    import services.document_visibility as dv
    import services.process_closed_guard as pcg
    import services.process_scope_guard as psg
    from services.auth import get_current_user

    _cenario_docs(fake_async_db)
    atual = {"user": SESSOES["ana"]}
    chamadas: dict[str, AsyncMock] = {}

    app = FastAPI()
    app.include_router(rd.router)
    app.dependency_overrides[get_current_user] = lambda: atual["user"]

    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(fake_async_db, guard, auth_mod, psg, pcg, rd, dpr, dv))
        for nome in HANDLERS_DE_DOCUMENTOS:
            chamadas[nome] = AsyncMock(return_value=DETALHE)
            pilha.enter_context(patch.object(rd, nome, chamadas[nome]))
        # O resolvedor e a guarda de visibilidade são os REAIS; só o S3 é falso.
        s3 = MagicMock()
        s3.list_files.return_value = {}
        pilha.enter_context(patch.object(rd, "s3_service", s3))
        cliente = TestClient(app)

        def como(quem: str):
            atual["user"] = SESSOES[quem]
            return cliente

        yield como, chamadas, fake_async_db


def _pedir(cliente, rota: str, cid: str):
    """As seis rotas de `/documents/client/{client_id}/…`."""
    base = f"/documents/client/{cid}"
    if rota == "files":
        return cliente.get(f"{base}/files")
    if rota == "upload":
        return cliente.post(
            f"{base}/upload", data={"category": "Financeiros"},
            files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
        )
    if rota == "init-folders":
        return cliente.post(f"{base}/init-folders")
    if rota == "download":
        return cliente.get(f"{base}/download", params={"file_path": f"{PASTA_PW}/x.pdf"})
    if rota == "delete":
        return cliente.delete(f"{base}/file", params={"file_path": f"{PASTA_PW}/x.pdf"})
    if rota == "bulk-delete":
        return cliente.post(f"{base}/bulk-delete", json={"file_paths": [f"{PASTA_PW}/x.pdf"]})
    raise AssertionError(rota)


ROTAS_DE_CLIENTE = ["files", "upload", "init-folders", "download", "delete", "bulk-delete"]


class TestOAtaqueAosDocumentosDoCliente:
    """`TestAExploracao`: a Domus contra a pasta de documentos da Power."""

    @pytest.mark.parametrize("rota", ROTAS_DE_CLIENTE)
    @pytest.mark.parametrize("cid", IDS_DA_POWER)
    def test_o_Bruno_da_Domus_nao_alcanca_a_pasta_da_Power(self, docs, rota, cid):
        como, chamadas, _ = docs
        resposta = _pedir(como("bruno"), rota, cid)

        assert resposta.status_code == 404, (rota, cid, resposta.text)
        # Nenhum handler correu: um 404 do handler provava o contrário.
        assert all(m.await_count == 0 for m in chamadas.values()), {
            n: m.await_count for n, m in chamadas.items() if m.await_count
        }

    @pytest.mark.parametrize("rota", ROTAS_DE_CLIENTE)
    def test_um_admin_da_Domus_e_local_e_tambem_nao(self, docs, rota):
        como, chamadas, _ = docs
        assert _pedir(como("ceo_domus"), rota, "c-pw").status_code == 404
        assert all(m.await_count == 0 for m in chamadas.values())

    @pytest.mark.parametrize("rota", ROTAS_DE_CLIENTE)
    def test_a_Power_nao_alcanca_a_pasta_da_Domus(self, docs, rota):
        como, chamadas, _ = docs
        assert _pedir(como("ana"), rota, "c-dm").status_code == 404
        assert _pedir(como("ana"), rota, "p-dm").status_code == 404
        assert all(m.await_count == 0 for m in chamadas.values())

    def test_o_alheio_responde_404_e_nunca_o_403_que_confirmava_o_id(self, docs):
        """A guarda de visibilidade (D-26) respondia 403 a um processo de outra
        rede: confirmava que o id existe. Agora a fronteira vem primeiro."""
        como, _, _ = docs
        for cid in ("c-pw", "p-pw", "cli-sem-ficha"):
            resposta = _pedir(como("bruno"), "files", cid)
            assert resposta.status_code == 404, cid
            assert resposta.json()["detail"] == "Cliente não encontrado"

    def test_o_init_folders_ja_nao_corre_para_quem_nao_pode(self, docs):
        """O `init-folders` nem recebia o utilizador: era escrever `s3_folder`
        no processo de outra rede sabendo só o id."""
        como, chamadas, _ = docs
        assert _pedir(como("bruno"), "init-folders", "p-pw").status_code == 404
        assert chamadas["run_initialize_folders"].await_count == 0


class TestOsFluxosLegitimosDosDocumentos:
    @pytest.mark.parametrize("rota", ROTAS_DE_CLIENTE)
    @pytest.mark.parametrize("cid", IDS_DA_POWER)
    def test_a_Power_abre_os_seus_por_qualquer_dos_tres_ids(self, docs, rota, cid):
        como, _, _ = docs
        assert _pedir(como("ana"), rota, cid).status_code == 200, (rota, cid)

    @pytest.mark.parametrize("rota", ROTAS_DE_CLIENTE)
    def test_a_Domus_abre_os_seus(self, docs, rota):
        como, _, _ = docs
        assert _pedir(como("bruno"), rota, "c-dm").status_code == 200
        assert _pedir(como("bruno"), rota, "p-dm").status_code == 200

    @pytest.mark.parametrize("rota", ROTAS_DE_CLIENTE)
    def test_quem_trabalha_nas_duas_redes_abre_ambas(self, docs, rota):
        como, _, _ = docs
        assert _pedir(como("carla"), rota, "c-pw").status_code == 200
        assert _pedir(como("carla"), rota, "c-dm").status_code == 200

    @pytest.mark.parametrize("rota", ROTAS_DE_CLIENTE)
    def test_o_Master_abre_qualquer_uma(self, docs, rota):
        como, _, _ = docs
        for cid in ("c-pw", "c-dm", "p-pw"):
            assert _pedir(como("master"), rota, cid).status_code == 200

    @pytest.mark.parametrize("rota", ["files", "download"])
    def test_o_processo_partilhado_abre_ao_convidado(self, docs, rota):
        """D-25/D-26: a rede convidada vê os documentos do processo partilhado."""
        como, _, _ = docs
        assert _pedir(como("bruno"), rota, "p-part").status_code == 200
        assert _pedir(como("bruno"), rota, "c-part").status_code == 200

    def test_a_Pool_e_aberta_a_qualquer_rede(self, docs):
        """Registo público sem processo: a reivindicação é de qualquer rede."""
        como, _, _ = docs
        assert _pedir(como("bruno"), "files", "c-pool").status_code == 200
        assert _pedir(como("ana"), "files", "c-pool").status_code == 200

    @pytest.mark.parametrize("rota", ROTAS_DE_CLIENTE)
    def test_um_cliente_meu_cujo_processo_e_de_outra_rede_tambem_fecha(self, docs, rota):
        como, chamadas, _ = docs
        assert _pedir(como("bruno"), rota, "c-cruzado").status_code == 404
        assert all(m.await_count == 0 for m in chamadas.values())

    def test_um_id_que_nao_existe_passa_e_o_handler_responde(self, docs):
        como, chamadas, _ = docs
        assert _pedir(como("bruno"), "init-folders", "c-nunca-existiu").status_code == 200
        assert chamadas["run_initialize_folders"].await_count == 1

    def test_as_rotas_sem_id_de_cliente_nao_sao_afectadas(self, docs):
        como, _, _ = docs
        assert como("bruno").get("/documents/types").status_code == 200


class TestAGuardaDosDocumentosEstaLigada:
    def test_o_router_leva_as_tres_dependencias_pela_ordem_certa(self):
        """A fronteira de rede vem ANTES da guarda de processo fechado: esta
        nunca pode ser um oráculo sobre outra rede."""
        import routes.documents as rd
        from services.by_id_scope import exigir_alvo_do_documento_no_ambito
        from services.process_closed_guard import exigir_processo_editavel
        from services.process_scope_guard import exigir_processo_no_ambito

        chamaveis = [d.dependency for d in rd.router.dependencies]
        assert chamaveis == [
            exigir_processo_no_ambito,
            exigir_alvo_do_documento_no_ambito,
            exigir_processo_editavel,
        ]

    def test_toda_a_rota_com_id_no_caminho_esta_sob_o_router_guardado(self):
        """Inventário por AST de `routes/documents.py`: nenhuma rota com
        `{client_id}`, `{process_id}` ou `{doc_id}` vive fora do router.
        Com contraprova: o inventário encontra mesmo as rotas conhecidas."""
        import ast
        import inspect

        import routes.documents as rd

        arvore = ast.parse(inspect.getsource(rd))
        decoradores = []
        for no in ast.walk(arvore):
            if isinstance(no, (ast.AsyncFunctionDef, ast.FunctionDef)):
                for d in no.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) \
                            and d.func.attr in {"get", "post", "put", "patch", "delete"} \
                            and isinstance(d.func.value, ast.Name):
                        decoradores.append((d.func.value.id, d.args[0].value if d.args and
                                            isinstance(d.args[0], ast.Constant) else ""))
        com_id = [c for c in decoradores if any(
            k in c[1] for k in ("{client_id}", "{process_id}", "{doc_id}"))]
        assert len(com_id) >= 25, "o inventário leu pouco"          # contraprova
        assert {"/client/{client_id}/files", "/client/{client_id}/init-folders"} <= {c[1] for c in com_id}
        assert {c[0] for c in decoradores} == {"router"}
        assert inspect.getsource(rd).count("APIRouter(") == 1

    def test_o_nome_do_parametro_no_caminho_e_o_que_a_guarda_le(self):
        """A dependência lê `client_id`/`doc_id`: renomear o parâmetro de uma
        rota desligava a guarda sem dar erro."""
        import routes.documents as rd

        for rota in rd.router.routes:
            caminho = getattr(rota, "path", "")
            for nome in ("cliente_id", "clientId", "documento_id", "docId"):
                assert "{" + nome + "}" not in caminho, caminho


# ════════════════════════════════════════════════════════════════════
#  2b · As rotas que chegam ao mesmo ficheiro por OUTRO caminho
# ════════════════════════════════════════════════════════════════════
FICHEIRO_PW = f"{PASTA_PW}/cc.pdf"
FICHEIRO_DM = f"{PASTA_DM}/cc.pdf"
FICHEIRO_PARTILHADO = "Documentação Clientes/c-part/processos/p-part/cc.pdf"


def _ctx_ficheiros(fake_db):
    import services.by_id_scope as guard
    import services.document_bulk_download as dbd
    import services.document_misc as dm
    import services.document_path_scope as dps

    # Só os módulos que têm o seu próprio `db` (o proxy não lê a base de dados).
    return tenant_db(fake_db, guard, dps, dbd, dm)


@pytest.fixture
def pastas(fake_async_db, rede_de_omissao_incumbente):
    _cenario_docs(fake_async_db)
    return fake_async_db


def _sob(pastas, quem: str):
    return _ctx_ficheiros(pastas), SESSOES[quem]


class TestAPosseDeUmaChaveS3:
    """A raiz (`assert_path_within_document_root`) impede o `backups/*.zip`; não
    impedia o ficheiro do cliente do vizinho."""

    @pytest.mark.asyncio
    async def test_a_Domus_nao_ve_um_ficheiro_da_Power(self, pastas):
        from services.document_path_scope import ficheiro_no_ambito

        ctx, bruno = _sob(pastas, "bruno")
        with ctx:
            assert await ficheiro_no_ambito(FICHEIRO_PW, bruno) is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("quem,ficheiro,esperado", [
        ("ana", FICHEIRO_PW, True),
        ("ana", FICHEIRO_DM, False),
        ("bruno", FICHEIRO_DM, True),
        ("carla", FICHEIRO_PW, True),
        ("carla", FICHEIRO_DM, True),
        ("master", FICHEIRO_PW, True),
        ("master", FICHEIRO_DM, True),
        # Processo PARTILHADO: a rede convidada (Domus) vê (D-25/D-26).
        ("bruno", FICHEIRO_PARTILHADO, True),
        ("bruno", "Documentação Clientes/Pasta_Partilhada/cc.pdf", True),
        ("ana", "Documentação Clientes/Pasta_Partilhada/cc.pdf", True),
        ("carla", "Documentação Clientes/Pasta_Partilhada/cc.pdf", True),
    ])
    async def test_quem_vê_o_quê(self, pastas, quem, ficheiro, esperado):
        from services.document_path_scope import ficheiro_no_ambito

        ctx, sessao = _sob(pastas, quem)
        with ctx:
            assert await ficheiro_no_ambito(ficheiro, sessao) is esperado

    @pytest.mark.asyncio
    async def test_a_pasta_do_cliente_sem_processo_segue_o_cliente(self, pastas):
        """Onboarding do Portal: o ficheiro vive na pasta do CLIENTE (Pool)."""
        from services.document_path_scope import ficheiro_no_ambito

        pastas.clients.docs.append({"id": "c-pool2", "nome": "Pool", "lead_status": "new"})
        ctx, bruno = _sob(pastas, "bruno")
        with ctx:
            assert await ficheiro_no_ambito("Documentação Clientes/c-pool2/cc.pdf", bruno) is True

    @pytest.mark.asyncio
    async def test_sem_dono_so_o_Master(self, pastas):
        """A órfã: ninguém a reclama, logo não tem rede."""
        from services.document_path_scope import ficheiro_no_ambito

        orfao = "Documentação Clientes/ninguem/cc.pdf"
        for quem, esperado in (("ana", False), ("bruno", False), ("master", True)):
            ctx, sessao = _sob(pastas, quem)
            with ctx:
                assert await ficheiro_no_ambito(orfao, sessao) is esperado, quem

    @pytest.mark.asyncio
    async def test_pasta_reclamada_por_duas_redes_nao_e_de_nenhuma(self, pastas):
        """A ambígua (homónimos): escolher à sorte qual das redes vê os
        ficheiros da outra é a fuga."""
        from services.document_path_scope import ficheiro_no_ambito

        pasta = "Documentação Clientes/Joao_Silva"
        pastas.processes.docs.extend([
            {"id": "p-js-pw", "s3_folder": pasta, "network_id": REDE_INCUMBENTE},
            {"id": "p-js-dm", "s3_folder": pasta, "network_id": REDE_DOMUS},
        ])
        for quem, esperado in (("ana", False), ("bruno", False), ("master", True)):
            ctx, sessao = _sob(pastas, quem)
            with ctx:
                assert await ficheiro_no_ambito(f"{pasta}/cc.pdf", sessao) is esperado, quem

    @pytest.mark.asyncio
    async def test_a_variacao_underscore_espaco_nao_foge_a_guarda(self, pastas):
        from services.document_path_scope import ficheiro_no_ambito

        pasta = "Documentação Clientes/Maria_Costa"
        pastas.processes.docs.append({"id": "p-mc", "s3_folder": pasta, "network_id": REDE_INCUMBENTE})
        ctx, bruno = _sob(pastas, "bruno")
        with ctx:
            assert await ficheiro_no_ambito("Documentação Clientes/Maria Costa/cc.pdf", bruno) is False
            assert await ficheiro_no_ambito(f"{pasta}/cc.pdf", bruno) is False
        ctx, ana = _sob(pastas, "ana")
        with ctx:
            assert await ficheiro_no_ambito("Documentação Clientes/Maria Costa/cc.pdf", ana) is True

    @pytest.mark.asyncio
    async def test_fora_da_raiz_nunca_e_de_ninguem_excepto_o_Master(self, pastas):
        from services.document_path_scope import ficheiro_no_ambito

        ctx, ana = _sob(pastas, "ana")
        with ctx:
            assert await ficheiro_no_ambito("backups/dump.zip", ana) is False

    def test_os_prefixos_incluem_todos_os_niveis_e_os_ids(self):
        """Contraprova do leitor: lê mesmo a chave."""
        from services.document_path_scope import prefixos_e_segmentos

        prefixos, segmentos = prefixos_e_segmentos(FICHEIRO_PW)
        assert "Documentação Clientes/c-pw" in prefixos
        assert PASTA_PW in prefixos
        assert {"c-pw", "processos", "p-pw"} <= set(segmentos)
        assert "cc.pdf" not in segmentos


class TestOsCaminhosPorChave:
    @pytest.mark.asyncio
    async def test_o_proxy_recusa_antes_de_tocar_no_S3(self, pastas):
        import services.document_proxy as dpx

        ctx, bruno = _sob(pastas, "bruno")
        with ctx, patch.object(dpx, "_get_s3_object") as s3:
            with pytest.raises(HTTPException) as erro:
                await dpx.run_proxy_s3_file(FICHEIRO_PW, user=bruno)
        assert erro.value.status_code == 404
        s3.assert_not_called()

    @pytest.mark.asyncio
    async def test_o_proxy_serve_o_que_e_da_rede(self, pastas):
        import services.document_proxy as dpx

        corpo = MagicMock()
        corpo.read.side_effect = [b"%PDF", b""]
        ctx, ana = _sob(pastas, "ana")
        with ctx, patch.object(dpx.s3_service, "is_configured", return_value=True), \
                patch.object(dpx, "_get_s3_object", return_value={
                    "Body": corpo, "ContentType": "application/pdf", "ContentLength": 4}) as s3:
            resposta = await dpx.run_proxy_s3_file(FICHEIRO_PW, user=ana)
        s3.assert_called_once()
        assert resposta.media_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_o_url_pre_assinado_nao_e_gerado_nem_o_bucket_consultado(self, pastas):
        """Sem oráculo: nem sequer se pergunta ao S3 se a chave existe."""
        import services.document_misc as dm

        ctx, bruno = _sob(pastas, "bruno")
        with ctx, patch.object(dm.s3_service, "file_exists") as existe, \
                patch.object(dm.s3_service, "get_presigned_url") as assinar:
            with pytest.raises(HTTPException) as erro:
                await dm.run_get_download_url_by_path(FICHEIRO_PW, user=bruno)
        assert erro.value.status_code == 404
        existe.assert_not_called()
        assinar.assert_not_called()

    @pytest.mark.asyncio
    async def test_o_url_pre_assinado_sai_para_a_propria_rede(self, pastas):
        import services.document_misc as dm

        ctx, ana = _sob(pastas, "ana")
        with ctx, patch.object(dm.s3_service, "file_exists", return_value=True), \
                patch.object(dm.s3_service, "get_presigned_url", return_value="https://s3/assinado"):
            resposta = await dm.run_get_download_url_by_path(FICHEIRO_PW, user=ana)
        assert resposta["url"] == "https://s3/assinado"

    @pytest.mark.asyncio
    async def test_o_download_em_massa_ignora_o_que_nao_e_da_rede(self, pastas):
        import services.document_bulk_download as dbd

        lidos = []

        def ler(chave):
            lidos.append(chave)
            return b"conteudo", "application/pdf"

        ctx, ana = _sob(pastas, "ana")
        with ctx, patch.object(dbd.s3_service, "is_configured", return_value=True), \
                patch.object(dbd, "_get_s3_file_content", side_effect=ler):
            resposta = await dbd.run_bulk_download_documents(
                {"document_ids": [FICHEIRO_PW, FICHEIRO_DM]}, user=ana,
            )
        assert resposta.media_type == "application/zip"
        # A Power só leu o que é da Power.
        assert lidos and all(k.startswith("Documentação Clientes/c-pw") for k in lidos)
        assert not any("c-dm" in k for k in lidos)

    @pytest.mark.asyncio
    async def test_o_download_em_massa_de_fora_nao_le_nada_e_nao_confirma(self, pastas):
        import services.document_bulk_download as dbd

        ctx, bruno = _sob(pastas, "bruno")
        with ctx, patch.object(dbd.s3_service, "is_configured", return_value=True), \
                patch.object(dbd, "_get_s3_file_content") as ler:
            with pytest.raises(HTTPException) as erro:
                await dbd.run_bulk_download_documents({"document_ids": [FICHEIRO_PW]}, user=bruno)
        ler.assert_not_called()
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_o_process_id_do_corpo_e_um_alvo(self, pastas):
        """Antes, o histórico de OUTRO processo ganhava a linha «Download em
        massa» só por se nomear o id no corpo."""
        import services.document_bulk_download as dbd

        ctx, bruno = _sob(pastas, "bruno")
        with ctx, patch.object(dbd.s3_service, "is_configured", return_value=True), \
                patch.object(dbd, "_get_s3_file_content") as ler, \
                patch.object(dbd, "log_history", new=AsyncMock()) as historia:
            with pytest.raises(HTTPException) as erro:
                await dbd.run_bulk_download_documents(
                    {"document_ids": [FICHEIRO_DM], "process_id": "p-pw"}, user=bruno,
                )
        assert erro.value.status_code == 404
        ler.assert_not_called()
        historia.assert_not_awaited()

    def test_as_rotas_entregam_o_utilizador_e_os_servicos_exigem_no_(self):
        """O parâmetro é obrigatório (kw-only, sem omissão): um `user=None` por
        omissão era o placebo do `build_company_scope_condition`."""
        import inspect

        import services.document_misc as dm
        import services.document_proxy as dpx
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
        import routes.documents as rd

        for funcao in (dm.run_get_download_url_by_path, dpx.run_proxy_s3_file):
            parametro = inspect.signature(funcao).parameters["user"]
            assert parametro.kind is inspect.Parameter.KEYWORD_ONLY
            assert parametro.default is inspect.Parameter.empty
            assert "exigir_ficheiro_no_ambito" in codigo_da_funcao_sem_comentarios(funcao)
        assert "user=user" in codigo_da_funcao_sem_comentarios(rd.get_download_url_by_path)
        assert "user=user" in codigo_da_funcao_sem_comentarios(rd.proxy_s3_file)


# ════════════════════════════════════════════════════════════════════
#  2c · `{process_id}` e `{doc_id}`: 404 ANTES do 403 da guarda de visibilidade
# ════════════════════════════════════════════════════════════════════
class TestOsOutrosIdsDoRouter:
    def test_os_metadados_de_um_processo_de_outra_rede_dao_404_e_nao_403(self, docs):
        """A guarda de visibilidade (D-26) respondia 403: confirmava o id."""
        como, _, _ = docs
        import routes.documents as rd

        with patch.object(rd, "run_get_document_metadata", new=AsyncMock(return_value=DETALHE)) as h:
            resposta = como("bruno").get("/documents/metadata/p-pw")
            assert resposta.status_code == 404
            h.assert_not_awaited()
            assert como("ana").get("/documents/metadata/p-pw").status_code == 200

    def test_a_revisao_de_um_documento_de_outra_rede_nem_corre(self, docs):
        como, _, db = docs
        db.document_metadata.docs.extend([
            {"id": "dm-pw", "process_id": "p-pw"},
            {"id": "dm-sem-dono"},
        ])
        analise = AsyncMock(return_value=DETALHE)
        with patch("services.document_review.run_analyze_document_for_review", analise):
            assert como("bruno").post("/documents/dm-pw/ai-analyze-review").status_code == 404
            analise.assert_not_awaited()
            # Um registo sem dono não se prova meu: só o Master.
            assert como("ana").post("/documents/dm-sem-dono/ai-analyze-review").status_code == 404
            assert como("master").post("/documents/dm-sem-dono/ai-analyze-review").status_code == 200
            assert como("ana").post("/documents/dm-pw/ai-analyze-review").status_code == 200

    @pytest.mark.asyncio
    async def test_a_regra_de_validade_segue_o_processo_ou_o_cliente(self, pastas):
        import services.by_id_scope as guard

        pastas.document_expiries.docs.extend([
            {"id": "ex-pw", "process_id": "p-pw"},
            {"id": "ex-cliente-dm", "client_id": "c-dm"},
        ])
        with tenant_db(pastas, guard):
            assert await guard.documento_no_ambito_por_id("ex-pw", SESSOES["bruno"]) is False
            assert await guard.documento_no_ambito_por_id("ex-pw", SESSOES["ana"]) is True
            assert await guard.documento_no_ambito_por_id("ex-cliente-dm", SESSOES["ana"]) is False
            assert await guard.documento_no_ambito_por_id("ex-cliente-dm", SESSOES["bruno"]) is True
            assert await guard.documento_no_ambito_por_id("nao-existe", SESSOES["bruno"]) is None


# ════════════════════════════════════════════════════════════════════
#  3 · /portal/{client_id}/verify  (pública: a guarda é a credencial)
# ════════════════════════════════════════════════════════════════════
class TestOVerifyDoPortalNaoTemOraculo:
    """Não há utilizador nem rede em contexto numa porta pública, logo não há
    «404 se for de outra rede» a aplicar: a parede é a credencial (NIF + nº do
    processo) e o travão de tentativas. O que um teste pode afirmar — e o que
    protege as outras redes — é que a resposta NÃO distingue «este cliente
    existe noutra rede» de «não existe» nem de «NIF errado»."""

    MENSAGEM = "Credenciais inválidas. Verifique o seu NIF e Número de Processo."

    @pytest.fixture
    def portal(self, fake_async_db):
        import services.portal_auth as pa
        import services.portal_security as ps

        fake_async_db.clients.docs.extend([
            {"id": "c-pw", "nome": "Cliente da Power", "network_id": REDE_INCUMBENTE,
             "dados_pessoais": {"nif": "123456789"}},
            {"id": "c-dm", "nome": "Cliente da Domus", "network_id": REDE_DOMUS,
             "dados_pessoais": {"nif": "987654321"}},
        ])
        fake_async_db.processes.docs.extend([
            {"id": "p-pw", "process_number": 7, "client_id": "c-pw", "status": "novo",
             "network_id": REDE_INCUMBENTE},
            {"id": "p-dm", "process_number": 9, "client_id": "c-dm", "status": "novo",
             "network_id": REDE_DOMUS},
        ])
        with patch.object(ps, "db", fake_async_db), patch.object(pa, "db", fake_async_db):
            yield fake_async_db, pa

    async def _tentar(self, pa, client_id, nif, numero):
        try:
            await pa.run_verify_portal_login(client_id, {"nif": nif, "process_number": numero})
        except HTTPException as erro:
            return erro.status_code, erro.detail
        raise AssertionError("a verificação devia ter falhado")

    @pytest.mark.asyncio
    async def test_inexistente_nif_errado_e_processo_alheio_respondem_o_mesmo(self, portal):
        _, pa = portal
        respostas = {
            "cliente que nao existe": await self._tentar(pa, "c-nunca", "123456789", 7),
            "nif errado": await self._tentar(pa, "c-pw", "111111111", 7),
            "processo que nao e dele": await self._tentar(pa, "c-pw", "123456789", 999),
            # O NIF e o nº são REAIS, mas de um cliente de OUTRA rede.
            "processo de outra rede": await self._tentar(pa, "c-pw", "123456789", 9),
            "cliente de outra rede com nif errado": await self._tentar(pa, "c-dm", "123456789", 9),
        }
        assert set(respostas.values()) == {(401, self.MENSAGEM)}, respostas

    @pytest.mark.asyncio
    async def test_o_travao_tambem_nao_distingue_o_que_existe(self, portal):
        """Cinco falhas bloqueiam um id inexistente tal como um real."""
        _, pa = portal
        for alvo in ("c-pw", "c-nunca"):
            for _ in range(5):
                await self._tentar(pa, alvo, "000000000", 1)
            estado, _detalhe = await self._tentar(pa, alvo, "000000000", 1)
            assert estado == 429, alvo

    @pytest.mark.asyncio
    async def test_as_credenciais_certas_abrem_o_proprio_cliente(self, portal):
        """Contraprova: o teste de cima não prova nada se nunca ninguém entrar."""
        import services.portal_security as ps

        with patch.object(ps, "db", portal[0]):
            resultado = await ps.verify_client_credentials("c-pw", "123456789", 7)
        assert resultado["process_id"] == "p-pw"

    @pytest.mark.asyncio
    async def test_o_nif_de_um_nao_abre_o_cliente_do_outro(self, portal):
        import services.portal_security as ps

        with patch.object(ps, "db", portal[0]):
            with pytest.raises(HTTPException) as erro:
                await ps.verify_client_credentials("c-dm", "123456789", 9)
        assert erro.value.status_code == 401
