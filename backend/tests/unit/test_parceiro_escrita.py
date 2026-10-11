"""
PORTAL DO PARCEIRO — ESCRITA: leads e ficheiros (V1)

Um agente externo a ESCREVER na base de dados. O que se prova:

  LEAD
  1. os carimbos (rede, empresa, autor, estado, origem) vêm do SERVIDOR; o
     corpo é `extra="forbid"` e só pode escolher entre as redes do próprio
     parceiro;
  2. nunca se toca num cliente existente (nada de find-or-create) e a
     resposta é igual quer exista um igual ou não — sem oráculo;
  3. o duplo clique do próprio parceiro devolve a lead que já existe;
  4. há tecto diário, consentimento e PII cifrada.

  FICHEIROS
  5. a posse da chave corre ANTES de tocar no objecto e de gravar (P0);
  6. o desvio inteligente do Bloco 2: por indexar → `Index` + fila da IA;
     indexado/Via Verde → pasta pedida, sem IA; lead → `Index`, sem fila;
  7. a quarentena decide o tamanho/tipo REAIS, e reprovar não grava nada;
  8. a descarga resolve um `file_id` (nunca uma chave) e revalida a posse;
  9. o que o parceiro envia é «novo» para a equipa e aparece na aba
     Documentos do CRM.
"""
from __future__ import annotations

import contextlib
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_DOMUS,
    REDE_INCUMBENTE,
    casa,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)
from tests.unit.test_parceiro_leitura import FASES, PT1, PT2, PT3, _lead, _proc

CHAVE_BOA = "Documentação Clientes/cli-a-novo/Index/cc.pdf"


class _S3Falso:
    """Um S3 que SÓ regista o que lhe pedem (não reimplementa regras)."""

    def __init__(self):
        self.chamadas: list[tuple] = []
        self.existe = True

    def is_configured(self):
        return True

    def generate_upload_presigned_url(self, **kw):
        self.chamadas.append(("presign_put", kw))
        pasta = (kw.get("s3_folder") or f"Documentação Clientes/{kw['client_id']}").rstrip("/")
        return {
            "upload_url": "https://s3.exemplo/put",
            "file_key": f"{pasta}/{kw['category']}/{kw['filename']}",
            "expires_at": "2026-10-10T16:00:00+00:00",
            "expires_in_seconds": 300,
        }

    def ensure_client_folder_mapping(self, storage_id, *a, **kw):
        self.chamadas.append(("ensure_mapping", storage_id))
        return {"success": True, "created": True, "s3_folder": f"Documentação Clientes/{storage_id}"}

    def file_exists(self, key):
        self.chamadas.append(("exists", key))
        return self.existe

    def get_presigned_url(self, key, expiration=3600):
        self.chamadas.append(("presign_get", key, expiration))
        return "https://s3.exemplo/get"

    def get_file_content(self, key):
        self.chamadas.append(("get_content", key))
        return b"%PDF-1.4 conteudo"


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.workflow_statuses.docs.extend(dict(f) for f in FASES)
    fake_async_db.partners.docs.extend([copy.deepcopy(PT1), copy.deepcopy(PT2), copy.deepcopy(PT3)])
    return fake_async_db


@pytest.fixture
def tarefas():
    """Captura (e fecha) as tarefas de segundo plano."""
    registo: list[str] = []

    def falso(coro, *, name=None):
        registo.append(name or "")
        coro.close()
        return MagicMock()

    with patch("services.background_tasks.spawn_background_task", falso):
        yield registo


@pytest.fixture
def s3():
    return _S3Falso()


@pytest.fixture
def veredicto():
    """A quarentena como DUPLO ao nível da função: o que se afirma é QUANDO é
    chamada e COM QUE argumentos; o conteúdo dos bytes tem os seus testes em
    `test_s3_content_quarantine.py`."""
    return AsyncMock(return_value=SimpleNamespace(tamanho=2048, tipo_detectado="application/pdf"))


@pytest.fixture
def com_bd(mundo, s3, veredicto, tarefas):
    import services.document_intake as intake
    import services.document_portal_counts as counts
    import services.history as history
    import services.partner_drafts as drafts
    import services.partner_leads as leads
    import services.partner_portal_read as ppr
    import services.partner_upload_ops as ops
    import services.portal_upload_ops as portal_ops

    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(mundo, ppr, ops, leads, intake, counts, history, portal_ops, drafts))
        pilha.enter_context(patch.object(ops, "s3_service", s3))
        pilha.enter_context(patch.object(portal_ops, "s3_service", s3))
        pilha.enter_context(patch.object(ops, "exigir_conteudo_valido", veredicto))
        yield mundo


def _rascunho(m, client_id):
    """A lead RETIDA do lado do parceiro (colecção `partner_drafts`)."""
    return next(c for c in m.partner_drafts.docs if c["id"] == client_id)


def _mundo(m, *, indexado=False, skip_index=False):
    m.processes.docs.clear()
    m.clients.docs.clear()
    m.processes.docs.append(
        _proc("a-novo", "pt-1", is_indexed=indexado, **({"skip_index": True} if skip_index else {}))
    )
    m.clients.docs.append({"id": "cli-a-novo", "nome": "Cliente a-novo", "s3_folder": "Documentação Clientes/cli-a-novo"})
    m.clients.docs.append(_lead("lead-1", "pt-1"))
    m.processes.docs.append(_proc("x-outro", "pt-2"))


# ════════════════════════════════════════════════════════════════════
#  LEAD
# ════════════════════════════════════════════════════════════════════
def _corpo(**extra):
    return {"name": "Joana Cliente", "email": "joana@cliente.pt", "phone": "912345678",
            "consent_confirmed": True, **extra}


