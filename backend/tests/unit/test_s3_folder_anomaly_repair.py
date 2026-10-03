"""Sanar o `s3_folder` gravado como par `(sucesso, caminho)` (Lote 8, ponto 1).

O relatório de produção deu a forma exacta:

    gravado: [True, 'Documentação Clientes/Nome_do_Cliente']

O pedido foi «substituir pelo valor do índice 1». Para ESTA forma é
exactamente isso. O que estes testes protegem são as formas que um
`valor[1]` cego estragaria numa escrita contra produção — e a mais
importante é a terceira, porque não é um erro de dados, é a parede de
segurança virada ao contrário.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from services.s3_document_root import RAIZ
from services.s3_folder_anomaly_repair import (
    VEREDICTO_FORA_DA_RAIZ,
    VEREDICTO_IRRECONHECIVEL,
    VEREDICTO_JA_E_TEXTO,
    VEREDICTO_PAR_DE_FALHA,
    VEREDICTO_PAR_DE_SUCESSO,
    VEREDICTOS_REPARAVEIS,
    classificar,
    resumir,
)
from tests.unit.helpers_fonte import codigo_sem_comentarios

CAMINHO_REAL = f"{RAIZ}Nome_do_Cliente"

RAIZ_DO_REPO = Path(__file__).resolve().parents[3]


def _fonte(caminho: str) -> str:
    with open(RAIZ_DO_REPO / caminho, encoding="utf-8") as fh:
        return codigo_sem_comentarios(fh.read())


class TestAFormaDeProducao:
    """O caso que de facto existe nos 10 registos."""

    def test_o_par_de_sucesso_e_reparavel(self):
        r = classificar([True, CAMINHO_REAL])
        assert r.veredicto == VEREDICTO_PAR_DE_SUCESSO
        assert r.reparavel is True

    def test_o_caminho_proposto_e_o_do_indice_1(self):
        r = classificar([True, CAMINHO_REAL])
        assert r.caminho == CAMINHO_REAL

    def test_a_barra_final_e_aparada(self):
        # Senão o mapeamento gravado difere do que o resto do sistema
        # compara, e `dentro_da_pasta` normaliza mas o relatório mentia.
        r = classificar([True, f"{CAMINHO_REAL}/"])
        assert r.caminho == CAMINHO_REAL

    def test_um_tuplo_vale_como_uma_lista(self):
        # O BSON não tem tuplos (o driver devolve lista), mas a origem do
        # defeito é um tuplo e o módulo é chamado com os dois.
        assert classificar((True, CAMINHO_REAL)).reparavel is True


class TestOQueUmIndice1CegoEstragaria:
    """As três formas em que `valor[1]` escreve a coisa errada."""

    def test_um_par_que_declara_FALHA_nao_se_repara(self):
        # `(False, caminho)`: o caminho está lá, mas é o que o código
        # tentou e não conseguiu usar. Gravá-lo cimenta um mapeamento que
        # o próprio sistema rejeitou.
        r = classificar([False, CAMINHO_REAL])
        assert r.veredicto == VEREDICTO_PAR_DE_FALHA
        assert r.reparavel is False
        # O caminho vai no relatório para a pessoa poder decidir...
        assert r.caminho == CAMINHO_REAL

    @pytest.mark.parametrize("caminho", [
        "backups/dump-2026-09-01.zip",
        "companies/logo.png",
        "../etc/passwd",
        "Documentação Clientes",      # a raiz NUA
        "Documentação Clientes/",
    ])
    def test_um_caminho_FORA_da_raiz_documental_nao_se_repara(self, caminho):
        # ESTE é o teste que importa. `build_s3_valid_prefixes` devolve o
        # `s3_folder` gravado como prefixo de posse, e
        # `assert_s3_file_belongs_to_process` autoriza tudo o que esteja
        # dentro dele — a partir do Portal, inclusive. Gravar `backups/`
        # aqui não corrige um registo: abre o bucket.
        # É a regra 1 do `s3_relink`, e a raiz nua é a regra 2.
        r = classificar([True, caminho])
        assert r.veredicto == VEREDICTO_FORA_DA_RAIZ
        assert r.reparavel is False

    def test_a_raiz_vence_o_sucesso_na_ORDEM_das_perguntas(self):
        # Com as perguntas ao contrário, um `[True, "backups/x.zip"]`
        # saía como `par_de_falha` — que se lê como «problema de dados» e
        # não como «tentativa de envenenar o prefixo».
        assert classificar(
            [True, "backups/x.zip"]
        ).veredicto == VEREDICTO_FORA_DA_RAIZ

    @pytest.mark.parametrize("valor", [
        [],                                   # [1] → IndexError
        [CAMINHO_REAL],                       # [1] → IndexError
        [True, CAMINHO_REAL, "extra"],        # três elementos: qual é?
        [True, None],                         # [1] → None
        [True, ""],                           # [1] → vazio
        [True, 123],
        [True, [CAMINHO_REAL]],               # lista dentro de lista
        {"path": CAMINHO_REAL},               # [1] → KeyError
        {0: True, 1: CAMINHO_REAL},           # [1] casaria, por acidente
        123,
        [CAMINHO_REAL, True],                 # par invertido
    ])
    def test_qualquer_outra_forma_EXIGE_decisao(self, valor):
        assert classificar(valor).veredicto == VEREDICTO_IRRECONHECIVEL
        assert classificar(valor).reparavel is False

    def test_o_par_INVERTIDO_nao_se_adivinha(self):
        # `[caminho, True]` tem o caminho no índice 0. Reordenar com base
        # em «qual dos dois parece um caminho» é adivinhar a intenção de
        # um escritor que já não existe.
        assert classificar([CAMINHO_REAL, True]).reparavel is False

    def test_o_motivo_NOMEIA_o_problema(self):
        # Um relatório que diz «irreconhecível» e mais nada obriga quem o
        # lê a ir ao Mongo à mão.
        for valor in ([False, CAMINHO_REAL], [True, "backups/x"], [1, 2, 3]):
            assert classificar(valor).motivo, valor


class TestOQueNaoEAnomalia:
    def test_uma_string_nao_e_anomalia_e_nao_se_toca(self):
        # Contraprova: se o caso normal entrasse como reparável, o script
        # reescrevia o mapeamento de toda a base de dados.
        r = classificar(CAMINHO_REAL)
        assert r.veredicto == VEREDICTO_JA_E_TEXTO
        assert r.reparavel is False

    def test_so_UM_veredicto_e_reparavel(self):
        # Guarda contra alargar `VEREDICTOS_REPARAVEIS` por distracção:
        # cada entrada nova aqui é uma escrita nova em produção.
        assert VEREDICTOS_REPARAVEIS == (VEREDICTO_PAR_DE_SUCESSO,)


class TestOResumo:
    def test_conta_por_veredicto_e_separa_quem_exige_decisao(self):
        resumo = resumir([
            classificar([True, CAMINHO_REAL]),
            classificar([True, f"{RAIZ}Outro"]),
            classificar([False, CAMINHO_REAL]),
            classificar([True, "backups/x.zip"]),
            classificar([1, 2, 3]),
        ])
        assert resumo["total"] == 5
        assert resumo["reparaveis"] == 2
        assert resumo["exigem_decisao"] == 3

    def test_uma_string_nao_conta_como_decisao_pendente(self):
        # Senão o script saía com código 1 por causa de registos sãos.
        resumo = resumir([classificar(CAMINHO_REAL)])
        assert resumo["exigem_decisao"] == 0
        assert resumo["reparaveis"] == 0


class TestOScript:
    """Guardas sobre a fonte: o que o script PODE escrever."""

    CAMINHO = "backend/scripts/fix_s3_folder_anomalies.py"

    def test_a_omissao_NAO_escreve(self):
        codigo = _fonte(self.CAMINHO)
        # Sem as aspas: o `ast.unparse` do helper normaliza-as, e
        # comparar `'"--aplicar"'` dava um falso negativo (regra do
        # `helpers_fonte`).
        assert "--aplicar" in codigo, "a bandeira de escrita tem de existir"
        assert "args.aplicar" in codigo, "e tem de ser consultada"

    def test_a_escrita_e_um_set_ESTRITO_na_chave(self):
        # Um `update_one` com o documento inteiro, ou um `$set` com mais
        # chaves do que estas, tocava em dados que não são o mapeamento.
        codigo = _fonte(self.CAMINHO)
        arvore = ast.parse(codigo)
        chaves = set()
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Dict):
                continue
            for chave, valor in zip(no.keys, no.values):
                if (isinstance(chave, ast.Constant) and chave.value == "$set"
                        and isinstance(valor, ast.Dict)):
                    chaves = {
                        k.value for k in valor.keys
                        if isinstance(k, ast.Constant)
                    }
        assert chaves == {
            "s3_folder", "s3_mapping_updated_at", "s3_mapping_updated_by",
        }, f"o $set toca em {chaves}"

    def test_NAO_chama_require_non_production_db(self):
        # Corre contra produção de propósito — é o único sítio onde estes
        # registos existem (precedente do `diagnose_assignment_drift`).
        assert "require_non_production_db" not in _fonte(self.CAMINHO)

    def test_a_decisao_de_reparar_vem_do_MODULO_e_nao_do_script(self):
        # Uma segunda cópia da regra no script divergiria da testada —
        # e a que divergisse era a que escrevia.
        codigo = _fonte(self.CAMINHO)
        assert "reparacao.reparavel" in codigo
        assert "classificar" in codigo
        # Procurar o texto `[1]` apanhava o `parents[1]` do próprio
        # script — um falso positivo da guarda. A pergunta é mais
        # estreita: o script nunca indexa o VALOR cru.
        indexa_o_valor = [
            ast.dump(no) for no in ast.walk(ast.parse(codigo))
            if isinstance(no, ast.Subscript)
            and any(
                isinstance(n, ast.Constant) and n.value in ("valor", "s3_folder")
                or isinstance(n, ast.Name) and "valor" in n.id
                for n in ast.walk(no.value)
            )
        ]
        assert indexa_o_valor == [], (
            "o script indexa o valor cru à mão em vez de pedir o caminho "
            f"ao módulo: {indexa_o_valor}"
        )

    def test_o_leitor_desta_guarda_le_MESMO_o_script(self):
        # Contraprova: as asserções acima passam com um leitor vazio.
        codigo = _fonte(self.CAMINHO)
        assert "async def principal" in codigo
        assert len(codigo) > 2000, "o leitor devolveu pouco para ser o script"

    def test_a_consulta_pergunta_POSITIVAMENTE_pelo_array(self):
        """A armadilha que só um Mongo REAL revelou.

        A primeira versão da consulta era

            {"$nor": [{"s3_folder": {"$type": "string"}}]}

        e encontrou **1 de 7** registos semeados. Numa consulta a um campo
        que contém um ARRAY, o Mongo compara o array E cada elemento:
        `$type: "string"` é verdadeiro para `[True, "Documentação…"]`,
        porque há ali um elemento string — logo o `$nor` excluía
        exactamente as fichas que o script existe para encontrar. Pior do
        que falhar: o relatório dizia «1 anomalia», que se lê como «as
        outras já estão sãs».

        É a família da lição do `$nor` no duplo de Mongo, e o duplo
        in-memory dos testes não implementa `$type` — por isso a guarda é
        sobre a FONTE e a prova é a execução contra um `mongod` avulso.
        """
        codigo = _fonte(self.CAMINHO)
        assert '$type' in codigo and 'array' in codigo, (
            "a consulta tem de perguntar `$type: \"array\"` — é o único "
            "operador que responde a «o campo É um array»"
        )
        assert "$nor" not in codigo, (
            "o `$nor` sobre `$type: \"string\"` exclui os arrays que "
            "contêm uma string, que são precisamente os 10 registos"
        )

    def test_o_script_filtra_pelo_TIPO_do_lado_do_mongo(self):
        # Trazer a colecção inteira para memória num `for` seria uma
        # passagem por 300+ processos com os dados pessoais desencriptados
        # (regra de projecção do `diagnose_s3_name_fallback`).
        codigo = _fonte(self.CAMINHO)
        assert "$type" in codigo
