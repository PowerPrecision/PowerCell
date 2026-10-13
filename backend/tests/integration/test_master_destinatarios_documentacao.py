"""O Master acede a «Destinatários de Documentação» (QA, Out 2026).

Percorre os endpoints que o ecrã usa, com a app REAL e um Master REAL, e em todas as
formas como o ecrã os chama (sem cabeçalhos, com o perfil activo e com a empresa activa).
"""
import pytest

pytestmark = pytest.mark.asyncio

CABECALHOS_POSSIVEIS = [
    {},
    {"X-Active-Role": "master"},
    {"X-Active-Role": "__all_roles__"},
    # Master a trabalhar COMO outro perfil (o ContextSwitcher permite-o).
    {"X-Active-Role": "admin"},
    {"X-Active-Role": "ceo", "X-Company-Id": "cmp-inexistente"},
]


async def _com(client, token, extra):
    return {"Authorization": f"Bearer {token}", **extra}


@pytest.mark.parametrize("extra", CABECALHOS_POSSIVEIS)
async def test_o_master_le_os_destinatarios(client, admin_token, extra):
    r = await client.get("/emails/document-recipients", headers=await _com(client, admin_token, extra))
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("extra", CABECALHOS_POSSIVEIS)
async def test_o_master_le_a_configuracao_e_os_campos(client, admin_token, extra):
    cab = await _com(client, admin_token, extra)
    for caminho in ("/system-config", "/system-config/fields", "/system-config/companies"):
        r = await client.get(caminho, headers=cab)
        assert r.status_code == 200, f"{caminho}: {r.status_code} {r.text}"


@pytest.mark.parametrize("extra", CABECALHOS_POSSIVEIS)
async def test_o_master_grava_a_seccao(client, admin_token, extra):
    cab = await _com(client, admin_token, extra)
    atual = (await client.get("/emails/document-recipients", headers=cab)).json()
    r = await client.patch(
        "/system-config/document_recipients", headers=cab,
        json={"enabled": bool(atual.get("enabled", False))},
    )
    assert r.status_code == 200, r.text
