"""QA-8 (8): «Desassociar» retira um email de um processo a que foi ligado por engano."""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import services.email_process_crud as mod

USER = {"id": "u1", "email": "ana@x.pt", "role": "consultor"}


@pytest.fixture
def base(fake_async_db):
    fake_async_db.emails.docs.append({
        "id": "e1", "message_id": "<m1>", "process_id": "p-1", "created_by": "u1",
        "subject": "Re: Docs [Ref: #p-1]", "direction": "received",
    })
    fake_async_db.emails.docs.append({"id": "e2", "message_id": "<m2>", "process_id": None, "created_by": "u1"})
    return fake_async_db


def _patches(base, *, pode_ler=True, processo_legivel=True, aberto=True):
    async def ler(email, user, detail=""):
        if not pode_ler:
            raise HTTPException(status_code=404, detail="x")

    async def ver(pid, user):
        if not processo_legivel:
            raise HTTPException(status_code=404, detail="x")

    async def aberto_(pid, user):
        if not aberto:
            raise HTTPException(status_code=403, detail="fechado")

    return [
        patch.object(mod, "db", base),
        patch("services.email_access.exigir_leitura_do_email", ler),
        patch("services.email_access.exigir_processo_legivel", ver),
        patch("services.process_closed_guard.exigir_processo_aberto_por_id", aberto_),
    ]


async def _correr(base, data, **kw):
    ps = _patches(base, **kw)
    for p in ps:
        p.start()
    try:
        return await mod.run_disassociate_email(data, USER)
    finally:
        for p in reversed(ps):
            p.stop()


class TestDesassociar:
    @pytest.mark.asyncio
    async def test_tira_o_process_id_e_deixa_rasto(self, base):
        r = await _correr(base, {"email_id": "e1"})
        assert r["success"] is True
        e1 = next(e for e in base.emails.docs if e["id"] == "e1")
        assert e1["process_id"] is None
        assert e1["disassociated_from_process_id"] == "p-1" and e1["disassociated_by"] == "u1"
        # não apaga o email nem lhe mexe no resto
        assert e1["subject"] == "Re: Docs [Ref: #p-1]"

    @pytest.mark.asyncio
    async def test_o_email_sai_da_lista_estrita_do_processo(self, base):
        from services.email_process_crud import build_process_emails_base_conditions

        await _correr(base, {"email_id": "e1"})
        condicao = build_process_emails_base_conditions("p-1")[0]
        assert not [e for e in base.emails.docs if all(e.get(k) == v for k, v in condicao.items())]

    @pytest.mark.asyncio
    async def test_aceita_o_message_id(self, base):
        await _correr(base, {"email_id": "<m1>"})
        assert next(e for e in base.emails.docs if e["id"] == "e1")["process_id"] is None

    @pytest.mark.asyncio
    async def test_sem_processo_e_idempotente(self, base):
        r = await _correr(base, {"email_id": "e2"})
        assert r["success"] is True and "já não está" in r["message"]

    @pytest.mark.asyncio
    async def test_email_inexistente_e_404_e_sem_id_e_400(self, base):
        with pytest.raises(HTTPException) as a:
            await _correr(base, {"email_id": "nao-existe"})
        with pytest.raises(HTTPException) as b:
            await _correr(base, {})
        assert (a.value.status_code, b.value.status_code) == (404, 400)

    # ---- as paredes: nada muda quando alguma recusa ---------------------------------------
    @pytest.mark.asyncio
    @pytest.mark.parametrize("kw,codigo", [
        ({"pode_ler": False}, 404), ({"processo_legivel": False}, 404), ({"aberto": False}, 403),
    ])
    async def test_recusas_nao_alteram_o_email(self, base, kw, codigo):
        with pytest.raises(HTTPException) as exc:
            await _correr(base, {"email_id": "e1"}, **kw)
        assert exc.value.status_code == codigo
        assert next(e for e in base.emails.docs if e["id"] == "e1")["process_id"] == "p-1"


class TestLigacao:
    def test_a_rota_existe_antes_de_qualquer_id_dinamico(self):
        from pathlib import Path

        import routes.emails as r
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(Path(r.__file__).read_text())
        assert "@router.post('/disassociate')" in fonte
        assert fonte.index("@router.post('/disassociate')") < fonte.index("@router.get('/{email_id}'")
