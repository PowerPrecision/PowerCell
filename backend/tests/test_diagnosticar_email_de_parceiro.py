"""Diagnóstico do 409 «Este email não pode ser usado para um parceiro» (só leitura)."""
from datetime import datetime, timedelta, timezone

from scripts.diagnosticar_email_de_parceiro import explicar


def _futuro(dias):
    return (datetime.now(timezone.utc) + timedelta(days=dias)).isoformat()


def test_email_livre_nao_explica_nada():
    assert explicar("a@b.pt", [], []) == []


def test_parceiro_eliminado_nao_bloqueia():
    assert explicar("a@b.pt", [{"id": "p", "status": "deleted"}], []) == []


def test_parceiro_convidado_com_convite_expirado_sugere_reenviar():
    p = {"id": "p", "name": "Ana", "status": "invited", "invite": {"token_hash": "h", "expires_at": _futuro(-1)}}
    [linha] = explicar("a@b.pt", [p], [])
    assert "EXPIRADO" in linha and "Reenviar Convite" in linha


def test_colaborador_com_o_mesmo_email():
    u = {"id": "u", "name": "Rui", "role": "consultor", "is_active": True, "password": "x"}
    [linha] = explicar("a@b.pt", [], [u])
    assert "perfil consultor" in linha and "outro endereço" in linha


def test_parceiro_antigo_sem_portal_aponta_para_adopcao():
    u = {"id": "u", "name": "Zé", "role": "parceiro", "password": None}
    [linha] = explicar("a@b.pt", [], [u])
    assert "ANTIGO" in linha and "adopt_user_id" in linha
