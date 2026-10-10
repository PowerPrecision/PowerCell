"""
PORTAL DO PARCEIRO — O CONTRATO COM O FRONTEND

A armadilha desta casa (a quarta vez): o ecrã lê um contrato que o servidor
não cumpre — e um MOCK com a forma inventada deixa a bateria do frontend
verde sobre um ecrã que não lê nada (`/portal/status`, `{config, fields}` dos
SLAs, o socket do Portal). Por isso os mocks do frontend NÃO são escritos à
mão: são as respostas REAIS destes serviços, geradas aqui sobre um cenário
semeado e gravadas em `frontend/src/test/fixtures/parceiro/*.json`.

  * este teste REGENERA as respostas e compara com os ficheiros;
  * se o servidor mudar de forma, falha — a dizer qual fixture e como a
    actualizar (`ATUALIZAR_FIXTURES_DO_PARCEIRO=1 pytest <este ficheiro>`);
  * o frontend importa esses ficheiros; mudar o servidor sem actualizar as
    fixtures parte ESTE teste, e actualizá-las pode partir os do frontend —
    é exactamente o aviso que se quer.

Os valores do cenário são DIFERENTES das omissões (nomes, números, etapas
espalhadas pelo funil): com valores iguais às omissões, um erro de leitura é
indistinguível de uma leitura correcta.
"""
from __future__ import annotations

import contextlib
import copy
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.helpers_tenant import (  # noqa: F401
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)
from tests.unit.test_parceiro_escrita import _S3Falso, _mundo
from tests.unit.test_parceiro_identidade import ADMIN_POWER, PASSWORD, _activar, _convidar
from tests.unit.test_parceiro_leitura import FASES, PT1, PT2, PT3, _documentos, _lead, _proc

PASTA = Path(__file__).resolve().parents[3] / "frontend" / "src" / "test" / "fixtures" / "parceiro"
ISO_COM_MICROSSEGUNDOS = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+\+00:00")


def _fixar(obj, mapa: dict[str, str]):
    """Troca o que muda de execução para execução por valores fixos."""
    if isinstance(obj, dict):
        return {k: _fixar(v, mapa) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_fixar(v, mapa) for v in obj]
    if isinstance(obj, str):
        for velho, novo in mapa.items():
            obj = obj.replace(velho, novo)
        return ISO_COM_MICROSSEGUNDOS.sub("2026-10-11T09:30:00+00:00", obj)
    return obj


def _escrever_ou_comparar(nome: str, dados) -> None:
    corpo = json.dumps(dados, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    caminho = PASTA / f"{nome}.json"
    if os.environ.get("ATUALIZAR_FIXTURES_DO_PARCEIRO") == "1":
        PASTA.mkdir(parents=True, exist_ok=True)
        caminho.write_text(corpo, encoding="utf-8")
        return
    assert caminho.exists(), (
        f"Falta a fixture {caminho.name}. Gere-a com: "
        "ATUALIZAR_FIXTURES_DO_PARCEIRO=1 pytest tests/unit/test_parceiro_contrato_frontend.py"
    )
    assert caminho.read_text(encoding="utf-8") == corpo, (
        f"O servidor deixou de devolver o que a fixture {caminho.name} diz. Se a mudança é intencional: "
        "ATUALIZAR_FIXTURES_DO_PARCEIRO=1 pytest tests/unit/test_parceiro_contrato_frontend.py "
        "— e corra depois os testes do frontend (`yarn test`)."
    )


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente, monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.delenv("JWT_PARTNER_SECRET", raising=False)
    semear(fake_async_db)
    fake_async_db.workflow_statuses.docs.extend(dict(f) for f in FASES)
    fake_async_db.partners.docs.extend([copy.deepcopy(PT1), copy.deepcopy(PT2), copy.deepcopy(PT3)])
    return fake_async_db


@pytest.fixture
def com_tudo(mundo):
    import services.admin_users_scope as scope_mod
    import services.audit_trail_service as audit
    import services.document_intake as intake
    import services.document_portal_counts as counts
    import services.history as history
    import services.partner_accounts as acc
    import services.partner_leads as leads
    import services.partner_portal_read as ppr
    import services.partner_security as sec
    import services.partner_upload_ops as ops
    import services.portal_upload_ops as portal_ops
    import services.servico_do_parceiro as svc
    import services.user_management_scope as ums

    s3 = _S3Falso()
    veredicto = AsyncMock(return_value=SimpleNamespace(tamanho=48213, tipo_detectado="application/pdf"))
    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(mundo, acc, sec, ppr, leads, ops, intake, counts, history, portal_ops,
                                      audit, scope_mod, ums, svc))
        pilha.enter_context(patch.object(ops, "s3_service", s3))
        pilha.enter_context(patch.object(portal_ops, "s3_service", s3))
        pilha.enter_context(patch.object(ops, "exigir_conteudo_valido", veredicto))
        pilha.enter_context(patch("services.background_tasks.spawn_background_task",
                                  lambda coro, name=None: (coro.close(), None)[1]))
        yield mundo