@pytest.mark.asyncio
class TestLeadCarimbosDoServidor:
    async def test_a_lead_nasce_com_os_carimbos_do_servidor(self, com_bd):
        import services.partner_leads as pl

        resposta = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo(nif="501964843", notes="Quer rever o spread")))
        lead = _rascunho(com_bd, resposta["id"])
        assert lead["submitted_by_partner_id"] == "pt-1" and lead["submitted_by_partner_name"] == "Rui"
        assert lead["network_id"] == REDE_INCUMBENTE and lead["company_id"] == "cmp-power"
        # RETIDA do lado do parceiro até haver comprovativo: a equipa não a vê.
        assert lead["partner_stage"] == "pendente" and lead["process_ids"] == []
        assert not [c for c in com_bd.clients.docs if c.get("id") == resposta["id"]]
        assert lead["fonte"] == "partner_portal" and lead["assigned_to"] is None
        assert lead["partner_consent"]["confirmed"] is True and lead["partner_consent"]["partner_id"] == "pt-1"
        assert lead["notas_do_parceiro"] == "Quer rever o spread"
        assert resposta["kind"] == "lead" and resposta["client_name"] == "Joana Cliente"

    async def test_a_pii_vai_cifrada_para_a_base_de_dados(self, com_bd):
        import services.partner_leads as pl

        resposta = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo(nif="501964843")))
        lead = _rascunho(com_bd, resposta["id"])
        assert lead["contacto"]["telefone"] != "912345678" and str(lead["contacto"]["telefone"]).startswith("ENC:")
        assert str(lead["dados_pessoais"]["nif"]).startswith("ENC:")
        assert "501964843" not in repr(lead) and "912345678" not in repr(lead)

    @pytest.mark.parametrize(
        "campo",
        ["lead_status", "assigned_to", "submitted_by_partner_id", "company_id", "company_name", "status",
         "fonte", "process_ids", "partner_consent", "id", "s3_folder", "is_deleted"],
    )
    async def test_o_corpo_nao_aceita_campos_que_o_servidor_decide(self, campo):
        import services.partner_leads as pl

        with pytest.raises(ValidationError):
            pl.PartnerLeadIn(**_corpo(**{campo: "x"}))

    async def test_uma_rede_pedida_que_nao_e_do_parceiro_e_404(self, com_bd):
        import services.partner_leads as pl

        with pytest.raises(HTTPException) as erro:
            await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo(network_id=REDE_DOMUS)))
        assert erro.value.status_code == 404
        assert not [c for c in (*com_bd.clients.docs, *com_bd.partner_drafts.docs) if c.get("fonte") == "partner_portal"]

    async def test_com_duas_redes_e_preciso_escolher_e_so_entre_as_suas(self, com_bd):
        import services.partner_leads as pl

        duas = {**PT1, "redes": [PT1["redes"][0], {"network_id": REDE_DOMUS, "company_id": "cmp-domus",
                                                    "company_name": "Domus", "status": "active"}]}
        with pytest.raises(HTTPException) as ambigua:
            await pl.run_submit_lead(duas, pl.PartnerLeadIn(**_corpo()))
        assert ambigua.value.status_code == 400
        r = await pl.run_submit_lead(duas, pl.PartnerLeadIn(**_corpo(network_id=REDE_DOMUS)))
        lead = _rascunho(com_bd, r["id"])
        assert lead["network_id"] == REDE_DOMUS and lead["company_id"] == "cmp-domus"

    async def test_uma_ligacao_suspensa_nao_recebe_leads(self, com_bd):
        import services.partner_leads as pl

        suspenso = {**PT1, "redes": [{**PT1["redes"][0], "status": "suspended"}]}
        with pytest.raises(HTTPException) as erro:
            await pl.run_submit_lead(suspenso, pl.PartnerLeadIn(**_corpo()))
        assert erro.value.status_code == 403

    async def test_a_lead_nao_aparece_a_outro_parceiro_nem_a_equipa_de_outra_rede(self, com_bd):
        import services.partner_leads as pl
        import services.partner_portal_read as ppr
        from services.tenant_network import TenantScope, documento_no_ambito

        r = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo()))
        assert {c["id"] for c in (await ppr.run_list_cases(PT1))["items"]} == {r["id"]}
        assert (await ppr.run_list_cases(PT2))["items"] == []
        assert (await ppr.run_list_cases(PT3))["items"] == []
        lead = _rascunho(com_bd, r["id"])
        assert documento_no_ambito(lead, TenantScope(network_ids=(REDE_INCUMBENTE,)))
        assert not documento_no_ambito(lead, TenantScope(network_ids=(REDE_DOMUS,)))


@pytest.mark.asyncio
class TestLeadValidacao:
    async def test_sem_consentimento_nao_ha_lead(self, com_bd):
        import services.partner_leads as pl

        with pytest.raises(HTTPException) as erro:
            await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo(consent_confirmed=False)))
        assert erro.value.status_code == 400
        assert not [c for c in (*com_bd.clients.docs, *com_bd.partner_drafts.docs) if c.get("fonte") == "partner_portal"]

    @pytest.mark.parametrize(
        "campo,valor",
        [("email", "isto-nao-e-email"), ("nif", "123"), ("nif", "123456789"), ("process_type", "nao_existe"),
         ("name", "<script>")],
    )
    async def test_dados_invalidos_sao_400_e_nao_gravam(self, com_bd, campo, valor):
        import services.partner_leads as pl

        with pytest.raises(HTTPException) as erro:
            await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo(**{campo: valor})))
        assert erro.value.status_code == 400
        assert not [c for c in (*com_bd.clients.docs, *com_bd.partner_drafts.docs) if c.get("fonte") == "partner_portal"]

    async def test_o_tecto_diario(self, com_bd, monkeypatch):
        import services.partner_leads as pl

        monkeypatch.setattr(pl, "LIMITE_DE_LEADS_POR_DIA", 2)
        for i in range(2):
            await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo(email=f"p{i}@c.pt", name=f"Pessoa {i}")))
        with pytest.raises(HTTPException) as erro:
            await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo(email="p9@c.pt", name="Pessoa Nove")))
        assert erro.value.status_code == 429
        # outro parceiro não é afectado pelo tecto do primeiro
        await pl.run_submit_lead(PT2, pl.PartnerLeadIn(**_corpo(email="q@c.pt", name="Pessoa Q")))


