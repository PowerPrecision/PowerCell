"""Alterar a empresa de um cliente (só Master) — Lote 2, Out 2026.

Um cliente registado na empresa errada não podia ser movido. A acção muda o
carimbo (cliente + processos + o que lista por esse carimbo) e NUNCA toca no S3:
o `s3_folder` fica tal e qual. Esta é a regra que mais importa afirmar — e a que
uma limpeza futura bem-intencionada («já que se muda de empresa, move-se a
pasta») quebraria em silêncio.
"""
# O `$pull` das redes convidadas e o `update_many` das colecções do processo são provados
# contra um MongoDB real em `tests/integration/test_cliente_alterar_empresa_mongo.py`:
# o duplo em memória não implementa `$pull` com subdocumento.
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services.auth import hash_password
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

SENHA = "Segredo-Certo-9!"
MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "Master", "email": "m@p.pt"}
S3_PASTA = "Documentação Clientes/uuid-do-cliente-da-power"


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.admin_helpers as helpers
    import services.client_company_transfer as mod
    import services.reauth_password as reauth

    bd = semear(fake_async_db)
    bd.users.docs.append({"id": "u-master", "email": MASTER["email"], "password": hash_password(SENHA), "is_active": True})
    cliente = next(c for c in bd.clients.docs if c["id"] == "c-power")
    cliente.update({"process_ids": ["p-power"], "s3_folder": S3_PASTA, "company": "Power Real Estate",
                    "company_name": "Power Real Estate"})
    processo = next(p for p in bd.processes.docs if p["id"] == "p-power")
    processo.update({"client_id": "c-power", "company_name": "Power Real Estate", "s3_folder": S3_PASTA,
                     "partner_network_ids": [REDE_DOMUS, "rede_x"],
                     "partner_companies": [{"company_id": "cmp-domus", "network_id": REDE_DOMUS},
                                           {"company_id": "cmp-x", "network_id": "rede_x"}]})
    # Um processo em que o cliente é só o 2.º titular: NÃO é dele.
    bd.processes.docs.append({"id": "p-de-outro", "client_id": "c-domus", "second_client_id": "c-power",
                             "network_id": REDE_DOMUS, "company_id": "cmp-domus", "company_name": "Domus"})
    for colecao in ("tasks", "deadlines", "visits"):
        getattr(bd, colecao).docs.append({"id": f"{colecao}-1", "process_id": "p-power",
                                           "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"})
        getattr(bd, colecao).docs.append({"id": f"{colecao}-2", "process_id": "p-domus",
                                           "network_id": REDE_DOMUS, "company_id": "cmp-domus"})
    with tenant_db(bd, helpers, mod, reauth), \
            patch("services.history.db", bd):
        yield bd, mod


def _corpo(mod, empresa="cmp-domus", password=SENHA):
    return mod.TransferirClienteIn(company_id=empresa, password=password)


def _cliente(bd, id_="c-power"):
    return next(c for c in bd.clients.docs if c["id"] == id_)


def _processo(bd, id_):
    return next(p for p in bd.processes.docs if p["id"] == id_)