@pytest.mark.asyncio
class TestOContratoComOFrontend:
    async def test_leitura_painel_lista_e_detalhes(self, com_tudo):
        import services.partner_portal_read as ppr

        m = com_tudo
        _mundo(m)
        # Um funil espalhado e valores que NÃO são as omissões.
        m.processes.docs.extend([
            _proc("b-aprovado", "pt-1", status="ch_aprovado"),
            _proc("c-escriturado", "pt-1", status="concluidos"),
            _proc("d-perdido", "pt-1", status="desistencias"),
        ])
        m.clients.docs.append(_lead("lead-2", "pt-1", updated_at="2026-10-09T10:00:00+00:00"))
        _documentos(m)
        m.documents.docs.append({
            "id": "req-lead", "client_id": "lead-1", "status": "REQUESTED", "source": "mandatory_checklist",
            "category": "Cartão de Cidadão", "notes": "Frente e verso", "expected_count": 2,
            "created_at": "2026-10-03T12:00:00+00:00",
        })

        _escrever_ou_comparar("painel", await ppr.run_get_dashboard(PT1))
        _escrever_ou_comparar("casos", await ppr.run_list_cases(PT1, page=1, size=20))
        _escrever_ou_comparar("caso_processo", await ppr.run_get_case(PT1, "a-novo"))
        _escrever_ou_comparar("caso_lead", await ppr.run_get_case(PT1, "lead-1"))

    async def test_perfil_convite_sessao_e_parceiros(self, com_tudo):
        import services.partner_accounts as acc

        convite = await _convidar(acc, ADMIN_POWER)
        info = await acc.run_get_invite(convite["invite_token"])
        pid = convite["partner"]["id"]
        mapa = {pid: "parceiro-novo", convite["invite_token"]: "TOKEN-DO-CONVITE"}

        _escrever_ou_comparar("convite", _fixar(info, mapa))
        _escrever_ou_comparar("convite_criado", _fixar({k: v for k, v in convite.items()}, mapa))

        sessao = await _activar(acc, convite)
        sessao_fixa = _fixar({**sessao, "access_token": "TOKEN-DA-SESSAO"}, mapa)
        _escrever_ou_comparar("sessao", sessao_fixa)
        _escrever_ou_comparar("perfil", sessao_fixa["partner"])
        _escrever_ou_comparar("parceiros", _fixar(await acc.run_list_partners(ADMIN_POWER), mapa))

    async def test_escrita_lead_e_ficheiros(self, com_tudo):
        import services.partner_leads as pl
        import services.partner_upload_ops as ops

        m = com_tudo
        _mundo(m)
        lead = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(
            name="Joana Cliente", email="joana@cliente.pt", phone="912345678", consent_confirmed=True,
        ))
        repetida = await pl.run_submit_lead(PT1, pl.PartnerLeadIn(
            name="Joana Cliente", email="joana@cliente.pt", phone="912345678", consent_confirmed=True,
        ))
        mapa = {lead["id"]: "lead-novo"}
        _escrever_ou_comparar("lead_criada", _fixar(lead, mapa))
        _escrever_ou_comparar("lead_repetida", _fixar(repetida, mapa))

        url = await ops.run_partner_upload_url(PT1, "a-novo", ops.PartnerUploadUrlIn(filename="cc.pdf", category="Identificação"))
        _escrever_ou_comparar("url_de_envio", _fixar(url, {}))
        confirmacao = await ops.run_partner_confirm_upload(
            PT1, "a-novo", ops.PartnerConfirmUploadIn(file_key=url["file_key"], original_filename="cc.pdf")
        )
        mapa_ficheiro = {confirmacao["id"]: "ficheiro-novo"}
        _escrever_ou_comparar("confirmacao_de_envio", _fixar(confirmacao, mapa_ficheiro))
        # O parceiro descarrega o que o CLIENTE enviou (o que ele próprio
        # submeteu não se descarrega — Bloco C).
        com_tudo.documents.docs.append({
            "id": "do-cliente", "process_id": "a-novo", "status": "RECEIVED", "source": "client_portal",
            "s3_path": "Documentação Clientes/cli-a-novo/Index/foto.jpg", "filename": "foto.jpg",
            "uploaded_by": "portal_client",
        })
        descarga = await ops.run_partner_download_url(PT1, "a-novo", "do-cliente")
        _escrever_ou_comparar("descarga", _fixar(descarga, {}))

    async def test_servico_do_parceiro_lado_da_equipa(self, com_tudo):
        import services.servico_do_parceiro as svc

        m = com_tudo
        _mundo(m)
        m.processes.docs[0].update({"network_id": "grupo_power_precision", "company_id": "cmp-power", "parceiro_name": "Rui"})
        ator = {"id": "u-ana", "name": "Ana", "email": "a@x.pt", "role": "administrativo", "effective_role": "administrativo"}
        _escrever_ou_comparar("servico_por_pagar", _fixar(await svc.run_get_servico("a-novo", ator), {}))
        await svc.run_set_servico(
            "a-novo", svc.ServicoDoParceiroBody(pago=True, observacoes="Transferência de 14/10\nRef. 8841"), ator
        )
        _escrever_ou_comparar("servico_pago", _fixar(await svc.run_get_servico("a-novo", ator), {}))