@pytest.mark.asyncio
class TestLeadSemOraculoNemEscritaAlheia:
    async def test_nunca_se_toca_num_cliente_existente(self, com_bd):
        import services.partner_leads as pl
        from services.encryption import generate_email_hash

        existente = {
            "id": "cli-ja-existe", "nome": "Joana Antiga", "network_id": REDE_INCUMBENTE,
            "contacto": {"email": "joana@cliente.pt", "email_hash": generate_email_hash("joana@cliente.pt")},
            "custom_fields": {"nota": "original"}, "titular2_data": {"nome": "Original"},
        }
        com_bd.clients.docs.append(copy.deepcopy(existente))
        r = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo()))
        assert r["id"] != "cli-ja-existe"
        assert next(c for c in com_bd.clients.docs if c["id"] == "cli-ja-existe") == existente

    async def test_a_resposta_e_igual_exista_ou_nao_um_cliente_igual(self, com_bd):
        import services.partner_leads as pl
        from services.encryption import generate_email_hash

        sem = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo(email="a@c.pt", name="Ana Um")))
        com_bd.clients.docs.append({
            "id": "cli-b", "nome": "Outro", "network_id": REDE_INCUMBENTE,
            "contacto": {"email": "b@c.pt", "email_hash": generate_email_hash("b@c.pt")},
        })
        com = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo(email="b@c.pt", name="Bia Dois")))
        assert set(sem) == set(com), "mesmo formato de resposta"
        assert com["repetida"] is False
        assert "duplicate" not in repr(com).lower()

    async def test_um_igual_na_mesma_rede_marca_a_lead_para_a_triagem_e_so_a_ela(self, com_bd):
        import services.partner_leads as pl
        from services.encryption import generate_email_hash

        h = generate_email_hash("joana@cliente.pt")
        com_bd.clients.docs.extend([
            {"id": "igual-mesma-rede", "network_id": REDE_INCUMBENTE, "contacto": {"email_hash": h}},
            {"id": "igual-outra-rede", "network_id": REDE_DOMUS, "contacto": {"email_hash": h}},
        ])
        r = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo()))
        lead = _rascunho(com_bd, r["id"])
        assert lead["possible_duplicate_of"] == ["igual-mesma-rede"], "nunca se cruza a fronteira da rede"

    async def test_o_duplo_clique_do_proprio_parceiro_devolve_a_mesma_lead(self, com_bd):
        import services.partner_leads as pl

        primeira = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo()))
        segunda = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo()))
        assert segunda["id"] == primeira["id"] and segunda["repetida"] is True
        assert len([c for c in com_bd.partner_drafts.docs if c.get("fonte") == "partner_portal"]) == 1

    async def test_o_mesmo_cliente_por_outro_parceiro_e_uma_lead_nova_e_nao_revela_a_primeira(self, com_bd):
        import services.partner_leads as pl

        a = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo()))
        b = await pl.run_submit_lead(PT2, pl.PartnerLeadIn(**_corpo()))
        assert b["id"] != a["id"] and b["repetida"] is False
        assert set(a) == set(b)


@pytest.mark.asyncio
class TestLeadEfeitosLaterais:
    async def test_agenda_a_checklist_mas_nao_avisa_a_gestao(self, com_bd, tarefas):
        """A lead está RETIDA: a equipa nem sabe que existe. O aviso sai na
        libertação (quando o comprovativo chega), nunca na submissão."""
        import services.partner_leads as pl

        r = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo()))
        assert f"partner-lead-checklist:{r['id']}" in tarefas
        assert f"partner-lead-alert:{r['id']}" not in tarefas

    async def test_a_checklist_liga_se_ao_cliente_sem_processo(self, com_bd):
        import services.partner_leads as pl

        cliente = {"id": "c-1", "company_id": "cmp-power"}
        with patch("services.portal_documents_notify.generate_mandatory_document_requests", new=AsyncMock()) as gerar:
            await pl.pedir_checklist(PT1, cliente)
        kw = gerar.await_args.kwargs
        assert kw["client_id"] == "c-1" and kw["process_id"] is None and kw["requested_by"] == "partner_portal"

    async def test_o_aviso_vai_para_a_gestao_da_rede_do_parceiro_e_diz_quem_trouxe(self, com_bd):
        import services.partner_leads as pl

        cliente = {"id": "c-1", "nome": "Joana", "contacto": {"email": "j@c.pt", "telefone": "9"},
                   "pending_process_type": "credito_habitacao", "has_property": True}
        with patch("services.alerts.notify_new_client_registration", new=AsyncMock()) as avisar:
            await pl.avisar_gestao_da_lead(PT1, cliente, PT1["redes"][0])
        enviado = avisar.await_args.args[0]
        assert enviado["network_id"] == REDE_INCUMBENTE, "o carimbo escolhe a gestão destinatária"
        assert avisar.await_args.kwargs["origem"] == "Parceiro Rui"
        assert avisar.await_args.kwargs["has_property"] is True

    async def test_uma_falha_nos_efeitos_nunca_faz_falhar_a_submissao(self, com_bd):
        import services.partner_leads as pl

        with patch("services.alerts.notify_new_client_registration", new=AsyncMock(side_effect=RuntimeError("smtp"))):
            await pl.avisar_gestao_da_lead(PT1, {"id": "c"}, PT1["redes"][0])  # não levanta


