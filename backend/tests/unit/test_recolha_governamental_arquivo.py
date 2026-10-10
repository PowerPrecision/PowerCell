"""Arquivo dos documentos obtidos no Estado (Bloco 5, pontos 8 e 9)."""
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services import gov_fetch_archive as arq
from services.pdf_validation import parece_pdf

PDF = b"%PDF-1.4\n" + b"conteudo " * 60


def doc(label, filename=None, category="Financeiros", conteudo=PDF, content_type="application/pdf"):
    return SimpleNamespace(
        label=label,
        filename=filename or label.replace(" ", "_") + ".pdf",
        category=category,
        content_bytes=conteudo,
        content_type=content_type,
    )


@pytest.fixture
def ambiente(fake_async_db):
    chamadas = []

    def upload(**kw):
        chamadas.append({**kw, "thread": threading.current_thread()})
        return f"{kw['s3_folder']}/{kw['category']}/{kw['filename']}"

    with patch.object(arq, "db", fake_async_db), \
         patch.object(arq.s3_service, "upload_file", side_effect=upload) as mock_upload:
        mock_upload.chamadas = chamadas
        fake_async_db.processes.docs.append({
            "id": "p1", "client_name": "Ana Costa", "client_id": "c1",
            "s3_folder": "Documentação Clientes/c1/processos/p1",
        })
        yield SimpleNamespace(db=fake_async_db, upload=mock_upload, chamadas=chamadas)


# ── validação de PDF ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "conteudo,esperado",
    [
        (PDF, True),
        (b"\xef\xbb\xbf\n" + PDF, True),  # lixo antes do cabeçalho, dentro do 1.º KB
        (b"<html>" + b"x" * 6000, False),  # a versão antiga guardava isto como PDF
        (b"x" * 6000, False),  # nem HTML nem PDF, mas «grande»
        (b"%PDF-1.4", False),  # pequeno demais para ser um documento
        (b"", False),
        (None, False),
        (b"x" * 2000 + PDF, False),  # cabeçalho fora da janela
    ],
)
def test_parece_pdf(conteudo, esperado):
    assert parece_pdf(conteudo) is esperado


# ── arquivo ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_o_upload_nao_corre_no_event_loop(ambiente):
    await arq.arquivar_documentos("p1", [doc("Nota de Liquidação IRS")], origem="auto_financas", enviado_por="sys")
    assert ambiente.chamadas, "nenhum upload"
    assert ambiente.chamadas[0]["thread"] is not threading.main_thread()


@pytest.mark.asyncio
async def test_o_ficheiro_vai_para_a_pasta_do_processo_e_regista(ambiente):
    r = await arq.arquivar_documentos("p1", [doc("Declaração de IRS", "IRS.pdf")], origem="auto_financas", enviado_por="sys")
    assert r.total == 1 and not r.falhados
    registo = await ambiente.db.documents.find_one({"process_id": "p1"})
    assert registo["s3_path"] == "Documentação Clientes/c1/processos/p1/Financeiros/IRS.pdf"
    assert registo["status"] == "RECEIVED"
    assert registo["custom_label"] == "Declaração de IRS"
    assert registo["source"] == "auto_financas"
    assert registo["id"]


@pytest.mark.asyncio
async def test_upload_falhado_nao_cria_registo_fantasma(ambiente):
    """Antes: «a criar registo sem S3 path» — o cliente via entregue um documento sem ficheiro."""
    ambiente.upload.side_effect = lambda **kw: None
    r = await arq.arquivar_documentos("p1", [doc("Nota de Liquidação IRS")], origem="o", enviado_por="s")
    assert r.total == 0
    assert r.falhados == ["Nota de Liquidação IRS"]
    assert await ambiente.db.documents.find_one({"process_id": "p1"}) is None


