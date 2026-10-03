"""A saúde de uma caixa de correio — persistida (Lote 7, ponto 4).

O QUE A AUDITORIA ENCONTROU
===========================
Quando a password do IMAP expira, o sistema sabe-o: `_fetch_all_from_folder_sync`
devolve `connection_error` com a mensagem certa («Autenticação IMAP falhou para
… — verifique email/password nas Configurações do Perfil»). O problema é o que
acontece a essa informação, e são dois caminhos com destinos diferentes:

* **Sincronização MANUAL** (o botão): o erro falha o job, o `pollJobStatus`
  recebe `status: "failed"` e o ecrã mostra um **toast**. Funciona — mas é
  transitório: fecha-se o separador e não resta nada.

* **Sincronização AUTOMÁTICA** (`webmail_worker_sync`, de 10 em 10 minutos, que
  é a que mantém a caixa fresca): o `run_webmail_worker_sync` apanha tudo num
  `except Exception` e faz `logger.warning`. **Mais nada.** A caixa deixa de
  receber email, o ecrã mostra a lista antiga sem um único aviso, e o ciclo
  volta a falhar de 10 em 10 minutos para sempre.

E não havia **nada persistido**: a colecção `user_email_configs` não tinha um
único campo sobre o estado da última sincronização. O `run_get_configured_accounts`
devolvia a conta como se estivesse boa. O utilizador só descobre quando repara
que não recebe email há dias — e o diagnóstico natural («o servidor está em
baixo») aponta para o sítio errado.

Isto é a forma de defeito desta casa: **o degradado que não produz erro nenhum.**
A mesma de uma notificação sem `user_id`, de uma coluna de notas sempre vazia, e
de um documento que desaparece do separador.

A REGRA
=======
O estado da última sincronização é **persistido na config**, pela mesma função,
nos DOIS caminhos (manual e automático). Um toast informa; um campo na base de
dados é o que permite ao ecrã dizer «esta caixa está a falhar há 3 dias» e ao
administrador ver quem está parado.

QUATRO DECISÕES
===============
1. **Distingue-se AUTENTICAÇÃO de REDE.** Uma password errada exige acção do
   utilizador e não se resolve sozinha; um servidor inatingível ou um rate limit
   passam. Mostrar o mesmo aviso aos dois ensina a ignorar os dois — é a regra do
   `desactivado ≠ em baixo` do painel de sinais vitais. Daí
   `CLASSE_AUTENTICACAO` / `CLASSE_REDE` / `CLASSE_LIMITE`.

2. **O sucesso LIMPA o erro.** Sem isso, um aviso fica no ecrã para sempre
   depois de a pessoa corrigir a password — e um aviso que não desaparece é
   indistinguível de um aviso falso.

3. **Gravar o estado NUNCA faz a sincronização falhar.** É a regra do
   `job_heartbeat` e do `_registar_na_auditoria`: observa, não intercepta. Uma
   excepção aqui propagar-se-ia para um ciclo de fundo que estava a correr bem.

4. **Conta-se as falhas CONSECUTIVAS, não um histórico.** Dois números (desde
   quando falha, quantas vezes) respondem à única pergunta que interessa — «isto
   é um soluço ou está parado?» — e não fazem a colecção crescer. É a decisão do
   `job_heartbeats`.

Cobertura: `tests/unit/test_mailbox_health.py`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

COLECCAO = "user_email_configs"

#: As três classes de falha, por ordem de quem tem de agir.
CLASSE_AUTENTICACAO = "autenticacao"
CLASSE_LIMITE = "limite"
CLASSE_REDE = "rede"
CLASSE_DESCONHECIDA = "desconhecida"

#: Só esta exige acção do UTILIZADOR. As outras passam sozinhas, e avisar
#: delas com a mesma força ensina a ignorar o aviso todo.
CLASSES_QUE_EXIGEM_ACCAO = frozenset({CLASSE_AUTENTICACAO})

_SINAIS_DE_AUTENTICACAO = (
    "autenticação", "autenticacao", "authentication", "authenticationfailed",
    "login failed", "invalid credentials", "incorrect authentication",
    "password", "credenciais", "535", "nologin", "auth",
)

_SINAIS_DE_LIMITE = (
    "policy violation", "temporarily refused", "too many", "rate limit",
    "connection limit", "abuse", "blocked", "throttl",
)

_SINAIS_DE_REDE = (
    "inatingível", "inatingivel", "timed out", "timeout", "connection refused",
    "conexão recusada", "conexao recusada", "unreachable", "getaddrinfo",
    "name or service not known", "ssl", "certificate", "broken pipe",
    "connection reset",
)

#: Mensagens para o ecrã. Dizem o que fazer, não o que aconteceu — um
#: «IMAP error 535» não diz a ninguém que tem de ir mudar a password.
MENSAGENS = {
    CLASSE_AUTENTICACAO: (
        "As credenciais desta caixa de correio foram recusadas pelo servidor. "
        "Actualize a password em Perfil → Configuração de Webmail; até lá não "
        "entram emails novos."
    ),
    CLASSE_LIMITE: (
        "O servidor de email recusou temporariamente as ligações (limite de "
        "tráfego). A sincronização volta a tentar sozinha."
    ),
    CLASSE_REDE: (
        "Não foi possível alcançar o servidor de email. A sincronização volta "
        "a tentar sozinha."
    ),
    CLASSE_DESCONHECIDA: (
        "A última sincronização desta caixa falhou. Se persistir, confirme as "
        "credenciais em Perfil → Configuração de Webmail."
    ),
}


def classificar_falha(mensagem: Any) -> str:
    """A classe de uma falha de sincronização, pela mensagem do servidor.

    A ordem das verificações é deliberada: **o limite de tráfego antes da
    autenticação**. Um servidor que responde «too many login attempts» tem
    as duas palavras, e tratá-lo como password errada mandava o utilizador
    mudar uma password que está certa — e a conta resolve-se sozinha.
    """
    texto = str(mensagem or "").lower()
    if not texto.strip():
        return CLASSE_DESCONHECIDA
    if any(sinal in texto for sinal in _SINAIS_DE_LIMITE):
        return CLASSE_LIMITE
    if any(sinal in texto for sinal in _SINAIS_DE_AUTENTICACAO):
        return CLASSE_AUTENTICACAO
    if any(sinal in texto for sinal in _SINAIS_DE_REDE):
        return CLASSE_REDE
    return CLASSE_DESCONHECIDA


def exige_accao_do_utilizador(classe: Any) -> bool:
    """True só para a classe que a pessoa tem de resolver."""
    return str(classe or "") in CLASSES_QUE_EXIGEM_ACCAO


def mensagem_para_o_ecra(classe: Any) -> str:
    return MENSAGENS.get(str(classe or ""), MENSAGENS[CLASSE_DESCONHECIDA])


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _filtro(user_id: Any, *, company_id: Any = None, account_id: Any = None) -> Optional[dict]:
    """A config exacta a marcar.

    Preferir o `account_id` quando existe: um utilizador pode ter várias
    contas na mesma empresa, e marcar a errada punha o aviso na caixa que
    está a funcionar — pior do que não avisar, porque manda procurar no
    sítio errado.
    """
    if account_id:
        return {"id": str(account_id)}
    uid = str(user_id or "").strip()
    if not uid:
        return None
    filtro: dict = {"user_id": uid}
    if company_id:
        filtro["company_id"] = str(company_id)
    return filtro


def construir_estado_de_falha(
    mensagem: Any, *, falhas_anteriores: int = 0, desde: Any = None,
) -> dict:
    """Os campos a gravar numa falha.

    `desde` preserva-se: é ele que responde «há quanto tempo está parado»,
    e reescrevê-lo a cada ciclo fazia um problema de três dias parecer
    acabado de acontecer.
    """
    classe = classificar_falha(mensagem)
    return {
        "sync_status": "failed",
        "sync_error_class": classe,
        "sync_error_message": str(mensagem or "")[:500],
        "sync_error_user_message": mensagem_para_o_ecra(classe),
        "sync_requires_action": exige_accao_do_utilizador(classe),
        "sync_failures": int(falhas_anteriores or 0) + 1,
        "sync_failing_since": desde or _agora(),
        "last_sync_attempt_at": _agora(),
    }


def construir_estado_de_sucesso() -> dict:
    """Os campos a gravar num sucesso — o erro é LIMPO.

    Sem isto, o aviso ficava no ecrã depois de a password ser corrigida, e
    um aviso que não desaparece é indistinguível de um aviso falso.
    """
    return {
        "sync_status": "ok",
        "sync_error_class": None,
        "sync_error_message": None,
        "sync_error_user_message": None,
        "sync_requires_action": False,
        "sync_failures": 0,
        "sync_failing_since": None,
        "last_sync_attempt_at": _agora(),
        "last_sync_ok_at": _agora(),
    }


async def registar_falha(
    user_id: Any,
    mensagem: Any,
    *,
    company_id: Any = None,
    account_id: Any = None,
) -> None:
    """Grava a falha na config. NUNCA propaga — observa, não intercepta."""
    filtro = _filtro(user_id, company_id=company_id, account_id=account_id)
    if not filtro:
        return
    try:
        actual = await db[COLECCAO].find_one(
            filtro, {"_id": 0, "sync_failures": 1, "sync_failing_since": 1},
        ) or {}
        await db[COLECCAO].update_one(
            filtro,
            {"$set": construir_estado_de_falha(
                mensagem,
                falhas_anteriores=actual.get("sync_failures") or 0,
                desde=actual.get("sync_failing_since"),
            )},
        )
    except Exception as exc:  # pragma: no cover - observar nunca propaga
        logger.warning(
            "[MAILBOX-HEALTH] Falha a registar o estado de %s: %s", user_id, exc,
        )


async def registar_sucesso(
    user_id: Any, *, company_id: Any = None, account_id: Any = None,
) -> None:
    """Limpa o erro da config. NUNCA propaga."""
    filtro = _filtro(user_id, company_id=company_id, account_id=account_id)
    if not filtro:
        return
    try:
        await db[COLECCAO].update_one(
            filtro, {"$set": construir_estado_de_sucesso()},
        )
    except Exception as exc:  # pragma: no cover - observar nunca propaga
        logger.warning(
            "[MAILBOX-HEALTH] Falha a limpar o estado de %s: %s", user_id, exc,
        )


def resumo_para_o_ecra(config: Optional[dict]) -> dict:
    """O que a UI precisa de saber sobre a saúde de uma caixa.

    Deliberadamente pequeno: a mensagem técnica do servidor **não vai** para
    o ecrã (pode conter o endereço do servidor e o código do erro), vai a
    mensagem que diz o que fazer. A técnica fica na config para quem
    diagnostica.
    """
    config = config or {}
    estado = config.get("sync_status") or "desconhecido"
    return {
        "sync_status": estado,
        "sync_requires_action": bool(config.get("sync_requires_action")),
        "sync_error_class": config.get("sync_error_class"),
        "sync_message": config.get("sync_error_user_message") or "",
        "sync_failures": int(config.get("sync_failures") or 0),
        "sync_failing_since": config.get("sync_failing_since"),
        "last_sync_ok_at": config.get("last_sync_ok_at"),
    }


__all__ = [
    "CLASSE_AUTENTICACAO",
    "CLASSE_DESCONHECIDA",
    "CLASSE_LIMITE",
    "CLASSE_REDE",
    "CLASSES_QUE_EXIGEM_ACCAO",
    "MENSAGENS",
    "classificar_falha",
    "construir_estado_de_falha",
    "construir_estado_de_sucesso",
    "exige_accao_do_utilizador",
    "mensagem_para_o_ecra",
    "registar_falha",
    "registar_sucesso",
    "resumo_para_o_ecra",
]
