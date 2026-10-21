"""P1/P2 — «Ver Detalhes da Lead»: tudo o que o parceiro submeteu, para a equipa analisar.

A rota devolve uma lista POSITIVA: nunca o documento (sem índices cegos, sem chaves S3, sem o código
de acesso ao Portal), com a fronteira de rede de qualquer leitura por id (404 igual ao de «não existe»).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import REDE_INCUMBENTE, semear, tenant_db

pytestmark = pytest.mark.asyncio

DIRETORA_DA_POWER = {"id": "u-ana", "name": "Ana", "role": "diretor", "effective_role": "diretor"}
DIRETOR_DA_DOMUS = {"id": "u-bruno", "name": "Bruno", "role": "diretor", "effective_role": "diretor"}


@pytest.fixture
def mundo(fake_async_db, monkeypatch):
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    semear(fake_async_db)
    fake_async_db.clients.docs.append({
        "id": "c-lead", "nome": "Rita Lead", "fonte": "partner_portal",
        "network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "company_name": "Power Real Estate",
        "contacto": {"email": "rita@x.pt", "telefone": "910000000", "email_hash": "SEGREDO"},
        "dados_pessoais": {"nif": "123456789", "nif_hash": "SEGREDO", "profissao": "Engenheira", "vazio": ""},
        "titular2_data": {"nome": "Rui Lead"},
        "dados_financeiros": {"rendimento_mensal": 2500},
        "dados_imobiliarios": {},
        "portal_access_code": "CODIGO-SECRETO",
        "pending_process_type": "credito_habitacao",
        "has_property": True,
        "notas_do_parceiro": "Cliente com urgência",
        "submitted_by_partner_id": "par-1", "submitted_by_partner_name": "Parceiro Um",
        "created_at": "2026-10-01T10:00:00+00:00",
        "validacao_financeira": {"estado": "pendente"},
    })
    fake_async_db.documents.docs.append({
        "id": "d1", "client_id": "c-lead", "comprovativo_de_pagamento": True,
        "declared_category": "Comprovativo de Pagamento",
        "s3_path": "Documentação Clientes/c-lead/pagamento.pdf",
        "original_filename": "pagamento.pdf", "uploaded_at": "2026-10-02T10:00:00+00:00",
    })
    fake_async_db.documents.docs.append({
        "id": "d2", "client_id": "c-lead", "category": "Identificação",
        "s3_path": "Documentação Clientes/c-lead/cc.pdf",
        "original_filename": "cc.pdf", "uploaded_at": "2026-10-03T10:00:00+00:00",
    })
    return fake_async_db


def _modulos():
    import services.financial_validation as fv

    return (fv,)


async def _detalhes(mundo, user=DIRETORA_DA_POWER, item="c-lead"):
    from services.financial_validation import run_detalhes_da_lead

    with tenant_db(mundo, *_modulos()):
        return await run_detalhes_da_lead(item, user)


class TestOQueOParceiroSubmeteu:
    async def test_devolve_o_que_a_equipa_precisa_para_analisar(self, mundo):
        r = await _detalhes(mundo)
        assert r["nome"] == "Rita Lead"
        assert r["contacto"] == {"email": "rita@x.pt", "telefone": "910000000"}
        assert r["dados_pessoais"] == {"nif": "123456789", "profissao": "Engenheira"}
        assert r["titular2_data"] == {"nome": "Rui Lead"}
        assert r["dados_financeiros"] == {"rendimento_mensal": 2500}
        assert r["notas_do_parceiro"] == "Cliente com urgência"
        assert r["parceiro"] == {"id": "par-1", "nome": "Parceiro Um"}
        assert r["empresa_destino"] == "Power Real Estate"
        assert r["tipo_de_pedido"] == "credito_habitacao"
        assert r["validacao"]["estado"] == "pendente"

    async def test_lista_os_ficheiros_com_o_comprovativo_marcado_e_sem_chaves_s3(self, mundo):
        r = await _detalhes(mundo)
        assert [f["filename"] for f in r["ficheiros"]] == ["cc.pdf", "pagamento.pdf"]  # mais recente primeiro
        por_nome = {f["filename"]: f for f in r["ficheiros"]}
        assert por_nome["pagamento.pdf"]["comprovativo"] is True
        assert por_nome["pagamento.pdf"]["category"] == "Comprovativo de Pagamento"
        assert por_nome["cc.pdf"]["comprovativo"] is False
        assert "s3_path" not in str(r)

    async def test_nunca_vaza_indices_cegos_nem_o_codigo_de_acesso(self, mundo):
        texto = str(await _detalhes(mundo))
        for proibido in ("SEGREDO", "CODIGO-SECRETO", "_hash", "portal_access_code"):
            assert proibido not in texto

    async def test_uma_lead_que_nao_veio_de_parceiro_tambem_abre(self, mundo):
        mundo.clients.docs.append({
            "id": "c-site", "nome": "Via Site", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
            "contacto": {"email": "s@x.pt"}, "dados_pessoais": {},
        })
        r = await _detalhes(mundo, item="c-site")
        assert r["nome"] == "Via Site" and r["parceiro"] is None and r["validacao"] is None


class TestAFronteira:
    async def test_o_ataque_outra_rede_recebe_404_igual_ao_de_nao_existe(self, mundo):
        with pytest.raises(HTTPException) as alheio:
            await _detalhes(mundo, user=DIRETOR_DA_DOMUS)
        with pytest.raises(HTTPException) as inexistente:
            await _detalhes(mundo, item="nao-existe")
        assert alheio.value.status_code == inexistente.value.status_code == 404
        assert alheio.value.detail == inexistente.value.detail


class TestARota:
    def test_a_rota_exige_staff(self):
        import ast
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "routes" / "financial_validation.py").read_text(encoding="utf-8")
        funcao = next(
            n for n in ast.walk(ast.parse(fonte))
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_lead_details"
        )
        assert "require_staff" in ast.unparse(funcao)


# ════════════════════════════════════════════════════════════════════
#  PRÉ-VISUALIZAR UM FICHEIRO DA LEAD
# ════════════════════════════════════════════════════════════════════
import io  # noqa: E402

RAIZ_DOCS = "Documentação Clientes"


def _s3(corpo=b"%PDF-1.4 conteudo", tamanho=None, erro=None):
    """`s3_service` falso AO NÍVEL DA CHAMADA: o que sai para o S3 (chave, bucket) é o que se afirma."""
    from unittest.mock import MagicMock

    cliente = MagicMock()
    if erro:
        cliente.get_object.side_effect = erro
    else:
        cliente.get_object.return_value = {
            "Body": io.BytesIO(corpo),
            "ContentLength": len(corpo) if tamanho is None else tamanho,
            "ContentType": "binary/octet-stream",  # o que o bucket diz NÃO manda
        }
    servico = MagicMock(is_configured=MagicMock(return_value=True), s3_client=cliente, bucket_name="bkt")
    return servico, cliente


async def _conteudo(mundo, file_id, user=DIRETORA_DA_POWER, item="c-lead", servico=None):
    from unittest.mock import patch

    from services.financial_validation import run_conteudo_do_ficheiro_da_lead

    servico = servico or _s3()[0]
    with tenant_db(mundo, *_modulos()), patch("services.s3_storage.s3_service", servico):
        resposta = await run_conteudo_do_ficheiro_da_lead(item, file_id, user)
        corpo = b"".join([b async for b in resposta.body_iterator]) if hasattr(resposta, "body_iterator") else b""
    return resposta, corpo


@pytest.fixture
def com_ficheiros(mundo):
    mundo.documents.docs.clear()
    mundo.documents.docs.extend([
        {"id": "f-pdf", "client_id": "c-lead", "comprovativo_de_pagamento": True, "original_filename": "pagamento.PDF",
         "s3_path": f"{RAIZ_DOCS}/c-lead/Comprovativos/pagamento.PDF", "uploaded_at": "2026-10-02T10:00:00+00:00"},
        {"id": "f-png", "client_id": "c-lead", "original_filename": "cc.png",
         "s3_path": f"{RAIZ_DOCS}/c-lead/cc.png", "uploaded_at": "2026-10-03T10:00:00+00:00"},
        {"id": "f-docx", "client_id": "c-lead", "original_filename": "contrato.docx",
         "s3_path": f"{RAIZ_DOCS}/c-lead/contrato.docx", "uploaded_at": "2026-10-04T10:00:00+00:00"},
        {"id": "f-veneno", "client_id": "c-lead", "original_filename": "x.pdf",
         "s3_path": "backups/dump-2026-09-01.zip", "uploaded_at": "2026-10-04T10:00:00+00:00"},
        {"id": "f-alheio", "client_id": "c-outro", "original_filename": "alheio.pdf",
         "s3_path": f"{RAIZ_DOCS}/c-outro/alheio.pdf", "uploaded_at": "2026-10-04T10:00:00+00:00"},
    ])
    return mundo


class TestAPrevisualizacao:
    async def test_um_pdf_sai_inline_com_o_tipo_que_NOS_decidimos(self, com_ficheiros):
        from unittest.mock import MagicMock

        servico, cliente = _s3(b"%PDF-1.4 bytes")
        resposta, corpo = await _conteudo(com_ficheiros, "f-pdf", servico=servico)
        assert corpo == b"%PDF-1.4 bytes"
        assert resposta.media_type == "application/pdf"  # o bucket dizia octet-stream
        assert resposta.headers["content-disposition"].startswith("inline;")
        assert resposta.headers["x-content-type-options"] == "nosniff"
        assert "no-store" in resposta.headers["cache-control"]
        # A chave que sai para o S3 é a do REGISTO, nunca uma que viaje no pedido.
        cliente.get_object.assert_called_once_with(Bucket="bkt", Key=f"{RAIZ_DOCS}/c-lead/Comprovativos/pagamento.PDF")

    async def test_uma_imagem_sai_com_o_tipo_da_extensao(self, com_ficheiros):
        resposta, corpo = await _conteudo(com_ficheiros, "f-png", servico=_s3(b"\x89PNG....")[0])
        assert resposta.media_type == "image/png" and corpo == b"\x89PNG...."

    async def test_a_lista_diz_o_que_se_pode_visualizar(self, com_ficheiros):
        r = await _detalhes(com_ficheiros)
        por_nome = {f["filename"]: f["previsualizavel"] for f in r["ficheiros"]}
        assert por_nome == {"pagamento.PDF": True, "cc.png": True, "contrato.docx": False, "x.pdf": True}

    async def test_tipo_sem_previsualizacao_da_415_sem_ir_ao_s3(self, com_ficheiros):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as exc:
            await _conteudo(com_ficheiros, "f-docx", servico=servico)
        assert exc.value.status_code == 415
        cliente.get_object.assert_not_called()

    async def test_demasiado_grande_da_413_e_fecha_o_corpo(self, com_ficheiros):
        from services.financial_validation import MAX_BYTES_DA_PREVISUALIZACAO

        servico, cliente = _s3(b"x", tamanho=MAX_BYTES_DA_PREVISUALIZACAO + 1)
        corpo = cliente.get_object.return_value["Body"]
        with pytest.raises(HTTPException) as exc:
            await _conteudo(com_ficheiros, "f-pdf", servico=servico)
        assert exc.value.status_code == 413
        assert corpo.closed

    async def test_ficheiro_em_falta_no_bucket_da_404_e_s3_em_baixo_da_503(self, com_ficheiros):
        from botocore.exceptions import ClientError

        def erro(codigo):
            return ClientError({"Error": {"Code": codigo}}, "GetObject")

        with pytest.raises(HTTPException) as nao_ha:
            await _conteudo(com_ficheiros, "f-pdf", servico=_s3(erro=erro("NoSuchKey"))[0])
        assert nao_ha.value.status_code == 404
        with pytest.raises(HTTPException) as em_baixo:
            await _conteudo(com_ficheiros, "f-pdf", servico=_s3(erro=erro("InternalError"))[0])
        assert em_baixo.value.status_code == 503


class TestAParedeDaPrevisualizacao:
    async def test_o_ataque_uma_chave_envenenada_no_registo_nao_abre_o_bucket(self, com_ficheiros):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as exc:
            await _conteudo(com_ficheiros, "f-veneno", servico=servico)
        assert exc.value.status_code == 403
        cliente.get_object.assert_not_called()

    async def test_o_ficheiro_de_outro_cliente_nao_se_alcanca_por_esta_lead(self, com_ficheiros):
        servico, cliente = _s3()
        with pytest.raises(HTTPException) as exc:
            await _conteudo(com_ficheiros, "f-alheio", servico=servico)
        assert exc.value.status_code == 404
        cliente.get_object.assert_not_called()

    async def test_outra_rede_recebe_404_igual_ao_de_nao_existe(self, com_ficheiros):
        with pytest.raises(HTTPException) as alheio:
            await _conteudo(com_ficheiros, "f-pdf", user=DIRETOR_DA_DOMUS)
        with pytest.raises(HTTPException) as inexistente:
            await _conteudo(com_ficheiros, "nao-existe")
        assert alheio.value.status_code == inexistente.value.status_code == 404
        assert alheio.value.detail == inexistente.value.detail

    def test_a_rota_exige_staff_esta_limitada_e_devolve_response(self):
        import ast
        import pathlib

        fonte = (pathlib.Path(__file__).resolve().parents[2] / "routes" / "financial_validation.py").read_text(encoding="utf-8")
        funcao = next(
            n for n in ast.walk(ast.parse(fonte))
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_lead_file_content"
        )
        texto = ast.unparse(funcao)
        assert "require_staff" in texto and "limiter.limit" in texto and "response: Response" in texto
        assert "request: Request" in texto
