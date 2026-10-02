"""Renomear IA: gestão OU atribuído ao processo — nunca o cargo sozinho.

A REGRA ANTIGA E PORQUE MUDOU (decisão do dono, Set 2026)
=========================================================
`POST /documents/rename-smart/{id}` estava em
`require_roles([ADMIN, CEO, DIRETOR])`. Não era um defeito — era a regra
documentada no `AGENTS.md` ("Renomear IA só para `MANAGEMENT_ROLES`") —
e foi por isso que o 403 do QA apareceu com um **consultor**.

O dono mudou a regra: *"não faz sentido o dono do processo não poder
organizar os próprios ficheiros"*. Passa a ser **gestão OU atribuído**.

PORQUE É QUE O `require_roles` NÃO SERVE
========================================
Ele decide com o CARGO e não vê o processo — nunca pode responder "está
atribuído?". A guarda tem de correr onde o processo já está carregado, e
é por isso que vive no serviço e não na rota.

A permissão deriva de `collect_assigned_ids`, o ponto único: foi a
divergência entre listas de campos que produziu o 403 falso positivo na
listagem, e repetir aqui uma lista à mão reproduzia o mesmo defeito numa
operação de ESCRITA.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.document_visibility import can_manage_process_documents

PROCESSO = {
    "id": "p-1",
    "assigned_consultor_ids": ["u-consultor"],
    "client_name": "Ana Cliente",
}

#: O caso de produção: lista vazia, só o singular legado preenchido.
PROCESSO_LEGADO = {
    "id": "p-2",
    "assigned_consultor_ids": [],
    "consultant_id": "u-legado",
}


class TestOAtribuidoPodeOrganizarOsSeusFicheiros:
    def test_o_consultor_atribuido_pode(self):
        assert can_manage_process_documents(
            {"id": "u-consultor", "role": "consultor"}, PROCESSO
        )

    def test_o_consultor_atribuido_SO_pelo_singular_legado_tambem_pode(self):
        """Deriva do ponto único — senão o 403 voltava por esta porta."""
        assert can_manage_process_documents(
            {"id": "u-legado", "role": "consultor"}, PROCESSO_LEGADO
        )

    def test_o_mediador_atribuido_pode(self):
        processo = {"id": "p-3", "assigned_mediador_id": "u-med"}
        assert can_manage_process_documents(
            {"id": "u-med", "role": "intermediario"}, processo
        )

    def test_o_consultor_NAO_atribuido_nao_pode(self):
        """A regra é "o dono do processo", não "qualquer consultor"."""
        assert not can_manage_process_documents(
            {"id": "u-estranho", "role": "consultor"}, PROCESSO
        )


class TestAGestaoMantemOAcessoGeral:
    @pytest.mark.parametrize("papel", ["admin", "ceo", "diretor"])
    def test_sem_estar_atribuido(self, papel):
        assert can_manage_process_documents({"id": "u-x", "role": papel}, PROCESSO)

    def test_o_perfil_ACTIVO_conta(self):
        """Um multi-perfil a trabalhar como diretor é diretor aqui.

        É a regra do PACOTE 9 (cargo efectivo), e sem ela um admin com
        perfil activo de consultor ficava de fora do seu próprio bypass.
        """
        assert can_manage_process_documents(
            {"id": "u-y", "role": "consultor", "effective_role": "diretor"},
            PROCESSO,
        )


class TestAGuardaEstaLigadaAoServico:
    """Uma regra certa que ninguém chama não protege nem autoriza nada."""

    def test_o_servico_chama_a_guarda(self):
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios
        from services.document_rename_smart import run_rename_document_smart

        fonte = codigo_da_funcao_sem_comentarios(run_rename_document_smart)
        assert "assert_can_manage_process_documents" in fonte

    def test_a_rota_deixou_de_filtrar_pelo_cargo_sozinho(self):
        """`require_roles` não vê o processo, logo nunca poderia deixar
        passar o consultor atribuído."""
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        caminho = Path(__file__).resolve().parents[2] / "routes" / "documents.py"
        fonte = codigo_sem_comentarios(caminho.read_text(encoding="utf-8"))
        i = fonte.index("async def rename_document_smart")
        corpo = fonte[i : i + 400]
        assert "require_roles" not in corpo
        assert "user" in corpo

    async def test_o_servico_recusa_quem_nao_pode(self, fake_async_db):
        """Ponta a ponta no serviço real, com o S3 e a BD falseados."""
        from unittest.mock import patch

        from services import document_rename_smart as modulo

        await fake_async_db.processes.insert_one(dict(PROCESSO))

        with patch.object(modulo, "db", fake_async_db):
            with pytest.raises(HTTPException) as erro:
                await modulo.run_rename_document_smart(
                    "p-1",
                    {"s3_path": "Documentação Clientes/Ana Cliente/cc.pdf"},
                    user={"id": "u-estranho", "role": "consultor"},
                )
        assert erro.value.status_code == 403
