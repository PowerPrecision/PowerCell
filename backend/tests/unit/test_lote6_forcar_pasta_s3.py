"""«Forçar criação de pasta» / «Religar S3» — a válvula de quem não tem pasta (Lote 6, ponto 4).

O QUE FALTAVA
=============
`POST /documents/client/{id}/init-folders` existia e ninguém o chamava (o frontend tinha
zero referências), servia só processos — um cliente sem processo, que vive sozinho na raiz
documental, respondia 404 — e quando o S3 falhava devolvia `success: false` num 200 que um
botão engolia. Quando a pasta gravada deixava de existir, deriva-se um caminho NOVO e
sobrepunha-se o ponteiro, decidindo sozinho que a documentação mudou de sítio.

AS REGRAS QUE ESTES TESTES FIXAM
================================
1. o caminho NUNCA vem do pedido: deriva do ID ou é o que já está gravado;
2. pasta gravada que existe → nada a fazer (idempotente, não escreve);
3. pasta gravada VÁLIDA mas inexistente → recria-se a estrutura NO MESMO caminho e o
   ponteiro não se mexe;
4. ponteiro inutilizável (fora da raiz, a própria raiz, tipo errado) → substitui-se pelo
   derivado do id — um `backups/` gravado era um passe para o bucket inteiro;
5. cliente sem processo → pasta do CLIENTE, gravada em `clients`;
6. S3 em baixo, ou a criar com erro → 503 legível, e NADA gravado;
7. os testes usam o `S3Service` REAL com um cliente `boto3` falso ao nível da chamada: o que se
   afirma são os PARÂMETROS que saem (`Key`), não o resultado de um duplo que reimplementa a
   lógica.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from services.s3_document_root import RAIZ, pasta_do_cliente, pasta_do_processo
from services.s3_storage import DEFAULT_CATEGORIES, S3Service, sanitize_folder_name

pytestmark = pytest.mark.asyncio

CID = "11111111-1111-4111-8111-111111111111"
PID = "22222222-2222-4222-8222-222222222222"
UTILIZADOR = {"id": "u-1", "role": "consultor"}
LEGADA = "Documentação Clientes/Carolina_Silva"


def _s3(*, existe: bool, falha_ao_escrever: bool = False, configurado: bool = True) -> S3Service:
    servico = S3Service.__new__(S3Service)
    if not configurado:
        servico.s3_client = None
        servico.bucket_name = None
        return servico
    cliente = MagicMock()
    cliente.list_objects_v2.return_value = {"KeyCount": 1 if existe else 0}
    # `head_object` a falhar = «o marcador não existe, cria-se».
    cliente.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
    if falha_ao_escrever:
        cliente.put_object.side_effect = ClientError({"Error": {"Code": "500"}}, "PutObject")
    servico.s3_client = cliente
    servico.bucket_name = "bucket-de-teste"
    return servico


def _chaves_escritas(servico: S3Service) -> list[str]:
    return [c.kwargs["Key"] for c in servico.s3_client.put_object.call_args_list]


async def _correr(fake_async_db, servico, id_pedido, espia=None):
    from services import document_misc as dm
    from services import document_process_resolve as dpr
    from services import s3_relink

    espia = espia or AsyncMock()
    with patch.object(dm, "db", fake_async_db), patch.object(dpr, "db", fake_async_db), \
            patch.object(dm, "s3_service", servico), \
            patch.object(s3_relink, "registar_na_auditoria", espia):
        return await dm.run_initialize_folders(id_pedido, user=UTILIZADOR)


async def _processo(fake_async_db, **extra):
    doc = {"id": PID, "client_id": CID, "client_name": "Carolina Agostinho da Silva"}
    doc.update(extra)
    await fake_async_db.processes.insert_one(doc)
    await fake_async_db.clients.insert_one({"id": CID, "nome": doc["client_name"]})


class TestProcessoSemPasta:
    async def test_deriva_do_ID_cria_a_estrutura_e_grava_o_ponteiro(self, fake_async_db):
        await _processo(fake_async_db)
        servico = _s3(existe=False)
        espia = AsyncMock()

        r = await _correr(fake_async_db, servico, PID, espia)

        esperada = pasta_do_processo(PID, CID)
        assert r["success"] is True and r["created"] is True and r["recreated"] is False
        assert r["s3_folder"] == esperada and r["entidade"] == "processo"
        chaves = _chaves_escritas(servico)
        assert chaves and all(k.startswith(esperada + "/") and k.endswith("/.keep") for k in chaves)
        # Uma chave por categoria standard (o nome vem do mesmo sanitizador da produção).
        assert {k.split("/")[-2] for k in chaves} == {sanitize_folder_name(c) for c in DEFAULT_CATEGORIES}
        gravado = await fake_async_db.processes.find_one({"id": PID})
        assert gravado["s3_folder"] == esperada
        espia.assert_awaited_once()

    async def test_o_cliente_pode_ser_o_id_pedido(self, fake_async_db):
        """O ecrã do cliente passa o id do CLIENTE; resolve-se para o processo dele."""
        await _processo(fake_async_db)
        await fake_async_db.clients.update_one({"id": CID}, {"$set": {"process_ids": [PID]}})
        r = await _correr(fake_async_db, _s3(existe=False), CID)
        assert r["entidade"] == "processo" and r["s3_folder"] == pasta_do_processo(PID, CID)


class TestIdempotencia:
    async def test_pasta_que_existe_nao_escreve_nada(self, fake_async_db):
        gravada = pasta_do_processo(PID, CID)
        await _processo(fake_async_db, s3_folder=gravada)
        servico = _s3(existe=True)
        espia = AsyncMock()

        r = await _correr(fake_async_db, servico, PID, espia)

        assert r["already_exists"] is True and r["created"] is False and r["s3_folder"] == gravada
        servico.s3_client.put_object.assert_not_called()
        espia.assert_not_awaited()
        assert (await fake_async_db.processes.find_one({"id": PID}))["s3_folder"] == gravada


class TestPastaGravadaQueJaNaoExiste:
    async def test_recria_NO_MESMO_caminho_e_nao_mexe_no_ponteiro(self, fake_async_db):
        """Mover o ponteiro seria decidir sozinho que a documentação mudou de sítio."""
        await _processo(fake_async_db, s3_folder=LEGADA)
        servico = _s3(existe=False)
        espia = AsyncMock()

        r = await _correr(fake_async_db, servico, PID, espia)

        assert r["recreated"] is True and r["created"] is False and r["s3_folder"] == LEGADA
        chaves = _chaves_escritas(servico)
        assert chaves and all(k.startswith(LEGADA + "/") for k in chaves)
        assert (await fake_async_db.processes.find_one({"id": PID}))["s3_folder"] == LEGADA
        espia.assert_not_awaited()


class TestPonteiroInutilizavel:
    @pytest.mark.parametrize("veneno", [
        "backups/dump-2026-09-01.zip",
        "companies/logos",
        RAIZ,
        RAIZ.rstrip("/"),
    ])
    async def test_fora_da_raiz_ou_a_propria_raiz_substitui_se_pelo_derivado(self, fake_async_db, veneno):
        await _processo(fake_async_db, s3_folder=veneno)
        servico = _s3(existe=True)  # mesmo «existindo» no bucket, não se reaproveita

        r = await _correr(fake_async_db, servico, PID)

        esperada = pasta_do_processo(PID, CID)
        assert r["created"] is True and r["s3_folder"] == esperada
        assert all(k.startswith(esperada + "/") for k in _chaves_escritas(servico))
        assert (await fake_async_db.processes.find_one({"id": PID}))["s3_folder"] == esperada

    async def test_s3_folder_gravado_como_lista_nao_rebenta_e_deriva_do_id(self, fake_async_db):
        await _processo(fake_async_db, s3_folder=[True, LEGADA])

        r = await _correr(fake_async_db, _s3(existe=False), PID)

        assert r["s3_folder"] == pasta_do_processo(PID, CID)
        gravado = await fake_async_db.processes.find_one({"id": PID})
        assert gravado["s3_folder"] == r["s3_folder"] and isinstance(gravado["s3_folder"], str)


class TestClienteSemProcesso:
    async def test_cria_a_pasta_do_CLIENTE_e_grava_em_clients(self, fake_async_db):
        await fake_async_db.clients.insert_one({"id": CID, "nome": "Ana Pool"})
        servico = _s3(existe=False)

        r = await _correr(fake_async_db, servico, CID)

        assert r["entidade"] == "cliente" and r["created"] is True
        assert r["s3_folder"] == pasta_do_cliente(CID)
        assert all(k.startswith(pasta_do_cliente(CID) + "/") for k in _chaves_escritas(servico))
        assert (await fake_async_db.clients.find_one({"id": CID}))["s3_folder"] == pasta_do_cliente(CID)

    async def test_cliente_inexistente_e_404(self, fake_async_db):
        with pytest.raises(HTTPException) as e:
            await _correr(fake_async_db, _s3(existe=False), "nao-existe")
        assert e.value.status_code == 404


class TestQuandoOS3Falha:
    async def test_s3_nao_configurado_e_503_e_nada_se_grava(self, fake_async_db):
        await _processo(fake_async_db)
        with pytest.raises(HTTPException) as e:
            await _correr(fake_async_db, _s3(existe=False, configurado=False), PID)
        assert e.value.status_code == 503
        assert "s3_folder" not in (await fake_async_db.processes.find_one({"id": PID}))

    async def test_erro_ao_escrever_e_503_e_nada_se_grava(self, fake_async_db):
        await _processo(fake_async_db)
        servico = _s3(existe=False, falha_ao_escrever=True)
        espia = AsyncMock()
        with pytest.raises(HTTPException) as e:
            await _correr(fake_async_db, servico, PID, espia)
        assert e.value.status_code == 503
        assert "s3_folder" not in (await fake_async_db.processes.find_one({"id": PID}))
        espia.assert_not_awaited()


class TestAFonte:
    def test_a_rota_passa_o_utilizador_ao_servico(self):
        """Sem o utilizador o rasto de auditoria sai sem autor."""
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
        from routes import documents

        codigo = codigo_da_funcao_sem_comentarios(documents.initialize_folders)
        assert "run_initialize_folders(client_id, user=user)" in codigo

    def test_o_servico_nao_aceita_o_caminho_do_pedido(self):
        import inspect

        from services.document_misc import run_initialize_folders

        assert set(inspect.signature(run_initialize_folders).parameters) == {"client_id", "user"}


class TestListagemDoClienteSemProcesso:
    """`base_path` a `null` é o sinal que mostra o botão; tem de ser verdadeiro e nunca esconder a saída."""

    async def _base(self, cliente, servico):
        from services import document_misc as dm

        with patch.object(dm, "s3_service", servico):
            return await dm.base_path_do_cliente_sem_processo(cliente)

    async def test_pasta_que_existe_devolve_o_caminho(self):
        pasta = pasta_do_cliente(CID)
        assert await self._base({"id": CID, "s3_folder": pasta}, _s3(existe=True)) == pasta

    async def test_pasta_gravada_que_nao_existe_no_s3_devolve_none(self):
        assert await self._base({"id": CID, "s3_folder": pasta_do_cliente(CID)}, _s3(existe=False)) is None

    async def test_sem_ponteiro_devolve_none(self):
        assert await self._base({"id": CID}, _s3(existe=True)) is None

    async def test_ponteiro_do_tipo_errado_devolve_none_sem_rebentar(self):
        assert await self._base({"id": CID, "s3_folder": [True, LEGADA]}, _s3(existe=True)) is None

    async def test_falha_do_s3_devolve_none_e_o_botao_aparece(self):
        servico = _s3(existe=True)
        servico.s3_client.list_objects_v2.side_effect = RuntimeError("rede")
        assert await self._base({"id": CID, "s3_folder": pasta_do_cliente(CID)}, servico) is None

    def test_a_rota_devolve_o_base_path_do_cliente_sem_processo(self):
        from routes import documents
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        codigo = codigo_da_funcao_sem_comentarios(documents.list_client_files)
        assert "base_path_do_cliente_sem_processo(client)" in codigo