# ════════════════════════════════════════════════════════════════════
#  A HERANÇA DO PARCEIRO NO PROCESSO
# ════════════════════════════════════════════════════════════════════
class TestHerancaDoParceiro:
    def test_o_processo_herda_o_parceiro_que_trouxe_a_lead(self):
        from services.partner_attribution import aplicar_parceiro_do_cliente

        doc = {"id": "p"}
        assert aplicar_parceiro_do_cliente(doc, {"submitted_by_partner_id": "pt-1", "submitted_by_partner_name": " Rui "})
        assert doc == {"id": "p", "assigned_parceiro_id": "pt-1", "parceiro_name": "Rui"}

    def test_nunca_sobrescreve_um_parceiro_atribuido_pela_equipa(self):
        from services.partner_attribution import aplicar_parceiro_do_cliente

        doc = {"assigned_parceiro_id": "escolhido-pela-equipa"}
        assert not aplicar_parceiro_do_cliente(doc, {"submitted_by_partner_id": "pt-1"})
        assert doc["assigned_parceiro_id"] == "escolhido-pela-equipa"

    @pytest.mark.parametrize("cliente", [None, {}, {"submitted_by_partner_id": None}, {"submitted_by_partner_id": "  "}])
    def test_um_cliente_sem_parceiro_nao_muda_nada(self, cliente):
        from services.partner_attribution import aplicar_parceiro_do_cliente

        doc = {"id": "p"}
        assert not aplicar_parceiro_do_cliente(doc, cliente)
        assert doc == {"id": "p"}

    @pytest.mark.asyncio
    async def test_a_leitura_do_cliente_para_o_processo_leva_o_parceiro(self, fake_async_db):
        import services.process_create as pc

        fake_async_db.clients.docs.append({
            "id": "c-1", "nome": "Joana", "contacto": {"email": "j@c.pt"},
            "submitted_by_partner_id": "pt-1", "submitted_by_partner_name": "Rui",
        })
        with patch.object(pc, "db", fake_async_db):
            campos = await pc.load_existing_client_for_process("c-1")
        assert campos["submitted_by_partner_id"] == "pt-1" and campos["submitted_by_partner_name"] == "Rui"

    @pytest.mark.asyncio
    async def test_a_lead_passa_a_processo_no_ecra_do_parceiro_sem_desaparecer(self, com_bd):
        """O caso que a herança existe para evitar: a lead deixa de o ser no
        momento em que tem processo; se o processo não herdar, o caso some."""
        import services.partner_leads as pl
        import services.partner_portal_read as ppr
        from services.partner_attribution import aplicar_parceiro_do_cliente

        r = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(**_corpo()))
        assert [c["kind"] for c in (await ppr.run_list_cases(PT1))["items"]] == ["lead"]

        # Só depois do comprovativo a lead chega à equipa e pode ter processo.
        cliente = _rascunho(com_bd, r["id"])
        com_bd.partner_drafts.docs.remove(cliente)
        com_bd.clients.docs.append(cliente)
        processo = {"id": "p-novo", "client_id": cliente["id"], "client_name": "Joana", "status": "fase_documental",
                    "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"}
        aplicar_parceiro_do_cliente(processo, cliente)
        com_bd.processes.docs.append(processo)
        cliente["process_ids"] = ["p-novo"]

        itens = (await ppr.run_list_cases(PT1))["items"]
        assert [(c["kind"], c["id"]) for c in itens] == [("process", "p-novo")]


@pytest.mark.asyncio
class TestOsEscritoresReaisHerdamOParceiro:
    """O inventário por AST prova que a chamada existe; aqui corre-se o
    escritor REAL e vê-se o documento que ele grava. É o caminho que a lead
    percorre até ao processo."""

    @staticmethod
    def _lead_com_parceiro():
        return {
            "id": "c-1", "nome": "Joana", "contacto": {"email": "j@c.pt", "telefone": "9"}, "dados_pessoais": {},
            "submitted_by_partner_id": "pt-1", "submitted_by_partner_name": "Rui", "network_id": REDE_INCUMBENTE,
        }

    async def test_o_processo_do_onboarding_nasce_atribuido_ao_parceiro(self, fake_async_db):
        import services.onboarding_mandatory_config as ob

        cliente = self._lead_com_parceiro()
        fake_async_db.clients.docs.append(dict(cliente))
        with patch.object(ob, "db", fake_async_db):
            await ob._criar_processo_do_onboarding("c-1", cliente, lambda c: c, AsyncMock(return_value=1))
        processo = fake_async_db.processes.docs[0]
        assert processo["assigned_parceiro_id"] == "pt-1" and processo["parceiro_name"] == "Rui"

    async def test_sem_parceiro_o_processo_do_onboarding_nao_ganha_atribuicao_nenhuma(self, fake_async_db):
        import services.onboarding_mandatory_config as ob

        cliente = {k: v for k, v in self._lead_com_parceiro().items() if not k.startswith("submitted_by")}
        fake_async_db.clients.docs.append(dict(cliente))
        with patch.object(ob, "db", fake_async_db):
            await ob._criar_processo_do_onboarding("c-1", cliente, lambda c: c, AsyncMock(return_value=1))
        assert "assigned_parceiro_id" not in fake_async_db.processes.docs[0]

    async def test_o_processo_criado_para_o_cliente_pela_equipa_herda_o_parceiro(self, fake_async_db):
        import services.client_process_ops as cpo

        fake_async_db.clients.docs.append(self._lead_com_parceiro())
        utilizador = {"id": "u-carla", "name": "Carla", "role": "consultor", "email": "c@x.pt"}
        with patch.object(cpo, "db", fake_async_db):
            await cpo.run_create_process_for_client("c-1", utilizador)
        processo = fake_async_db.processes.docs[0]
        assert processo["assigned_parceiro_id"] == "pt-1"
        assert processo["assigned_consultor_id"] == "u-carla", "a atribuição da equipa não é afectada"