@pytest.mark.asyncio
async def test_excepcao_no_upload_nao_derruba_os_restantes(ambiente):
    original = ambiente.upload.side_effect

    def mau_para_o_primeiro(**kw):
        if kw["filename"] == "A.pdf":
            raise RuntimeError("S3 em baixo")
        return original(**kw)

    ambiente.upload.side_effect = mau_para_o_primeiro
    r = await arq.arquivar_documentos(
        "p1", [doc("Declaração de IRS", "A.pdf"), doc("Nota de Liquidação IRS", "B.pdf")], origem="o", enviado_por="s"
    )
    assert [x["label"] for x in r.registados] == ["Nota de Liquidação IRS"]
    assert r.falhados == ["Declaração de IRS"]


@pytest.mark.asyncio
async def test_html_disfarcado_de_pdf_e_recusado_antes_de_ir_para_o_s3(ambiente):
    r = await arq.arquivar_documentos(
        "p1", [doc("Declaração de IRS", conteudo=b"<html>" + b"x" * 8000)], origem="o", enviado_por="s"
    )
    assert r.total == 0 and r.falhados == ["Declaração de IRS"]
    assert not ambiente.chamadas


@pytest.mark.asyncio
async def test_repetir_a_recolha_no_mesmo_dia_nao_duplica_o_registo(ambiente):
    for _ in range(2):
        await arq.arquivar_documentos("p1", [doc("Nota de Liquidação IRS", "N.pdf")], origem="o", enviado_por="s")
    registos = [d for d in ambiente.db.documents.docs if d.get("process_id") == "p1"]
    assert len(registos) == 1


@pytest.mark.asyncio
async def test_sem_pasta_mapeada_resolve_e_usa_o_mapeamento_pelo_id(ambiente):
    ambiente.db.processes.docs[0].pop("s3_folder")
    mapeamento = AsyncMock(return_value={"success": True, "s3_folder": "Documentação Clientes/c1/processos/p1"})
    with patch("services.s3_mapping_on_create.ensure_s3_mapping_for_entity", mapeamento):
        r = await arq.arquivar_documentos("p1", [doc("Declaração de IRS")], origem="o", enviado_por="s")
    assert r.total == 1
    kw = mapeamento.await_args.kwargs
    assert kw["entity_id"] == "p1" and kw["owner_client_id"] == "c1"
    assert ambiente.chamadas[0]["s3_folder"] == "Documentação Clientes/c1/processos/p1"


@pytest.mark.asyncio
async def test_s3_folder_corrompido_nao_rebenta_e_cai_no_mapeamento(ambiente):
    ambiente.db.processes.docs[0]["s3_folder"] = [True, "Documentação Clientes/x"]
    mapeamento = AsyncMock(return_value={"success": True, "s3_folder": "Documentação Clientes/c1/processos/p1"})
    with patch("services.s3_mapping_on_create.ensure_s3_mapping_for_entity", mapeamento):
        r = await arq.arquivar_documentos("p1", [doc("Declaração de IRS")], origem="o", enviado_por="s")
    assert r.total == 1


@pytest.mark.asyncio
async def test_sem_pasta_possivel_falha_tudo_sem_escrever_em_lado_nenhum(ambiente):
    ambiente.db.processes.docs[0].pop("s3_folder")
    with patch("services.s3_mapping_on_create.ensure_s3_mapping_for_entity", AsyncMock(return_value={"success": False})):
        r = await arq.arquivar_documentos("p1", [doc("Declaração de IRS"), doc("Nota de Liquidação IRS")], origem="o", enviado_por="s")
    assert r.total == 0 and len(r.falhados) == 2
    assert not ambiente.chamadas


# ── pedidos pendentes ──────────────────────────────────────────────────────

def pedido(id_, label=None, category="Financeiros", status="REQUESTED", **extra):
    return {"id": id_, "process_id": "p1", "custom_label": label, "category": category, "status": status, **extra}


