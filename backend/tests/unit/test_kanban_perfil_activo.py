"""
O Kanban ignorava o perfil ACTIVO (Lote 5, achado lateral do ponto 15).

O SINTOMA REPORTADO
  Utilizadores multi-perfil trocam de cargo no ContextSwitcher e o quadro
  Kanban não acompanha.

AS DUAS CAUSAS, E SÃO INDEPENDENTES
  1. `get_kanban_board` era o ÚNICO endpoint de listagem a usar
     `user["role"]` — o papel do JWT — em vez de
     `get_effective_role(request, user)`. Todos os outros
     (`/processes`, `/processes/me`, `/processes/paginated`) já o
     faziam. Mesmo com o header correcto a chegar, o quadro respondia
     sobre o papel BASE.
  2. O frontend chamava `/processes/kanban` por `fetch` CRU em três
     sítios, com `Authorization` e mais nada. O interceptor que injecta
     `X-Company-Id` / `X-Active-Role` vive no cliente Axios — quinta
     instância do incidente de 2026-09-21. Sem header nenhum, nem havia
     o que honrar.

  Corrigir só uma delas não resolvia nada: sem header o backend não tem
  o que ler; sem `get_effective_role` o header não é lido.

`__all_roles__` NÃO É UM PAPEL, E NO QUADRO NÃO PODE PASSAR
  O perfil "all" do ContextSwitcher resolve para `__all_roles__`, que as
  LISTAGENS entendem (`all_roles=` faz a união das visibilidades). O
  `build_kanban_role_base_query` não o conhece: cairia no ramo de gestão,
  sem filtro nenhum. Para quem tem `indexacao` como papel base isso era
  um ALARGAMENTO — hoje vê a fila da Indexação, passaria a ver o quadro
  inteiro. O quadro não suporta união de âmbitos, por isso `__all_roles__`
  recua para o papel do JWT: a escolha conservadora nunca alarga.
"""
from pathlib import Path

import pytest

from tests.unit.helpers_fonte import codigo_sem_comentarios


def _fonte(*partes: str) -> str:
    caminho = Path(__file__).resolve().parents[2].joinpath(*partes)
    return codigo_sem_comentarios(caminho.read_text())


def _argumentos_da_chamada(fonte: str, nome: str) -> str:
    """Só os argumentos de UMA chamada, até ao parêntese que a fecha.

    Uma janela de N caracteres a partir do `def` não serve: o
    `ast.unparse` colapsa a chamada numa linha só e a janela apanhava o
    endpoint SEGUINTE — que também chama `get_effective_role`. A guarda
    passava com a mutação aplicada, e foi isso que a mutação denunciou.
    """
    inicio = fonte.index(nome + "(") + len(nome) + 1
    profundidade = 1
    for i in range(inicio, len(fonte)):
        if fonte[i] == "(":
            profundidade += 1
        elif fonte[i] == ")":
            profundidade -= 1
            if profundidade == 0:
                return fonte[inicio:i]
    raise AssertionError(f"chamada a {nome} não fecha")


def _sem_aspas(texto: str) -> str:
    """`ast.unparse` normaliza as aspas — comparar sem elas."""
    return texto.replace("'", "").replace('"', "")


class TestOEndpointHonraOPerfilActivo:
    def test_deixou_de_ler_o_papel_do_jwt(self):
        fonte = _fonte("routes", "processes.py")
        argumentos = _argumentos_da_chamada(fonte, "run_get_kanban_board")
        assert "role=user[role]" not in _sem_aspas(argumentos)

    def test_usa_o_resolvedor_de_papel_efectivo(self):
        fonte = _fonte("routes", "processes.py")
        argumentos = _argumentos_da_chamada(fonte, "run_get_kanban_board")
        assert "role=get_effective_role(request, user)" in argumentos

    def test_contraprova_a_guarda_olha_para_a_chamada_certa(self):
        """Sem isto, um extractor partido (janela larga, parêntese mal
        contado) passava sempre — foi o que aconteceu."""
        fonte = _fonte("routes", "processes.py")
        argumentos = _argumentos_da_chamada(fonte, "run_get_kanban_board")
        assert "kanban_projection=PROCESS_KANBAN_PROJECTION" in argumentos
        assert "run_get_my_clients" not in argumentos

    def test_o_handler_recebe_o_request(self):
        """Sem `request` não há headers para ler — o resolvedor devolveria
        sempre o papel base e a correcção seria decorativa."""
        fonte = _fonte("routes", "processes.py")
        inicio = fonte.index("async def get_kanban_board")
        assinatura = fonte[inicio : fonte.index(")", fonte.index("(", inicio))]
        assert "request" in assinatura


class TestAllRolesRecuaNoQuadro:
    def test_all_roles_nao_chega_ao_construtor(self):
        from services.process_kanban_enrichment import resolver_papel_do_quadro

        assert resolver_papel_do_quadro("__all_roles__", {"role": "indexacao"}) == "indexacao"

    def test_quem_tem_indexacao_como_base_mantem_o_seu_ambito(self):
        """O alargamento que isto impede: a Indexação vê a sua fila, não
        o quadro inteiro, mesmo com o perfil "all" escolhido."""
        from services.process_kanban_enrichment import resolver_papel_do_quadro
        from services.process_list_filters import build_kanban_role_base_query

        papel = resolver_papel_do_quadro("__all_roles__", {"role": "indexacao", "id": "u1"})
        query = build_kanban_role_base_query({"id": "u1", "role": "indexacao"}, papel, show_all=True)
        assert "$or" in query, "a Indexação perdeu o seu âmbito próprio"

    def test_um_papel_normal_passa_intacto(self):
        """Contraprova: o recuo é só para `__all_roles__`. Se recuasse
        sempre, a correcção toda ficava sem efeito."""
        from services.process_kanban_enrichment import resolver_papel_do_quadro

        assert resolver_papel_do_quadro("indexacao", {"role": "consultor"}) == "indexacao"
        assert resolver_papel_do_quadro("consultor", {"role": "admin"}) == "consultor"

    def test_sem_papel_nenhum_cai_no_do_utilizador(self):
        from services.process_kanban_enrichment import resolver_papel_do_quadro

        assert resolver_papel_do_quadro(None, {"role": "consultor"}) == "consultor"
        assert resolver_papel_do_quadro("", {"role": "consultor"}) == "consultor"

    def test_sem_papel_de_lado_nenhum_nao_rebenta(self):
        from services.process_kanban_enrichment import resolver_papel_do_quadro

        assert resolver_papel_do_quadro(None, {}) == ""
