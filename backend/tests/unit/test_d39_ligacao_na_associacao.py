"""D-39 — a consolidação dos ficheiros está LIGADA à associação, e nunca a derruba.

A mecânica (mover, reapontar, retomar) está em `tests/integration/test_d39_consolidar_ficheiros_mongo.py`
contra um MongoDB real. Aqui prova-se a ligação no fluxo do parceiro: a associação marca a consolidação
como pendente NO MESMO ACTO, chama-a com a lead e o cliente existente, e uma falha dela não desfaz a
associação (apagar a chamada não parte nenhum teste de comportamento sem estes).
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.test_b2b_colisao_de_cliente import (  # noqa: F401  (fixtures do mundo do parceiro)
    _cliente,
    _existente,
    _submeter_e_libertar,
    com_bd,
    mundo,
    rede_de_omissao_incumbente,
    s3,
    tarefas,
    veredicto,
    NIF_DA_LEAD,
)

BACKEND = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
class TestALigacao:
    async def test_a_associacao_chama_a_consolidacao_com_a_lead_e_o_cliente_existente(self, com_bd):
        _existente(com_bd)
        with patch("services.partner_lead_files.consolidar_ficheiros_da_lead", new=AsyncMock(return_value={})) as consolidar:
            cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)

        consolidar.assert_awaited_once()
        args, kwargs = consolidar.await_args
        assert args[0] == cid and args[1]["id"] == "c-existente" and kwargs["agora"]

    async def test_a_marca_de_pendente_nasce_com_a_associacao(self, com_bd):
        """Se o processo morrer antes de os ficheiros mudarem, a repetição diária sabe que falta."""
        _existente(com_bd)
        with patch("services.partner_lead_files.consolidar_ficheiros_da_lead", new=AsyncMock(return_value={})):
            cid, _ = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        rascunho = next(d for d in com_bd.partner_drafts.docs if d["id"] == cid)
        assert rascunho["partner_stage"] == "associada" and rascunho["matched_client_id"] == "c-existente"
        assert rascunho["consolidacao_pendente"]["desde"]

    async def test_uma_falha_da_consolidacao_nao_desfaz_a_associacao(self, com_bd):
        _existente(com_bd)
        with patch("services.partner_lead_files.consolidar_ficheiros_da_lead", new=AsyncMock(side_effect=RuntimeError("s3 em baixo"))):
            cid, resposta = await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)

        assert not [c for c in com_bd.clients.docs if c["id"] == cid], "a lead não passou a cliente novo"
        assert _cliente(com_bd, "c-existente")["partner_leads"][0]["lead_id"] == cid
        assert next(d for d in com_bd.partner_drafts.docs if d["id"] == cid)["partner_stage"] == "associada"
        assert resposta["lead_submetida"] is True

    async def test_sem_correspondencia_nao_ha_nada_a_consolidar(self, com_bd):
        with patch("services.partner_lead_files.consolidar_ficheiros_da_lead", new=AsyncMock()) as consolidar:
            await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        consolidar.assert_not_awaited()

    async def test_uma_lead_retida_por_conflito_de_identidade_nao_move_ficheiros(self, com_bd):
        _existente(com_bd, id="c-outra-pessoa", nif="123456789", email="joana@cliente.pt")
        with patch("services.partner_lead_files.consolidar_ficheiros_da_lead", new=AsyncMock()) as consolidar, \
                patch("services.alerts.notify_new_client_registration", new=AsyncMock()):
            await _submeter_e_libertar(com_bd, nif=NIF_DA_LEAD)
        consolidar.assert_not_awaited()


class TestAGuardaDeFonte:
    def test_a_associacao_chama_o_gancho(self):
        arvore = ast.parse((BACKEND / "services" / "partner_drafts.py").read_text(encoding="utf-8"))
        funcao = next(
            n for n in ast.walk(arvore)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_associar_a_cliente_existente"
        )
        chamadas = [getattr(c.func, "id", "") for c in ast.walk(funcao) if isinstance(c, ast.Call)]
        assert "_consolidar_ficheiros_da_lead" in chamadas

    def test_o_gancho_nunca_levanta(self):
        arvore = ast.parse((BACKEND / "services" / "partner_drafts.py").read_text(encoding="utf-8"))
        gancho = next(
            n for n in ast.walk(arvore)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_consolidar_ficheiros_da_lead"
        )
        assert any(isinstance(n, ast.Try) for n in ast.walk(gancho))

    def test_a_repeticao_diaria_esta_no_agendador(self):
        fonte = (BACKEND / "services" / "scheduled_tasks.py").read_text(encoding="utf-8")
        assert "self.consolidate_partner_lead_files" in fonte
        assert "consolidar_pendentes" in fonte

    def test_o_modulo_nao_apaga_antes_de_reapontar(self):
        """A ordem é parte do contrato: dentro de `_mover_um`, o `delete_file` vem DEPOIS do `_reapontar`."""
        arvore = ast.parse((BACKEND / "services" / "partner_lead_files.py").read_text(encoding="utf-8"))
        funcao = next(n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_mover_um")
        linhas = {}
        for no in ast.walk(funcao):
            if isinstance(no, ast.Call):
                nome = getattr(no.func, "id", "") or getattr(no.func, "attr", "")
                linhas.setdefault(nome, []).append(no.lineno)
            if isinstance(no, ast.Attribute) and no.attr == "delete_file":
                linhas.setdefault("delete_file", []).append(no.lineno)
        assert max(linhas["_reapontar"]) < max(linhas["delete_file"])