@pytest.mark.parametrize(
    "rotulo,pedido_,esperado",
    [
        ("Declaração de IRS", pedido("a", "Declaração de IRS", "IRS"), True),
        ("Declaração de IRS", pedido("a", None, "IRS"), True),
        ("Nota de Liquidação IRS", pedido("a", "Nota de Liquidação", "Financeiros"), True),
        ("Nota de Liquidação IRS", pedido("a", "Declaração de IRS", "IRS"), False),
        ("Declaração de IRS", pedido("a", "Nota de Liquidação IRS", "IRS"), False),
        ("Declaração de IRS", pedido("a", "Recibos de vencimento", "Financeiros"), False),
        ("Nota de Liquidação IRS", pedido("a", "Recibos de vencimento", "Financeiros"), False),
        ("Situação Contributiva", pedido("a", "Situação contributiva", "Financeiros"), True),
        ("Situação Contributiva", pedido("a", None, "Seguranca_Social"), True),
        ("Extrato de Remunerações", pedido("a", "Extrato de remunerações", "Financeiros"), True),
        ("Extrato de Remunerações", pedido("a", "Recibos de vencimento", "Financeiros"), False),
        ("Documento Qualquer", pedido("a", "Documento Qualquer", "Financeiros"), False),
    ],
)
def test_pedido_corresponde(rotulo, pedido_, esperado):
    assert arq.pedido_corresponde(rotulo, pedido_) is esperado


@pytest.mark.asyncio
async def test_a_nota_de_liquidacao_nao_fecha_o_pedido_de_recibos_de_vencimento(ambiente):
    """Antes um `update_many` por categoria fechava QUALQUER pedido de «Financeiros»."""
    ambiente.db.documents.docs += [
        pedido("recibos", "Recibos de vencimento"),
        pedido("nota", "Nota de Liquidação do IRS"),
    ]
    await arq.arquivar_documentos("p1", [doc("Nota de Liquidação IRS", "N.pdf")], origem="auto_financas", enviado_por="sys")
    por_id = {d["id"]: d for d in ambiente.db.documents.docs}
    assert por_id["recibos"]["status"] == "REQUESTED"
    assert por_id["nota"]["status"] == "UPLOADED"
    assert por_id["nota"]["s3_path"].endswith("N.pdf")


@pytest.mark.asyncio
async def test_uma_captura_de_ecra_arquiva_mas_nao_fecha_pedidos(ambiente):
    ambiente.db.documents.docs.append(pedido("nota", "Nota de Liquidação IRS"))
    r = await arq.arquivar_documentos(
        "p1", [doc("Nota de Liquidação IRS (captura de ecrã)", "C.pdf")], origem="o", enviado_por="s"
    )
    assert r.total == 1
    por_id = {d["id"]: d for d in ambiente.db.documents.docs}
    assert por_id["nota"]["status"] == "REQUESTED"


@pytest.mark.asyncio
async def test_um_pedido_so_e_fechado_por_um_documento(ambiente):
    ambiente.db.documents.docs.append(pedido("irs", None, "IRS"))
    await arq.arquivar_documentos(
        "p1", [doc("Declaração de IRS", "A.pdf"), doc("Declaração de IRS", "B.pdf")], origem="o", enviado_por="s"
    )
    assert {d["id"]: d for d in ambiente.db.documents.docs}["irs"]["s3_path"].endswith("A.pdf")


# ── em falta ───────────────────────────────────────────────────────────────

def test_em_falta_lista_o_que_o_portal_nao_trouxe():
    obtidos = [{"label": "Declaração de IRS"}]
    assert arq.rotulos_em_falta("financas", obtidos) == ["Nota de Liquidação IRS"]
    assert arq.rotulos_em_falta("financas", []) == ["Declaração de IRS", "Nota de Liquidação IRS"]
    assert arq.rotulos_em_falta("seguranca_social", [{"label": "Situação Contributiva"}, {"label": "Extrato de Remunerações"}]) == []


def test_uma_captura_de_ecra_conta_como_em_falta():
    obtidos = [{"label": "Declaração de IRS"}, {"label": "Nota de Liquidação IRS (captura de ecrã)"}]
    assert arq.rotulos_em_falta("financas", obtidos) == ["Nota de Liquidação IRS"]


def test_fonte_desconhecida_nao_inventa_documentos_em_falta():
    assert arq.rotulos_em_falta("outra", []) == []
