"""QA-8 (9): o email enviado a partir de um processo aparece nos «Enviados» do Webmail.

O documento gravado por `send_email` não tinha `is_archived` e a pasta filtrava
`{"is_archived": False}` — em Mongo, igualdade com `False` NÃO casa um campo em falta. O email
ficava no histórico do processo (que filtra por `process_id`) e a pasta dizia «Sem emails nesta
pasta». Segunda causa: o carimbo de empresa — um envio sem `X-Company-Id` ou por uma conta que não é
uma das contas pessoais do utilizador ficava fora do filtro de empresa do separador.
Usa `run_webmail_list` a sério (só o papel e as contas são falseados), com o documento TAL COMO o
`send_email` o grava.
"""
from unittest.mock import patch

import pytest

from tests.unit.helpers_tenant import tenant_db
from tests.unit.test_webmail_tenant_isolation import _ucr

USER = {"id": "u1", "email": "ana@power.pt", "role": "consultor"}


def _enviado(eid, **extra):
    """O que `email_service.send_email` grava (campos relevantes)."""
    doc = {
        "id": eid, "process_id": "p-1", "direction": "sent", "folder": "Sent",
        "from_email": "ana@power.pt", "to_emails": ["cliente@x.pt"], "subject": f"Assunto {eid}",
        "status": "sent", "sent_at": "2026-10-18T10:00:00+00:00", "created_by": "u1",
        "synced_for_user": "u1", "synced": False, "account": "ana@power.pt", "is_read": True,
        "is_archived": False, "is_starred": False,
    }
    doc.update(extra)
    return doc


@pytest.fixture
def base(fake_async_db):
    fake_async_db.user_company_roles.docs.append(_ucr("power", "consultor"))
    fake_async_db.companies.docs.append({"id": "power", "name": "Power Real Estate"})
    return fake_async_db


async def _enviados(base, company_id="power"):
    import services.email_webmail as mod

    async def papel(_r, _u):
        return "consultor"

    async def contas(_uid):
        return ["ana@power.pt"]

    async def cargos(_r, _u):
        return {"consultor"}

    import services.email_enrich as enrich

    with tenant_db(base, mod, enrich), patch("services.webmail_scope.db", base), \
            patch("services.auth.get_effective_role_async", papel), \
            patch.object(mod, "_resolve_conversation_emails", contas), \
            patch.object(mod, "_user_ucr_roles", cargos):
        resultado = await mod.run_webmail_list(
            None, USER, folder="sent", box="personal", company_id=company_id,
        )
    return {e["id"] for e in resultado.get("emails", [])}


class TestOEnviadoApareceNosEnviados:
    @pytest.mark.asyncio
    async def test_o_email_tal_como_o_send_email_o_grava(self, base):
        base.emails.docs.append(_enviado("e1", company_id="power"))
        assert "e1" in await _enviados(base)

    @pytest.mark.asyncio
    async def test_um_documento_antigo_sem_is_archived_tambem_aparece(self, base):
        doc = _enviado("legado", company_id="power")
        del doc["is_archived"]
        base.emails.docs.append(doc)
        assert "legado" in await _enviados(base)

    @pytest.mark.asyncio
    async def test_sem_carimbo_de_empresa_e_por_uma_conta_que_nao_e_pessoal(self, base):
        base.emails.docs.append(_enviado("sem-carimbo", account="geral@caixa-geral.pt"))
        assert "sem-carimbo" in await _enviados(base)

    # ---- contraprovas: o que NÃO pode aparecer -------------------------------------------
    @pytest.mark.asyncio
    async def test_o_enviado_por_outra_pessoa_sem_carimbo_nao_aparece(self, base):
        base.emails.docs.append(_enviado("alheio", created_by="u2", synced_for_user="u2",
                                         account="outro@power.pt", from_email="outro@power.pt"))
        assert "alheio" not in await _enviados(base)

    @pytest.mark.asyncio
    async def test_o_carimbado_para_outra_empresa_nao_aparece_neste_separador(self, base):
        base.emails.docs.append(_enviado("de-outra", company_id="domus"))
        assert "de-outra" not in await _enviados(base)

    @pytest.mark.asyncio
    async def test_um_rascunho_nao_e_um_enviado(self, base):
        base.emails.docs.append(_enviado("rascunho", company_id="power", status="draft"))
        assert "rascunho" not in await _enviados(base)

    @pytest.mark.asyncio
    async def test_um_email_arquivado_nao_aparece(self, base):
        base.emails.docs.append(_enviado("lixo", company_id="power", is_archived=True))
        assert "lixo" not in await _enviados(base)


class TestOEscritorGravaOsCampos:
    def test_send_email_grava_is_archived_e_is_starred(self):
        from pathlib import Path

        import services.email_service as mod
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(Path(mod.__file__).read_text())
        bloco = fonte[fonte.index("'folder': 'Sent'"):]
        bloco = bloco[:bloco.index("inserir_email")]
        assert "'is_archived': False" in bloco and "'is_starred': False" in bloco
