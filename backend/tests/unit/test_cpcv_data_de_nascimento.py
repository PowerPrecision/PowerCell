"""O CPCV passou a extrair a data de nascimento dos compradores (D-17).

A dívida D-17 dizia: «a estrutura que a IA grava do CPCV não tem data de
nascimento nenhuma», pelo que a regra Sub35 estrita não podia considerar um
terceiro comprador. O que faltava era o CONTRATO dos dois lados:

  1. o **esquema** que vai para o modelo tem de pedir o campo (sem ele, o
     modelo não o devolve — e o `additionalProperties: True` que já lá estava
     deixava passar o que o mapeador depois descartava em silêncio: é o mesmo
     desencontro do `naturalidade` entre os dois mapas da IA, no Lote 4);
  2. o **mapeador** tem de o levar para a ficha com o nome canónico do
     `services.sub35` — um nome novo aqui seria o quinto nome da mesma data.

Os dois lados são afirmados aqui, e o nome do campo é cruzado com o do
`sub35` em vez de ser escrito à mão.
"""
from __future__ import annotations

from services.ai_document import get_document_tool_definition
from services.sub35 import CAMPOS_DE_NASCIMENTO


def _compradores_do_esquema() -> dict:
    tool = get_document_tool_definition("cpcv")
    props = tool["function"]["parameters"]["properties"]
    return props["compradores"]["items"]["properties"]


class TestOEsquemaPedeADataAoModelo:
    def test_o_campo_existe_e_tem_o_nome_CANONICO(self):
        campos = _compradores_do_esquema()
        assert any(nome in campos for nome in CAMPOS_DE_NASCIMENTO), (
            "o esquema do CPCV não pede nenhum dos nomes que o sub35 lê: "
            f"{CAMPOS_DE_NASCIMENTO}"
        )

    def test_a_data_NAO_e_obrigatoria(self):
        """Um CPCV português identifica as partes por NIF/CC e estado civil;
        muitas vezes não indica a data de nascimento. Exigi-la levaria o
        modelo a inventá-la, e uma data inventada é pior do que nenhuma —
        a regra sabe tratar «não sei» (bloqueia), não sabe tratar uma
        mentira."""
        tool = get_document_tool_definition("cpcv")
        obrigatorios = tool["function"]["parameters"]["properties"]["compradores"][
            "items"
        ].get("required", [])
        assert not set(CAMPOS_DE_NASCIMENTO) & set(obrigatorios)

    def test_a_descricao_proibe_inferir(self):
        campos = _compradores_do_esquema()
        campo = next(n for n in CAMPOS_DE_NASCIMENTO if n in campos)
        descricao = campos[campo]["description"].lower()
        assert "não inferir" in descricao or "nao inferir" in descricao


class TestOMapeadorLevaADataParaAFicha:
    def test_o_buyer_data_inclui_a_data(self):
        import inspect

        from services import ai_document
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(
            inspect.getsource(ai_document.build_update_data_from_extraction)
        ).replace("'", '"')
        assert '"data_nascimento": comprador.get("data_nascimento")' in fonte

    def test_o_primeiro_comprador_preenche_a_ficha(self):
        import inspect

        from services import ai_document
        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios(
            inspect.getsource(ai_document.build_update_data_from_extraction)
        ).replace("'", '"')
        assert 'personal_update["data_nascimento"] = buyer_data["data_nascimento"]' in fonte
