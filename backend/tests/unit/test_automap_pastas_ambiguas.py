"""O botão de mapeamento automático escolhia um cliente à sorte (Lote 6).

`run_auto_map_client_s3_folders` resolvia pasta → processo com um
`find_one` sobre `{"client_name": {"$regex": f"{primeiro}.*{último}"}}` e
ficava com o PRIMEIRO documento devolvido, sem verificar unicidade. A
pasta `Carolina_Silva` casa com "Carolina Silva" e com "Carolina
Agostinho da Silva": qual delas ficava com a pasta dependia da ordem de
varrimento do Mongo — e o resultado era gravado em `s3_folder`.

A diferença que estes testes fixam: **"não encontrei" é trabalho
pendente; "encontrei dois" é um cruzamento de dados à espera de
acontecer**, e nenhum automatismo o resolve.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _s3_com_pastas(*nomes):
    fake = MagicMock()
    fake.is_configured.return_value = True
    fake.bucket_name = "b"
    fake.s3_client.list_objects_v2.return_value = {
        "CommonPrefixes": [
            {"Prefix": f"Documentação Clientes/{n}/"} for n in nomes
        ]
    }
    return fake


class TestAPastaAmbiguaNaoEMapeada:
    """A pasta cujo nome não é o de ninguém, mas se parece com dois.

    `Carolina_da_Silva` não casa exactamente com nenhuma ficha; a tentativa
    larga (primeiro nome + último nome) casa com "Carolina Silva" **e** com
    "Carolina Agostinho da Silva". Era aqui que o `find_one` escolhia uma.
    """

    async def test_duas_clientes_de_nome_parecido_nao_recebem_a_pasta(
        self, fake_async_db
    ):
        from services import admin_s3_client_mappings as mod

        await fake_async_db.processes.insert_one(
            {"id": "p-curto", "client_name": "Carolina Silva"}
        )
        await fake_async_db.processes.insert_one(
            {"id": "p-longo", "client_name": "Carolina Agostinho da Silva"}
        )

        with patch.object(mod, "db", fake_async_db), patch(
            "services.s3_storage.s3_service", _s3_com_pastas("Carolina_da_Silva")
        ):
            r = await mod.run_auto_map_client_s3_folders({"id": "admin"})

        assert r["mapped"] == 0
        assert len(r["ambiguas"]) == 1
        assert set(r["ambiguas"][0]["processos"]) == {"p-curto", "p-longo"}

        # E nenhuma das duas fichas foi tocada.
        for pid in ("p-curto", "p-longo"):
            doc = await fake_async_db.processes.find_one({"id": pid})
            assert doc.get("s3_folder") is None

    async def test_o_relatorio_diz_QUEM_ficou_ambiguo(self, fake_async_db):
        from services import admin_s3_client_mappings as mod

        await fake_async_db.processes.insert_one({"id": "p1", "client_name": "Ana Costa"})
        await fake_async_db.processes.insert_one(
            {"id": "p2", "client_name": "Ana Maria Costa"}
        )

        with patch.object(mod, "db", fake_async_db), patch(
            "services.s3_storage.s3_service", _s3_com_pastas("Ana_Lucia_Costa")
        ):
            r = await mod.run_auto_map_client_s3_folders({"id": "admin"})

        # Sem nomes no relatório, o administrador não sabe o que decidir.
        assert r["ambiguas"][0]["nomes"]
        assert all(r["ambiguas"][0]["nomes"])


class TestOQueCONTINUAAFuncionar:
    """Contraprova: recusar o ambíguo não pode recusar o inequívoco."""

    async def test_um_so_candidato_e_mapeado(self, fake_async_db):
        from services import admin_s3_client_mappings as mod

        await fake_async_db.processes.insert_one(
            {"id": "p1", "client_name": "Rui Pereira"}
        )

        with patch.object(mod, "db", fake_async_db), patch(
            "services.s3_storage.s3_service", _s3_com_pastas("Rui_Pereira")
        ):
            r = await mod.run_auto_map_client_s3_folders({"id": "admin"})

        assert r["mapped"] == 1
        assert r["ambiguas"] == []
        doc = await fake_async_db.processes.find_one({"id": "p1"})
        assert doc["s3_folder"] == "Documentação Clientes/Rui_Pereira"

    async def test_o_nome_EXACTO_ganha_ao_padrao_largo(self, fake_async_db):
        """A pasta `Ana_Costa` é EXACTAMENTE o nome de um processo.

        Sem a ordem das tentativas, o padrão largo `^Ana.*Costa$` também
        casaria com "Ana Maria Costa" e o caso certo seria recusado como
        ambíguo — recusar demasiado também é um defeito.
        """
        from services import admin_s3_client_mappings as mod

        await fake_async_db.processes.insert_one({"id": "p1", "client_name": "Ana Costa"})
        await fake_async_db.processes.insert_one(
            {"id": "p2", "client_name": "Ana Maria Costa"}
        )

        with patch.object(mod, "db", fake_async_db), patch(
            "services.s3_storage.s3_service", _s3_com_pastas("Ana_Costa")
        ):
            r = await mod.run_auto_map_client_s3_folders({"id": "admin"})

        assert r["mapped"] == 1
        doc = await fake_async_db.processes.find_one({"id": "p1"})
        assert doc["s3_folder"] == "Documentação Clientes/Ana_Costa"

    async def test_mapeamento_existente_nunca_e_sobrescrito(self, fake_async_db):
        from services import admin_s3_client_mappings as mod

        await fake_async_db.processes.insert_one(
            {
                "id": "p1",
                "client_name": "Rui Pereira",
                "s3_folder": "Documentação Clientes/pasta-escolhida-a-mao",
            }
        )

        with patch.object(mod, "db", fake_async_db), patch(
            "services.s3_storage.s3_service", _s3_com_pastas("Rui_Pereira")
        ):
            r = await mod.run_auto_map_client_s3_folders({"id": "admin"})

        assert r["mapped"] == 0
        doc = await fake_async_db.processes.find_one({"id": "p1"})
        assert doc["s3_folder"] == "Documentação Clientes/pasta-escolhida-a-mao"


class TestONomeDaPastaNaoEUmaExpressaoRegular:
    async def test_metacaracteres_no_nome_da_pasta_nao_rebentam(self, fake_async_db):
        """As pastas antigas foram criadas à mão no Explorador.

        Um `(` ou `+` no nome ia cru para o `$regex`: a consulta casava com
        outra coisa ou levantava. Hoje vai escapado.
        """
        from services import admin_s3_client_mappings as mod

        await fake_async_db.processes.insert_one(
            {"id": "p1", "client_name": "Maria (Casa Nova)"}
        )

        with patch.object(mod, "db", fake_async_db), patch(
            "services.s3_storage.s3_service", _s3_com_pastas("Maria (Casa Nova)")
        ):
            r = await mod.run_auto_map_client_s3_folders({"id": "admin"})

        assert r["errors"] == []
        assert r["mapped"] == 1


class TestUmUuidNaoEUmNome:
    """Os reparadores de nome extraíam o nome DA PASTA (Lote 6).

    Com a pasta a derivar do ID, o primeiro segmento é um uuid — e gravá-lo
    como `client_name` punha-o depois em emails, PDFs e documentos RGPD. As
    outras fontes (email, `personal_data`) são melhores do que uma pasta, e é
    para lá que o caso tem de cair.
    """

    async def test_o_reparador_de_nomes_nao_grava_o_id(self, fake_async_db):
        from services import admin_s3_process_mappings as mod
        from services.s3_document_root import pasta_do_cliente

        cid = "11111111-1111-4111-8111-111111111111"
        await fake_async_db.processes.insert_one({
            "id": "p1",
            "client_name": "Sem nome",
            "s3_folder": pasta_do_cliente(cid),
            "client_email": "rui.pereira@exemplo.pt",
        })

        with patch.object(mod, "db", fake_async_db):
            await mod.run_fix_missing_client_names({"id": "admin"})

        doc = await fake_async_db.processes.find_one({"id": "p1"})
        assert cid not in doc["client_name"]
        # Contraprova: caiu na fonte seguinte, não ficou sem nome.
        assert doc["client_name"] == "Rui Pereira"

    async def test_a_pasta_LEGADA_continua_a_dar_o_nome(self, fake_async_db):
        from services import admin_s3_process_mappings as mod

        await fake_async_db.processes.insert_one({
            "id": "p2",
            "client_name": "",
            "s3_folder": "Documentação Clientes/Rui_Pereira",
        })

        with patch.object(mod, "db", fake_async_db):
            await mod.run_fix_missing_client_names({"id": "admin"})

        doc = await fake_async_db.processes.find_one({"id": "p2"})
        assert doc["client_name"] == "Rui Pereira"