# ════════════════════════════════════════════════════════════════════
#  FICHEIROS — URL DE ENVIO
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestUrlDeEnvio:
    async def test_processo_por_indexar_vai_para_a_index_seja_qual_for_a_pasta_pedida(self, com_bd, s3):
        import services.partner_upload_ops as ops

        _mundo(com_bd, indexado=False)
        r = await ops.run_partner_upload_url(PT1, "a-novo", ops.PartnerUploadUrlIn(filename="cc.pdf", category="Identificação"))
        chamada = next(c for c in s3.chamadas if c[0] == "presign_put")[1]
        assert chamada["category"] == "Index"
        assert chamada["s3_folder"] == "Documentação Clientes/cli-a-novo", "a pasta é a do processo, derivada do id"
        assert r["destino"]["fila_ia"] is True and r["destino"]["categoria_pedida"] == "Identificação"
        assert "/Index/" in r["file_key"]

    async def test_processo_indexado_usa_a_pasta_pedida(self, com_bd, s3):
        import services.partner_upload_ops as ops

        _mundo(com_bd, indexado=True)
        r = await ops.run_partner_upload_url(PT1, "a-novo", ops.PartnerUploadUrlIn(filename="cc.pdf", category="Identificação"))
        assert next(c for c in s3.chamadas if c[0] == "presign_put")[1]["category"] == "Identificação"
        assert r["destino"]["fila_ia"] is False

    async def test_via_verde_conta_como_indexado(self, com_bd, s3):
        import services.partner_upload_ops as ops

        _mundo(com_bd, skip_index=True)
        r = await ops.run_partner_upload_url(PT1, "a-novo", ops.PartnerUploadUrlIn(filename="cc.pdf", category="Financeiros"))
        assert r["destino"]["fila_ia"] is False and r["destino"]["categoria_final"] == "Financeiros"

    async def test_uma_lead_vai_para_a_index_do_cliente_e_cria_o_mapeamento_pelo_id(self, com_bd, s3):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        r = await ops.run_partner_upload_url(PT1, "lead-1", ops.PartnerUploadUrlIn(filename="cc.pdf", category="Identificação"))
        assert ("ensure_mapping", "lead-1") in s3.chamadas, "a pasta nasce do ID do cliente, nunca do nome"
        assert r["file_key"].startswith("Documentação Clientes/lead-1/Index/")
        assert next(c for c in com_bd.clients.docs if c["id"] == "lead-1")["s3_folder"] == "Documentação Clientes/lead-1"

    async def test_um_caso_alheio_e_404_e_nao_chega_ao_s3(self, com_bd, s3):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        for alheio in ("x-outro", "nao-existe"):
            with pytest.raises(HTTPException) as erro:
                await ops.run_partner_upload_url(PT1, alheio, ops.PartnerUploadUrlIn(filename="x.pdf"))
            assert erro.value.status_code == 404
        assert s3.chamadas == []

    async def test_um_pedido_de_outro_caso_e_404_antes_de_assinar(self, com_bd, s3):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        com_bd.documents.docs.append({"id": "req-alheio", "process_id": "x-outro", "status": "REQUESTED", "source": "admin_request"})
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_upload_url(PT1, "a-novo", ops.PartnerUploadUrlIn(filename="x.pdf", request_id="req-alheio"))
        assert erro.value.status_code == 404 and s3.chamadas == []

    async def test_o_corpo_recusa_campos_a_mais(self):
        import services.partner_upload_ops as ops

        with pytest.raises(ValidationError):
            ops.PartnerUploadUrlIn(filename="x.pdf", s3_folder="backups")
        with pytest.raises(ValidationError):
            ops.PartnerConfirmUploadIn(file_key="k", original_filename="x.pdf", file_size=1)


# ════════════════════════════════════════════════════════════════════
#  FICHEIROS — CONFIRMAR
# ════════════════════════════════════════════════════════════════════
def _confirmar(ops, key=CHAVE_BOA, nome="cc.pdf", **extra):
    return ops.PartnerConfirmUploadIn(file_key=key, original_filename=nome, **extra)


