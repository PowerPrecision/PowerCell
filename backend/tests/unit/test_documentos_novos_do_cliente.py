"""A bolinha verde: «o cliente enviou documentos novos» (Bloco 2, ponto 18).

O defeito: `fetch_new_documents_map` perguntava por `status == "uploaded"` e o
Portal escreve `RECEIVED` + `uploaded_by: "portal_client"` — a bolinha estava
desenhada em três ecrãs e não acendia nunca. Os documentos dos testes vêm do
ESCRITOR de produção (`_create_document_record`), não de uma forma suposta.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from services import document_novelty as novidade

AGORA = datetime.now(timezone.utc)


def _iso(dias_atras=0):
    return (AGORA - timedelta(days=dias_atras)).isoformat()


@pytest.fixture
def bd(fake_async_db):
    with patch.object(novidade, "db", fake_async_db):
        yield fake_async_db


async def _doc_do_portal(bd, process_id="p-1", quando=None):
    """Um documento criado pelo escritor REAL do Portal."""
    from services import portal_upload_ops

    with patch.object(portal_upload_ops, "db", bd):
        await portal_upload_ops._create_document_record(
            f"d-{len(bd.documents.docs)}", process_id, "Documentação Clientes/c/Index/cc.pdf",
            "cc.pdf", "Cartao_Cidadao", 100, "application/pdf", quando or _iso(), client_id="c-1",
        )


@pytest.mark.asyncio
class TestAExploracao:
    async def test_um_upload_do_portal_acende_a_bolinha(self, bd):
        """O defeito: antes, este documento NUNCA contava."""
        await _doc_do_portal(bd)
        assert await novidade.mapa_de_documentos_novos(["p-1"]) == {"p-1": True}

    async def test_o_upload_da_equipa_nao_acende(self, bd):
        bd.documents.docs.append({
            "id": "d1", "process_id": "p-1", "status": "RECEIVED",
            "uploaded_by": "u-consultor", "source": "staff_crm_upload", "uploaded_at": _iso(),
        })
        assert await novidade.mapa_de_documentos_novos(["p-1"]) == {}

    async def test_o_estado_legado_uploaded_continua_a_contar(self, bd):
        bd.documents.docs.append({"id": "d1", "process_id": "p-1", "status": "uploaded", "uploaded_at": _iso()})
        assert await novidade.mapa_de_documentos_novos(["p-1"]) == {"p-1": True}


@pytest.mark.asyncio
class TestAJanelaEOVisto:
    async def test_o_que_a_equipa_ja_viu_nao_acende(self, bd):
        await _doc_do_portal(bd)
        bd.documents.docs[0]["staff_seen_at"] = _iso()
        assert await novidade.mapa_de_documentos_novos(["p-1"]) == {}

    async def test_o_historico_antigo_nao_acende_em_todo_o_lado(self, bd):
        """Sem a janela, o primeiro deploy acendia TODOS os processos com
        algum upload do Portal, para sempre."""
        await _doc_do_portal(bd, quando=_iso(dias_atras=novidade.JANELA_DE_NOVIDADE_DIAS + 5))
        assert await novidade.mapa_de_documentos_novos(["p-1"]) == {}

    async def test_dentro_da_janela_acende(self, bd):
        await _doc_do_portal(bd, quando=_iso(dias_atras=novidade.JANELA_DE_NOVIDADE_DIAS - 2))
        assert await novidade.mapa_de_documentos_novos(["p-1"]) == {"p-1": True}

    async def test_marcar_como_vistos_apaga_a_bolinha_so_deste_processo(self, bd):
        await _doc_do_portal(bd, "p-1")
        await _doc_do_portal(bd, "p-2")
        await novidade.marcar_como_vistos("p-1")
        assert await novidade.mapa_de_documentos_novos(["p-1", "p-2"]) == {"p-2": True}

    async def test_o_visto_nao_guarda_quem(self, bd):
        """O perfil `indexacao` não deixa rasto: guarda-se QUANDO, nunca QUEM."""
        await _doc_do_portal(bd)
        await novidade.marcar_como_vistos("p-1")
        doc = bd.documents.docs[0]
        assert doc["staff_seen_at"]
        assert not any(k in doc for k in ("staff_seen_by", "seen_by", "viewed_by"))

    async def test_um_documento_novo_depois_de_visto_volta_a_acender(self, bd):
        await _doc_do_portal(bd)
        await novidade.marcar_como_vistos("p-1")
        await _doc_do_portal(bd)
        assert await novidade.mapa_de_documentos_novos(["p-1"]) == {"p-1": True}

    async def test_marcar_nunca_propaga(self, bd):
        class Quebrada:
            async def update_many(self, *a, **k):
                raise RuntimeError("Mongo em baixo")

        with patch.object(novidade, "db", type("D", (), {"documents": Quebrada()})()):
            assert await novidade.marcar_como_vistos("p-1") == 0

    async def test_entradas_vazias(self, bd):
        assert await novidade.mapa_de_documentos_novos([]) == {}
        assert await novidade.mapa_de_documentos_novos([None, ""]) == {}
        assert await novidade.marcar_como_vistos("") == 0


@pytest.mark.asyncio
class TestOsEcrasUsamADefinicaoUnica:
    async def test_o_mapa_das_listagens_e_o_mesmo(self, bd):
        """Kanban, «Os Meus Processos» e a listagem filtrada chamam isto."""
        from services.process_my_clients import fetch_new_documents_map

        await _doc_do_portal(bd)
        assert await fetch_new_documents_map(object(), ["p-1"]) == {"p-1": True}

    async def test_abrir_os_documentos_marca_como_vistos_depois_da_guarda(self):
        from routes import documents
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        fonte = codigo_da_funcao_sem_comentarios(documents.list_client_files)
        assert "marcar_como_vistos(" in fonte
        assert fonte.index("assert_can_view_process_documents(") < fonte.index("marcar_como_vistos(")

    async def test_a_condicao_usada_a_limpar_e_a_usada_a_perguntar(self):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        assert "condicao_de_documento_novo()" in codigo_da_funcao_sem_comentarios(novidade.marcar_como_vistos)
        assert "condicao_de_documento_novo()" in codigo_da_funcao_sem_comentarios(novidade.mapa_de_documentos_novos)
