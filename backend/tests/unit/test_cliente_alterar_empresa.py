"""Alterar a empresa de PROCESSOS de um cliente (só Master) — Lote 2, reescrito no Lote 6.

O que transita de uma rede para a outra quando a triagem se enganou é o PROCESSO: o cliente fica
onde está (pode ter processos em várias empresas). A acção muda o carimbo dos processos ESCOLHIDOS
(+ o que lista por esse carimbo) e NUNCA toca na ficha nem no S3: o `s3_folder` fica tal e qual. Esta é a regra que mais importa afirmar — e a que
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


def _corpo(mod, empresa="cmp-domus", password=SENHA, processos=("p-power",)):
    return mod.TransferirClienteIn(company_id=empresa, process_ids=list(processos), password=password)


def _cliente(bd, id_="c-power"):
    return next(c for c in bd.clients.docs if c["id"] == id_)


def _processo(bd, id_):
    return next(p for p in bd.processes.docs if p["id"] == id_)


@pytest.mark.asyncio
class TestATransferencia:
    async def test_muda_o_carimbo_do_processo_escolhido(self, mundo):
        bd, mod = mundo
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)

        assert resposta["transferido"] is True and resposta["processos_transferidos"] == 1
        doc = _processo(bd, "p-power")
        assert (doc["company_id"], doc["company_name"], doc["network_id"]) == ("cmp-domus", "Domus", REDE_DOMUS)

    async def test_a_ficha_do_cliente_fica_exactamente_como_estava(self, mundo):
        """A regra do Lote 6: o cliente pode pertencer a várias empresas — só o processo transita."""
        bd, mod = mundo
        antes = dict(_cliente(bd))
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert _cliente(bd) == antes
        assert _cliente(bd)["network_id"] == REDE_INCUMBENTE

    async def test_so_move_os_processos_escolhidos(self, mundo):
        bd, mod = mundo
        bd.processes.docs.append({
            "id": "p-power-2", "client_id": "c-power", "company_id": "cmp-power",
            "company_name": "Power Real Estate", "network_id": REDE_INCUMBENTE,
        })
        _cliente(bd)["process_ids"] = ["p-power", "p-power-2"]
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert _processo(bd, "p-power")["network_id"] == REDE_DOMUS
        ficou = _processo(bd, "p-power-2")
        assert (ficou["company_id"], ficou["network_id"]) == ("cmp-power", REDE_INCUMBENTE)

    async def test_a_exploracao_o_s3_folder_fica_exactamente_como_estava(self, mundo):
        bd, mod = mundo
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert _cliente(bd)["s3_folder"] == S3_PASTA
        assert _processo(bd, "p-power")["s3_folder"] == S3_PASTA

    async def test_o_campo_legado_company_acompanha_o_nome_no_processo(self, mundo):
        bd, mod = mundo
        _processo(bd, "p-power")["company"] = "Power Real Estate"
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert _processo(bd, "p-power")["company"] == "Domus"  # senão continuaria visível à empresa antiga pelo nome

    async def test_tarefas_prazos_e_visitas_do_processo_acompanham(self, mundo):
        bd, mod = mundo
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        for colecao in ("tasks", "deadlines", "visits"):
            movido = next(d for d in getattr(bd, colecao).docs if d["id"] == f"{colecao}-1")
            intacto = next(d for d in getattr(bd, colecao).docs if d["id"] == f"{colecao}-2")
            assert movido["network_id"] == REDE_DOMUS and movido["company_id"] == "cmp-domus"
            assert intacto["network_id"] == REDE_DOMUS  # o de outro processo não foi tocado
            assert intacto["company_id"] == "cmp-domus"

    async def test_um_processo_que_nao_e_do_cliente_recusa_o_pedido_inteiro(self, mundo):
        """O processo em que é só 2.º titular NÃO é dele: pedir para o mover é um erro, não um favor."""
        bd, mod = mundo
        with pytest.raises(HTTPException) as erro:
            await mod.run_transfer_client_company(
                "c-power", _corpo(mod, empresa="cmp-precision", processos=("p-power", "p-de-outro")), MASTER,
            )
        assert erro.value.status_code == 400
        outro = _processo(bd, "p-de-outro")
        assert (outro["company_id"], outro["network_id"]) == ("cmp-domus", REDE_DOMUS)
        # E nada foi movido: o pedido é tudo-ou-nada.
        assert _processo(bd, "p-power")["network_id"] == REDE_INCUMBENTE

    async def test_um_processo_eliminado_nao_se_move(self, mundo):
        bd, mod = mundo
        _processo(bd, "p-power")["is_deleted"] = True
        with pytest.raises(HTTPException) as erro:
            await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert erro.value.status_code == 400

    async def test_deixa_rasto_de_auditoria_sem_a_password(self, mundo):
        bd, mod = mundo
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        (rasto,) = [a for a in bd.audit_logs.docs if a["action"] == "process_company_transferred"]
        assert rasto["entity_id"] == "c-power"
        assert rasto["details"]["de"]["p-power"]["company_name"] == "Power Real Estate"
        assert rasto["details"]["para"]["company_name"] == "Domus"
        assert rasto["details"]["processos"] == ["p-power"]
        assert rasto["details"]["ficha_do_cliente"] == "inalterada"
        assert SENHA not in repr(rasto)

    async def test_um_processo_que_ja_esta_no_destino_nao_escreve_nada(self, mundo):
        bd, mod = mundo
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod, empresa="cmp-power"), MASTER)
        assert resposta["transferido"] is False
        assert [p["id"] for p in resposta["processos_ja_no_destino"]] == ["p-power"]
        assert not [a for a in bd.audit_logs.docs if a["action"] == "process_company_transferred"]


@pytest.mark.asyncio
class TestRecusas:
    async def test_sem_password_e_400_e_nada_muda(self, mundo):
        bd, mod = mundo
        with pytest.raises(HTTPException) as erro:
            await mod.run_transfer_client_company("c-power", _corpo(mod, password=None), MASTER)
        assert erro.value.status_code == 400
        assert _processo(bd, "p-power")["network_id"] == REDE_INCUMBENTE

    async def test_password_errada_e_403_nunca_401_e_nada_muda(self, mundo):
        bd, mod = mundo
        with pytest.raises(HTTPException) as erro:
            await mod.run_transfer_client_company("c-power", _corpo(mod, password="errada"), MASTER)
        assert erro.value.status_code == 403
        assert _processo(bd, "p-power")["network_id"] == REDE_INCUMBENTE
        assert not [a for a in bd.audit_logs.docs if a["action"] == "process_company_transferred"]

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
        assert _processo(bd, "p-power")["company_id"] == "cmp-power"

    async def test_o_corpo_exige_pelo_menos_um_processo(self, mundo):
        """«O cliente todo» já não é uma opção: sem processos escolhidos o corpo nem é válido."""
        _, mod = mundo
        with pytest.raises(Exception):
            mod.TransferirClienteIn(company_id="cmp-domus", process_ids=[], password="x")
        with pytest.raises(Exception):
            mod.TransferirClienteIn(company_id="cmp-domus", password="x")

    async def test_o_corpo_nao_aceita_carimbo_escolhido_por_quem_pede(self, mundo):
        _, mod = mundo
        with pytest.raises(Exception):
            mod.TransferirClienteIn(
                company_id="cmp-domus", process_ids=["p-power"], password="x", network_id="grupo_qualquer",
            )


@pytest.mark.asyncio
class TestOPreview:
    async def test_lista_os_processos_do_cliente_sem_escrever(self, mundo):
        bd, mod = mundo
        antes = dict(_processo(bd, "p-power"))
        res = await mod.run_preview_transfer_client_company("c-power", None, MASTER)
        assert [p["id"] for p in res["processos"]] == ["p-power"]
        assert _processo(bd, "p-power") == antes

    async def test_com_destino_diz_quais_ja_la_estao(self, mundo):
        _, mod = mundo
        res = await mod.run_preview_transfer_client_company("c-power", "cmp-power", MASTER)
        assert res["processos"][0]["ja_no_destino"] is True
        res = await mod.run_preview_transfer_client_company("c-power", "cmp-domus", MASTER)
        assert res["processos"][0]["ja_no_destino"] is False

    async def test_nao_lista_o_processo_em_que_e_so_segundo_titular_nem_os_eliminados(self, mundo):
        bd, mod = mundo
        bd.processes.docs.append({"id": "p-apagado", "client_id": "c-power", "is_deleted": True,
                                  "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"})
        res = await mod.run_preview_transfer_client_company("c-power", None, MASTER)
        assert {p["id"] for p in res["processos"]} == {"p-power"}


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

    def test_o_servico_nunca_escreve_na_colecao_de_clientes(self):
        """O cliente fica onde está: nenhum `db.clients.update_*` neste módulo."""
        import inspect

        from services import client_company_transfer
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(inspect.getsource(client_company_transfer))
        assert "db.clients.update" not in fonte
        assert "db.clients.delete" not in fonte
