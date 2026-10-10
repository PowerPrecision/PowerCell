"""Quem pode mexer num evento do calendário (Lote 7, ponto 3).

O QUE A AUDITORIA ENCONTROU
===========================
Os três pontos de escrita e leitura de um evento tinham guardas diferentes,
e dois não tinham guarda nenhuma:

1. **`DELETE /deadlines/{id}` era `delete_one({"id": deadline_id})`.** Havia
   `require_roles` com todos os perfis de staff na rota — logo um consultor
   da Domus (que é uma ilha) apagava um evento da Power sabendo o id. Nem
   posse, nem rede, nem rasto no histórico.

2. **`PUT /deadlines/{id}` lia o evento por id e escrevia.** Além de
   atravessar redes, deixava **repontar `process_id`** para qualquer
   processo: um evento passava a pertencer a um processo que quem edita não
   pode ver, e o calendário da outra rede ganhava uma linha com o nome e o
   email do cliente (o `_enrich_calendar_rows` devolve os dois).

3. **`GET /deadlines?process_id=X` filtrava só por `process_id`** — sem
   verificar que o utilizador pode ver esse processo. Um título de prazo
   diz mais do que parece («Escritura Ana Martins — 2.ª hipoteca»).

A REGRA, NUM SÓ SÍTIO
=====================
`pode_mexer_no_evento` responde «este utilizador pode escrever neste
evento?» e é usada pelo `update` e pelo `delete`. Duas cópias da mesma
regra divergem na primeira mudança, e a que divergir não dá erro — deixa
escrever.

QUATRO DECISÕES
===============
1. **404 e não 403**, como nas notificações: distinguir «não existe» de
   «não é teu» confirma o id a quem está a adivinhar. O utilizador legítimo
   nunca vê este 404 porque o evento aparece-lhe na lista.

2. **A gestão tem bypass DENTRO da rede, não fora dela.** Um diretor é
   diretor da sua rede; o `TEAM_CALENDAR_ROLES` dá-lhe a agenda da equipa,
   não a agenda da Domus. O bypass global pertence ao papel `diretor` no
   sentido do produto (acesso total à SUA rede) e à ADMINISTRAÇÃO
   (admin/ceo), que reconciliam o sistema inteiro.

3. **Quem CRIOU o evento pode sempre mexer-lhe.** Um evento pessoal (uma
   ausência, um bloco de agenda) não tem processo nem empresa, logo
   nenhuma condição de rede o alcança; sem esta regra, o autor deixava de
   poder apagar a sua própria marcação — e isso nota-se, ao contrário de
   uma fuga.

4. **Um evento por carimbar é de quem lhe está ligado, não de todos.** A
   pilha antiga não tem `network_id`; a leitura aceita-a (senão desaparecem
   eventos que existem), mas a ESCRITA exige ligação — atribuição, autoria,
   ou um processo visível. É a assimetria deliberada do `sub35`: a leitura
   é generosa, a escrita é estrita.

Cobertura: `tests/unit/test_deadline_scope.py`.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from models.auth import UserRole
from services.deadlines_api_helpers import TEAM_CALENDAR_ROLES
from services.role_scope import PAPEIS_GLOBAIS, e_papel_global
from services.tenant_network import CAMPO_REDE, VALORES_SEM_EMPRESA

#: A fronteira de rede não se aplica a quem atravessa empresas — hoje só o
#: MASTER (adenda de RBAC, Out 2026). Até aí eram o Admin e o CEO, o que
#: fazia de cada um «dono do sistema inteiro»; a lista vive em
#: `services/role_scope.py` e não se escreve outra vez à mão.
PAPEIS_SEM_FRONTEIRA_DE_REDE = frozenset(PAPEIS_GLOBAIS)

#: Os campos pelos quais um evento fica ligado a uma pessoa.
CAMPOS_DE_PESSOA = (
    "created_by",
    "assigned_consultor_id",
    "assigned_mediador_id",
)


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def _papel_normalizado(papel: Any) -> str:
    return _texto(papel).lower()


def e_papel_sem_fronteira(papel: Any) -> bool:
    """Só o MASTER: atravessa empresas e reconcilia a pilha por carimbar."""
    return e_papel_global(papel)


def e_papel_de_equipa(papel: Any) -> bool:
    """Vê (e gere) a agenda da equipa — DENTRO da sua rede."""
    return _papel_normalizado(papel) in {
        _papel_normalizado(p) for p in TEAM_CALENDAR_ROLES
    }


def pessoas_do_evento(evento: Optional[dict]) -> set[str]:
    """Os ids ligados ao evento: atribuídos, responsáveis e autor."""
    evento = evento or {}
    ids: set[str] = set()
    for uid in evento.get("assigned_user_ids") or []:
        if _texto(uid):
            ids.add(_texto(uid))
    for campo in CAMPOS_DE_PESSOA:
        if _texto(evento.get(campo)):
            ids.add(_texto(evento[campo]))
    return ids


def esta_ligado_a_pessoa(evento: Optional[dict], user_id: Any) -> bool:
    uid = _texto(user_id)
    return bool(uid) and uid in pessoas_do_evento(evento)


def rede_do_evento(evento: Optional[dict]) -> str:
    """A rede carimbada no evento, ou "" se estiver por carimbar."""
    valor = _texto((evento or {}).get(CAMPO_REDE))
    return "" if valor in {_texto(v) for v in VALORES_SEM_EMPRESA} else valor


def evento_na_rede(evento: Optional[dict], redes: Iterable[str]) -> bool:
    """True quando a rede do evento está no âmbito dado.

    Um evento POR CARIMBAR devolve False de propósito: para a escrita, a
    ligação tem de ser provada por outra via (pessoa ou processo visível).
    Na leitura a pilha por carimbar entra pelo `build_network_scope_condition`,
    que é generoso por desenho — ver o cabeçalho.
    """
    rede = rede_do_evento(evento)
    if not rede:
        return False
    return rede in {_texto(r) for r in redes if _texto(r)}


def pode_mexer_no_evento(
    evento: Optional[dict],
    *,
    user_id: Any,
    papel: Any,
    redes: Iterable[str] = (),
    processos_visiveis: Iterable[str] = (),
) -> bool:
    """Pode este utilizador EDITAR ou ELIMINAR este evento?

    A ordem das provas é da mais barata e mais segura para a mais larga:

    1. não há evento → não;
    2. MASTER → sim (único perfil que atravessa redes);
    3. está ligado a si (atribuído, responsável ou **autor**) → sim;
    4. o evento é de um processo que o utilizador vê → sim;
    5. é papel de equipa E o evento está na sua rede → sim;
    6. o resto → não. **Falha fechada**, incluindo para o evento por
       carimbar sem nenhuma ligação: a leitura aceita-o, a escrita não.
    """
    if not evento:
        return False
    if e_papel_sem_fronteira(papel):
        return True
    if esta_ligado_a_pessoa(evento, user_id):
        return True

    processo = _texto(evento.get("process_id"))
    if processo and processo in {_texto(p) for p in processos_visiveis}:
        return True

    if e_papel_de_equipa(papel) and evento_na_rede(evento, redes):
        return True
    return False


def pode_apontar_para_o_processo(
    process_id: Any,
    *,
    papel: Any,
    processos_visiveis: Iterable[str] = (),
) -> bool:
    """Pode mover o evento PARA este processo?

    Separada da anterior porque a pergunta é outra: a de cima é sobre o
    evento que já existe, esta é sobre o DESTINO. Sem ela, um editor
    legítimo repontava um evento para o processo de outra rede e o
    calendário dessa rede ganhava uma linha com o nome e o email do
    cliente — o `_enrich_calendar_rows` devolve os dois.

    Limpar o processo (`None`/`""`) é sempre permitido: transforma o evento
    num evento geral e não revela nada.
    """
    destino = _texto(process_id)
    if not destino:
        return True
    if e_papel_sem_fronteira(papel):
        return True
    return destino in {_texto(p) for p in processos_visiveis}


__all__ = [
    "CAMPOS_DE_PESSOA",
    "PAPEIS_SEM_FRONTEIRA_DE_REDE",
    "e_papel_de_equipa",
    "e_papel_sem_fronteira",
    "esta_ligado_a_pessoa",
    "evento_na_rede",
    "pessoas_do_evento",
    "pode_apontar_para_o_processo",
    "pode_mexer_no_evento",
    "rede_do_evento",
]
