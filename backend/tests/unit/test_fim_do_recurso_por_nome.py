"""D-19 fechada: o recurso por NOME foi apagado (Lote 8, ponto 2).

A medição em produção deu **zero** fichas a perder documentos, o que
autoriza o corte. Mas a medição respondeu a UMA pergunta — «que fichas
não têm `s3_folder`?» — e o corte depende de uma segunda que ela não
cobre: **«que CHAMADORES se esquecem de passar o `s3_folder`?»**

Esses não aparecem na medição (as fichas estão mapeadas) e perdem tudo
no corte, porque para eles o ramo do nome era o único que corria. É o
`GET /onedrive/files/{client_name}` do Lote 7 outra vez, com outra porta.

E havia um: `run_categorize_all_documents`. Pior do que um risco futuro —
para uma ficha mapeada por ID o nome não resolve pasta nenhuma, logo
«Categorizar Todos» e «Renomear IA» (que o chama primeiro) **já hoje
processam zero documentos em silêncio**, em todos os clientes criados
depois do Lote 6.

O QUE FICA NO LUGAR
===================
O mapeamento gravado, e nada mais. `build_s3_valid_prefixes` deixa de
derivar prefixos de posse do NOME e passa a derivá-los do ID — o que
fecha a última metade da D-19: dois homónimos exactos deixam de poder
autorizar ficheiros um do outro.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.document_process_resolve import build_s3_valid_prefixes
from services.s3_document_root import RAIZ, pasta_do_cliente, pasta_do_processo
from tests.unit.helpers_fonte import codigo_sem_comentarios

RAIZ_DO_REPO = Path(__file__).resolve().parents[3]

#: As funções do recurso por nome. Apagadas, não desligadas: código
#: adormecido atrás de um `raise` é um convite a religá-lo (regra do
#: `POST /api/activities`).
FUNCOES_APAGADAS = (
    "_find_client_folder_combined",
    "_get_possible_client_paths",
    "_find_client_folder",
    "_nomes_de_pasta_candidatos",
)


def _fonte(caminho: str) -> str:
    with open(RAIZ_DO_REPO / caminho, encoding="utf-8") as fh:
        return codigo_sem_comentarios(fh.read())


class TestOChamadorQueSoUsavaONome:
    """O pré-requisito do corte, e um defeito já em produção."""

    @pytest.fixture(autouse=True)
    def _ligar_db(self, fake_async_db):
        self._db = fake_async_db

    @pytest.mark.asyncio
    async def test_categorizar_todos_passa_o_s3_folder_gravado(self):
        from services import document_categorize

        processo = {
            "id": "p1",
            "client_name": "Ana Costa",
            "s3_folder": f"{RAIZ}0b1c2d3e-4f50-6171-8291-a2b3c4d5e6f7",
        }
        falso_s3 = MagicMock()
        falso_s3.list_files.return_value = {"files": {}}
        # `fake_async_db` e não um MagicMock: o serviço faz `await` em
        # mais do que um sítio e um duplo sincrono rebenta antes de a
        # asserção correr (regra do conftest).
        await self._db.processes.insert_one(processo)
        with patch.object(document_categorize, "db", self._db), \
             patch.object(document_categorize, "s3_service", falso_s3):
            await document_categorize.run_categorize_all_documents("p1")

        assert falso_s3.list_files.called
        argumentos = falso_s3.list_files.call_args
        passados = list(argumentos.args) + list(argumentos.kwargs.values())
        assert processo["s3_folder"] in passados, (
            "sem o `s3_folder` esta chamada resolvia pelo NOME: para uma "
            "ficha mapeada por ID o nome não resolve pasta nenhuma e "
            "«Categorizar Todos» processava zero documentos em silêncio"
        )


class TestTodosOsChamadoresDoListFiles:
    """Inventário por AST: nenhum chamador omite o mapeamento.

    Falha por OMISSÃO para um chamador novo. É o inventário que o Lote 5
    mandou fazer («inventariar os sítios que LISTAM»), aplicado ao
    argumento em vez de à condição.
    """

    MODULOS = [
        "backend/services/document_categorize.py",
        "backend/services/document_queries.py",
        "backend/services/ai_api_analyze.py",
        "backend/services/storage_service.py",
        "backend/routes/documents.py",
    ]

    def _chamadas_sem_pasta(self, caminho):
        codigo = _fonte(caminho)
        faltas = []
        for no in ast.walk(ast.parse(codigo)):
            if not isinstance(no, ast.Call):
                continue
            func = no.func
            nome = (
                func.attr if isinstance(func, ast.Attribute)
                else getattr(func, "id", "")
            )
            if nome != "list_files":
                continue
            # 4.º posicional OU `s3_folder=` — as duas formas existem no
            # código e as duas servem.
            tem = len(no.args) >= 4 or any(
                kw.arg == "s3_folder" for kw in no.keywords
            )
            if not tem:
                faltas.append(ast.unparse(no)[:90])
        return faltas

    @pytest.mark.parametrize("modulo", MODULOS)
    def test_a_chamada_leva_sempre_o_mapeamento(self, modulo):
        faltas = self._chamadas_sem_pasta(modulo)
        assert faltas == [], (
            f"{modulo} chama `list_files` sem `s3_folder`: {faltas}. "
            "Sem o recurso por nome, essa chamada devolve vazio."
        )

    def test_o_leitor_encontra_MESMO_as_chamadas(self):
        # Contraprova: `== []` passa com um leitor que não leia nada.
        total = 0
        for modulo in self.MODULOS:
            codigo = _fonte(modulo)
            total += sum(
                1 for no in ast.walk(ast.parse(codigo))
                if isinstance(no, ast.Call)
                and (getattr(no.func, "attr", None) == "list_files"
                     or getattr(no.func, "id", None) == "list_files")
            )
        assert total >= 5, f"o leitor só encontrou {total} chamadas"


class TestORecursoPorNomeFoiAPAGADO:
    """Apagado do `s3_storage`, não desligado."""

    @pytest.mark.parametrize("funcao", FUNCOES_APAGADAS)
    def test_a_funcao_ja_nao_existe_no_servico(self, funcao):
        from services.s3_storage import S3Service

        assert not hasattr(S3Service, funcao), (
            f"`{funcao}` continua no S3Service — o recurso por nome está "
            "apagado, não desligado"
        )

    @pytest.mark.parametrize("funcao", FUNCOES_APAGADAS)
    def test_o_nome_ja_nao_aparece_na_fonte(self, funcao):
        assert funcao not in _fonte("backend/services/s3_storage.py")

    def test_o_list_files_ja_nao_tem_ramo_de_palpites(self):
        codigo = _fonte("backend/services/s3_storage.py")
        assert "parar_no_primeiro" not in codigo, (
            "o `parar_no_primeiro` só existia para a lista de palpites de "
            "grafia; sem ela é estado morto"
        )

    def test_o_sanitize_folder_name_FICA(self):
        # Contraprova no sentido oposto: apagar tudo o que toca em nomes
        # levaria também a sanitização das CATEGORIAS, que não tem nada a
        # ver com identidade de cliente.
        from services.s3_storage import sanitize_folder_name

        assert sanitize_folder_name("Documentos Pessoais")


class TestSemMapeamentoNaoSeAdivinha:
    def test_uma_ficha_sem_s3_folder_devolve_vazio_e_NAO_rebenta(self):
        from services.s3_storage import S3Service

        servico = S3Service.__new__(S3Service)
        servico.is_configured = lambda: True
        resultado = servico.list_files("p1", "Ana Costa", None, None)
        assert resultado.get("files") == {} or not any(
            resultado.get("files", {}).values()
        )

    def test_a_ausencia_de_mapeamento_e_REGISTADA(self, caplog):
        from services.s3_storage import S3Service

        servico = S3Service.__new__(S3Service)
        servico.is_configured = lambda: True
        with caplog.at_level("WARNING"):
            servico.list_files("p1", "Ana Costa", None, None)
        registo = "\n".join(r.getMessage() for r in caplog.records)
        assert "p1" in registo, (
            "uma listagem vazia por falta de mapeamento não pode ser "
            "silenciosa — era assim que um documento desaparecia sem erro"
        )


class TestAPosseDerivaDoIDeNaoDoNome:
    """A última metade da D-19: a guarda de posse.

    `build_s3_valid_prefixes` devolvia prefixos derivados do NOME quando
    não havia `s3_folder`. Dois homónimos EXACTOS produziam o mesmo
    prefixo, logo cada um autorizava os ficheiros do outro — e isso é
    alcançável do Portal (`_dono_do_prefixo_s3`).
    """

    def test_com_mapeamento_gravado_e_esse_o_unico_prefixo(self):
        pasta = f"{RAIZ}0b1c2d3e-4f50-6171-8291-a2b3c4d5e6f7"
        assert build_s3_valid_prefixes({"id": "p1", "s3_folder": pasta}) == [
            pasta
        ]

    def test_sem_mapeamento_o_prefixo_vem_do_ID(self):
        prefixos = build_s3_valid_prefixes(
            {"id": "0b1c2d3e-4f50-6171-8291-a2b3c4d5e6f7",
             "client_name": "Ana Costa"}
        )
        assert prefixos == [
            pasta_do_processo("0b1c2d3e-4f50-6171-8291-a2b3c4d5e6f7")
        ]

    def test_sem_mapeamento_o_prefixo_NUNCA_vem_do_nome(self):
        prefixos = build_s3_valid_prefixes(
            {"id": "0b1c2d3e-4f50-6171-8291-a2b3c4d5e6f7",
             "client_name": "Ana Costa"}
        )
        assert all("Ana" not in p for p in prefixos), prefixos

    def test_dois_HOMONIMOS_exactos_deixam_de_partilhar_prefixo(self):
        # O teste invertido da D-19. Antes: os dois davam
        # `Documentação Clientes/Ana Costa` e autorizavam-se um ao outro.
        a = build_s3_valid_prefixes(
            {"id": "11111111-1111-1111-1111-111111111111",
             "client_name": "Ana Costa"}
        )
        b = build_s3_valid_prefixes(
            {"id": "22222222-2222-2222-2222-222222222222",
             "client_name": "Ana Costa"}
        )
        assert a and b
        assert set(a).isdisjoint(set(b)), (
            "dois homónimos exactos continuam a partilhar prefixo de posse"
        )

    def test_a_pasta_do_CLIENTE_entra_quando_e_um_cliente(self):
        # O Portal sem processo (onboarding) resolve o dono pelo CLIENTE.
        prefixos = build_s3_valid_prefixes(
            {"id": "33333333-3333-3333-3333-333333333333",
             "nome": "Ana Costa", "tipo": "cliente"}
        )
        assert prefixos == [
            pasta_do_cliente("33333333-3333-3333-3333-333333333333")
        ] or prefixos == [
            pasta_do_processo("33333333-3333-3333-3333-333333333333")
        ]

    def test_sem_id_utilizavel_recusa_TUDO(self):
        # A regra que já existia: lista vazia recusa tudo. Um id que não
        # serve como segmento não produz prefixo nenhum.
        assert build_s3_valid_prefixes({"client_name": "Ana Costa"}) == []
        assert build_s3_valid_prefixes({"id": "", "client_name": "Ana"}) == []
        assert build_s3_valid_prefixes({"id": "../x"}) == []

    def test_a_raiz_NUA_nunca_e_um_prefixo(self):
        for processo in (
            {}, {"id": None}, {"client_name": ""}, {"id": "a"},
        ):
            for prefixo in build_s3_valid_prefixes(processo):
                assert prefixo.rstrip("/") != RAIZ.rstrip("/"), processo


class TestOsTestesLegadosForamINVERTIDOS:
    """O teste legado inverte-se, não se apaga (regra da casa)."""

    def test_a_concordancia_com_o_oraculo_de_producao_foi_invertida(self):
        # O `test_s3_name_fallback_audit.py` comparava
        # `nomes_de_pasta_candidatos` com o `_nomes_de_pasta_candidatos`
        # real. O oráculo deixou de existir, logo o teste passou a
        # afirmar isso mesmo.
        fonte = _fonte("backend/tests/unit/test_s3_name_fallback_audit.py")
        assert "_nomes_de_pasta_candidatos" in fonte, (
            "o teste da concordância foi APAGADO em vez de invertido"
        )
        assert "hasattr" in fonte or "not hasattr" in fonte
