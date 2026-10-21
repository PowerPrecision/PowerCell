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
