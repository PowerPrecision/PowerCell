"""Quem vê e quem mexe numa visita — `db.visits` (Lote 9, parte 2, D-21).

O QUE CORREU MAL
================
A colecção `visits` não tinha filtro de tenant NENHUM, e tinha as TRÊS
formas do defeito ao mesmo tempo:

1. **Listagens abertas.** `run_list_visits` e `run_get_visits_kanban`
   abriam com `query = {}` e o único recorte era
   `if user_role in ["consultor", "intermediario"]` por atribuição. Logo
   um **diretor, administrativo, admin ou CEO via as visitas de TODAS as
   redes** — e o documento leva `client_name`, `client_email` e
   `client_phone`. A Domus é uma ilha. Os dois papéis que escapavam
   escapavam **por acidente**, como o `run_get_my_tasks`, e foi essa
   metade a funcionar que escondeu a outra.

2. **Escritas sem posse.** `run_get_visit`, `run_update_visit` e
   `run_cancel_visit` faziam `find_one({"id": visit_id})` e mais nada. O
   `require_roles`/`get_current_user` da rota autoriza o VERBO, não o
   OBJECTO — é literalmente o `run_delete_deadline` do Lote 7.

3. **Carimbo errado na criação.** `visit_list_create` gravava
   `"company_id": user.get("company_id")`, e o documento de utilizador tem
   `company` (o NOME); o `company_id` vive no UCR. Toda a visita criada
   pela equipa nascia com `company_id: None`, e `network_id` não existia
   em sítio nenhum da colecção.

O papel era lido de `user["role"]` (o do JWT) e não do EFECTIVO: 5.ª
ocorrência da forma do `history._is_stealth_user`.

PORQUE É QUE O CONJUNTO DE EQUIPA NÃO É O DO CALENDÁRIO
=======================================================
`TEAM_CALENDAR_ROLES` é {ADMIN, CEO, DIRETOR}. Aqui entra também o
**ADMINISTRATIVO**: é o back-office que marca e remarca visitas, muitas
vezes para outra pessoa, e estreitá-lo a «só as minhas» fazia-o perder de
vista o que ele próprio agendou — e **uma visita que desaparece não
produz erro nenhum**, que é a forma de defeito desta casa. Ficam de fora
`indexacao` (tem carimbo próprio e nunca é um atribuído) e `parceiro`
(conta fantasma): esses vêem só o que lhes está ligado.

**Consequência operacional, dita de propósito:** para `administrativo` o
âmbito ESTREITA de «todas as redes» para «a sua rede». É a mesma mudança
que o calendário sofreu no Lote 7 e vai no sentido seguro.

DUAS PERGUNTAS, DUAS FUNÇÕES
============================
`pode_mexer_na_visita` é sobre a visita que JÁ existe;
`pode_atribuir_a_consultor` é sobre o DESTINO. Juntá-las numa deixava a
segunda por fazer, e é a segunda que impede o `PATCH` de reatribuir uma
visita a um consultor de OUTRA rede — o que lhe entregava na lista o
nome, o email e o telefone de um cliente que não é dele. É a mesma
separação do `pode_apontar_para_o_processo` do calendário, pelo mesmo
motivo.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from models.auth import UserRole
from services.deadline_scope import (
    PAPEIS_SEM_FRONTEIRA_DE_REDE,
    e_papel_sem_fronteira,
)
from services.tenant_network import CAMPO_REDE, VALORES_SEM_EMPRESA

#: A mesma mensagem para "não existe" e para "não é tua": distinguir as
#: duas confirma o id a quem está a adivinhar (precedente das
#: notificações, e o legítimo nunca a vê porque a visita aparece-lhe na
#: lista).
ERRO_VISITA_NAO_ENCONTRADA = "Visita não encontrada"

#: Vêem as visitas da EQUIPA — dentro da sua rede. Ver a docstring do
#: módulo para o motivo de o `administrativo` estar aqui e não no
#: conjunto do calendário.
PAPEIS_QUE_VEEM_AS_VISITAS_DA_EQUIPA = frozenset({
    UserRole.MASTER, UserRole.ADMIN,
    UserRole.CEO,
    UserRole.DIRETOR,
    UserRole.ADMINISTRATIVO,
})

#: Os campos pelos quais uma visita fica ligada a uma pessoa. O
#: `created_by` entra porque quem agendou pode sempre mexer (regra 3 do
#: `deadline_scope`): sem ele, o administrativo que marcou a visita de um
#: consultor deixava de a poder remarcar.
CAMPOS_DE_PESSOA = (
    "consultor_id",
    "consultor_ids",
    "created_by",
)

#: Onde vive o processo de uma visita. `client_id` é o nome LEGADO do
#: mesmo valor (`process_id = client_id` na arquitectura actual) e o
#: Portal grava os dois — ler só um deixava metade das visitas sem
#: processo, logo invisíveis a quem trata do processo.
CAMPOS_DE_PROCESSO = ("process_id", "client_id")


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def _papel_normalizado(papel: Any) -> str:
    return _texto(papel).lower()


def e_papel_de_equipa_nas_visitas(papel: Any) -> bool:
    """Vê (e gere) as visitas da equipa — DENTRO da sua rede."""
    return _papel_normalizado(papel) in {
        _papel_normalizado(p) for p in PAPEIS_QUE_VEEM_AS_VISITAS_DA_EQUIPA
    }


def pessoas_da_visita(visita: Optional[dict]) -> set[str]:
    """Os ids ligados à visita: consultor(es) e autor."""
    ids: set[str] = set()
    for campo in CAMPOS_DE_PESSOA:
        valor = (visita or {}).get(campo)
        if isinstance(valor, (list, tuple, set)):
            ids.update(_texto(v) for v in valor if _texto(v))
        elif _texto(valor):
            ids.add(_texto(valor))
    return ids


def esta_ligado_a_pessoa(visita: Optional[dict], user_id: Any) -> bool:
    uid = _texto(user_id)
    return bool(uid) and uid in pessoas_da_visita(visita)


def processos_da_visita(visita: Optional[dict]) -> set[str]:
    return {
        _texto((visita or {}).get(campo))
        for campo in CAMPOS_DE_PROCESSO
        if _texto((visita or {}).get(campo))
    }


def rede_da_visita(visita: Optional[dict]) -> str:
    return _texto((visita or {}).get(CAMPO_REDE))


def visita_na_rede(visita: Optional[dict], redes: Iterable[str]) -> bool:
    """A visita está numa das redes do utilizador?

    Uma visita POR CARIMBAR (sem rede) entra: é a pilha anterior ao
    isolamento, e cegá-la no dia do deploy esconderia trabalho real a
    quem o tem de fazer. É a mesma tolerância do
    `build_network_scope_condition`, e desaparece à medida que a migração
    carimba.
    """
    rede = rede_da_visita(visita)
    if not rede or rede in VALORES_SEM_EMPRESA:
        return True
    return rede in {_texto(r) for r in redes if _texto(r)}


def pode_ver_visita(
    visita: Optional[dict],
    *,
    user_id: Any,
    papel: Any,
    redes: Iterable[str] = (),
    processos_visiveis: Iterable[str] = (),
) -> bool:
    """Pode este utilizador LER esta visita?

    A ordem das provas é da mais barata e mais segura para a mais larga:

    1. não há visita → não;
    2. ADMIN/CEO → sim (reconciliam a pilha inteira);
    3. está ligado a si (consultor ou autor) → sim;
    4. a visita é de um processo que o utilizador vê → sim;
    5. é papel de equipa E a visita está na sua rede → sim;
    6. o resto → não. **Falha fechada.**
    """
    if not visita:
        return False
    if e_papel_sem_fronteira(papel):
        return True
    if esta_ligado_a_pessoa(visita, user_id):
        return True

    visiveis = {_texto(p) for p in processos_visiveis if _texto(p)}
    if processos_da_visita(visita) & visiveis:
        return True

    if e_papel_de_equipa_nas_visitas(papel) and visita_na_rede(visita, redes):
        return True
    return False


def pode_mexer_na_visita(
    visita: Optional[dict],
    *,
    user_id: Any,
    papel: Any,
    redes: Iterable[str] = (),
    processos_visiveis: Iterable[str] = (),
) -> bool:
    """Pode EDITAR ou CANCELAR esta visita?

    Hoje é a mesma resposta da leitura, e isso é uma DECISÃO e não um
    descuido: uma visita é um compromisso de agenda entre um consultor e
    um cliente, e quem a vê na lista é quem a remarca ou cancela ao
    telefone. Fica como função própria porque a pergunta é outra — se um
    dia a escrita tiver de ser mais estrita (como no calendário, onde a
    visita por carimbar entra na leitura e não na escrita), é aqui que
    muda, e os chamadores não precisam de saber.
    """
    return pode_ver_visita(
        visita,
        user_id=user_id,
        papel=papel,
        redes=redes,
        processos_visiveis=processos_visiveis,
    )


def pode_atribuir_a_consultor(
    redes_do_consultor: Iterable[str],
    *,
    papel: Any,
    redes: Iterable[str] = (),
) -> bool:
    """Pode passar a visita para ESTE consultor?

    A pergunta do DESTINO. Sem ela, o `PATCH` reatribuía uma visita a um
    consultor de outra rede e a lista dele ganhava uma linha com o nome,
    o email e o telefone de um cliente que não é dele — o mesmo buraco
    que o `pode_apontar_para_o_processo` fechou no calendário.

    **Falha fechada:** um consultor sem rede determinável é recusado. Um
    utilizador órfão de empresa recebe a rede de omissão no
    `resolve_tenant_scope`, pelo que um conjunto vazio aqui significa que
    nem isso se conseguiu resolver.
    """
    if e_papel_sem_fronteira(papel):
        return True
    dele = {_texto(r) for r in redes_do_consultor if _texto(r)}
    if not dele:
        return False
    minhas = {_texto(r) for r in redes if _texto(r)}
    return bool(dele & minhas)


def condicao_pessoal(user_id: Any) -> list[dict]:
    """Os ramos Mongo de «esta visita está ligada a mim».

    Derivam de `CAMPOS_DE_PESSOA` — uma lista escrita à mão aqui seria a
    segunda cópia, e a que divergir deixa ver ou esconde. No Mongo,
    `{"campo": valor}` casa com o escalar E com o array que o contém,
    logo o mesmo ramo serve `consultor_id` e `consultor_ids`.
    """
    uid = _texto(user_id)
    if not uid:
        return []
    return [{campo: uid} for campo in CAMPOS_DE_PESSOA]


def ramo_dos_processos(processos: Iterable[str]) -> dict:
    """«A visita é de um destes processos», nos dois nomes do campo.

    Um conjunto VAZIO devolve uma condição impossível e **nunca** `{}`:
    `{}` casa com tudo e era a forma de a guarda se desligar sozinha
    (precedente do `{"process_id": None}` do calendário, que casava com
    todos os eventos gerais).
    """
    ids = sorted({_texto(p) for p in processos if _texto(p)})
    if not ids:
        return {"id": {"$in": []}}
    return {"$or": [{campo: {"$in": ids}} for campo in CAMPOS_DE_PROCESSO]}


def build_visit_rbac_condition(
    *,
    user_id: Any,
    papel: Any,
    processos_visiveis: Iterable[str] = (),
) -> dict:
    """O recorte da LISTAGEM, por dentro da condição de rede.

    Para ADMIN/CEO e para os papéis de equipa é `{}`: o âmbito é a
    condição de REDE, aplicada por fora com o `com_isolamento` — nunca um
    `{}` escrito à mão que atravessa redes de propósito (é a nota do
    `run_get_deadlines`).
    """
    if e_papel_sem_fronteira(papel) or e_papel_de_equipa_nas_visitas(papel):
        return {}
    ramos = [*condicao_pessoal(user_id), ramo_dos_processos(processos_visiveis)]
    return {"$or": ramos}


__all__ = [
    "CAMPOS_DE_PESSOA",
    "CAMPOS_DE_PROCESSO",
    "ERRO_VISITA_NAO_ENCONTRADA",
    "PAPEIS_QUE_VEEM_AS_VISITAS_DA_EQUIPA",
    "PAPEIS_SEM_FRONTEIRA_DE_REDE",
    "build_visit_rbac_condition",
    "condicao_pessoal",
    "e_papel_de_equipa_nas_visitas",
    "esta_ligado_a_pessoa",
    "pessoas_da_visita",
    "pode_atribuir_a_consultor",
    "pode_mexer_na_visita",
    "pode_ver_visita",
    "processos_da_visita",
    "ramo_dos_processos",
    "rede_da_visita",
    "visita_na_rede",
]
