"""A guarda de posse comparava TEXTO, não caminho (Lote 6, ponto 1).

`assert_s3_file_belongs_to_process` tem dois ramos. Com `s3_folder`
gravado compara `startswith(f"{prefixo}/")` — correcto. Sem ele, degrada
para o NOME do cliente e constrói `f"Documentação Clientes/{nome}"`
**sem a barra final**:

    "Documentação Clientes/Carolina Silva Agostinho/Financeiros/irs.pdf"
        .startswith("Documentação Clientes/Carolina Silva")   → True

Um processo da "Carolina Silva" autorizava TUDO o que estivesse na pasta
da "Carolina Silva Agostinho". Idem em `build_s3_valid_prefixes`, que
alimenta a eliminação em massa.

E esse degradado é alcançável **do Portal** — a única superfície externa —
via `_dono_do_prefixo_s3`, para um cliente que ainda não tenha
`s3_folder` (todo o onboarding antes do primeiro mapeamento).

Este buraco é INDEPENDENTE do `fuzzy match`: não precisa de duas fichas
partilharem pasta, basta um nome ser prefixo do outro.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.document_process_resolve import (
    assert_s3_file_belongs_to_process,
    build_s3_valid_prefixes,
)
from services.portal_upload_ops import assert_portal_file_key_e_do_cliente

CHAVE_DA_VIZINHA = (
    "Documentação Clientes/Carolina Silva Agostinho/Financeiros/irs.pdf"
)
PROCESSO_SEM_PASTA = {"id": "p-1", "client_name": "Carolina Silva"}


class TestOVizinhoDeNomeMaisLongo:
    def test_o_CRM_recusa_a_pasta_de_quem_tem_o_nome_mais_longo(self):
        with pytest.raises(HTTPException) as erro:
            assert_s3_file_belongs_to_process(CHAVE_DA_VIZINHA, PROCESSO_SEM_PASTA)
        assert erro.value.status_code == 403

    def test_o_PORTAL_recusa_o_mesmo(self):
        # A superfície externa: o cliente escolhe a chave que quiser.
        with pytest.raises(HTTPException) as erro:
            assert_portal_file_key_e_do_cliente(
                CHAVE_DA_VIZINHA,
                process=None,
                client={"id": "c-1", "nome": "Carolina Silva"},
            )
        assert erro.value.status_code == 403

    def test_a_eliminacao_em_massa_nao_alcanca_a_vizinha(self):
        from services.s3_document_root import chave_pertence_a_leitura, Leitura

        prefixos = build_s3_valid_prefixes(PROCESSO_SEM_PASTA)
        assert not any(
            chave_pertence_a_leitura(CHAVE_DA_VIZINHA, Leitura(prefixo=p))
            for p in prefixos
        )

    def test_o_sufixo_de_desambiguacao_tambem_fica_fora(self):
        # `_2` é como o sistema desambiguava homónimos nas pastas antigas.
        with pytest.raises(HTTPException):
            assert_s3_file_belongs_to_process(
                "Documentação Clientes/Joao_Silva_2/RGPD/x.pdf",
                {"id": "p-2", "s3_folder": "Documentação Clientes/Joao_Silva"},
            )


class TestOQueTemDeCONTINUARAPassar:
    """Contraprova: apertar a guarda não pode fechar o caso legítimo."""

    def test_o_proprio_cliente_passa_com_nome_em_espacos(self):
        assert_s3_file_belongs_to_process(
            "Documentação Clientes/Carolina Silva/Financeiros/irs.pdf",
            PROCESSO_SEM_PASTA,
        )

    def test_o_proprio_cliente_passa_com_nome_sanitizado(self):
        assert_s3_file_belongs_to_process(
            "Documentação Clientes/Carolina_Silva/Financeiros/irs.pdf",
            PROCESSO_SEM_PASTA,
        )

    def test_a_pasta_gravada_continua_a_mandar(self):
        assert_s3_file_belongs_to_process(
            "Documentação Clientes/Joao_Silva/RGPD/x.pdf",
            {"id": "p-3", "s3_folder": "Documentação Clientes/Joao_Silva"},
        )

    def test_o_documento_do_PROCESSO_por_id_passa(self):
        from services import s3_document_root as raiz

        cid = "11111111-1111-4111-8111-111111111111"
        pid = "33333333-3333-4333-8333-333333333333"
        pasta = raiz.pasta_do_processo(pid, client_id=cid)
        assert_s3_file_belongs_to_process(
            f"{pasta}/Financeiros/irs.pdf", {"id": pid, "s3_folder": pasta}
        )

    def test_o_documento_do_CLIENTE_passa_para_o_processo_dele(self):
        # A pasta do processo está DENTRO da do cliente: quem tem a pasta
        # do cliente gravada vê também os documentos dos processos dele.
        from services import s3_document_root as raiz

        cid = "11111111-1111-4111-8111-111111111111"
        pid = "33333333-3333-4333-8333-333333333333"
        assert_s3_file_belongs_to_process(
            f"{raiz.pasta_do_processo(pid, client_id=cid)}/Financeiros/irs.pdf",
            {"id": "c-1", "s3_folder": raiz.pasta_do_cliente(cid)},
        )


class TestOsNomesVaziosContinuamRecusados:
    def test_nome_vazio_nao_autoriza_a_raiz(self):
        with pytest.raises(HTTPException):
            assert_s3_file_belongs_to_process(
                "Documentação Clientes/Alguem/x.pdf", {"id": "p", "client_name": ""}
            )

    def test_build_prefixes_sem_nome_nao_devolve_a_raiz_nua(self):
        prefixos = build_s3_valid_prefixes({"id": "p", "client_name": ""})
        assert "Documentação Clientes" not in [p.rstrip("/") for p in prefixos]