@pytest.mark.asyncio
class TestATransferencia:
    async def test_muda_o_carimbo_do_cliente_e_dos_processos_dele(self, mundo):
        bd, mod = mundo
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)

        assert resposta["transferido"] is True and resposta["processos_transferidos"] == 1
        for doc in (_cliente(bd), _processo(bd, "p-power")):
            assert (doc["company_id"], doc["company_name"], doc["network_id"]) == ("cmp-domus", "Domus", REDE_DOMUS)

    async def test_a_exploracao_o_s3_folder_fica_exactamente_como_estava(self, mundo):
        bd, mod = mundo
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert _cliente(bd)["s3_folder"] == S3_PASTA
        assert _processo(bd, "p-power")["s3_folder"] == S3_PASTA

    async def test_o_campo_legado_company_acompanha_o_nome(self, mundo):
        bd, mod = mundo
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert _cliente(bd)["company"] == "Domus"  # senão continuaria visível à empresa antiga pelo nome

    async def test_tarefas_prazos_e_visitas_do_processo_acompanham(self, mundo):
        bd, mod = mundo
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        for colecao in ("tasks", "deadlines", "visits"):
            movido = next(d for d in getattr(bd, colecao).docs if d["id"] == f"{colecao}-1")
            intacto = next(d for d in getattr(bd, colecao).docs if d["id"] == f"{colecao}-2")
            assert movido["network_id"] == REDE_DOMUS and movido["company_id"] == "cmp-domus"
            assert intacto["network_id"] == REDE_DOMUS  # o de outro processo não foi tocado
            assert intacto["company_id"] == "cmp-domus"

    async def test_o_processo_em_que_e_so_segundo_titular_nao_se_mexe(self, mundo):
        bd, mod = mundo
        await mod.run_transfer_client_company("c-power", _corpo(mod, empresa="cmp-precision"), MASTER)
        outro = _processo(bd, "p-de-outro")
        assert (outro["company_id"], outro["network_id"]) == ("cmp-domus", REDE_DOMUS)

    async def test_deixa_rasto_de_auditoria_sem_a_password(self, mundo):
        bd, mod = mundo
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        (rasto,) = [a for a in bd.audit_logs.docs if a["action"] == "client_company_transferred"]
        assert rasto["entity_id"] == "c-power"
        assert rasto["details"]["de"]["company_name"] == "Power Real Estate"
        assert rasto["details"]["para"]["company_name"] == "Domus"
        assert rasto["details"]["processos"] == ["p-power"]
        assert SENHA not in repr(rasto)

    async def test_o_mesmo_destino_nao_escreve_nada(self, mundo):
        bd, mod = mundo
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod, empresa="cmp-power"), MASTER)
        assert resposta["transferido"] is False
        assert not [a for a in bd.audit_logs.docs if a["action"] == "client_company_transferred"]
        # Contraprova: nem sequer pediu a password (não há nada a confirmar).
        assert (await mod.run_transfer_client_company("c-power", _corpo(mod, "cmp-power", None), MASTER))["transferido"] is False


@pytest.mark.asyncio
class TestRecusas:
    async def test_sem_password_e_400_e_nada_muda(self, mundo):
        bd, mod = mundo
        with pytest.raises(HTTPException) as erro:
            await mod.run_transfer_client_company("c-power", _corpo(mod, password=None), MASTER)
        assert erro.value.status_code == 400
        assert _cliente(bd)["network_id"] == REDE_INCUMBENTE
        assert _processo(bd, "p-power")["network_id"] == REDE_INCUMBENTE

    async def test_password_errada_e_403_nunca_401_e_nada_muda(self, mundo):
        bd, mod = mundo
        with pytest.raises(HTTPException) as erro:
            await mod.run_transfer_client_company("c-power", _corpo(mod, password="errada"), MASTER)
        assert erro.value.status_code == 403
        assert _cliente(bd)["network_id"] == REDE_INCUMBENTE
        assert not [a for a in bd.audit_logs.docs if a["action"] == "client_company_transferred"]

    async def test_cliente_inexistente_e_404(self, mundo):
        _, mod = mundo
        with pytest.raises(HTTPException) as erro:
            await mod.run_transfer_client_company("nao-existe", _corpo(mod), MASTER)
        assert erro.value.status_code == 404

    async def test_empresa_de_destino_inexistente_e_404_e_nada_muda(self, mundo):
        bd, mod = mundo
        with pytest.raises(HTTPException) as erro:
            await mod.run_transfer_client_company("c-power", _corpo(mod, empresa="cmp-fantasma"), MASTER)
        assert erro.value.status_code == 404
        assert _cliente(bd)["company_id"] == "cmp-power"

    async def test_o_corpo_nao_aceita_carimbo_escolhido_por_quem_pede(self, mundo):
        _, mod = mundo
        with pytest.raises(Exception):
            mod.TransferirClienteIn(company_id="cmp-domus", password="x", network_id="grupo_qualquer")


class TestSoOMasterEPeloServidor:
    def test_a_rota_exige_apenas_o_master(self):
        from routes.clients_company_transfer import router

        rota = next(r for r in router.routes if getattr(r, "path", "").endswith("/transfer-company"))
        guardas = [
            getattr(d.call, "allowed_roles", None) for d in rota.dependant.dependencies
        ]
        assert ["master"] in [[str(getattr(p, "value", p)) for p in g] for g in guardas if g]

    def test_o_servico_nunca_toca_no_s3(self):
        import inspect

        from services import client_company_transfer
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(inspect.getsource(client_company_transfer))
        for proibido in ("s3_service", "s3_storage", "move_file", "boto3", "s3_folder\":", "\"s3_folder\"]"):
            assert proibido not in fonte, f"«{proibido}» não pode aparecer: a transferência não mexe no S3"
