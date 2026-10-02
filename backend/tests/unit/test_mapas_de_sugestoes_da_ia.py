"""Os dois mapas de campos da IA têm de concordar (Lote 4).

A IA passa por DOIS mapas escritos à mão, em módulos diferentes:

1. `ai_document_analyzer.compare_extracted_with_existing` traduz o nome
   do campo do DOCUMENTO para o nome canónico da ficha
   (`salario_liquido` → `monthly_income`). É este nome que viaja para o
   frontend dentro de `conflicts`/`newValues` e que o consultor vê ao
   lado do campo.

2. `document_ai_analyze.AI_SUGGESTION_FIELD_MAP` traduz esse nome para o
   caminho Mongo da escrita (`monthly_income` →
   `financial_data.monthly_income`), e **descarta em silêncio** o que
   não conhecer:

       if field not in AI_SUGGESTION_FIELD_MAP:
           continue

O DEFEITO QUE ISTO ENCONTROU: `naturalidade` estava no primeiro mapa e
não no segundo. O consultor via a sugestão, clicava em aprovar, o
pedido respondia 200 — e o valor não era gravado em sítio nenhum. Uma
aprovação sem efeito é pior do que não oferecer o campo: o utilizador
acredita que decidiu.

É a forma dos campos canónicos de atribuição do Lote 5: duas listas
escritas à mão divergem, e a divergência não produz erro nenhum.
Lido por AST porque o primeiro mapa vive DENTRO de uma função.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

ANALYZER = BACKEND / "services" / "ai_document_analyzer.py"


def _mapa_da_comparacao() -> dict[str, str]:
    """O `field_mapping` de `compare_extracted_with_existing`."""
    arvore = ast.parse(ANALYZER.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if not (isinstance(no, ast.FunctionDef) and no.name == "compare_extracted_with_existing"):
            continue
        for interno in ast.walk(no):
            if (
                isinstance(interno, ast.Assign)
                and any(getattr(alvo, "id", "") == "field_mapping" for alvo in interno.targets)
                and isinstance(interno.value, ast.Dict)
            ):
                return {
                    chave.value: valor.value
                    for chave, valor in zip(interno.value.keys, interno.value.values)
                    if isinstance(chave, ast.Constant) and isinstance(valor, ast.Constant)
                }
    raise AssertionError("field_mapping não encontrado em compare_extracted_with_existing")


class TestOsDoisMapasConcordam:
    def test_o_leitor_por_AST_le_mesmo_o_mapa(self):
        """Contraprova obrigatória de toda a leitura por AST: sem ela,
        um leitor que devolva `{}` faz o teste principal passar."""
        mapa = _mapa_da_comparacao()
        assert len(mapa) > 20, mapa
        # Dois pares que a docstring da função promete explicitamente.
        assert mapa["salario_liquido"] == "monthly_income"
        assert mapa["entidade_empregadora"] == "employer_name"

    def test_tudo_o_que_e_sugerido_pode_ser_GRAVADO(self):
        from services.document_ai_analyze import AI_SUGGESTION_FIELD_MAP

        sugeridos = set(_mapa_da_comparacao().values())
        sem_destino = sorted(sugeridos - set(AI_SUGGESTION_FIELD_MAP))
        assert not sem_destino, (
            f"campos que a IA sugere e o apply descarta em silêncio: {sem_destino}. "
            "Aprovar uma sugestão destas responde 200 e não grava nada."
        )

    def test_naturalidade_grava_na_ficha(self):
        """O campo que estava em falta, agora pelo caminho real."""
        from services.document_ai_analyze import map_ai_suggestions_to_mongo_update

        update = map_ai_suggestions_to_mongo_update({"naturalidade": "Porto"})
        assert update == {"personal_data.naturalidade": "Porto"}

    def test_o_2o_titular_continua_a_ir_para_titular2_data(self):
        """Contraprova de que o campo novo não escapa à regra do titular."""
        from services.document_ai_analyze import map_ai_suggestions_to_mongo_update

        update = map_ai_suggestions_to_mongo_update(
            {"naturalidade": "Porto"}, target_titular="titular2",
        )
        assert update == {"titular2_data.naturalidade": "Porto"}

    def test_os_campos_do_IMOVEL_nao_viajam_para_o_titular2(self):
        """O imóvel é do PROCESSO e não de um titular — se isto mudar, um
        documento do 2.º titular passa a escrever o valor do imóvel num
        sítio onde ninguém o lê."""
        from services.document_ai_analyze import map_ai_suggestions_to_mongo_update

        update = map_ai_suggestions_to_mongo_update(
            {"valor_imovel": 250000}, target_titular="titular2",
        )
        assert update == {"real_estate_data.valor_imovel": 250000}
