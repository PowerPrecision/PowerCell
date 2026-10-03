"""
====================================================================
SINCRONIZAÇÃO DE WEBMAIL DO WORKER (rede de segurança)
====================================================================
Lote 2, ponto 1 — extraído de `worker.py`.

PORQUE É QUE SAIU DO `worker.py`
  Eram ~113 linhas em linha dentro do `scheduler_loop`, com o seu
  próprio `try`. Isso tinha duas consequências, e nenhuma delas era o
  tamanho do ficheiro:

  1. **O batimento não embrulhava o trabalho.** O
     `_bater_webmail_worker_sync` abria e fechava um `heartbeat` com um
     `pass` lá dentro e o trabalho corria A SEGUIR, fora do envelope. O
     painel dizia `ok` a um ciclo em que TODAS as caixas podiam ter
     falhado, e a duração registada era de microssegundos. Um monitor que
     mente com ar de autoridade é pior do que não ter monitor — a mesma
     regra que o `background_job_monitor` do lado web já cumpria.

  2. **Não havia forma de a invocar.** O botão «Forçar Execução» do
     painel precisa de UMA função; um bloco em linha dentro de um `while`
     não é chamável, e a alternativa era uma segunda cópia da lógica.

  A rede de segurança continua a ser rede de segurança: o sync do
  processo API (`run_email_auto_sync`, ~5 min) é o que emite o
  WebSocket `new_email`; este ciclo de 10 min cobre o caso de o worker
  primário da API estar em baixo. As duas cadências estão
  deliberadamente desencontradas para não caírem em cima uma da outra no
  mesmo servidor IMAP.
====================================================================
"""
from __future__ import annotations

import asyncio
import logging

from database import db

logger = logging.getLogger(__name__)


async def run_webmail_worker_sync() -> None:
    """Uma passagem completa de sincronização de webmail do worker.

    Não devolve resumo: o detalhe de cada caixa vai para o log, como
    sempre foi. Levanta o que levantar — quem chama decide (o batimento
    precisa de ver a excepção para registar `erro`).
    """
    from services.email_service import sync_user_emails
    from services.user_email_config_service import get_active_email_configs_for_sync
    from services.email_config_resolver import resolve_email_config_for_sync

    # 1. Sync de caixas pessoais (multi-empresa)
    # ----------------------------------------------------------------
    # SUBSTITUI a query legacy db.users.find({"email_config.is_configured": True})
    # que só encontrava configs flat embebidas. Agora consultamos a coleção
    # canónica user_email_configs (uma config por par user+empresa), que
    # suporta a arquitetura multi-empresa e as configs guardadas via
    # Perfil > Configuração de Webmail.
    # ----------------------------------------------------------------
    active_configs = await get_active_email_configs_for_sync(limit=50)
    if active_configs:
        for cfg in active_configs:
            user_id = cfg["user_id"]
            company_id = cfg["company_id"]
            auth_method = cfg.get("auth_method", "imap_smtp")
            try:
                # OAuth pessoal ainda não tem sync function própria
                # (só IMAP/SMTP via sync_user_emails). Saltar com log
                # debug — não é regressão (legacy também não suportava).
                if auth_method == "google_oauth":
                    logger.debug(
                        f"Webmail sync: user={user_id} company={company_id} "
                        f"usa Google OAuth — sync pessoal OAuth ainda não implementada (a saltar)"
                    )
                    continue

                # Resolver a config canónica para este par user+empresa
                # (passa a saber exatamente que credenciais usar)
                resolved = await resolve_email_config_for_sync(
                    user_id,
                    active_company_id=company_id,
                    account_id=cfg.get("id"),
                )
                if not resolved:
                    logger.debug(
                        f"Webmail sync: config não resolúvel para "
                        f"user={user_id} company={company_id} — a saltar"
                    )
                    continue

                result = await sync_user_emails(
                    user_id,
                    days=30,
                    max_emails=50,
                    resolved_config=resolved,
                )
                synced = result.get("total_synced", 0)
                if synced > 0:
                    logger.info(
                        f"Webmail sync user={user_id} company={company_id}: "
                        f"{synced} novos emails"
                    )
                # Se houve policy violation, parar de iterar contas
                if result.get("error") and any(kw in result["error"].lower() for kw in [
                    "policy violation", "temporarily refused", "rate limit",
                    "too many", "blocked", "connection limit", "abuse"
                ]):
                    logger.warning(
                        f"Webmail sync: policy violation para "
                        f"user={user_id} company={company_id} — a parar iteração"
                    )
                    break
            except Exception as user_err:
                err_str = str(user_err)
                if any(kw in err_str.lower() for kw in [
                    "policy violation", "temporarily refused", "rate limit",
                    "too many", "blocked", "connection limit", "abuse"
                ]):
                    logger.warning(
                        f"Webmail sync: policy violation para "
                        f"user={user_id} company={company_id} — a parar iteração: {err_str[:200]}"
                    )
                    break
                logger.warning(
                    f"Erro ao sincronizar webmail do user={user_id} "
                    f"company={company_id}: {user_err}"
                )
            # Delay entre contas para evitar ligações IMAP simultâneas (3s)
            await asyncio.sleep(3)
        logger.info(
            f"Sincronização webmail pessoal concluída "
            f"({len(active_configs)} configs multi-empresa)"
        )
    else:
        logger.debug("Nenhuma config de email pessoal ativa encontrada em user_email_configs")

    # 2. Sync de caixas partilhadas via Gmail API (ex: indexacao)
    from services.gmail_api_service import gmail_api_sync_to_db
    shared_configs = await db.shared_role_email_configs.find(
        {
            "is_configured": True,
            "google_refresh_token": {"$ne": "", "$exists": True},
        },
        {"role": 1, "email_address": 1},
    ).to_list(10)
    if shared_configs:
        for shared_cfg in shared_configs:
            role = shared_cfg.get("role")
            try:
                result = await gmail_api_sync_to_db(role=role, days=3, max_emails=100)
                if result.get("success"):
                    synced = result.get("total_synced", 0)
                    if synced > 0:
                        logger.info(f"Gmail API sync role '{role}': {synced} novos emails")
                else:
                    logger.warning(f"Gmail API sync role '{role}' falhou: {result.get('error')}")
            except Exception as shared_err:
                logger.warning(f"Erro ao sincronizar Gmail API do role '{role}': {shared_err}")
        logger.info(f"Sincronização Gmail API concluída ({len(shared_configs)} roles)")


async def bater_e_sincronizar_webmail() -> None:
    """A passagem com o batimento a embrulhar o TRABALHO.

    É este o ponto de entrada do laço e do botão de execução forçada —
    nunca o `run_webmail_worker_sync` cru, senão o painel volta a não
    saber se o ciclo correu bem.
    """
    from services.job_heartbeat import heartbeat

    async with heartbeat("webmail_worker_sync", interval_seconds=600):
        await run_webmail_worker_sync()
