"""
Âmbito do Painel de Administração — Lote 5, Secção B, ponto 11.

A DECISÃO DO DONO
  "Ser 'Admin' significa ser Admin da sua REDE, não do sistema global.
  Um Admin da Domus só pode ver a(s) empresa(s) que partilham o seu
  `network_id` e os utilizadores que pertencem a essas empresas."

PORQUE É QUE O UTILIZADOR SE FILTRA PELAS EMPRESAS, E NÃO PELA REDE
  A colecção `users` não tem `network_id` e nunca teve. O que liga um
  utilizador à rede são os UCRs (`user_company_roles.company_id`) e o
  campo legado `users.company`, que é o NOME da empresa (a confusão
  id/nome de 2026-09-21 mora aqui). O âmbito resolve-se em DOIS passos:
  rede → empresas → utilizadores dessas empresas.

  Aplicar `{"network_id": ...}` directamente a `users` devolveria sempre
  vazio — e um painel vazio parece uma base de dados vazia, não um
  filtro errado. Seria um defeito silencioso, do pior tipo.

FAIL-CLOSED, MAS SÓ QUANDO HÁ FRONTEIRA
  Um âmbito FECHADO sem empresas nenhumas devolve ZERO (a regra do
  `CONDICAO_IMPOSSIVEL` do Lote 4: uma condição impossível, nunca
  "sem filtro"). Um âmbito ABERTO — dev/CI sem `TENANT_DEFAULT_NETWORK_ID`
  — mantém o comportamento anterior, senão um deploy esvaziava o painel
  de administração de toda a gente ao mesmo tempo.

@module services/admin_users_scope
"""
import logging
from dataclasses import dataclass, field

from database import db
from services.tenant_network import (
    VALORES_SEM_EMPRESA,
    build_network_scope_condition,
    resolve_tenant_scope,
)
from utils.input_sanitization import escape_regex

logger = logging.getLogger(__name__)

#: Query que não casa com documento nenhum (os docs têm sempre `_id`).
QUERY_IMPOSSIVEL: dict = {"id": {"$in": []}}

#: Onde um utilizador pode ter o NOME da empresa gravado.
CAMPOS_EMPRESA_NO_UTILIZADOR: tuple[str, ...] = ("company", "company_name")


def _sem_empresa_nenhuma() -> dict:
    """Utilizador sem NENHUMA marca de empresa.

    `{"campo": {"$in": [None, ""]}}` no Mongo casa também com o campo
    AUSENTE — é o mesmo predicado para "nulo", "vazio" e "não existe".
    """
    vazios = list(VALORES_SEM_EMPRESA)
    return {
        "$and": [{campo: {"$in": vazios}} for campo in CAMPOS_EMPRESA_NO_UTILIZADOR]
    }


@dataclass(frozen=True)
class EmpresasDoAmbito:
    """As empresas que o utilizador pode administrar."""

    ids: list[str] = field(default_factory=list)
    nomes: list[str] = field(default_factory=list)
    #: `True` quando existe mesmo uma fronteira de rede a aplicar.
    fechado: bool = True
    #: As contas SEM empresa nenhuma entram neste âmbito?
    #:
    #: A pilha por carimbar segue a mesma regra dos documentos (Lote 4):
    #: pertence a quem detém a rede de omissão. Sem isto, uma conta órfã
    #: — tipicamente administração antiga, exactamente as que a
    #: Atribuição Rápida do Lote 4 veio impedir de nascer — desaparecia
    #: do painel no dia do deploy, e ninguém a poderia voltar a associar
    #: a uma empresa porque deixava de a ver.
    inclui_sem_empresa: bool = True


async def empresas_do_ambito(user: dict) -> EmpresasDoAmbito:
    """Empresas da rede de quem pede.

    Usa a MESMA condição de tenant das listagens de processos — o ponto
    único de `services/tenant_network.py`. Duplicar a cadeia aqui daria
    dois sítios a divergir, que é a raiz do incidente de 2026-09-21.
    """
    scope = await resolve_tenant_scope(user or {})
    condicao = build_network_scope_condition(scope)

    # SEM `try/except` de propósito. Engolir a falha devolvia um âmbito
    # vazio, o âmbito vazio devolve zero utilizadores (fail-closed), e o
    # painel ficava EM BRANCO sem dizer porquê — a falha de leitura
    # disfarçada de "não há nada", que é o defeito do ponto 13 noutro
    # sítio. Numa fronteira de segurança, falhar alto é o correcto: quem
    # chama traduz isto num erro visível.
    empresas = await db.companies.find(
        condicao, {"_id": 0, "id": 1, "name": 1}
    ).to_list(500)

    ids = [str(e["id"]) for e in empresas if e.get("id")]
    nomes = [str(e["name"]) for e in empresas if e.get("name")]
    return EmpresasDoAmbito(
        ids=ids,
        nomes=nomes,
        fechado=True,
        inclui_sem_empresa=bool(scope.inclui_rede_de_omissao),
    )


async def build_users_scope_query(ambito: EmpresasDoAmbito) -> dict:
    """Query Mongo que restringe `users` às empresas do âmbito.

    Apanha os DOIS caminhos: o UCR (id canónico) e o campo legado no
    próprio utilizador (o NOME). Um utilizador antigo sem UCR só tem o
    segundo; ignorá-lo fá-lo-ia desaparecer do painel.
    """
    if not ambito.fechado:
        return {}

    ramos: list[dict] = []

    if ambito.inclui_sem_empresa:
        # Contas órfãs: a pilha por carimbar pertence a quem detém a rede
        # de omissão, tal como nos documentos (Lote 4). Uma conta sem
        # empresa que desaparecesse do painel nunca mais podia ser
        # associada a uma, porque deixava de se ver.
        ramos.append(_sem_empresa_nenhuma())

    if ambito.ids or ambito.nomes:
        ucr_query: dict = {"$or": []}
        if ambito.ids:
            ucr_query["$or"].append({"company_id": {"$in": ambito.ids}})
        if ambito.nomes:
            ucr_query["$or"].append({"company_name": {"$in": ambito.nomes}})
        ucrs = await db.user_company_roles.find(
            ucr_query, {"_id": 0, "user_id": 1}
        ).to_list(10000)
        user_ids = [str(u["user_id"]) for u in ucrs if u.get("user_id")]
        if user_ids:
            ramos.append({"id": {"$in": user_ids}})

    if ambito.nomes:
        ramos.extend(
            {campo: {"$in": ambito.nomes}} for campo in CAMPOS_EMPRESA_NO_UTILIZADOR
        )

    # Fail-closed: sem ramos nenhuns, ZERO — nunca "sem filtro".
    return {"$or": ramos} if ramos else QUERY_IMPOSSIVEL


def build_users_search_condition(termo) -> dict | None:
    """Pesquisa por nome, email OU empresa.

    A pesquisa era feita no CLIENTE, sobre `name`/`email`, depois de
    trazer a tabela inteira — e não procurava por empresa, que é como um
    administrador procura alguém.

    `None` quer dizer "não filtrar": um ramo sempre presente esconderia
    os utilizadores sem os campos.
    """
    texto = str(termo or "").strip()
    if not texto:
        return None
    # Um `.` ou `(` num termo é regex, não texto: sem escape, pesquisar
    # "a.b" devolvia "axb".
    padrao = escape_regex(texto)
    campos = ("name", "email", *CAMPOS_EMPRESA_NO_UTILIZADOR)
    return {"$or": [{c: {"$regex": padrao, "$options": "i"}} for c in campos]}
