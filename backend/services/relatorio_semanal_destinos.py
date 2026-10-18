"""
====================================================================
RELATÓRIO DE SEGUNDA-FEIRA: UM POR REDE, PARA A GESTÃO DESSA REDE
====================================================================
(adenda de RBAC, Out 2026 — fecha o que a D-7 tinha deixado aberto)

O QUE ERA
  Um email CONSOLIDADO — a produtividade de todas as empresas — enviado
  a `CEO_EMAIL` ou, na falta, a todos os utilizadores com o papel `ceo`
  de qualquer empresa. Era «a única excepção deliberada ao isolamento por
  rede» (D-7): o CEO da Domus recebia, por email, o nome e os números de
  cada colaborador da Power. Com o Admin e o CEO passados a perfis
  LOCAIS, essa excepção deixa de ter dono.

O QUE É
  * **Um relatório por rede.** Cada rede é um âmbito fechado: o relatório
    de uma contém só as pessoas e os processos dessa rede.
  * **Destinatários = a gestão (CEO e Admin) DESSA rede** — quem tem um
    acesso `ceo` ou `admin` numa empresa da rede (UCR), mais as contas
    antigas só com o campo legado `users.company`. Quem gere duas redes
    recebe dois emails, um por rede: nunca um misturado.
  * **O consolidado existe: vai aos Master e a `CEO_EMAIL`.** Os utilizadores
    Master e os endereços de `CEO_EMAIL` — seja qual for o papel da conta
    desse endereço — recebem o relatório global (QA-7: o endereço do CEO
    configurado no deploy é uma decisão explícita do operador; antes era
    ignorado com aviso se a conta não fosse Master). Um CEO/Admin LOCAL
    que não esteja em `CEO_EMAIL` continua a receber só o da sua rede.
  * **A marca de «já enviei» é por destino**, não uma só: se o envio da
    rede A falhar, o ciclo horário seguinte repete só a A — e não manda
    outra vez à B, que já tem o dela.

PORQUE É QUE ISTO VIVE NUM MÓDULO PRÓPRIO
  A pergunta «a quem vai cada relatório» é a fronteira de segurança
  desta funcionalidade, e estava dentro de um método de 100 linhas do
  `scheduled_tasks`. Aqui é puro (a parte de decisão) e testável sem
  email nem agendador.
====================================================================
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from database import db
from services.role_scope import PAPEIS_GLOBAIS, e_papel_global
from services.tenant_network import (
    TenantScope,
    rede_de_omissao,
    resolve_network_id,
)

logger = logging.getLogger(__name__)

#: Os perfis que recebem o relatório da sua rede.
PAPEIS_DESTINATARIOS = ("ceo", "admin")

CHAVE_BASE = "relatorio_semanal_ceo"
CHAVE_GLOBAL = f"{CHAVE_BASE}:global"


@dataclass
class DestinoDoRelatorio:
    """Um relatório a gerar e a quem o mandar."""

    chave: str
    rotulo: str
    #: `None` = consolidado global (só Master).
    scope: Optional[TenantScope]
    destinatarios: list[dict] = field(default_factory=list)
    empresas: list[str] = field(default_factory=list)

    @property
    def emails(self) -> list[str]:
        return [d["email"] for d in self.destinatarios if d.get("email")]


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def _email_valido(valor: Any) -> bool:
    texto = _texto(valor)
    return "@" in texto and "placeholder.internal" not in texto


def chave_da_rede(rede: str) -> str:
    return f"{CHAVE_BASE}:{rede}"


def emails_configurados() -> list[str]:
    """Os endereços de `CEO_EMAIL` (minúsculas, sem repetidos)."""
    bruto = os.environ.get("CEO_EMAIL", "").strip()
    return list(dict.fromkeys(e.strip().lower() for e in bruto.split(",") if e.strip()))


def agrupar_por_rede(
    empresas: Iterable[dict],
    acessos: Iterable[dict],
    utilizadores: Iterable[dict],
    *,
    rede_omissao: Optional[str] = None,
) -> list[DestinoDoRelatorio]:
    """Decide, a partir de dados já lidos, quem recebe o relatório de cada rede.

    PURA — sem base de dados, sem ambiente — porque é a decisão de
    segurança e tem de se poder provar em testes sem email.

    * `empresas`: documentos de `companies` (`id`, `name`, `network_id`).
    * `acessos`: UCRs (`user_id`, `company_id`, `company_name`, `role`).
    * `utilizadores`: contas activas com email (`id`, `email`, `name`,
      `role`, `company`).

    Um utilizador Master nunca é destinatário de um relatório LOCAL: o dele
    é o global.
    """
    redes: dict[str, dict] = {}
    rede_por_empresa: dict[str, str] = {}

    for empresa in empresas:
        cid = _texto(empresa.get("id"))
        nome = _texto(empresa.get("name"))
        rede = resolve_network_id(empresa, company_id=cid or nome)
        if not rede:
            continue
        bloco = redes.setdefault(rede, {"ids": set(), "nomes": set(), "destinatarios": {}})
        if cid:
            bloco["ids"].add(cid)
            rede_por_empresa[cid.lower()] = rede
        if nome:
            bloco["nomes"].add(nome)
            rede_por_empresa[nome.lower()] = rede

    por_id = {_texto(u.get("id")): u for u in utilizadores if _texto(u.get("id"))}

    def _adicionar(rede: str, utilizador: dict) -> None:
        if e_papel_global(utilizador.get("role")):
            return
        if not _email_valido(utilizador.get("email")):
            return
        redes[rede]["destinatarios"][_texto(utilizador["id"])] = {
            "id": _texto(utilizador["id"]),
            "name": _texto(utilizador.get("name")),
            "email": _texto(utilizador["email"]).lower(),
        }

    for acesso in acessos:
        if _texto(acesso.get("role")).lower() not in PAPEIS_DESTINATARIOS:
            continue
        utilizador = por_id.get(_texto(acesso.get("user_id")))
        if not utilizador:
            continue
        rede = rede_por_empresa.get(_texto(acesso.get("company_id")).lower()) or rede_por_empresa.get(
            _texto(acesso.get("company_name")).lower()
        )
        if rede:
            _adicionar(rede, utilizador)

    # Contas antigas sem UCR: só têm o NOME da empresa em `users.company`.
    com_acesso = {_texto(a.get("user_id")) for a in acessos}
    for utilizador in por_id.values():
        if _texto(utilizador.get("id")) in com_acesso:
            continue
        if _texto(utilizador.get("role")).lower() not in PAPEIS_DESTINATARIOS:
            continue
        rede = rede_por_empresa.get(_texto(utilizador.get("company")).lower())
        if rede:
            _adicionar(rede, utilizador)

    destinos: list[DestinoDoRelatorio] = []
    for rede, bloco in sorted(redes.items()):
        if not bloco["destinatarios"]:
            logger.info("[RELATORIO-SEMANAL] Rede %s sem CEO/Admin — sem relatório.", rede)
            continue
        scope = TenantScope(
            network_ids=(rede,),
            company_ids=tuple(sorted(bloco["ids"])),
            company_names=tuple(sorted(bloco["nomes"])),
            inclui_rede_de_omissao=bool(rede_omissao) and rede == rede_omissao,
        )
        destinos.append(DestinoDoRelatorio(
            chave=chave_da_rede(rede),
            rotulo=", ".join(sorted(bloco["nomes"])) or rede,
            scope=scope,
            destinatarios=sorted(bloco["destinatarios"].values(), key=lambda d: d["email"]),
            empresas=sorted(bloco["nomes"]),
        ))
    return destinos


def destino_global(
    utilizadores: Iterable[dict],
    configurados: Iterable[str] = (),
) -> Optional[DestinoDoRelatorio]:
    """O consolidado: os Master e os endereços de `CEO_EMAIL`.

    O endereço configurado em `CEO_EMAIL` é uma decisão explícita de quem opera o deploy («envia o
    consolidado para este endereço»), por isso recebe-o MESMO que a conta não seja Master — a regra
    anterior descartava-o com um aviso e o CEO da empresa ficava sem relatório. A porta continua a ser
    a variável de ambiente (quem a escreve é o operador), nunca um perfil de utilizador: um CEO/Admin
    local NÃO recebe o consolidado por ter esse papel.
    """
    por_email: dict[str, dict] = {}
    for u in utilizadores:
        if e_papel_global(u.get("role")) and _email_valido(u.get("email")):
            por_email[_texto(u["email"]).lower()] = {
                "id": _texto(u.get("id")), "name": _texto(u.get("name")), "email": _texto(u["email"]).lower(),
            }
    por_conta = {_texto(u.get("email")).lower(): u for u in utilizadores if _email_valido(u.get("email"))}
    for endereco in configurados:
        email = _texto(endereco).lower()
        if not _email_valido(email) or email in por_email:
            continue
        conta = por_conta.get(email) or {}
        por_email[email] = {"id": _texto(conta.get("id")), "name": _texto(conta.get("name")), "email": email}
    destinatarios = [por_email[e] for e in sorted(por_email)]
    if not destinatarios:
        return None
    return DestinoDoRelatorio(
        chave=CHAVE_GLOBAL,
        rotulo="Consolidado (todas as empresas)",
        scope=TenantScope(inclui_rede_de_omissao=True, sem_fronteira=True),
        destinatarios=destinatarios,
        empresas=[],
    )


# ─────────────────────────────────────────────────────────────────────
# RELATÓRIO DE IA (Lote 3, Out 2026)
# ─────────────────────────────────────────────────────────────────────
# O relatório de extracções de IA tinha a mesma forma do consolidado de segunda-feira
# que a adenda de RBAC fechou: somava os processos de TODAS as redes e enviava-os a
# «admins» (todos os Admin/CEO de todas as redes — perfis locais), «all_staff» (todos
# os utilizadores activos, de todas as redes) ou a uma lista de ids sem confinar. Passa a
# usar os MESMOS destinos: um relatório por rede, calculado sobre os processos dessa
# rede, para quem a configuração diz DENTRO dessa rede; o consolidado só vai aos Master.

CHAVE_RELATORIO_IA = "relatorio_ia"

TIPOS_DE_DESTINATARIOS_IA = ("admins", "all_staff", "custom")

#: Contas que não são equipa: nunca entram em «toda a equipa».
PAPEIS_QUE_NAO_SAO_EQUIPA = ("cliente", "parceiro")


def chave_do_relatorio_ia(destino: DestinoDoRelatorio) -> str:
    """A marca de «já enviei neste período», por destino (como a do relatório de segunda)."""
    sufixo = destino.chave.split(":", 1)[1] if ":" in destino.chave else "global"
    return f"{CHAVE_RELATORIO_IA}:{sufixo}"


def _consolidado(destino: DestinoDoRelatorio) -> bool:
    return destino.scope is None or bool(destino.scope.sem_fronteira)


async def _emails_da_equipa(destino: DestinoDoRelatorio, base) -> set[str]:
    """Os emails da equipa activa de uma REDE (UCR numa das suas empresas, ou conta antiga).

    Master, clientes e parceiros nunca contam como «equipa» da rede. A conta antiga
    (só `users.company`, o NOME) só conta se não tiver NENHUM UCR — quem tem UCR já foi
    colocado pelos acessos.
    """
    scope = destino.scope
    if scope is None:
        return set()
    ids = list(scope.company_ids)
    nomes = list(scope.company_names)
    if not ids and not nomes:
        return set()

    ucrs = await base.user_company_roles.find(
        {
            "$or": [{"company_id": {"$in": ids + nomes}}, {"company_name": {"$in": nomes + ids}}],
            "is_deleted": {"$ne": True},
            "is_active": {"$ne": False},
        },
        {"_id": 0, "user_id": 1},
    ).to_list(20000)
    com_acesso_aqui = {_texto(u.get("user_id")) for u in ucrs if _texto(u.get("user_id"))}

    candidatos = await base.users.find(
        {
            "is_active": {"$ne": False},
            "$or": [{"id": {"$in": sorted(com_acesso_aqui)}}, {"company": {"$in": nomes}}],
        },
        {"_id": 0, "id": 1, "email": 1, "role": 1, "company": 1},
    ).to_list(5000)

    so_legados = [
        _texto(u.get("id")) for u in candidatos
        if _texto(u.get("id")) not in com_acesso_aqui
    ]
    com_ucr_noutro_lado: set[str] = set()
    if so_legados:
        outros = await base.user_company_roles.find(
            {"user_id": {"$in": so_legados}, "is_deleted": {"$ne": True}},
            {"_id": 0, "user_id": 1},
        ).to_list(20000)
        com_ucr_noutro_lado = {_texto(o.get("user_id")) for o in outros}

    emails: set[str] = set()
    for utilizador in candidatos:
        uid = _texto(utilizador.get("id"))
        if uid not in com_acesso_aqui and uid in com_ucr_noutro_lado:
            continue
        papel = _texto(utilizador.get("role")).lower()
        if e_papel_global(papel) or papel in PAPEIS_QUE_NAO_SAO_EQUIPA:
            continue
        if _email_valido(utilizador.get("email")):
            emails.add(_texto(utilizador["email"]).lower())
    return emails


async def destinatarios_do_relatorio_de_ia(
    destino: DestinoDoRelatorio,
    tipo: str,
    custom_ids: Iterable[str] = (),
    base=None,
) -> list[str]:
    """Os emails que recebem o relatório de IA deste destino, segundo a configuração.

    * `admins` — a gestão do destino (CEO/Admin da rede; Master no consolidado).
    * `all_staff` — toda a equipa DA REDE; o consolidado, por atravessar redes, só os Master.
    * `custom` — os ids escolhidos que pertencem ao destino: da rede, ou Master no
      consolidado. Um id de outra rede NÃO recebe o relatório desta.

    Um tipo desconhecido cai no mais estreito (`admins`). Nunca devolve emails fora do
    destino, qualquer que seja o tipo configurado.
    """
    base = base if base is not None else db
    tipo = (_texto(tipo) or "admins").lower()
    if tipo not in TIPOS_DE_DESTINATARIOS_IA:
        tipo = "admins"

    if tipo == "admins":
        return sorted(set(destino.emails))

    permitidos = set(destino.emails) if _consolidado(destino) else await _emails_da_equipa(destino, base)
    if tipo == "all_staff":
        return sorted(permitidos)

    ids = [i for i in dict.fromkeys(_texto(i) for i in custom_ids) if i]
    if not ids:
        return []
    escolhidos = await base.users.find(
        {"id": {"$in": ids}, "is_active": {"$ne": False}}, {"_id": 0, "email": 1},
    ).to_list(len(ids))
    emails = {
        _texto(u["email"]).lower() for u in escolhidos if _email_valido(u.get("email"))
    }
    return sorted(emails & permitidos)


async def montar_destinos(base=None) -> list[DestinoDoRelatorio]:
    """Lê os dados e devolve os relatórios a enviar (um por rede + o global)."""
    base = base if base is not None else db

    empresas = await base.companies.find(
        {"is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1, "network_id": 1},
    ).to_list(1000)
    acessos = await base.user_company_roles.find(
        {
            "role": {"$in": list(PAPEIS_DESTINATARIOS)},
            "is_deleted": {"$ne": True},
            "is_active": {"$ne": False},
        },
        {"_id": 0, "user_id": 1, "company_id": 1, "company_name": 1, "role": 1},
    ).to_list(5000)
    todos_com_acesso = await base.user_company_roles.find(
        {"is_deleted": {"$ne": True}, "is_active": {"$ne": False}},
        {"_id": 0, "user_id": 1},
    ).to_list(20000)
    utilizadores = await base.users.find(
        {
            "is_active": {"$ne": False},
            "$or": [
                {"role": {"$in": [*PAPEIS_DESTINATARIOS, *PAPEIS_GLOBAIS]}},
                {"id": {"$in": sorted({_texto(a.get("user_id")) for a in acessos})}},
            ],
        },
        {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1, "company": 1},
    ).to_list(5000)

    # `acessos` para a decisão tem de incluir TODOS os UCRs de quem tem
    # conta antiga: só quem não aparece em nenhum UCR cai no campo legado.
    ids_com_ucr = {_texto(a.get("user_id")) for a in todos_com_acesso}
    acessos_para_decisao = [
        *acessos,
        *({"user_id": uid, "role": ""} for uid in ids_com_ucr - {_texto(a.get("user_id")) for a in acessos}),
    ]

    destinos = agrupar_por_rede(
        empresas, acessos_para_decisao, utilizadores, rede_omissao=rede_de_omissao(),
    )
    global_ = destino_global(utilizadores, emails_configurados())
    if global_:
        destinos.append(global_)
    return destinos
