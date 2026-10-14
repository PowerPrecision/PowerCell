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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class Politica:
    """A política de força bruta de UMA porta: quantas tentativas, quanto bloqueio, onde se conta.

    Cada porta tem os seus números (D-4 fechada, Out 2026): eram duas implementações
    independentes da mesma ideia, e uma correcção feita numa não chegava à outra. Hoje há UMA
    implementação e uma tabela — e um teste a afirmar que cada porta MANTÉM os seus números,
    que é o que distingue uma consolidação de uma alteração de política (apertar o login para
    5 bloqueia quem erra um código de 6 caracteres cinco vezes; alargar o verify para 8/10 abre
    a porta que tem o espaço de busca mais pequeno).
    """

    tentativas: int
    minutos_de_bloqueio: int
    colecao: str
    #: O 429 leva o `detail` em TEXTO (o formato histórico do `verify`) em vez do dicionário
    #: do login. Os dois ecrãs do frontend já tratam cada um o seu.
    detalhe_em_texto: bool = False


#: A política do login por email do Portal (e das portas que a herdam: login do Parceiro,
#: confirmação por password). Desde sempre 8 tentativas / 10 minutos.
POLITICA_DO_LOGIN = Politica(8, 10, "portal_login_attempts")

#: O `verify` (NIF + nº de processo): espaço de busca mais pequeno, logo mais apertado.
POLITICA_DO_VERIFY = Politica(5, 15, "portal_verify_attempts", detalhe_em_texto=True)

#: O âmbito é um PARÂMETRO (`chave_do_travao` recebe-o), para uma porta nova não gastar as
#: tentativas de outra. Um âmbito sem entrada própria herda a política do login.
AMBITO_DO_LOGIN = "portal_login"
AMBITO_DO_VERIFY = "portal_verify"

POLITICAS: dict[str, Politica] = {
    AMBITO_DO_LOGIN: POLITICA_DO_LOGIN,
    AMBITO_DO_VERIFY: POLITICA_DO_VERIFY,
}


def politica_de(ambito: str) -> Politica:
    return POLITICAS.get(ambito, POLITICA_DO_LOGIN)


#: Compatibilidade: as constantes do login, usadas por `portal_auth` e pelos testes.
MAX_TENTATIVAS = POLITICA_DO_LOGIN.tentativas
MINUTOS_DE_BLOQUEIO = POLITICA_DO_LOGIN.minutos_de_bloqueio

#: Quanto tempo o registo de tentativas sobrevive depois da última escrita
#: (D-31, remate). A identidade (o email, aqui) é escolhida por quem pergunta, logo
#: cada email inventado deixava um documento que nunca expirava — e, com
#: `attempts >= MAX`, cada pedido renovava o bloqueio antes de olhar para a
#: credencial: quem esgotava as tentativas ficava trancado PARA SEMPRE.
#: O índice TTL (`db_indexes`, campo `expire_at`) purga-os.
#:
#: É a constante de TODAS as portas. **Tem de ser MAIOR que qualquer
#: bloqueio** — um registo apagado a meio do bloqueio desbloqueava o alvo.
MINUTOS_DE_VIDA_DO_REGISTO = 30
assert all(MINUTOS_DE_VIDA_DO_REGISTO > p.minutos_de_bloqueio for p in POLITICAS.values())


def expira_em(agora: datetime) -> datetime:
    """Quando o registo de tentativas deixa de interessar (BSON Date, UTC).

    Datetime NATIVO de propósito: o TTL do Mongo não actua sobre uma string
    ISO (foi o que inutilizou o `idx_ttl` antigo).
    """
    return agora + timedelta(minutes=MINUTOS_DE_VIDA_DO_REGISTO)