@pytest.mark.asyncio
class TestPosseAntesDeTudo:
    @pytest.mark.parametrize(
        "chave",
        [
            "backups/dump-2026-09-01.zip",                                  # o P0
            "companies/logo.png",
            "Documentação Clientes/cli-outro/Index/x.pdf",                  # o cliente do vizinho
            "Documentação Clientes/cli-a-novo-EXTRA/Index/x.pdf",           # prefixo de texto, não de segmento
            "Documentação Clientes/x.pdf",                                  # a raiz
            "Documentação Clientes/",
            "",
        ],
    )
    async def test_uma_chave_fora_da_pasta_do_caso_e_403_sem_tocar_em_nada(self, com_bd, s3, veredicto, chave):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        antes = copy.deepcopy(com_bd.documents.docs)
        with pytest.raises((HTTPException, ValidationError)) as erro:
            await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, key=chave or "x"))
        if isinstance(erro.value, HTTPException):
            assert erro.value.status_code == 403
        veredicto.assert_not_awaited()
        assert com_bd.documents.docs == antes and s3.chamadas == []

    async def test_a_chave_de_outro_caso_do_mesmo_parceiro_com_outro_cliente_tambem_e_recusada(self, com_bd, veredicto):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_confirm_upload(PT1, "lead-1", _confirmar(ops, key=CHAVE_BOA))
        assert erro.value.status_code == 403
        veredicto.assert_not_awaited()

    async def test_um_prefixo_de_posse_envenenado_nao_abre_o_bucket(self, com_bd, veredicto):
        """O `s3_folder` gravado no processo aponta para fora da árvore de
        documentos: a guarda da RAIZ é a que defende (e não é redundante)."""
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        com_bd.processes.docs[0]["s3_folder"] = "backups"
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, key="backups/dump.zip"))
        assert erro.value.status_code == 403
        veredicto.assert_not_awaited()

    async def test_o_pedido_invalido_e_recusado_antes_da_quarentena(self, com_bd, veredicto):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, request_id="nao-existe"))
        assert erro.value.status_code == 404
        veredicto.assert_not_awaited()

    async def test_outro_parceiro_nao_confirma_no_meu_caso(self, com_bd, veredicto):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_confirm_upload(PT2, "a-novo", _confirmar(ops))
        assert erro.value.status_code == 404
        veredicto.assert_not_awaited()


@pytest.mark.asyncio
class TestDesvioInteligenteDoBloco2:
    async def test_por_indexar_entra_na_fila_da_ia_e_agenda_a_categorizacao(self, com_bd, tarefas):
        import services.partner_upload_ops as ops

        _mundo(com_bd, indexado=False)
        r = await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, category="Identificação"))
        fila = [m for m in com_bd.document_metadata.docs if m.get("in_index_queue")]
        assert [(m["process_id"], m["s3_path"], m["queue_source"]) for m in fila] == [("a-novo", CHAVE_BOA, "portal_parceiro")]
        assert "partner-categorize:a-novo" in tarefas
        assert r["destino"]["fila_ia"] is True

    async def test_indexado_guarda_na_pasta_pedida_sem_ia(self, com_bd, tarefas):
        import services.partner_upload_ops as ops

        _mundo(com_bd, indexado=True)
        r = await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, category="Identificação"))
        assert com_bd.document_metadata.docs == []
        assert "partner-categorize:a-novo" not in tarefas
        assert r["destino"]["categoria_final"] == "Identificação" and r["destino"]["fila_ia"] is False
        assert next(d for d in com_bd.documents.docs if d["id"] == r["id"])["category"] == "Identificação"

    async def test_via_verde_nao_gasta_ia(self, com_bd, tarefas):
        import services.partner_upload_ops as ops

        _mundo(com_bd, skip_index=True)
        await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops))
        assert com_bd.document_metadata.docs == [] and "partner-categorize:a-novo" not in tarefas

    async def test_uma_lead_nao_tem_fila_e_dispara_a_verificacao_de_onboarding(self, com_bd, tarefas):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        r = await ops.run_partner_confirm_upload(
            PT1, "lead-1", _confirmar(ops, key="Documentação Clientes/lead-1/Index/cc.pdf")
        )
        doc = next(d for d in com_bd.documents.docs if d["id"] == r["id"])
        assert doc["client_id"] == "lead-1" and doc["process_id"] is None and doc["category"] == "Index"
        assert com_bd.document_metadata.docs == []
        assert "onboarding-check:lead-1" in tarefas


@pytest.mark.asyncio
class TestConfirmarGrava:
    async def test_o_registo_leva_a_autoria_do_parceiro_e_os_valores_reais(self, com_bd):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        r = await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops))
        doc = next(d for d in com_bd.documents.docs if d["id"] == r["id"])
        assert doc["uploaded_by"] == "partner:pt-1" and doc["source"] == "partner_portal" and doc["status"] == "RECEIVED"
        assert doc["file_size"] == 2048 and doc["content_type"] == "application/pdf", "os valores da quarentena, não os do browser"
        assert doc["process_id"] == "a-novo" and doc["client_id"] == "cli-a-novo" and doc["s3_path"] == CHAVE_BOA

    async def test_a_quarentena_recebe_a_chave_e_o_nome(self, com_bd, veredicto):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, nome="meu cc.pdf"))
        veredicto.assert_awaited_once_with(CHAVE_BOA, filename="meu cc.pdf")

    async def test_a_resposta_nao_leva_chave_nem_url(self, com_bd):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        r = await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops))
        blob = repr(r)
        assert "s3_path" not in blob and "Documentação Clientes" not in blob and "http" not in blob

    async def test_reprovar_na_quarentena_nao_grava_nada(self, com_bd, veredicto):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        veredicto.side_effect = HTTPException(status_code=400, detail="Conteúdo não permitido")
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops))
        assert erro.value.status_code == 400
        assert com_bd.documents.docs == [] and com_bd.document_metadata.docs == [] and com_bd.history.docs == []

    async def test_uma_falha_transitoria_do_s3_e_503_e_nao_grava(self, com_bd, veredicto):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        veredicto.side_effect = HTTPException(status_code=503, detail="Serviço de armazenamento indisponível")
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops))
        assert erro.value.status_code == 503 and com_bd.documents.docs == []

    async def test_deixa_rasto_no_historico_do_processo_com_o_nome_do_parceiro(self, com_bd):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, category="Identificação"))
        rasto = [h for h in com_bd.history.docs if h.get("process_id") == "a-novo"]
        assert rasto and rasto[0]["action"] == "DOCUMENT_UPLOADED_BY_PARTNER"
        assert "Rui" in str(rasto[0].get("user_name") or rasto[0]) and "cc.pdf" in repr(rasto[0])

    async def test_avisa_a_equipa_atribuida_a_dizer_que_foi_o_parceiro(self, com_bd, tarefas):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        com_bd.processes.docs[0]["assigned_consultor_id"] = "u-carla"
        com_bd.users.docs.append({"id": "u-carla", "email": "carla@x.pt", "name": "Carla"})
        with patch("services.notification_service.send_notification_with_preference_check", new=AsyncMock()) as enviar:
            caso = await ops.resolver_caso(PT1, "a-novo")
            await ops._avisar_a_equipa(caso, PT1, "cc.pdf")
        enviar.assert_awaited_once()
        mensagem = enviar.await_args.args[2]
        assert "parceiro Rui" in mensagem and "cc.pdf" in mensagem and "cliente" not in mensagem.lower().split("(")[0]

    async def test_o_envio_aparece_logo_no_detalhe_do_parceiro_como_dele(self, com_bd):
        import services.partner_portal_read as ppr
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        r = await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops))
        detalhe = await ppr.run_get_case(PT1, "a-novo")
        assert [(f["id"], f["by"]) for f in detalhe["ficheiros"]] == [(r["id"], "eu")]


