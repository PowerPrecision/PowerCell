"""Contenção de caminhos no Explorador de Ficheiros (Épico 10, Gestor S3).

O QUE ESTAVA ABERTO
===================
O explorador navega o bucket INTEIRO, e o bucket não guarda só documentos de
clientes: os **backups da base de dados** vivem no mesmo sítio, sob
`backups/`. Três das seis operações aceitavam uma chave S3 arbitrária, sem
qualquer contenção à raiz do explorador:

    run_s3_download(path)      → get_object(Key=path)   → backups/dump.gz
    run_s3_delete(data.path)   → apaga o prefixo        → backups/
    run_s3_rename(old_path)    → move o prefixo         → qualquer coisa

Não era sequer preciso `../`: bastava escrever `backups/`. As outras três
passavam por `_resolve_explorer_path`, que só fazia `startswith` — e
`Documentação Clientes/../backups` satisfaz `startswith`.

Enquanto a página esteve trancada a admin/CEO isto ficou contido (e ainda
assim um engano de quem escreve um caminho apaga os backups). Abrir a página
a utilizadores normais sem fechar isto seria abrir a porta primeiro e pôr a
fechadura depois.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.s3_explorer_paths import (
    RAIZ_DO_EXPLORADOR,
    assert_dentro_da_raiz,
    caminho_dentro_da_raiz,
    normalizar_caminho,
    primeiro_segmento,
)


class TestNormalizacao:
    def test_vazio_devolve_a_raiz(self):
        for entrada in ["", "   ", None]:
            assert normalizar_caminho(entrada) == RAIZ_DO_EXPLORADOR

    def test_caminho_relativo_ganha_a_raiz(self):
        assert normalizar_caminho("Joao_Silva") == f"{RAIZ_DO_EXPLORADOR}/Joao_Silva"

    def test_caminho_ja_absoluto_fica_igual(self):
        p = f"{RAIZ_DO_EXPLORADOR}/Joao_Silva/Financeiros"
        assert normalizar_caminho(p) == p

    def test_barras_a_mais_sao_colapsadas(self):
        assert normalizar_caminho("Joao//Silva/") == f"{RAIZ_DO_EXPLORADOR}/Joao/Silva"

    def test_ponto_simples_desaparece(self):
        assert normalizar_caminho("./Joao/./Silva") == f"{RAIZ_DO_EXPLORADOR}/Joao/Silva"

    def test_subir_dentro_da_raiz_e_legitimo(self):
        # "Joao/Financeiros/.." é "Joao" — continua dentro, não é fuga.
        assert normalizar_caminho("Joao/Financeiros/..") == f"{RAIZ_DO_EXPLORADOR}/Joao"


class TestFugasDaRaiz:
    """A propriedade de segurança é "não SAIR da raiz", não "recusar".

    Um caminho RELATIVO (`backups/dump.gz`) é prefixado com a raiz e fica
    contido — `Documentação Clientes/backups/dump.gz`, que é uma pasta
    qualquer dentro da área de clientes e não o backup real. É seguro, e é
    o comportamento que o explorador já tinha para `create`/`upload`.

    Só escapa quem SOBE acima da raiz ou entra por caminho absoluto. Foi
    aqui que me enganei a escrever os testes à primeira: pedi recusa onde
    a contenção bastava, e a contenção é que é a propriedade real.
    """

    @pytest.mark.parametrize("fuga", [
        "../backups",
        "../../backups",
        f"{RAIZ_DO_EXPLORADOR}/../backups",
        f"{RAIZ_DO_EXPLORADOR}/Joao/../../backups",
        "/backups",
        "/etc/passwd",
        f"/{RAIZ_DO_EXPLORADOR}/../../backups",
    ])
    def test_sair_da_raiz_e_recusado(self, fuga):
        assert caminho_dentro_da_raiz(fuga) is False
        with pytest.raises(HTTPException) as exc:
            assert_dentro_da_raiz(fuga)
        assert exc.value.status_code == 400

    @pytest.mark.parametrize("relativo", [
        "backups/dump.gz",
        "backups/",
        f"{RAIZ_DO_EXPLORADOR}_outro/Joao",
    ])
    def test_caminho_relativo_fica_contido_na_raiz(self, relativo):
        resolvido = assert_dentro_da_raiz(relativo)
        assert resolvido.startswith(f"{RAIZ_DO_EXPLORADOR}/")

    def test_o_backup_real_nunca_e_alcancavel(self):
        """O que interessa não é o 400 — é a chave que chega ao S3.

        `backups/dump.gz` tem de deixar de ser a chave do backup; que se
        transforme numa chave inexistente dentro da área de clientes é
        suficiente e é o que não parte o uso legítimo.
        """
        for tentativa in ["backups/dump.gz", "../backups/dump.gz", "/backups/dump.gz"]:
            try:
                resolvido = assert_dentro_da_raiz(tentativa)
            except HTTPException:
                continue  # recusado — também serve
            assert resolvido != "backups/dump.gz"
            assert not resolvido.startswith("backups/")

    def test_o_prefixo_parecido_nao_conta_como_raiz(self):
        """`startswith` de TEXTO aceitava "Documentação Clientes_outro".

        Era metade da falha do `_resolve_explorer_path` original: comparar
        por prefixo de texto em vez de por fronteira de segmento. Um
        caminho já absoluto com esse nome tem de ser tratado como fora.
        """
        assert caminho_dentro_da_raiz(f"/{RAIZ_DO_EXPLORADOR}_outro/x") is False
        assert caminho_dentro_da_raiz(f"{RAIZ_DO_EXPLORADOR}/x") is True

    def test_a_propria_raiz_e_valida(self):
        assert caminho_dentro_da_raiz(RAIZ_DO_EXPLORADOR) is True
        assert caminho_dentro_da_raiz(f"{RAIZ_DO_EXPLORADOR}/") is True


class TestPrimeiroSegmento:
    """A pasta de cliente — onde a decisão de âmbito vai viver (Passo 3)."""

    def test_extrai_a_pasta_do_cliente(self):
        assert primeiro_segmento(f"{RAIZ_DO_EXPLORADOR}/Joao_Silva/Financeiros/a.pdf") == "Joao_Silva"

    def test_na_raiz_nao_ha_pasta(self):
        assert primeiro_segmento(RAIZ_DO_EXPLORADOR) is None
        assert primeiro_segmento("") is None

    def test_normaliza_antes_de_extrair(self):
        # Sem normalizar, "Joao/../Maria" daria "Joao" — a pasta errada, e a
        # decisão de âmbito seria tomada sobre um cliente que não é o alvo.
        assert primeiro_segmento("Joao/../Maria/Financeiros") == "Maria"

    def test_caminho_que_sai_da_raiz_nao_tem_segmento(self):
        # Quem sai não tem pasta de cliente — e o chamador recusa antes.
        assert primeiro_segmento("../backups/dump.gz") is None
        assert primeiro_segmento("/backups/dump.gz") is None