def chave_do_travao(ambito: str, identidade) -> str:
    """`<âmbito>:<identidade>` (ex.: `portal_verify:<client_id>`).

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


def esgotou_as_tentativas(doc: Optional[dict], politica: Politica = POLITICA_DO_LOGIN) -> bool:
    if not doc:
        return False
    try:
        return int(doc.get("attempts", 0) or 0) >= politica.tentativas
    except (TypeError, ValueError):
        return False


def _erro_de_bloqueio(segundos: int, politica: Politica = POLITICA_DO_LOGIN) -> HTTPException:
    minutos = max(1, segundos // 60)
    if politica.detalhe_em_texto:
        return HTTPException(
            status_code=429,
            detail=(
                f"Muitas tentativas falhadas. Tente novamente em {minutos} "
                f"minuto{'s' if minutos != 1 else ''}."
            ),
            headers={"Retry-After": str(segundos)},
        )
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
    politica = politica_de(ambito)
    colecao = getattr(db, politica.colecao)
    try:
        doc = await colecao.find_one({"_id": chave})
    except Exception as exc:
        logger.warning("[PORTAL] Falha a ler o travão de %s: %s", chave, exc)
        return

    agora = datetime.now(timezone.utc)
    restantes = segundos_de_bloqueio(doc, agora=agora)
    if restantes:
        logger.warning("[PORTAL] %s bloqueado por %ds", chave, restantes)
        raise _erro_de_bloqueio(restantes, politica)

    # Tentativas esgotadas e sem `locked_until`: é o caso de quem chegou
    # ao limite e volta. Carimba-se o bloqueio aqui para a janela começar
    # a contar, senão as tentativas ficavam no limite e o travão nunca
    # fechava.
    if esgotou_as_tentativas(doc, politica):
        segundos = politica.minutos_de_bloqueio * 60
        ate = (agora + timedelta(minutes=politica.minutos_de_bloqueio)).isoformat()
        try:
            await colecao.update_one(
                {"_id": chave}, {"$set": {"locked_until": ate}}
            )
        except Exception as exc:
            logger.warning("[PORTAL] Falha a carimbar o bloqueio de %s: %s", chave, exc)
        logger.warning("[PORTAL] Bloqueio aplicado a %s", chave)
        raise _erro_de_bloqueio(segundos, politica)


async def registar_falha(db, ambito: str, identidade) -> None:
    """Conta uma tentativa falhada, e bloqueia quando chega ao limite."""
    chave = chave_do_travao(ambito, identidade)
    politica = politica_de(ambito)
    colecao = getattr(db, politica.colecao)
    agora = datetime.now(timezone.utc)
    try:
        await colecao.update_one(
            {"_id": chave},
            {
                "$inc": {"attempts": 1},
                "$set": {
                    "last_attempt_at": agora.isoformat(),
                    "expire_at": expira_em(agora),
                },
                # `primeira_em` preservado: reescrevê-lo em cada falha
                # fazia um ataque de três dias parecer começado agora (a
                # regra do `desde` do `mailbox_health`).
                "$setOnInsert": {"primeira_em": agora.isoformat(), "ambito": ambito},
            },
            upsert=True,
        )
        doc = await colecao.find_one({"_id": chave})
    except Exception as exc:
        # Aqui NÃO se engole em silêncio: se não se consegue contar, o
        # travão não existe, e isso tem de aparecer no log como aviso.
        logger.warning("[PORTAL] Falha a registar tentativa em %s: %s", chave, exc)
        return

    if esgotou_as_tentativas(doc, politica) and not segundos_de_bloqueio(doc, agora=agora):
        ate = (agora + timedelta(minutes=politica.minutos_de_bloqueio)).isoformat()
        try:
            await colecao.update_one(
                {"_id": chave}, {"$set": {"locked_until": ate}}
            )
            logger.warning(
                "[PORTAL] Bloqueio aplicado a %s após %d tentativas",
                chave, politica.tentativas,
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
        await getattr(db, politica_de(ambito).colecao).delete_one({"_id": chave})
    except Exception as exc:
        logger.warning("[PORTAL] Falha a limpar o travão de %s: %s", chave, exc)


__all__ = [
    "AMBITO_DO_LOGIN",
    "AMBITO_DO_VERIFY",
    "POLITICAS",
    "POLITICA_DO_LOGIN",
    "POLITICA_DO_VERIFY",
    "Politica",
    "politica_de",
    "MAX_TENTATIVAS",
    "MINUTOS_DE_BLOQUEIO",
    "MINUTOS_DE_VIDA_DO_REGISTO",
    "chave_do_travao",
    "esgotou_as_tentativas",
    "exigir_sem_bloqueio",
    "expira_em",
    "limpar",
    "registar_falha",
    "segundos_de_bloqueio",
]
