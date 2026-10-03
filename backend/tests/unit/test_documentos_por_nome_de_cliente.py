"""`GET /onedrive/files/{client_name}` — a porta que ficou aberta (D-19).

O QUE ESTE ENDPOINT FAZIA
========================
Resolvia o processo por ``{"client_name": {"$regex": nome, "$options": "i"}}``
— **parcial e não escapado** — e chamava `s3_storage.list_files` **sem**
`s3_folder`, com `Depends(get_current_user)` e nada mais. Três defeitos
numa linha:

1. **Sem guarda de visibilidade.** Qualquer sessão autenticada —
   `indexacao`, `parceiro`, um consultor de outra rede — enumerava os
   documentos de um cliente escrevendo o nome dele no URL. Nem
   `assert_can_view_process_documents`, nem condição de rede, nem
   atribuição.
2. **Regex parcial e não escapado.** `/onedrive/files/a` casa com o
   primeiro processo que tenha um «a» no nome; um parêntese no nome ia cru
   para o motor de regex. É o defeito do auto-mapeamento com outra porta.
3. **O recurso por NOME, sempre.** Sem `s3_folder`, o `list_files` toma
   o ramo legado mesmo para uma ficha correctamente mapeada pelo ID — logo
   esta superfície tinha a colisão da D-19 com força total, e um corte do
   recurso por nome partia-a por inteiro.

A DECISÃO: 410, NÃO UMA GUARDA
==============================
Endurecer não resolve o problema de fundo — **um nome não é uma
identidade**. Dois homónimos exactos continuariam a dar documentos de um
deles, à escolha do Mongo, e era por aqui que a D-19 entrava. O caminho
canónico existe e recebe um ID: `GET /documents/client/{id}/files`.

Responde 410 (e não 404 nem 405) pelo precedente do `POST /api/activities`:
o caminho `/onedrive/files` continua a existir para a listagem por pasta, e
um 405 lê-se como avaria de encaminhamento. A mensagem diz para onde ir,
senão manda procurar às cegas.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.onedrive_files import run_get_client_files_by_name


class TestAPortaFechada:
    @pytest.mark.asyncio
    async def test_responde_410_e_nao_lista_nada(self):
        with pytest.raises(HTTPException) as exc:
            await run_get_client_files_by_name(
                "Ana Costa", "", {"id": "u1", "role": "indexacao"},
            )
        assert exc.value.status_code == 410

    @pytest.mark.asyncio
    async def test_a_mensagem_diz_para_onde_ir(self):
        """Sem o caminho novo, a mensagem manda procurar às cegas."""
        with pytest.raises(HTTPException) as exc:
            await run_get_client_files_by_name("Ana Costa", "", {"id": "u1"})
        detalhe = str(exc.value.detail)
        assert "/documents/client/" in detalhe
        assert "nome" in detalhe.lower()

    def test_nao_toca_na_base_de_dados_NENHUMA_vez(self):
        """Senão o código de resposta vira oráculo de quem existe.

        Mesma regra da guarda do Portal (Incidente P0): se a recusa viesse
        depois do `find_one`, um 410 para um nome existente e um 404 para um
        inexistente distinguiam-se, e o endpoint continuava a responder à
        pergunta «este cliente existe?». A prova mais forte é a que o
        módulo dá: já não importa a base de dados.
        """
        import services.onedrive_files as modulo

        assert not hasattr(modulo, "db"), (
            "o módulo voltou a ligar-se à base de dados"
        )

    @pytest.mark.asyncio
    async def test_recusa_seja_qual_for_o_nome(self, monkeypatch):
        """Incluindo os que exploravam o regex parcial e o não escapado."""
        for nome in ["a", "", "Ana (Costa)", ".*", "Ana|Rui"]:
            with pytest.raises(HTTPException) as exc:
                await run_get_client_files_by_name(nome, "", {"id": "u1"})
            assert exc.value.status_code == 410


class TestAFonteNaoVoltaAoCaminhoLegADO:
    """Guardas sobre o código-fonte: as três causas não podem reaparecer."""

    def _fonte(self):
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        caminho = (
            Path(__file__).resolve().parents[2]
            / "services" / "onedrive_files.py"
        )
        return codigo_sem_comentarios(caminho.read_text(encoding="utf-8"))

    def test_nao_resolve_mais_um_processo_por_regex_de_nome(self):
        fonte = self._fonte()
        assert "$regex" not in fonte, (
            "voltou a procurar o processo por nome — é a colisão da D-19"
        )
        # `client_name` como CHAVE de consulta (o parâmetro da função
        # continua a chamar-se assim e isso não é o defeito).
        assert '"client_name"' not in fonte
        assert "db.processes" not in fonte

    def test_nao_chama_mais_o_list_files(self):
        """Era a chamada SEM `s3_folder`, logo sempre pelo recurso por nome."""
        assert "list_files" not in self._fonte()

    def test_contraprova_a_recusa_esta_mesmo_la(self):
        """Sem isto, apagar a função satisfazia os dois guardas acima."""
        fonte = self._fonte()
        assert "410" in fonte
        assert "HTTPException" in fonte
