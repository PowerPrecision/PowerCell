"""Gestão avançada de parceiros contra um MongoDB REAL.

O duplo in-memory não prova o que aqui importa: o índice ÚNICO do email com dois parceiros eliminados
(o marcador tem de ser único por parceiro), o `$unset` pontuado (`terms.ip`) e o filtro `$ne` do estado.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from services import db_indexes
from services.auth import hash_password

SENHA = "Segredo-Master-9!"
MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "Master", "email": "m@x.pt"}


@pytest_asyncio.fixture
async def bd():
    import services.admin_users_scope as aus
    import services.audit_trail_service as audit
    import services.partner_accounts as acc
    import services.partner_accounts_admin as adm
    import services.partner_security as sec
    import services.reauth_password as reauth
    import services.tenant_network as tn

    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_pa_{uuid.uuid4().hex[:8]}"]
    resultados = {"created": [], "errors": [], "skipped": []}
    for idx in db_indexes.INDEX_DEFINITIONS["partners"]:
        await db_indexes._create_index_safe(base.partners, idx, "partners", resultados)
    assert resultados["errors"] == []
    await base.users.insert_one({"id": "u-master", "email": "m@x.pt", "password": hash_password(SENHA)})
    await base.companies.insert_many([
        {"id": "cmp-a", "name": "Empresa A", "network_id": "rede_a"},
        {"id": "cmp-b", "name": "Empresa B", "network_id": "rede_b"},
    ])
    with patch.object(acc, "db", base), patch.object(adm, "db", base), patch.object(sec, "db", base), \
            patch.object(reauth, "db", base), patch.object(audit, "db", base), patch.object(tn, "db", base), \
            patch.object(aus, "db", base):
        yield base
    await cliente.drop_database(base.name)
    cliente.close()


async def _parceiro(bd, nome, email, rede="rede_a", empresa="cmp-a"):
    import services.partner_accounts as acc
    from services.partner_security import hash_de_token

    pid = str(uuid.uuid4())
    agora = datetime.now(timezone.utc)
    doc = acc.novo_documento_de_parceiro(
        partner_id=pid, name=nome, email=email, phone="912345678",
        ligacao={"network_id": rede, "company_id": empresa, "company_name": empresa, "status": "active"},
        token_hash=hash_de_token("t-" + pid), agora=agora, convidado_pela_rede=rede,
    )
    doc.update({"status": "active", "password_hash": hash_password("Antiga#2026x"),
                "terms": {"version": "v", "accepted_at": agora.isoformat(), "ip": "10.0.0.1"}})
    await bd.partners.insert_one(dict(doc))
    await bd.users.insert_one({"id": pid, "name": nome, "email": email, "role": "parceiro", "is_active": True})
    return pid


@pytest.mark.asyncio
async def test_dois_parceiros_eliminados_nao_chocam_no_indice_unico_do_email(bd):
    import services.partner_accounts_admin as adm

    a = await _parceiro(bd, "Ana", "ana@p.pt")
    b = await _parceiro(bd, "Bia", "bia@p.pt")
    await adm.run_delete_partner(a, SENHA, MASTER)
    await adm.run_delete_partner(b, SENHA, MASTER)
    emails = {d["email"] for d in await bd.partners.find({"status": "deleted"}).to_list(10)}
    assert emails == {adm.email_marcador(a), adm.email_marcador(b)}
    # e o endereço real fica livre — o índice único aceita um parceiro novo com ele
    await _parceiro(bd, "Ana Nova", "ana@p.pt")


@pytest.mark.asyncio
async def test_o_unset_pontuado_tira_o_ip_dos_termos_e_so_ele(bd):
    import services.partner_accounts_admin as adm

    a = await _parceiro(bd, "Ana", "ana@p.pt")
    await adm.run_delete_partner(a, SENHA, MASTER)
    doc = await bd.partners.find_one({"id": a}, {"_id": 0})
    assert doc["terms"] == {"version": "v", "accepted_at": doc["terms"]["accepted_at"]}
    assert "password_hash" not in doc and "invite" not in doc
    assert doc["token_epoch"] == 1 and doc["status"] == "deleted" and doc["name"] == "Ana"


@pytest.mark.asyncio
async def test_a_lista_e_as_opcoes_excluem_os_eliminados(bd):
    import services.partner_accounts as acc
    import services.partner_accounts_admin as adm

    a = await _parceiro(bd, "Ana", "ana@p.pt")
    b = await _parceiro(bd, "Bia", "bia@p.pt")
    await adm.run_delete_partner(a, SENHA, MASTER)
    assert [p["id"] for p in (await acc.run_list_partners(MASTER))["partners"]] == [b]
    assert [p["id"] for p in (await acc.run_list_partner_options(MASTER))["partners"]] == [b]


@pytest.mark.asyncio
async def test_email_duplicado_e_recusado_e_o_proprio_nao(bd):
    import services.partner_accounts as acc

    a = await _parceiro(bd, "Ana", "ana@p.pt")
    await _parceiro(bd, "Bia", "bia@p.pt")
    with pytest.raises(HTTPException) as erro:
        await acc.run_update_partner(a, acc.PartnerUpdate(email="bia@p.pt"), MASTER)
    assert erro.value.status_code == 409
    r = await acc.run_update_partner(a, acc.PartnerUpdate(email="ana2@p.pt"), MASTER)
    assert r["email"] == "ana2@p.pt"
    assert (await bd.users.find_one({"id": a}))["email"] == "ana2@p.pt"


@pytest.mark.asyncio
async def test_mudar_de_empresa_grava_a_ligacao_nova_e_o_directorio(bd):
    import services.partner_accounts_admin as adm

    a = await _parceiro(bd, "Ana", "ana@p.pt")
    r = await adm.run_change_company(a, adm.PartnerChangeCompany(company_id="cmp-b"), MASTER)
    assert r["alterado"] is True
    doc = await bd.partners.find_one({"id": a}, {"_id": 0})
    assert [(x["company_id"], x["network_id"]) for x in doc["redes"]] == [("cmp-b", "rede_b")]
    assert doc["convidado_pela_rede"] == "rede_b"
    assert (await bd.users.find_one({"id": a}))["criado_pela_rede"] == "rede_b"
