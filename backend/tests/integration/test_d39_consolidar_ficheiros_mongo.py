"""D-39 contra um MongoDB REAL: os ficheiros da lead passam para a pasta definitiva do cliente.

O S3 é um cliente `boto3` falso AO NÍVEL DA CHAMADA (guarda objectos em memória e responde a
`head_object` / `copy_object` / `delete_object` como o S3), com o `S3Service` REAL por cima — as
primitivas de chave exacta são as de produção. O que se prova:

* os objectos mudam de pasta, o `s3_path` (topo e `attached_files`) e o `document_metadata`
  acompanham-nos, e a origem só é apagada DEPOIS de a base de dados apontar para o destino;
* nunca se sobrescreve: um nome ocupado ganha ` (2)`; o mesmo conteúdo (retoma) reaproveita-se;
* uma falha a meio deixa o estado pendente e a segunda passagem retoma sem duplicar;
* nada fora da pasta de origem se move; o destino nunca sai da raiz documental;
* a cópia que não bate (tamanho) apaga-se e a origem fica intacta.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from botocore.exceptions import ClientError
from motor.motor_asyncio import AsyncIOMotorClient

LEAD = "11111111-1111-4111-8111-111111111111"
CLIENTE = "22222222-2222-4222-8222-222222222222"
ORIGEM = f"Documentação Clientes/{LEAD}"
DESTINO = f"Documentação Clientes/{CLIENTE}"
AGORA = "2026-10-23T10:00:00+00:00"


class S3EmMemoria:
    """Um cliente boto3 mínimo: o S3 responde pelas chamadas, não pela lógica do código testado."""

    def __init__(self):
        self.objectos: dict[str, bytes] = {}
        self.chamadas: list[tuple[str, dict]] = []
        self.falha_copia_em: set[str] = set()
        self.copia_truncada = False
        self.falha_delete = False
        self.falha_head_em: set[str] = set()

    def _404(self, op):
        return ClientError({"Error": {"Code": "404", "Message": "x"}}, op)

    def head_object(self, **kw):
        self.chamadas.append(("head", kw))
        if kw["Key"] in self.falha_head_em:
            raise ClientError({"Error": {"Code": "500", "Message": "x"}}, "HeadObject")
        if kw["Key"] not in self.objectos:
            raise self._404("HeadObject")
        corpo = self.objectos[kw["Key"]]
        return {"ContentLength": len(corpo), "ContentType": "application/pdf", "ETag": f'"{hash(corpo) & 0xffffffff:x}"'}

    def copy_object(self, **kw):
        self.chamadas.append(("copy", kw))
        origem = kw["CopySource"]["Key"]
        if origem not in self.objectos:
            raise self._404("CopyObject")
        if origem in self.falha_copia_em:
            raise ClientError({"Error": {"Code": "500", "Message": "x"}}, "CopyObject")
        corpo = self.objectos[origem]
        self.objectos[kw["Key"]] = corpo[:-1] if self.copia_truncada else corpo

    def delete_object(self, **kw):
        self.chamadas.append(("delete", kw))
        if self.falha_delete:
            raise ClientError({"Error": {"Code": "500", "Message": "x"}}, "DeleteObject")
        self.objectos.pop(kw["Key"], None)


@pytest_asyncio.fixture
async def ambiente():
    from services import partner_lead_files as modulo
    from services.s3_storage import s3_service

    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_d39_{uuid.uuid4().hex[:8]}"]
    s3 = S3EmMemoria()
    with patch.object(modulo, "db", base), patch.object(s3_service, "s3_client", s3), \
            patch.object(s3_service, "bucket_name", "bucket-teste"):
        yield modulo, base, s3
    await cliente.drop_database(base.name)
    cliente.close()


async def _preparar(base, s3, *, ficheiros, existente_extra=None):
    """Lead com ``ficheiros`` (``nome -> bytes``) sob a origem, registados como o Portal do Parceiro faz."""
    existente = {"id": CLIENTE, "nome": "Existente", "partner_leads": [{"lead_id": LEAD}], **(existente_extra or {})}
    await base.clients.insert_one(dict(existente))
    await base.partner_drafts.insert_one({
        "id": LEAD, "partner_stage": "associada", "matched_client_id": CLIENTE,
        "consolidacao_pendente": {"desde": AGORA},
    })
    chaves = []
    for i, (nome, corpo) in enumerate(ficheiros.items()):
        chave = f"{ORIGEM}/{nome}"
        s3.objectos[chave] = corpo
        chaves.append(chave)
        if i % 2 == 0:
            await base.documents.insert_one({"id": f"d{i}", "client_id": LEAD, "s3_path": chave})
        else:
            await base.documents.insert_one({
                "id": f"d{i}", "client_id": LEAD, "s3_path": chave,
                "attached_files": [{"file_id": f"f{i}", "s3_path": chave}, {"file_id": "outro", "s3_path": f"{ORIGEM}/Index/outro-{i}.pdf"}],
            })
            s3.objectos[f"{ORIGEM}/Index/outro-{i}.pdf"] = b"outro"
        await base.document_metadata.insert_one({"id": f"m{i}", "s3_path": chave})
    return existente, chaves


async def _chaves_dos_registos(base):
    chaves = set()
    async for doc in base.documents.find({}, {"_id": 0}):
        chaves.add(doc.get("s3_path"))
        chaves.update(a["s3_path"] for a in doc.get("attached_files") or [])
    async for meta in base.document_metadata.find({}, {"_id": 0}):
        chaves.add(meta.get("s3_path"))
    return chaves


@pytest.mark.asyncio
class TestMoverOsFicheiros:
    async def test_os_objectos_mudam_de_pasta_e_a_base_de_dados_acompanha(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/cc.pdf": b"cc", "Index/irs.pdf": b"irs"})

        relatorio = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)

        assert relatorio["movido"] == 3 and relatorio["falhou"] == 0 and relatorio["pendente"] is False
        assert not [k for k in s3.objectos if k.startswith(f"{ORIGEM}/")], "a origem ficou com objectos"
        assert {f"{DESTINO}/Index/cc.pdf", f"{DESTINO}/Index/irs.pdf", f"{DESTINO}/Index/outro-1.pdf"} <= set(s3.objectos)
        chaves = await _chaves_dos_registos(base)
        assert all(c.startswith(f"{DESTINO}/") for c in chaves), chaves
        assert all(c in s3.objectos for c in chaves), "um registo aponta para uma chave inexistente"

    async def test_attached_files_e_metadados_acompanham(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a", "Index/b.pdf": b"b"})
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)

        doc = await base.documents.find_one({"id": "d1"}, {"_id": 0})
        assert [a["s3_path"] for a in doc["attached_files"]] == [f"{DESTINO}/Index/b.pdf", f"{DESTINO}/Index/outro-1.pdf"]
        assert doc["s3_path"] == f"{DESTINO}/Index/b.pdf"
        assert doc["consolidado"]["s3_path_anterior"] in {f"{ORIGEM}/Index/b.pdf", f"{ORIGEM}/Index/outro-1.pdf"}
        meta = await base.document_metadata.find_one({"id": "m1"}, {"_id": 0})
        assert meta["s3_path"] == f"{DESTINO}/Index/b.pdf"

    async def test_o_client_id_do_registo_nao_muda(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert (await base.documents.find_one({"id": "d0"}))["client_id"] == LEAD

    async def test_a_origem_so_e_apagada_depois_de_a_base_de_dados_apontar_para_o_destino(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        visto = []
        apagar = s3.delete_object

        async def _ler():
            return await base.documents.find_one({"id": "d0"}, {"_id": 0})

        def delete_espiado(**kw):
            if kw["Key"] == f"{ORIGEM}/Index/a.pdf":
                # No momento exacto do delete, o registo já tem de apontar para o destino.
                visto.append(asyncio.run_coroutine_threadsafe(_ler(), self_loop).result(timeout=5))
            return apagar(**kw)

        self_loop = asyncio.get_running_loop()
        s3.delete_object = delete_espiado
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert visto, "a origem nunca chegou a ser apagada"
        assert all(r["s3_path"] == f"{DESTINO}/Index/a.pdf" for r in visto), visto

    async def test_o_estado_pendente_sai_e_a_entrada_da_lead_aponta_para_o_destino(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert "consolidacao_pendente" not in await base.partner_drafts.find_one({"id": LEAD})
        cliente = await base.clients.find_one({"id": CLIENTE})
        entrada = cliente["partner_leads"][0]
        assert entrada["pasta_dos_documentos_do_lead"] == DESTINO
        assert entrada["ficheiros_consolidados_em"] == AGORA

    async def test_cliente_sem_ponteiro_ganha_o_da_pasta_definitiva(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert (await base.clients.find_one({"id": CLIENTE}))["s3_folder"] == DESTINO

    async def test_um_ponteiro_existente_nunca_se_sobrepoe(self, ambiente):
        modulo, base, s3 = ambiente
        legado = "Documentação Clientes/Legado Ana"
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"}, existente_extra={"s3_folder": legado})
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert (await base.clients.find_one({"id": CLIENTE}))["s3_folder"] == legado
        assert f"{legado}/Index/a.pdf" in s3.objectos


@pytest.mark.asyncio
class TestNuncaSobrescreve:
    async def test_nome_ocupado_com_outro_conteudo_ganha_sufixo(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/cc.pdf": b"da-lead"})
        s3.objectos[f"{DESTINO}/Index/cc.pdf"] = b"do-cliente-existente"

        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)

        assert s3.objectos[f"{DESTINO}/Index/cc.pdf"] == b"do-cliente-existente", "sobrescreveu um ficheiro do cliente"
        assert s3.objectos[f"{DESTINO}/Index/cc (2).pdf"] == b"da-lead"
        assert (await base.documents.find_one({"id": "d0"}))["s3_path"] == f"{DESTINO}/Index/cc (2).pdf"

    async def test_nunca_se_copia_para_uma_chave_ocupada(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/cc.pdf": b"da-lead"})
        s3.objectos[f"{DESTINO}/Index/cc.pdf"] = b"do-cliente-existente"
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        destinos = [c["Key"] for op, c in s3.chamadas if op == "copy"]
        assert f"{DESTINO}/Index/cc.pdf" not in destinos

    async def test_o_mesmo_conteudo_ja_no_destino_reaproveita_se(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/cc.pdf": b"igual"})
        s3.objectos[f"{DESTINO}/Index/cc.pdf"] = b"igual"
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert not [c for op, c in s3.chamadas if op == "copy"], "copiou um conteúdo que já lá estava"
        assert (await base.documents.find_one({"id": "d0"}))["s3_path"] == f"{DESTINO}/Index/cc.pdf"
        assert f"{ORIGEM}/Index/cc.pdf" not in s3.objectos


@pytest.mark.asyncio
class TestFalhasERetoma:
    async def test_falha_de_copia_deixa_a_origem_intacta_e_o_estado_pendente(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a", "Index/b.pdf": b"b"})
        s3.falha_copia_em = {f"{ORIGEM}/Index/a.pdf"}

        relatorio = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)

        assert relatorio["falhou"] == 1 and relatorio["pendente"] is True
        assert f"{ORIGEM}/Index/a.pdf" in s3.objectos
        assert (await base.documents.find_one({"id": "d0"}))["s3_path"] == f"{ORIGEM}/Index/a.pdf"
        pendente = (await base.partner_drafts.find_one({"id": LEAD}))["consolidacao_pendente"]
        assert pendente["ficheiros"] == 1

    async def test_a_segunda_passagem_retoma_sem_duplicar(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a", "Index/b.pdf": b"b"})
        s3.falha_copia_em = {f"{ORIGEM}/Index/a.pdf"}
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        s3.falha_copia_em = set()

        segunda = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)

        assert segunda["pendente"] is False
        assert f"{DESTINO}/Index/a.pdf" in s3.objectos and f"{DESTINO}/Index/b.pdf" in s3.objectos
        assert not [k for k in s3.objectos if "(2)" in k], "a retoma duplicou ficheiros"
        assert "consolidacao_pendente" not in await base.partner_drafts.find_one({"id": LEAD})

    async def test_origem_que_nao_se_apagou_nao_e_uma_falha(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        s3.falha_delete = True
        primeira = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert primeira["movido"] == 1
        assert (await base.documents.find_one({"id": "d0"}))["s3_path"] == f"{DESTINO}/Index/a.pdf"
        assert f"{ORIGEM}/Index/a.pdf" in s3.objectos

    async def test_copia_que_nao_bate_apaga_se_e_a_origem_fica(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"abcdef"})
        s3.copia_truncada = True
        relatorio = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert relatorio["falhou"] == 1
        assert f"{DESTINO}/Index/a.pdf" not in s3.objectos, "ficou uma cópia truncada"
        assert s3.objectos[f"{ORIGEM}/Index/a.pdf"] == b"abcdef"
        assert (await base.documents.find_one({"id": "d0"}))["s3_path"] == f"{ORIGEM}/Index/a.pdf"

    async def test_erro_transitorio_a_ler_a_origem_nao_e_origem_ausente(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        s3.falha_head_em = {f"{ORIGEM}/Index/a.pdf"}
        relatorio = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert relatorio["falhou"] == 1 and relatorio["origem_ausente"] == 0
        assert relatorio["pendente"] is True

    async def test_origem_apagada_com_o_destino_la_reaponta_a_base_de_dados(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        s3.objectos[f"{DESTINO}/Index/a.pdf"] = s3.objectos.pop(f"{ORIGEM}/Index/a.pdf")
        relatorio = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert relatorio["ja_movido"] == 1
        assert (await base.documents.find_one({"id": "d0"}))["s3_path"] == f"{DESTINO}/Index/a.pdf"

    async def test_registo_partido_sem_origem_nem_destino_nao_se_inventa(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        s3.objectos.pop(f"{ORIGEM}/Index/a.pdf")
        relatorio = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert relatorio["origem_ausente"] == 1 and relatorio["falhou"] == 0
        assert (await base.documents.find_one({"id": "d0"}))["s3_path"] == f"{ORIGEM}/Index/a.pdf"


@pytest.mark.asyncio
class TestRegistoJaNoDestino:
    async def test_um_registo_que_ja_aponta_para_o_destino_conta_como_ja_movido(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        antes = len(s3.chamadas)
        segunda = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert segunda["ja_movido"] == 1 and segunda["fora_da_origem"] == 0 and segunda["movido"] == 0
        # Só as chamadas da 2.ª execução contam (as da 1.ª incluem a cópia legítima).
        assert not [c for op, c in s3.chamadas[antes:] if op == "copy"]


@pytest.mark.asyncio
class TestAParede:
    async def test_chave_fora_da_origem_nunca_se_move(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        s3.objectos["backups/dump-2026.zip"] = b"zip"
        await base.documents.insert_one({"id": "envenenado", "client_id": LEAD, "s3_path": "backups/dump-2026.zip"})
        outro = "Documentação Clientes/99999999-9999-4999-8999-999999999999/Index/x.pdf"
        s3.objectos[outro] = b"x"
        await base.documents.insert_one({"id": "alheio", "client_id": LEAD, "s3_path": outro})

        relatorio = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)

        assert relatorio["fora_da_origem"] == 2
        assert "backups/dump-2026.zip" in s3.objectos and outro in s3.objectos
        assert [c for op, c in s3.chamadas if op == "copy" and c["CopySource"]["Key"] in ("backups/dump-2026.zip", outro)] == []

    async def test_pasta_de_outra_lead_com_prefixo_de_texto_parecido_nao_entra(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        parecida = f"{ORIGEM}9/Index/z.pdf"
        s3.objectos[parecida] = b"z"
        await base.documents.insert_one({"id": "parecida", "client_id": LEAD, "s3_path": parecida})
        relatorio = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert relatorio["fora_da_origem"] == 1 and parecida in s3.objectos

    async def test_destino_fora_da_raiz_nao_move_nada(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"}, existente_extra={"s3_folder": "backups/2026"})
        relatorio = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert relatorio.get("sem_pastas") is True and relatorio["pendente"] is True
        assert f"{ORIGEM}/Index/a.pdf" in s3.objectos
        assert not [k for k in s3.objectos if k.startswith("backups/")]
        assert not [c for op, c in s3.chamadas if op == "copy"]

    async def test_lead_com_id_inutilizavel_nao_move_nada(self, ambiente):
        modulo, base, s3 = ambiente
        existente = {"id": CLIENTE}
        relatorio = await modulo.consolidar_ficheiros_da_lead("../../backups", existente, agora=AGORA)
        assert relatorio.get("sem_pastas") is True
        assert not [c for op, c in s3.chamadas if op == "copy"]

    async def test_nunca_levanta(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        with patch.object(modulo, "_registos_da_lead", side_effect=RuntimeError("bd em baixo")):
            relatorio = await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        assert relatorio["pendente"] is True


@pytest.mark.asyncio
class TestPendentes:
    async def test_consolidar_pendentes_repete_o_que_ficou_a_meio(self, ambiente):
        modulo, base, s3 = ambiente
        existente, _ = await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        s3.falha_copia_em = {f"{ORIGEM}/Index/a.pdf"}
        await modulo.consolidar_ficheiros_da_lead(LEAD, existente, agora=AGORA)
        s3.falha_copia_em = set()

        resumo = await modulo.consolidar_pendentes(agora=AGORA)

        assert resumo == {"pendentes": 1, "concluidas": 1, "ainda_pendentes": 0}
        assert f"{DESTINO}/Index/a.pdf" in s3.objectos

    async def test_simulacao_nao_escreve(self, ambiente):
        modulo, base, s3 = ambiente
        await _preparar(base, s3, ficheiros={"Index/a.pdf": b"a"})
        resumo = await modulo.consolidar_pendentes(agora=AGORA, aplicar=False)
        assert resumo["pendentes"] == 1
        assert f"{ORIGEM}/Index/a.pdf" in s3.objectos
        assert not [c for op, c in s3.chamadas if op in ("copy", "delete")]

    async def test_cliente_que_ja_nao_existe_continua_pendente(self, ambiente):
        modulo, base, s3 = ambiente
        await base.partner_drafts.insert_one({
            "id": LEAD, "matched_client_id": "sumiu", "consolidacao_pendente": {"desde": AGORA},
        })
        resumo = await modulo.consolidar_pendentes(agora=AGORA)
        assert resumo["ainda_pendentes"] == 1