@pytest.mark.asyncio
class TestRespostaAUmPedido:
    def _pedido(self, m, **extra):
        m.documents.docs.append({
            "id": "req-1", "process_id": "a-novo", "status": "REQUESTED", "source": "admin_request",
            "category": "Identificação", "expected_count": 2, "created_at": "2026-10-04T10:00:00+00:00", **extra,
        })

    async def test_satisfaz_pela_contagem_como_no_portal_do_cliente(self, com_bd):
        import services.partner_portal_read as ppr
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        self._pedido(com_bd)
        await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, key=CHAVE_BOA, request_id="req-1"))
        pedido = next(d for d in com_bd.documents.docs if d["id"] == "req-1")
        assert pedido["status"] == "REQUESTED", "1 de 2: continua pendente"
        assert pedido["attached_files"][0]["uploaded_by"] == "partner:pt-1"

        await ops.run_partner_confirm_upload(
            PT1, "a-novo", _confirmar(ops, key="Documentação Clientes/cli-a-novo/Index/cc2.pdf", request_id="req-1")
        )
        assert next(d for d in com_bd.documents.docs if d["id"] == "req-1")["status"] == "RECEIVED"
        detalhe = await ppr.run_get_case(PT1, "a-novo")
        assert detalhe["pedidos_pendentes"] == 0
        assert [f["by"] for f in detalhe["pedidos"][0]["ficheiros"]] == ["eu", "eu"]

    async def test_nunca_cria_um_envio_solto_quando_o_pedido_nao_casa(self, com_bd):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        com_bd.documents.docs.append({"id": "req-x", "process_id": "x-outro", "status": "REQUESTED", "source": "admin_request"})
        antes = len(com_bd.documents.docs)
        with pytest.raises(HTTPException):
            await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, request_id="req-x"))
        assert len(com_bd.documents.docs) == antes

    async def test_se_o_pedido_deixa_de_casar_entre_a_verificacao_e_a_escrita_e_409_e_nao_cria_envio_solto(self, com_bd):
        """A verificação do pedido e a escrita são duas operações: se o pedido
        desaparece pelo meio (apagado pela equipa), o ficheiro não vira um
        envio solto em silêncio — o parceiro é avisado."""
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        self._pedido(com_bd)
        antes = [d["id"] for d in com_bd.documents.docs]
        with patch.object(ops, "apply_portal_request_upload", new=AsyncMock(return_value={"matched": False})):
            with pytest.raises(HTTPException) as erro:
                await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, request_id="req-1"))
        assert erro.value.status_code == 409
        assert [d["id"] for d in com_bd.documents.docs] == antes

    async def test_um_pedido_ancorado_so_ao_cliente_re_ancora_se_ao_processo(self, com_bd):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        com_bd.documents.docs.append({
            "id": "req-cli", "client_id": "cli-a-novo", "status": "REQUESTED",
            "source": "mandatory_checklist", "category": "Identificação",
        })
        await ops.run_partner_confirm_upload(PT1, "a-novo", _confirmar(ops, request_id="req-cli"))
        pedido = next(d for d in com_bd.documents.docs if d["id"] == "req-cli")
        assert pedido["process_id"] == "a-novo" and pedido["status"] == "RECEIVED"

    async def test_um_pedido_de_uma_lead_e_satisfeito_pelo_parceiro(self, com_bd):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        com_bd.documents.docs.append({
            "id": "req-lead", "client_id": "lead-1", "status": "REQUESTED",
            "source": "mandatory_checklist", "category": "Identificação",
        })
        await ops.run_partner_confirm_upload(
            PT1, "lead-1", _confirmar(ops, key="Documentação Clientes/lead-1/Index/cc.pdf", request_id="req-lead")
        )
        assert next(d for d in com_bd.documents.docs if d["id"] == "req-lead")["status"] == "RECEIVED"


