"""
====================================================================
CAIXAS PARTILHADAS POR CARGO — A REDE É PARTE DA IDENTIDADE (D-8)
====================================================================

O QUE ESTAVA ERRADO
  `shared_role_email_configs` tinha UMA linha por cargo (`indexacao`,
  `suporte`, `comercial`, `admin`) para o sistema inteiro. Tudo o que lia ou
  escrevia uma caixa partilhada identificava-a só pelo cargo:

    * a configuração (IMAP/SMTP, refresh token do Google) era única — o
      Admin da Domus editava, via OAuth, a caixa de Indexação da Power;
    * os emails sincronizados levavam `shared_role` e nenhuma rede, e a regra
      de leitura «caixa partilhada do seu cargo» dava a TODOS os utilizadores
      `indexacao` de TODAS as redes os emails da caixa de Indexação — que
      leva os documentos e os dados de clientes de cada rede;
    * o aviso em tempo real (`new_email`) ia a todos os utilizadores com o
      cargo, de qualquer rede.

  Num SaaS que serve redes concorrentes isto cruza emails entre elas.

O QUE É AGORA
  A caixa partilhada identifica-se por **(cargo, rede)**. A configuração
  leva `network_id`; cada email sincronizado herda o da configuração; a
  leitura exige o email no âmbito de rede de quem pergunta.

  * **A rede em contexto de quem administra** é a da empresa activa
    (`X-Company-Id`) — o mesmo contexto do workflow e dos formulários
    (`workflow_scope.rede_em_contexto`). O Master escolhe a empresa no
    seletor; Admin/CEO só administram as redes do seu âmbito (404 fora dele).
  * **Sem `network_id` = a pilha antiga**, que pertence à rede de omissão
    (`TENANT_DEFAULT_NETWORK_ID`). Foi assim que todas as outras colecções
    se migraram sem partir produção: nada se apaga, nada se move, e a
    configuração e os emails que já lá estavam continuam a ser do grupo que
    sempre os usou. Sem `TENANT_DEFAULT_NETWORK_ID` (dev/CI) mantém-se o
    comportamento anterior.
  * **Esquecer a rede fecha, não abre.** Uma chamada que não diga a rede só
    alcança a pilha por carimbar — nunca a configuração de uma rede
    concreta. O contrário («sem rede = todas») é o placebo do
    `build_company_scope_condition`.

QUEM RECEBE UM EMAIL NOVO
  `notify_new_email_for_shared_role` avisava todos os utilizadores com o
  cargo. Agora só os que têm o email no seu âmbito de rede
  (`destinatarios_da_caixa`).

O QUE NÃO MUDA, DE PROPÓSITO
  * Os cargos continuam a ser os mesmos (`ALLOWED_ROLES`).
  * Os emails já sincronizados sem carimbo continuam por carimbar até ao
    backfill (`scripts/backfill_shared_mailbox_network_id.py`), mas deixam de
    ser lidos por quem não é da rede de omissão — a leitura resolve-se pelo
    mesmo predicado de todas as outras colecções (`documento_no_ambito`).
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from database import db
from services.tenant_network import (
    CAMPO_REDE,
    TenantScope,
    build_network_scope_condition,
    com_isolamento,
    documento_no_ambito,
    rede_de_omissao,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

COLECCAO = "shared_role_email_configs"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def ambito_da_caixa(rede: Optional[str]) -> TenantScope:
    """O âmbito de UMA caixa: a rede dela e, só para a rede de omissão, a pilha antiga.

    `rede=None` («não sei de que rede é») só alcança a pilha por carimbar.
    """
    rede = _texto(rede)
    if not rede:
        return TenantScope(inclui_rede_de_omissao=True)
    omissao = rede_de_omissao()
    return TenantScope(
        network_ids=(rede,),
        inclui_rede_de_omissao=(not omissao) or rede == omissao,
    )


def condicao_da_caixa(role: str, rede: Optional[str]) -> dict:
    """Filtro Mongo da configuração de (cargo, rede). A única forma de a pedir."""
    return com_isolamento(
        build_network_scope_condition(ambito_da_caixa(rede)),
        {"role": role},
    )


def e_a_pilha_antiga(rede: Optional[str]) -> bool:
    """A «rede» pedida é a da pilha antiga (a de omissão, ou nenhuma em dev/CI)?

    Serve para a única coisa que não é multi-rede por natureza: a caixa de
    SISTEMA (`system_webmail`, Integrações), que é infra do grupo incumbente e
    não de uma ilha.
    """
    rede = _texto(rede)
    omissao = rede_de_omissao()
    return not rede or not omissao or rede == omissao


def rede_da_config(config: Optional[dict]) -> Optional[str]:
    """A rede a que uma configuração pertence (a pilha antiga → a de omissão)."""
    carimbo = _texto((config or {}).get(CAMPO_REDE))
    return carimbo or (rede_de_omissao() or None)


def duplicado_da_caixa(message_id: str, role: str, config: Optional[dict], **extra: Any) -> dict:
    """Filtro do «já sincronizei este email?» — DENTRO da rede da caixa.

    O mesmo Message-ID chega às caixas de duas redes quando o email foi para
    ambas; com um filtro global a segunda rede achava-o duplicado e ficava
    sem a sua cópia.
    """
    return com_isolamento(
        build_network_scope_condition(ambito_da_caixa(rede_da_config(config))),
        {"message_id": message_id, "shared_role": role, **extra},
    )


def carimbo_da_caixa(config: Optional[dict]) -> dict:
    """O que se acrescenta a um email sincronizado dessa caixa (vazio sem rede)."""
    rede = rede_da_config(config)
    return {CAMPO_REDE: rede} if rede else {}


async def config_da_caixa(
    role: str,
    rede: Optional[str],
    projeccao: Optional[dict] = None,
    **filtro_extra: Any,
) -> Optional[dict]:
    """A configuração de (cargo, rede), ou ``None``."""
    filtro = condicao_da_caixa(role, rede)
    if filtro_extra:
        filtro = {"$and": [filtro, filtro_extra]}
    return await db.shared_role_email_configs.find_one(filtro, projeccao or {"_id": 0})


async def configs_da_rede(rede: Optional[str], projeccao: Optional[dict] = None, limite: int = 50) -> list[dict]:
    """Todas as configurações de uma rede (para a listagem de administração)."""
    filtro = com_isolamento(build_network_scope_condition(ambito_da_caixa(rede)), {})
    return await db.shared_role_email_configs.find(filtro, projeccao or {"_id": 0}).to_list(limite)


async def caixas_a_sincronizar() -> list[tuple[str, Optional[str]]]:
    """Os pares (cargo, rede) com caixa configurada — o que o worker percorre.

    Antes o worker percorria os CARGOS que existiam entre os utilizadores
    (`users.distinct("role")`), o que com duas redes sincronizava uma caixa só
    e a dava a todas.
    """
    configs = await db.shared_role_email_configs.find(
        {"is_configured": True}, {"_id": 0, "role": 1, CAMPO_REDE: 1},
    ).to_list(200)
    pares: list[tuple[str, Optional[str]]] = []
    for cfg in configs:
        par = (_texto(cfg.get("role")), rede_da_config(cfg))
        if par[0] and par not in pares:
            pares.append(par)
    return pares


async def configs_do_utilizador(
    role: str,
    user: dict,
    projeccao: Optional[dict] = None,
    **filtro_extra: Any,
) -> list[dict]:
    """As configurações do cargo que estão no âmbito de rede do utilizador."""
    scope = await resolve_tenant_scope(user)
    filtro: dict = com_isolamento(build_network_scope_condition(scope), {"role": role})
    if filtro_extra:
        filtro = {"$and": [filtro, filtro_extra]}
    configs = await db.shared_role_email_configs.find(filtro, projeccao or {"_id": 0}).to_list(20)
    return sorted(configs, key=lambda c: _texto(c.get(CAMPO_REDE)))


async def config_do_utilizador(
    role: str,
    user: dict,
    projeccao: Optional[dict] = None,
    **filtro_extra: Any,
) -> Optional[dict]:
    """A caixa partilhada do cargo, **na rede de quem pergunta**.

    Um utilizador em duas redes com o mesmo cargo teria duas: aqui escolhe-se
    de forma determinística (ordem da rede) e diz-se no log — o envio e a
    sincronização do cargo não podem depender da ordem do Mongo.
    """
    configs = await configs_do_utilizador(role, user, projeccao, **filtro_extra)
    if len(configs) > 1:
        logger.info(
            "[SharedMailbox] %s tem %s caixas do cargo '%s' (redes %s): usa a primeira.",
            (user or {}).get("id"), len(configs), role,
            [c.get(CAMPO_REDE) for c in configs],
        )
    return configs[0] if configs else None


def email_no_ambito(email: Optional[dict], scope: TenantScope) -> bool:
    """Este email de caixa partilhada está no âmbito de rede de quem pergunta?"""
    return documento_no_ambito(email, scope)


async def condicao_de_emails_da_caixa(role: str, user: dict) -> dict:
    """Condição Mongo dos emails `shared_role=<cargo>` que ESTE utilizador pode ver.

    O cargo isolado nunca basta: é o cargo **dentro do âmbito de rede**.
    """
    scope = await resolve_tenant_scope(user)
    return {"$and": [{"shared_role": role}, build_network_scope_condition(scope)]}


async def destinatarios_da_caixa(role: str, email_doc: dict) -> list[str]:
    """Os utilizadores com o cargo que têm este email no seu âmbito de rede."""
    if not role:
        return []
    ids: list[str] = []
    cursor = db.users.find(
        {"role": role, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "role": 1, "company": 1},
    )
    async for utilizador in cursor:
        uid = utilizador.get("id")
        if not uid:
            continue
        try:
            scope = await resolve_tenant_scope(utilizador)
        except Exception as exc:  # noqa: BLE001 — falha fechada: sem âmbito, sem aviso
            logger.warning("[SharedMailbox] Âmbito de %s indisponível (%s): sem aviso.", uid, exc)
            continue
        if email_no_ambito(email_doc, scope):
            ids.append(uid)
    return ids


__all__ = [
    "COLECCAO",
    "ambito_da_caixa",
    "caixas_a_sincronizar",
    "carimbo_da_caixa",
    "condicao_da_caixa",
    "condicao_de_emails_da_caixa",
    "duplicado_da_caixa",
    "config_da_caixa",
    "config_do_utilizador",
    "configs_da_rede",
    "configs_do_utilizador",
    "destinatarios_da_caixa",
    "e_a_pilha_antiga",
    "email_no_ambito",
    "rede_da_config",
]
