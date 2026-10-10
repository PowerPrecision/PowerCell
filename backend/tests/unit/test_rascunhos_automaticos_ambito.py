"""
Os rascunhos automáticos têm fronteira de rede (D-31, vertente dos emails).

O ACHADO
  `GET /emails/drafts` mostrava a admin/CEO os rascunhos de TODAS as redes
  (com o nome do cliente), e `PUT/POST send/DELETE /emails/drafts/{id}` e
  `POST /emails/drafts/create` recebiam só o id: qualquer sessão de staff
  enviava (do seu servidor de email) ou apagava o rascunho de um cliente de
  outra rede. Com o rascunho de confirmação de receção a gerar um rascunho
  por upload crítico, a superfície deixou de ser teórica.

  O filtro dos «outros» perfis olhava para `processes.assigned_to`, que o
  processo quase nunca tem: o consultor não via rascunho nenhum dos seus.
"""
from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

ANA = {"id": "u-ana", "role": "diretor", "effective_role": "diretor", "name": "Ana", "email": "ana@power.pt"}
BRUNO = {"id": "u-bruno", "role": "diretor", "effective_role": "diretor", "name": "Bruno", "email": "b@domus.pt"}
CONSULTOR = {"id": "u-consultor", "role": "consultor", "effective_role": "consultor", "name": "Cons", "email": "c@power.pt"}
ADMIN_POWER = {"id": "u-admin", "role": "admin", "effective_role": "admin", "name": "Adm", "email": "a@power.pt"}
MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "M", "email": "m@x.pt"}


def _rascunho(id_, process_id, **extra):
    return {"id": id_, "process_id": process_id, "is_auto_draft": True, "status": "draft",
            "subject": "s", "body": "b", "to_emails": ["c@x.pt"], "created_at": f"2026-10-0{len(id_) % 9 + 1}",
            "auto_draft_doc_type": "irs", "auto_draft_doc_label": "IRS", **extra}


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.document_visibility as dv
    import services.email_access as ea
    import services.email_draft_service as eds
    import services.email_templates_drafts as etd

    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.extend([
        {"user_id": "u-consultor", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "consultor"},
        {"user_id": "u-admin", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "admin"},
    ])
    fake_async_db.processes.docs.extend([
        {"id": "p-power-meu", "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
         "assigned_consultor_id": "u-consultor", "client_name": "Cliente A", "is_indexed": True},
        {"id": "p-power-outro", "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
         "assigned_consultor_id": "u-outro", "client_name": "Cliente B", "is_indexed": True},
    ])
    fake_async_db.emails.docs.extend([
        _rascunho("d-meu", "p-power-meu", network_id=REDE_INCUMBENTE, company_id="cmp-power"),
        _rascunho("d-outro", "p-power-outro", network_id=REDE_INCUMBENTE, company_id="cmp-power"),
        _rascunho("d-domus", "p-domus", network_id=REDE_DOMUS, company_id="cmp-domus"),
        _rascunho("d-legado", "p-legado"),  # sem carimbo nenhum
    ])
    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(fake_async_db, eds, etd, ea, dv))
        yield fake_async_db, etd


def _ids(rascunhos):
    return {d["id"] for d in rascunhos}


@pytest.mark.asyncio
class TestAListagem:
    async def test_a_Domus_so_ve_os_da_Domus(self, mundo):
        _, etd = mundo
        r = await etd.run_list_auto_drafts(BRUNO)
        assert _ids(r["drafts"]) == {"d-domus"}
        assert r["stats"]["total"] == 1

    async def test_a_gestao_da_Power_ve_os_da_sua_rede_e_o_legado_nao_os_da_Domus(self, mundo):
        _, etd = mundo
        for utilizador in (ANA, ADMIN_POWER):
            r = await etd.run_list_auto_drafts(utilizador)
            assert _ids(r["drafts"]) == {"d-meu", "d-outro", "d-legado"}, utilizador["id"]
            assert r["stats"]["total"] == 3

    async def test_o_Master_ve_todos(self, mundo):
        _, etd = mundo
        r = await etd.run_list_auto_drafts(MASTER)
        assert _ids(r["drafts"]) == {"d-meu", "d-outro", "d-domus", "d-legado"}

    async def test_o_consultor_ve_os_dos_seus_processos_pelo_campo_canonico(self, mundo):
        _, etd = mundo
        r = await etd.run_list_auto_drafts(CONSULTOR)
        assert _ids(r["drafts"]) == {"d-meu"}
        assert r["stats"]["total"] == 1

    async def test_o_consultor_ve_tambem_o_que_e_seu_mesmo_sem_processo_atribuido(self, mundo):
        db, etd = mundo
        db.emails.docs.append(_rascunho("d-criado-por-mim", "p-power-outro", network_id=REDE_INCUMBENTE,
                                        company_id="cmp-power", created_by="u-consultor"))
        assert "d-criado-por-mim" in _ids((await etd.run_list_auto_drafts(CONSULTOR))["drafts"])

    async def test_o_papel_efectivo_decide_e_nao_o_do_token(self, mundo):
        """Um admin de base que entra COMO consultor vê o que um consultor vê."""
        _, etd = mundo
        comoconsultor = {**CONSULTOR, "role": "admin", "effective_role": "consultor"}
        assert _ids((await etd.run_list_auto_drafts(comoconsultor))["drafts"]) == {"d-meu"}

    async def test_os_enviados_nao_aparecem(self, mundo):
        db, etd = mundo
        db.emails.docs[0]["status"] = "sent"
        assert "d-meu" not in _ids((await etd.run_list_auto_drafts(ANA))["drafts"])


