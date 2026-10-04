"""Travão de tentativas no Portal — ponto único do lockout.

O QUE CORREU MAL (LOTE 10, D-4)
===============================
O `run_portal_login` — a entrada por **email + código de acesso** — tinha
a política de força bruta escrita à mão em ~55 linhas **e uma segunda
cópia** no `_record_login_attempt`, no mesmo ficheiro. Duas cópias da
mesma política divergem na primeira mudança, e aqui a divergência tinha a
forma de dois contadores a tratar o mesmo email.

Este módulo é o ponto único dessa porta.

**UMA CORRECÇÃO AO QUE ESTE MÓDULO AFIRMOU PRIMEIRO.** A versão inicial
dizia que o `run_verify_portal_login` prometia «5 tentativas, lockout de
15 min» na docstring e não tinha código nenhum a contar tentativas.
**Era falso.** O travão dessa porta existe, está completo e diz
exactamente 5/15 — vive em `portal_security.verify_client_credentials`
(`MAX_VERIFY_ATTEMPTS`, `VERIFY_LOCKOUT_MINUTES`, colecção
`portal_verify_attempts`), que é a camada que conhece as credenciais: lê
o bloqueio antes de buscar o cliente, regista em cada ramo 401 e limpa no
sucesso.

O erro nasceu de **inventariar UM módulo e concluir da ausência** — é
literalmente a lição dos três produtores de token do CRM («o erro nasceu
de inventariar UM produtor») e a do `assignment_drift` («uma dedução
sobre quem escreve o quê vale o inventário que a suporta, e o inventário
nunca está provado»). O travão que acrescentei ao `verify` era uma
SEGUNDA política na mesma porta, com constantes diferentes (8/10 contra
5/15) e noutra colecção, e foi retirado: dois travões na mesma porta é
pior do que um, porque passam a poder discordar sobre quem está
bloqueado.

A dívida REAL que isto revelou — duas implementações independentes da
mesma política para as duas portas do mesmo Portal — está registada na
D-4.

O LIMITE DE PEDIDOS NÃO SUBSTITUI ISTO
======================================
Os dois eixos respondem a perguntas diferentes e são precisos os dois:

* o `@limiter.limit` conta por CHAVE DE PEDIDO. Num endpoint
  pré-autenticação não há JWT, logo a chave é o IP — e o IP sai do
  `X-Forwarded-For`, que é um cabeçalho que o cliente envia. Quem
  ataca muda-o a cada pedido e o limite nunca morde. Fica como primeira
  linha, honesta sobre o que vale (ver D-4);
* o lockout conta por IDENTIDADE (o email, aqui; o `client_id`, no
  travão do `portal_security`), que é o que o atacante NÃO pode variar
  sem desistir do alvo. É este o eixo que fecha a porta.

CONSEQUÊNCIA QUE SE ASSUME
==========================
Um lockout por identidade permite a um terceiro BLOQUEAR um cliente
legítimo com tentativas erradas de propósito. É o preço, e é o mesmo que
o login por email já paga desde sempre: dez minutos de espera para o
cliente, contra um espaço de busca aberto para quem adivinha. A escolha é
deliberada e o prazo é curto por causa dela.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

#: Tentativas falhadas antes de bloquear. O valor do login de email
#: desde sempre; o verify passa a usar o MESMO, para não haver duas
#: políticas de força bruta no mesmo ecrã de entrada.
MAX_TENTATIVAS = 8
#: Minutos de bloqueio depois de esgotadas as tentativas.
MINUTOS_DE_BLOQUEIO = 10

#: O prefixo de chave em uso. O âmbito é um PARÂMETRO (`chave_do_travao`
#: recebe-o), para uma porta nova não gastar as tentativas de outra; mas
#: só se declara a constante que tem chamador — declarei
#: `AMBITO_DO_VERIFY` e `AMBITO_DO_MFA` sem os usar, e uma constante sem
#: chamador lê-se como código vivo (foi o que o `AGENCY_LINK_TEXTS`
#: ensinou neste mesmo lote).
AMBITO_DO_LOGIN = "portal_login"


def chave_do_travao(ambito: str, identidade) -> str:
    """`portal_verify:<client_id>`.

    A identidade é NORMALIZADA (minúsculas, aparada): `A@B.PT` e `a@b.pt`
    são a mesma conta, e sem isto bastava alternar a caixa das letras para
    duplicar as tentativas — um travão que se contorna com a tecla de
    maiúsculas não é um travão.
    """
    return f"{ambito}:{str(identidade or '').strip().lower()}"


def _para_data(valor) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        lido = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return lido if lido.tzinfo else lido.replace(tzinfo=timezone.utc)


def segundos_de_bloqueio(doc: Optional[dict], *, agora: datetime) -> int:
    """Quantos segundos faltam do bloqueio. `0` = não está bloqueado.

    PURA — o `agora` entra por parâmetro. Uma data ilegível devolve `0`
    (não bloqueia) de propósito: o travão existe para travar quem
    adivinha, e um registo corrompido não pode trancar um cliente
    legítimo para sempre. O registo da falha, esse, continua a correr.
    """
    if not doc:
        return 0
    ate = _para_data(doc.get("locked_until"))
    if not ate:
        return 0
    restantes = int((ate - agora).total_seconds())
    return restantes if restantes > 0 else 0


def esgotou_as_tentativas(doc: Optional[dict]) -> bool:
    if not doc:
        return False
    try:
        return int(doc.get("attempts", 0) or 0) >= MAX_TENTATIVAS
    except (TypeError, ValueError):
        return False


def _erro_de_bloqueio(segundos: int) -> HTTPException:
    minutos = max(1, segundos // 60)
    return HTTPException(
        status_code=429,
        detail={
            "error": "Acesso temporariamente bloqueado",
            "message": (
                f"Muitas tentativas falhadas. Tente novamente em {minutos} "
                f"minuto{'s' if minutos != 1 else ''}."
            ),
            "retry_after": segundos,
            "retry_after_minutes": minutos,
        },
        headers={"Retry-After": str(segundos)},
    )


async def exigir_sem_bloqueio(db, ambito: str, identidade) -> None:
    """Levanta 429 quando a identidade está bloqueada.

    Chamada ANTES de se verificar qualquer credencial: o código de
    resposta de uma verificação é, ele próprio, informação sobre a
    credencial, e devolvê-la a quem já esgotou as tentativas seria
    continuar a responder ao ataque enquanto se diz que não.

    Falhar a LER o travão não bloqueia o cliente (`warning` e segue): a
    base de dados em baixo não pode trancar o Portal à chave. Falhar a
    ESCREVER, sim, é a parte que importa e vai no `registar_falha`.
    """
    chave = chave_do_travao(ambito, identidade)
    try:
        doc = await db.portal_login_attempts.find_one({"_id": chave})
    except Exception as exc:
        logger.warning("[PORTAL] Falha a ler o travão de %s: %s", chave, exc)
        return

    agora = datetime.now(timezone.utc)
    restantes = segundos_de_bloqueio(doc, agora=agora)
    if restantes:
        logger.warning("[PORTAL] %s bloqueado por %ds", chave, restantes)
        raise _erro_de_bloqueio(restantes)

    # Tentativas esgotadas e sem `locked_until`: é o caso de quem chegou
    # ao limite e volta. Carimba-se o bloqueio aqui para a janela começar
    # a contar, senão as tentativas ficavam no limite e o travão nunca
    # fechava.
    if esgotou_as_tentativas(doc):
        segundos = MINUTOS_DE_BLOQUEIO * 60
        ate = (agora + timedelta(minutes=MINUTOS_DE_BLOQUEIO)).isoformat()
        try:
            await db.portal_login_attempts.update_one(
                {"_id": chave}, {"$set": {"locked_until": ate}}
            )
        except Exception as exc:
            logger.warning("[PORTAL] Falha a carimbar o bloqueio de %s: %s", chave, exc)
        logger.warning("[PORTAL] Bloqueio aplicado a %s", chave)
        raise _erro_de_bloqueio(segundos)


async def registar_falha(db, ambito: str, identidade) -> None:
    """Conta uma tentativa falhada, e bloqueia quando chega ao limite."""
    chave = chave_do_travao(ambito, identidade)
    agora = datetime.now(timezone.utc)
    try:
        await db.portal_login_attempts.update_one(
            {"_id": chave},
            {
                "$inc": {"attempts": 1},
                "$set": {"last_attempt_at": agora.isoformat()},
                # `primeira_em` preservado: reescrevê-lo em cada falha
                # fazia um ataque de três dias parecer começado agora (a
                # regra do `desde` do `mailbox_health`).
                "$setOnInsert": {"primeira_em": agora.isoformat(), "ambito": ambito},
            },
            upsert=True,
        )
        doc = await db.portal_login_attempts.find_one({"_id": chave})
    except Exception as exc:
        # Aqui NÃO se engole em silêncio: se não se consegue contar, o
        # travão não existe, e isso tem de aparecer no log como aviso.
        logger.warning("[PORTAL] Falha a registar tentativa em %s: %s", chave, exc)
        return

    if esgotou_as_tentativas(doc) and not segundos_de_bloqueio(doc, agora=agora):
        ate = (agora + timedelta(minutes=MINUTOS_DE_BLOQUEIO)).isoformat()
        try:
            await db.portal_login_attempts.update_one(
                {"_id": chave}, {"$set": {"locked_until": ate}}
            )
            logger.warning(
                "[PORTAL] Bloqueio aplicado a %s após %d tentativas",
                chave, MAX_TENTATIVAS,
            )
        except Exception as exc:
            logger.warning("[PORTAL] Falha a bloquear %s: %s", chave, exc)


async def limpar(db, ambito: str, identidade) -> None:
    """Apaga o registo depois de uma entrada bem sucedida.

    Sem isto, oito tentativas espalhadas por semanas — com entradas
    certas pelo meio — acabavam por bloquear um cliente que nunca errou
    duas vezes seguidas. Um contador que só sobe mede a vida da conta e
    não um ataque.
    """
    chave = chave_do_travao(ambito, identidade)
    try:
        await db.portal_login_attempts.delete_one({"_id": chave})
    except Exception as exc:
        logger.warning("[PORTAL] Falha a limpar o travão de %s: %s", chave, exc)


__all__ = [
    "AMBITO_DO_LOGIN",
    "MAX_TENTATIVAS",
    "MINUTOS_DE_BLOQUEIO",
    "chave_do_travao",
    "esgotou_as_tentativas",
    "exigir_sem_bloqueio",
    "limpar",
    "registar_falha",
    "segundos_de_bloqueio",
]
