"""
====================================================================
CONFIRMAR UMA ACÇÃO DESTRUTIVA COM A PASSWORD ACTUAL (reautenticação)
====================================================================
Uma sessão aberta não prova que quem está ao teclado é o dono da conta — um
portátil esquecido, um token roubado. Para as acções que não se desfazem
(repor o workflow ou o formulário de uma rede ao modelo) o servidor exige a
password ACTUAL do utilizador autenticado, e só executa se ela estiver certa.

REGRAS QUE NÃO SE PODEM PERDER
  * **403 e nunca 401.** O interceptor do Axios trata um 401 como «sessão
    expirada» e desloga o utilizador; uma password errada de confirmação não
    é isso. (O 403 de confirmação não leva o toast de «Acesso Negado»: o
    chamador pede `skipErrorToast`.)
  * **Travão por identidade.** Confirmar uma password num endpoint de uma
    sessão já aberta é o sítio onde um token roubado tenta adivinhar a
    password. Usa o travão partilhado (`portal_brute_force`, âmbito próprio,
    chave = id do utilizador): esgotadas as tentativas responde 429 SEM olhar
    para a password. O sucesso limpa o contador.
  * **A password nunca é registada** (nem em log, nem no rasto de auditoria).
  * **Durante uma personificação não passa**: o token é o do utilizador alvo,
    cuja password quem personifica não conhece — uma acção destrutiva não se
    faz «como outra pessoa».
  * **Verifica contra o utilizador do TOKEN, lido da base de dados** — nunca
    contra um email/id vindo do corpo do pedido.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from database import db
from services import portal_brute_force as travao
from services.auth import verify_password

logger = logging.getLogger(__name__)

#: O âmbito do travão: tentativas de confirmação não gastam as do login do Portal.
AMBITO_DA_CONFIRMACAO = "confirmar_password"

ERRO_PASSWORD_EM_FALTA = "Indique a sua password para confirmar esta acção."
ERRO_PASSWORD_INCORRECTA = "Password incorrecta."
ERRO_SEM_PASSWORD = "Esta conta não tem password definida: não é possível confirmar a acção."
ERRO_PERSONIFICACAO = "Esta acção não pode ser confirmada durante uma personificação."


def _esta_a_personificar(user: dict) -> bool:
    return bool(user.get("is_impersonated") or user.get("impersonated_by"))


async def exigir_password_actual(user: dict, password: Optional[str]) -> None:
    """Levanta se a password não for a do utilizador autenticado. Devolve ``None`` se for."""
    if _esta_a_personificar(user):
        raise HTTPException(status_code=403, detail=ERRO_PERSONIFICACAO)
    if not isinstance(password, str) or not password:
        raise HTTPException(status_code=400, detail=ERRO_PASSWORD_EM_FALTA)

    identidade = user.get("id")
    # ANTES de olhar para a password: responder a quem esgotou as tentativas é continuar a responder ao ataque.
    await travao.exigir_sem_bloqueio(db, AMBITO_DA_CONFIRMACAO, identidade)

    registo = await db.users.find_one({"id": identidade}, {"_id": 0, "password": 1, "hashed_password": 1})
    guardada = (registo or {}).get("password") or (registo or {}).get("hashed_password") or ""
    if not guardada:
        raise HTTPException(status_code=403, detail=ERRO_SEM_PASSWORD)

    if not verify_password(password, guardada):
        await travao.registar_falha(db, AMBITO_DA_CONFIRMACAO, identidade)
        logger.warning("[REAUTH] Password de confirmação incorrecta para o utilizador %s", identidade)
        raise HTTPException(status_code=403, detail=ERRO_PASSWORD_INCORRECTA)

    await travao.limpar(db, AMBITO_DA_CONFIRMACAO, identidade)


__all__ = [
    "AMBITO_DA_CONFIRMACAO",
    "ERRO_PASSWORD_EM_FALTA",
    "ERRO_PASSWORD_INCORRECTA",
    "ERRO_PERSONIFICACAO",
    "ERRO_SEM_PASSWORD",
    "exigir_password_actual",
]
