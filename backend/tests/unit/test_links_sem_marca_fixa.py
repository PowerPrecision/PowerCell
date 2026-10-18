"""Os links por email nunca apontam para um domínio de marca escrito no código (QA-6)."""
import pytest

from services import rgpd_service, temp_link_service
from services.frontend_url import base_do_frontend
from tests.unit.helpers_fonte import codigo_sem_comentarios


def test_a_base_pedida_vence_a_variavel_e_perde_a_barra(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://env.exemplo.pt/")
    assert base_do_frontend("https://pedido.exemplo.pt/") == "https://pedido.exemplo.pt"
    assert base_do_frontend() == "https://env.exemplo.pt"


def test_sem_nada_a_base_e_vazia_e_nunca_uma_marca(monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    assert base_do_frontend(None) == ""
    assert base_do_frontend("   ") == ""


@pytest.mark.asyncio
async def test_rgpd_sem_base_nao_envia(monkeypatch):
    monkeypatch.delenv("FRONTEND_URL", raising=False)
    enviado = await rgpd_service.send_rgpd_email(
        "alguem@exemplo.pt", "Nome", "tok", "req-1", "equipa@exemplo.pt", process_id="p1",
    )
    assert enviado is False


@pytest.mark.parametrize("modulo", [rgpd_service, temp_link_service])
def test_nenhum_dominio_de_marca_no_codigo(modulo):
    with open(modulo.__file__, encoding="utf-8") as ficheiro:
        fonte = codigo_sem_comentarios(ficheiro.read())
    for marca in ("powercell.pt", "precisioncredito.pt", "powercell.vercel.app"):
        assert marca not in fonte, f"{marca} escrito à letra em {modulo.__name__}"
