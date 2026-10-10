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
  * **O consolidado existe, e é do Master.** Os utilizadores Master (e
    os endereços de `CEO_EMAIL` que SEJAM Master) recebem o relatório
    global. Um endereço de `CEO_EMAIL` que não seja Master é IGNORADO, com
    aviso: era a porta por onde o consolidado podia chegar a quem não
    devia, e não há forma de o distinguir de uma opção deliberada sem
    isto.
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
    """O consolidado: só para Master.

    Os endereços de `CEO_EMAIL` só valem se pertencerem a um Master activo;
    os restantes são descartados com aviso (nunca em silêncio).
    """
    masters = {
        _texto(u["email"]).lower(): u
        for u in utilizadores
        if e_papel_global(u.get("role")) and _email_valido(u.get("email"))
    }
    destinatarios = [
        {"id": _texto(u.get("id")), "name": _texto(u.get("name")), "email": email}
        for email, u in sorted(masters.items())
    ]
    for endereco in configurados:
        if _texto(endereco).lower() not in masters:
            logger.warning(
                "[RELATORIO-SEMANAL] O endereço %r de CEO_EMAIL não pertence a "
                "um utilizador Master activo: NÃO recebe o consolidado (atravessa "
                "empresas). Se é gestão de uma empresa, recebe o relatório da sua "
                "rede enquanto CEO/Admin.", endereco,
            )
    if not destinatarios:
        return None
    return DestinoDoRelatorio(
        chave=CHAVE_GLOBAL,
        rotulo="Consolidado (todas as empresas)",
        scope=TenantScope(inclui_rede_de_omissao=True, sem_fronteira=True),
        destinatarios=destinatarios,
        empresas=[],
    )


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
