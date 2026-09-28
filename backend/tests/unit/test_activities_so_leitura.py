"""Criar uma atividade pela API deixou de ser possível (Ponto 9).

O PEDIDO: "Se matámos a UI, mata o endpoint. O Histórico é só de leitura
(system-driven)."

PORQUE É QUE É 410 E NÃO O ENDPOINT APAGADO
===========================================
Apagar a rota deixa o `POST /api/activities` a responder **405** (o
caminho continua a existir para o GET e o DELETE), e um 405 lê-se como
avaria de encaminhamento: quem lá bater vai procurar o defeito no
router. O 410 diz o que aconteceu e para onde ir, e é o precedente que
o `POST /auth/login` já usa neste repositório.

A GUARDA É SOBRE O SERVIÇO, NÃO SÓ SOBRE A ROTA
===============================================
Afirmar o 410 no stub provaria só que o stub chama alguém. O que não
pode voltar é a ESCRITA: `run_create_activity` deixou de inserir em
`db.activities` — o corpo antigo foi removido, não desligado, para não
ficar código adormecido à espera de ser religado.

O QUE **NÃO** SE FECHOU, DE PROPÓSITO
=====================================
Os escritores de SISTEMA continuam: `voice_note_engine` (a nota ditada
entra na timeline) e `temp_link_api_public` (o cliente que envia por
link temporário). Escrevem em `db.activities` directamente e nunca
passaram por este endpoint — fechá-los seria matar a própria linha
temporal que o Ponto 9 quer manter viva.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException

from services import activities_api_crud
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios


class TestOEndpointMorreu:
    @pytest.mark.asyncio
    async def test_criar_atividade_responde_410(self):
        with pytest.raises(HTTPException) as erro:
            await activities_api_crud.run_create_activity(
                data=object(), user={"id": "u-1", "role": "consultor"}
            )

        assert erro.value.status_code == 410

    @pytest.mark.asyncio
    async def test_a_resposta_diz_para_onde_ir(self):
        """Um 410 sem destino manda a pessoa procurar às cegas."""
        with pytest.raises(HTTPException) as erro:
            await activities_api_crud.run_create_activity(
                data=object(), user={"id": "u-1", "role": "consultor"}
            )

        assert "Resumo" in str(erro.value.detail)

    @pytest.mark.asyncio
    async def test_recusa_ANTES_de_olhar_para_o_processo(self):
        """Sem base de dados nenhuma — se tocasse no `db` isto rebentava.

        É a diferença entre "o endpoint morreu" e "o endpoint valida e
        depois recusa": o segundo continua a ser uma superfície que lê a
        base de dados por ordem de quem chama.
        """
        # `data=object()` não tem `.process_id`; chegar ao `find_one`
        # levantaria AttributeError em vez de HTTPException.
        with pytest.raises(HTTPException):
            await activities_api_crud.run_create_activity(
                data=object(), user={}
            )


class TestAEscritaFoiREMOVIDA:
    """Contraprova: sem isto, bastava trocar o `raise` por um `if`."""

    def test_a_funcao_nao_insere_em_db_activities(self):
        fonte = codigo_da_funcao_sem_comentarios(
            activities_api_crud.run_create_activity
        )
        assert "insert_one" not in fonte
        assert "activity_doc" not in fonte

    def test_a_rota_continua_a_existir_para_o_410_chegar(self):
        """Apagar a rota daria 405, que se lê como avaria de router."""
        fonte = Path("routes/activities.py").read_text()
        arvore = ast.parse(fonte)
        decoradores = [
            d
            for no in ast.walk(arvore)
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef))
            for d in no.decorator_list
        ]
        posts = [
            d for d in decoradores
            if isinstance(d, ast.Call)
            and isinstance(d.func, ast.Attribute)
            and d.func.attr == "post"
        ]
        assert posts, "o stub do POST /activities tem de continuar a existir"


class TestOsEscritoresDeSISTEMAContinuam:
    """A linha temporal não pode ter ficado vazia."""

    @pytest.mark.parametrize(
        "modulo",
        ["services/voice_note_engine.py", "services/temp_link_api_public.py"],
    )
    def test_o_escritor_de_sistema_continua_a_escrever(self, modulo):
        fonte = Path(modulo).read_text()
        assert "db.activities.insert_one" in fonte, (
            f"{modulo} deixou de alimentar a timeline — o Ponto 9 fecha a "
            "escrita MANUAL, não o registo automático."
        )

    def test_a_leitura_e_a_eliminacao_continuam(self):
        """"Só de leitura" não pode ter virado "sem nada"."""
        assert callable(activities_api_crud.run_get_activities)
        assert callable(activities_api_crud.run_delete_activity)