@pytest.mark.asyncio
class TestEditarEnviarEDescartar:
    @pytest.mark.parametrize("operacao", ["editar", "enviar", "descartar"])
    async def test_a_Domus_nao_mexe_num_rascunho_da_Power(self, mundo, operacao):
        _, etd = mundo
        with patch.object(etd, "update_draft", AsyncMock()) as upd, \
             patch.object(etd, "send_draft", AsyncMock()) as snd, \
             patch.object(etd, "discard_draft", AsyncMock()) as dsc:
            with pytest.raises(HTTPException) as exc:
                if operacao == "editar":
                    await etd.run_edit_auto_draft("d-meu", {"subject": "x"}, BRUNO)
                elif operacao == "enviar":
                    await etd.run_send_auto_draft("d-meu", BRUNO)
                else:
                    await etd.run_delete_auto_draft("d-meu", BRUNO)
        assert exc.value.status_code == 404 and exc.value.detail == "Rascunho não encontrado"
        upd.assert_not_called(); snd.assert_not_called(); dsc.assert_not_called()

    async def test_o_404_de_um_alheio_e_igual_ao_de_um_inexistente(self, mundo):
        _, etd = mundo
        with pytest.raises(HTTPException) as alheio:
            await etd.run_send_auto_draft("d-meu", BRUNO)
        with pytest.raises(HTTPException) as nada:
            await etd.run_send_auto_draft("nao-existe", BRUNO)
        assert (alheio.value.status_code, alheio.value.detail) == (nada.value.status_code, nada.value.detail)

    async def test_a_Power_trata_dos_seus(self, mundo):
        _, etd = mundo
        with patch.object(etd, "update_draft", AsyncMock(return_value={"success": True})) as upd, \
             patch.object(etd, "send_draft", AsyncMock(return_value={"success": True})) as snd, \
             patch.object(etd, "discard_draft", AsyncMock(return_value={"success": True})) as dsc:
            await etd.run_edit_auto_draft("d-meu", {"subject": "novo"}, ANA)
            await etd.run_send_auto_draft("d-meu", CONSULTOR)
            await etd.run_delete_auto_draft("d-meu", ADMIN_POWER)
        upd.assert_awaited_once(); snd.assert_awaited_once(); dsc.assert_awaited_once()

    async def test_so_sao_rascunhos_automaticos(self, mundo):
        """Um email normal com o mesmo id não se apaga por esta rota."""
        db, etd = mundo
        db.emails.docs.append({"id": "e-normal", "process_id": "p-power-meu", "status": "sent",
                               "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"})
        with pytest.raises(HTTPException) as exc:
            await etd.run_delete_auto_draft("e-normal", ANA)
        assert exc.value.status_code == 404

    async def test_a_guarda_sozinha_so_aceita_rascunhos_automaticos(self, mundo):
        """O serviço também filtra por `is_auto_draft`; com ele neutralizado,
        a guarda tem de recusar por si — são duas camadas a dizer o mesmo."""
        db, etd = mundo
        db.emails.docs.append({"id": "e-normal", "process_id": "p-power-meu", "status": "sent",
                               "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"})
        with patch.object(etd, "discard_draft", AsyncMock(return_value={"success": True})) as dsc:
            with pytest.raises(HTTPException) as exc:
                await etd.run_delete_auto_draft("e-normal", ANA)
        assert exc.value.status_code == 404
        dsc.assert_not_called()

    async def test_criar_manualmente_num_processo_de_outra_rede_e_recusado(self, mundo):
        _, etd = mundo
        with patch.object(etd, "create_missing_doc_draft", AsyncMock()) as criar:
            with pytest.raises(HTTPException) as exc:
                await etd.run_manually_create_draft({"process_id": "p-power-meu", "doc_type": "irs"}, BRUNO)
        assert exc.value.status_code in (403, 404)
        criar.assert_not_called()

    async def test_criar_manualmente_no_seu_processo_funciona(self, mundo):
        _, etd = mundo
        with patch.object(etd, "create_missing_doc_draft", AsyncMock(return_value={"success": True})) as criar:
            await etd.run_manually_create_draft({"process_id": "p-power-meu", "doc_type": "irs"}, ANA)
        criar.assert_awaited_once()


class TestAsPortasEstaoLigadas:
    def test_as_tres_rotas_por_id_exigem_leitura_antes_de_agir(self):
        import ast
        from pathlib import Path

        fonte = Path(__file__).resolve().parents[2] / "services" / "email_templates_drafts.py"
        arvore = ast.parse(fonte.read_text(encoding="utf-8"))
        funcoes = {n.name: n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef)}
        for nome in ("run_edit_auto_draft", "run_send_auto_draft", "run_delete_auto_draft"):
            primeiras = [ast.unparse(s) for s in funcoes[nome].body[:3]]
            assert any("_exigir_rascunho_legivel" in s for s in primeiras), nome

    def test_a_listagem_passa_o_utilizador_para_a_rede(self):
        import ast
        from pathlib import Path

        fonte = Path(__file__).resolve().parents[2] / "services" / "email_templates_drafts.py"
        arvore = ast.parse(fonte.read_text(encoding="utf-8"))
        chamadas = [n for n in ast.walk(arvore) if isinstance(n, ast.Call)
                    and getattr(n.func, "id", "") in {"get_pending_drafts", "get_draft_stats"}]
        assert len(chamadas) == 3
        for chamada in chamadas:
            assert any(k.arg == "user" for k in chamada.keywords)
