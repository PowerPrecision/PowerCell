"""Apagar uma entrada da trilha: a colecção decide-se pela ORIGEM do id.

O QUE ESTAVA MAL (Set 2026) — E É CONSEQUÊNCIA DO PONTO 9
=========================================================
A rota `DELETE /api/activities/{id}` nunca caiu: continua registada, e o
`POST` a responder 410 não lhe tocou. O 404 vinha de outro sítio.

A trilha do separador Histórico é UNIFICADA: o `UnifiedAuditTrail` funde
`db.history` com `db.activities`. O `classifyAuditEvent` devolve
`"comment"` também para registos de HISTÓRICO — basta o `field` ser
`observation_notes`/`observations`, ou a acção conter "coment"/"observaç"
— e o componente mostra o botão de apagar para **qualquer**
`type === "comment"`, enviando `event.id`.

O `run_delete_activity` procurava só em `db.activities`. Resultado: 404.

E o Ponto 9 tornou isto quase universal: ao fazer do Resumo o local
OFICIAL das notas, elas passaram a ser gravadas por `log_history` em
`db.history`. O botão foi construído para `db.activities`, portanto
hoje falha em praticamente todas as notas — só funciona nas atividades
antigas.

A REGRA
=======
O id decide a colecção, e a permissão é a mesma nas duas: dono ou admin.
A trilha é de auditoria, logo o apagar continua a ser a **válvula de
rectificação** que o dono quis deixar aberta — não uma porta nova.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services import activities_api_crud as modulo

DONO = {"id": "u-dono", "role": "consultor"}
OUTRO = {"id": "u-outro", "role": "consultor"}
ADMIN = {"id": "u-admin", "role": "admin"}


async def _apagar(fake_async_db, activity_id, user):
    with patch.object(modulo, "db", fake_async_db):
        return await modulo.run_delete_activity(activity_id, user)


@pytest.fixture
async def _semeado(fake_async_db):
    await fake_async_db.activities.insert_one({
        "id": "a-1", "process_id": "p-1", "user_id": "u-dono",
        "description": "nota antiga",
    })
    await fake_async_db.history.insert_one({
        "id": "h-1", "process_id": "p-1", "user_id": "u-dono",
        "field": "observation_notes", "action": "Atualizou observações",
    })
    return fake_async_db


class TestONoteDoResumoEApagavel:
    """O caso que dava 404 em produção."""

    async def test_apaga_a_entrada_do_HISTORICO(self, _semeado):
        resultado = await _apagar(_semeado, "h-1", DONO)
        assert "eliminad" in str(resultado.get("message", "")).lower()
        assert await _semeado.history.find_one({"id": "h-1"}) is None

    async def test_e_continua_a_apagar_a_ATIVIDADE_antiga(self, _semeado):
        """Contraprova: mudar de colecção não pode partir o caso que
        funcionava."""
        await _apagar(_semeado, "a-1", DONO)
        assert await _semeado.activities.find_one({"id": "a-1"}) is None

    async def test_apagar_o_historico_NAO_toca_na_atividade(self, _semeado):
        """Ids distintos, colecções distintas — nada de apagar as duas."""
        await _apagar(_semeado, "h-1", DONO)
        assert await _semeado.activities.find_one({"id": "a-1"}) is not None


class TestAPermissaoEAMesmaNasDuasColeccoes:
    async def test_outro_utilizador_nao_apaga_o_historico_alheio(self, _semeado):
        with pytest.raises(HTTPException) as erro:
            await _apagar(_semeado, "h-1", OUTRO)
        assert erro.value.status_code == 403
        assert await _semeado.history.find_one({"id": "h-1"}) is not None

    async def test_o_admin_apaga_qualquer_uma(self, _semeado):
        await _apagar(_semeado, "h-1", ADMIN)
        await _apagar(_semeado, "a-1", ADMIN)
        assert await _semeado.history.find_one({"id": "h-1"}) is None
        assert await _semeado.activities.find_one({"id": "a-1"}) is None

    async def test_uma_entrada_de_SISTEMA_nao_e_de_ninguem(self, _semeado):
        """Sem `user_id`, só o admin rectifica.

        Um registo automático não tem dono; tratá-lo como "sem dono, logo
        de todos" abriria a trilha de auditoria a qualquer utilizador.
        """
        await _semeado.history.insert_one({
            "id": "h-sys", "process_id": "p-1",
            "action": "Mudou o estado para Aprovado",
        })
        with pytest.raises(HTTPException) as erro:
            await _apagar(_semeado, "h-sys", DONO)
        assert erro.value.status_code == 403


class TestOIdInexistente:
    async def test_continua_a_dar_404(self, _semeado):
        """Procura nas duas e não encontra: aí o 404 é a resposta certa."""
        with pytest.raises(HTTPException) as erro:
            await _apagar(_semeado, "nao-existe", ADMIN)
        assert erro.value.status_code == 404