# ════════════════════════════════════════════════════════════════════
#  DESCARREGAR
# ════════════════════════════════════════════════════════════════════
def _ficheiros_para_descarga(m):
    m.documents.docs.extend([
        {"id": "meu", "process_id": "a-novo", "status": "RECEIVED", "source": "partner_portal",
         "s3_path": CHAVE_BOA, "filename": "cc.pdf", "uploaded_by": "partner:pt-1"},
        {"id": "do-cliente", "process_id": "a-novo", "status": "RECEIVED", "source": "client_portal",
         "s3_path": "Documentação Clientes/cli-a-novo/Index/foto.jpg", "filename": "foto.jpg", "uploaded_by": "portal_client"},
        {"id": "da-equipa", "process_id": "a-novo", "status": "RECEIVED", "source": "client_portal",
         "s3_path": "Documentação Clientes/cli-a-novo/Financeiros/interno.pdf", "filename": "interno.pdf",
         "uploaded_by": "u-consultora"},
        # Do CLIENTE (visível ao parceiro), para que o teste exercite a posse
        # da chave e não a recusa de descarregar os próprios ficheiros.
        {"id": "envenenado", "process_id": "a-novo", "status": "RECEIVED", "source": "client_portal",
         "s3_path": "backups/dump-2026-09-01.zip", "filename": "dump.zip", "uploaded_by": "portal_client"},
    ])


@pytest.mark.asyncio
class TestDescarga:
    async def test_descarrega_o_que_o_cliente_enviou(self, com_bd, s3):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        _ficheiros_para_descarga(com_bd)
        r = await ops.run_partner_download_url(PT1, "a-novo", "do-cliente")
        assert r["url"] == "https://s3.exemplo/get" and r["expires_in"] == 900
        assert [c[2] for c in s3.chamadas if c[0] == "presign_get"] == [900], "15 minutos, não 1 hora"

    async def test_o_que_o_proprio_parceiro_submeteu_nao_se_descarrega(self, com_bd, s3):
        """Bloco C: o botão saiu do ecrã; a parede é o servidor."""
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        _ficheiros_para_descarga(com_bd)
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_download_url(PT1, "a-novo", "meu")
        assert erro.value.status_code == 403
        assert not [c for c in s3.chamadas if c[0] == "presign_get"]

    async def test_o_que_a_equipa_juntou_e_404(self, com_bd, s3):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        _ficheiros_para_descarga(com_bd)
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_download_url(PT1, "a-novo", "da-equipa")
        assert erro.value.status_code == 404
        assert not [c for c in s3.chamadas if c[0] == "presign_get"]

    @pytest.mark.parametrize("fid", ["backups/dump-2026-09-01.zip", CHAVE_BOA, "../../etc/passwd", "", "nao-existe"])
    async def test_uma_chave_nunca_e_aceite_no_lugar_de_um_id(self, com_bd, s3, fid):
        """O parceiro não nomeia chaves: se o fizer, é um id que não existe."""
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        _ficheiros_para_descarga(com_bd)
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_download_url(PT1, "a-novo", fid)
        assert erro.value.status_code == 404
        assert not [c for c in s3.chamadas if c[0] == "presign_get"]

    async def test_um_registo_envenenado_do_passado_deixa_de_ser_servido(self, com_bd, s3):
        """A janela vulnerável do P0 deixou registos com `s3_path` fora da
        pasta. A posse na LEITURA neutraliza-os sem limpar a colecção."""
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        _ficheiros_para_descarga(com_bd)
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_download_url(PT1, "a-novo", "envenenado")
        assert erro.value.status_code == 403
        assert not [c for c in s3.chamadas if c[0] == "presign_get"]

    async def test_outro_parceiro_nao_descarrega_do_meu_caso(self, com_bd):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        _ficheiros_para_descarga(com_bd)
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_download_url(PT2, "a-novo", "meu")
        assert erro.value.status_code == 404

    async def test_um_ficheiro_que_ja_nao_existe_no_bucket_e_404(self, com_bd, s3):
        import services.partner_upload_ops as ops

        _mundo(com_bd)
        _ficheiros_para_descarga(com_bd)
        s3.existe = False
        with pytest.raises(HTTPException) as erro:
            await ops.run_partner_download_url(PT1, "a-novo", "do-cliente")
        assert erro.value.status_code == 404


# ════════════════════════════════════════════════════════════════════
#  O LADO DA EQUIPA
# ════════════════════════════════════════════════════════════════════
class TestOLadoDaEquipa:
    def test_a_origem_do_parceiro_esta_na_lista_do_crm(self):
        """Sem isto a aba Documentos do CRM não mostrava o que o parceiro enviou."""
        from services.document_portal_request import PORTAL_REQUEST_SOURCES

        assert "partner_portal" in PORTAL_REQUEST_SOURCES

    def test_o_envio_do_parceiro_acende_a_bolinha_verde_e_o_da_equipa_nao(self):
        from datetime import datetime, timezone

        from services.document_novelty import condicao_de_documento_novo

        agora = datetime.now(timezone.utc)
        cond = condicao_de_documento_novo(agora)
        base = {"uploaded_at": agora.isoformat()}
        assert casa({**base, "uploaded_by": "partner:pt-1"}, cond)
        assert casa({**base, "uploaded_by": "portal_client"}, cond)
        assert not casa({**base, "uploaded_by": "u-consultora"}, cond)
        assert not casa({**base, "uploaded_by": "partner:pt-1", "staff_seen_at": agora.isoformat()}, cond)

    def test_o_parceiro_e_o_cliente_vencem_no_filtro_de_visibilidade_e_a_equipa_nao(self):
        from services.partner_visibility import ficheiro_e_visivel

        assert ficheiro_e_visivel("portal_client", "pt-1")
        assert ficheiro_e_visivel("partner:pt-1", "pt-1")
        assert not ficheiro_e_visivel("partner:pt-2", "pt-1")
        assert not ficheiro_e_visivel("u-consultora", "pt-1")
        assert not ficheiro_e_visivel(None, "pt-1")
        assert not ficheiro_e_visivel("partner:", ""), "sem id de parceiro nada é visível por prefixo"
