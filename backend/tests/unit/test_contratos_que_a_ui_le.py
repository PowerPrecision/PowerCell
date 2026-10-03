"""Dois contratos que a UI lia e o servidor não enviava (Lote 3).

A FORMA DO DEFEITO, DUAS VEZES
==============================
O Lote 3 foi pedido como «estritamente de interface», e dois dos quatro
pontos não eram: a UI não pode mostrar o que não lhe é dado.

**Ponto 1 — o `doc_id`.** O `S3FileManager` chama
`POST /documents/{doc_id}/ai-analyze-review` e tira o id de
`file.doc_id || file.id`, com um comentário a afirmar que «o listing de
ficheiros expõe o ID do document_metadata em `file.doc_id`». Nunca expôs:
o `s3_service.list_files` devolve `name/path/size/category/temporary_url`
e a projecção do enriquecimento tinha CATORZE campos e não o `id`. O botão
«Analisar IA» morria sempre em "doc_id em falta" — nunca funcionou.

É a mesma forma da fila Mongo do Lote 2: uma crença escrita em comentário,
nunca um contrato, e ninguém verificou.

**Ponto 4 — o `attached_files`.** O `/portal/status` tem TRÊS
serializações (requested / uploaded / received) e o PACOTE DE só
acrescentou `attached_files` à terceira. A explicação da correcção está
escrita nesse bloco, a poucas linhas das duas que ficaram de fora. Um
cliente que enviasse 5 ficheiros para um pedido ainda incompleto via lista
nenhuma, e o único nome no ecrã era o `filename` de topo — O ÚLTIMO.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from tests.unit.helpers_fonte import codigo_sem_comentarios  # noqa: E402

ROTAS_DOCUMENTOS = BACKEND / "routes" / "documents.py"
PORTAL_STATUS = BACKEND / "services" / "portal_status.py"


def _fonte(caminho: Path) -> str:
    return codigo_sem_comentarios(caminho.read_text(encoding="utf-8"))


class TestOIdDoDocumentoVaiNaListagem:
    """Ponto 1 — sem ele o botão «Analisar IA» não tinha o que enviar."""

    def test_a_projeccao_pede_o_id(self):
        fonte = _fonte(ROTAS_DOCUMENTOS)
        # A projecção do `document_metadata` da listagem de ficheiros.
        bloco = fonte[fonte.index("meta_docs = await db.document_metadata.find"):]
        bloco = bloco[: bloco.index("meta_by_path")]
        assert "id" in bloco.replace("'", '"')
        assert '"id": 1' in bloco.replace("'", '"')

    def test_o_enriquecimento_poe_doc_id_em_cada_ficheiro(self):
        fonte = _fonte(ROTAS_DOCUMENTOS)
        assert 'f["doc_id"] = meta.get("id")' in fonte.replace("'", '"')

    def test_a_ordem_importa_a_projeccao_vem_ANTES_do_uso(self):
        """Contraprova de coerência: pedir o campo e não o usar, ou usá-lo
        sem o pedir, são os dois modos de isto voltar a falhar."""
        fonte = _fonte(ROTAS_DOCUMENTOS).replace("'", '"')
        assert fonte.index('"id": 1') < fonte.index('f["doc_id"]')

    def test_o_endpoint_de_revisao_resolve_por_esse_id(self):
        """O elo do outro lado: o id que a listagem envia tem de ser o que o
        endpoint procura. Sem isto, as duas guardas acima podiam estar certas
        e o pedido continuar a dar 404."""
        from services import document_review

        fonte = codigo_sem_comentarios(
            Path(document_review.__file__).read_text(encoding="utf-8")
        ).replace("'", '"')
        assert 'db.document_metadata.find_one' in fonte
        assert '{"id": doc_id}' in fonte


def _chaves_do_dicionario(no) -> set[str]:
    """As CHAVES de um literal de dicionário.

    As chaves e não o texto: a primeira versão deste teste comparava o
    dicionário renderizado com `"attached_files" in bloco`, e isso é
    satisfeito por `"uploaded_count": len(d.get("attached_files") or [])` —
    a subcadeia aparece noutra linha. A mutação que apagou o campo de uma
    das seis serializações SOBREVIVEU a essa versão. Mesma armadilha do
    Lote 2 (`tipos=` é subcadeia de `excluir_tipos=`), agora por dentro de
    uma expressão.
    """
    import ast

    return {
        chave.value
        for chave in no.keys
        if isinstance(chave, ast.Constant) and isinstance(chave.value, str)
    }


def _serializacoes() -> list[tuple[int, frozenset]]:
    """TODOS os sítios do `/portal/status` que montam um documento para a UI.

    Por ÁRVORE DE SINTAXE e não por `fonte.index(...)`: a primeira versão
    procurava a primeira ocorrência de cada `*_docs.append(` e acertava no
    sítio errado — há SEIS, não três. Foi este teste a apanhar o meu próprio
    inventário incompleto, que é exactamente o defeito que ele existe para
    impedir.

    Um `append(entry)` monta o dicionário numa atribuição anterior: essa
    resolve-se pelo nome da variável, senão os dois sítios do caminho do
    cliente sem processo ficavam fora da verificação.
    """
    import ast

    arvore = ast.parse(PORTAL_STATUS.read_text(encoding="utf-8"))

    # Dicionários atribuídos a um nome (o `entry = {...}`).
    por_nome: dict[str, tuple[int, set[str]]] = {}
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign) and isinstance(no.value, ast.Dict):
            for alvo in no.targets:
                if isinstance(alvo, ast.Name):
                    por_nome[alvo.id] = (no.lineno, _chaves_do_dicionario(no.value))

    encontrados: list[tuple[int, frozenset]] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        func = no.func
        if not isinstance(func, ast.Attribute) or func.attr != "append":
            continue
        if getattr(func.value, "id", "") not in (
            "requested_docs", "uploaded_docs", "received_docs",
        ):
            continue
        for arg in no.args:
            if isinstance(arg, ast.Dict):
                encontrados.append((no.lineno, frozenset(_chaves_do_dicionario(arg))))
            elif isinstance(arg, ast.Name) and arg.id in por_nome:
                linha, chaves = por_nome[arg.id]
                encontrados.append((no.lineno, frozenset(chaves)))
    return encontrados


class TestOsFicheirosAnexadosVaoEmTODASAsSerializacoes:
    """Ponto 4 — faltava em quatro das seis, e era numa das que já o tinha
    que estava a explicação escrita."""

    def test_ha_SEIS_sitios_a_serializar_documentos(self):
        """Contraprova de cobertura, e o número que me corrigiu: eu tinha
        contado três. Se este número mudar, há um sítio novo a verificar."""
        assert len(_serializacoes()) == 6, _serializacoes()

    @pytest.mark.parametrize("linha,chaves", _serializacoes())
    def test_cada_serializacao_leva_attached_files(self, linha, chaves):
        # A CHAVE e não a subcadeia: `"uploaded_count": len(d.get(
        # "attached_files") or [])` contém o texto e não é o campo.
        assert "attached_files" in chaves, f"linha {linha} não leva attached_files"

    @pytest.mark.parametrize("linha,chaves", _serializacoes())
    def test_cada_serializacao_leva_o_progresso(self, linha, chaves):
        """`expected_count`/`uploaded_count` — é o «1/3» que diz ao cliente
        que ainda falta, e sem ele um pedido incompleto parece completo."""
        assert "expected_count" in chaves, f"linha {linha} sem expected_count"
        assert "uploaded_count" in chaves, f"linha {linha} sem uploaded_count"

    def test_os_append_de_VARIAVEL_entram_na_contagem(self):
        """Os dois `append(entry)` do caminho do cliente SEM PROCESSO — que é
        o primeiro ecrã que ele vê. Um inventário que só olhasse para
        literais passava por cima deles, e foi a mutação a prová-lo."""
        import ast

        arvore = ast.parse(PORTAL_STATUS.read_text(encoding="utf-8"))
        porVariavel = [
            no.lineno
            for no in ast.walk(arvore)
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr == "append"
            and getattr(no.func.value, "id", "") in (
                "requested_docs", "uploaded_docs", "received_docs",
            )
            and any(isinstance(a, ast.Name) for a in no.args)
        ]
        assert len(porVariavel) == 2, porVariavel

    def test_a_contagem_vem_do_ponto_unico(self):
        """Nunca uma regra de quantidade escrita aqui: a do resto do sistema
        vive em `document_portal_counts.parse_expected_count`."""
        fonte = _fonte(PORTAL_STATUS)
        assert "parse_expected_count" in fonte
        # CONTRAPROVA: o ponto único existe e é importável.
        from services.document_portal_counts import parse_expected_count

        assert parse_expected_count({"expected_count": 3}) == 3
        assert parse_expected_count({}) == 1
