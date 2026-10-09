"""Quem pode LER um email, e quem pode abrir os emails de um processo (Bloco 2).

O PROBLEMA QUE ISTO FECHA
=========================
Havia quatro regras para a mesma pergunta, e a menos exigente era a que
mais tráfego tinha:

* o `GET /emails/{id}` e o descarregamento do Webmail avaliavam
  propriedade / caixa partilhada / conversa — e deixavam passar
  `admin/ceo/diretor` **sem fronteira de rede** (D-8: `db.emails` não leva
  carimbo de rede);
* as **cinco** rotas legadas de anexos (`/{id}/attachments`, o descarregar,
  o preview e o URL pré-assinado) não tinham guarda NENHUMA: qualquer
  sessão — um parceiro, um consultor de outra rede — descarregava o anexo
  de qualquer email sabendo o id;
* as rotas **por processo** (`/process/{id}`, `/stats`, `/timeline`,
  `/sync`, `/monitored`, `/send-documentation`) recebiam só o
  `process_id`: listavam o corpo dos emails de um processo de outra rede, e
  o `force_refresh` apagava emails à vista de toda a gente.

Este módulo é o ponto único. As duas perguntas são diferentes e têm duas
funções: `pode_ler_email` (um email) e `exigir_processo_legivel` (os
emails de um processo, que reaproveita a guarda de DOCUMENTOS da D-26,
fronteira de rede incluída).

A REGRA DE LEITURA DE UM EMAIL (por esta ordem; as que fazem I/O só correm
quando a sua pré-condição se verifica — um consultor a abrir o seu próprio
email não toca na base de dados):

1. **admin e CEO** — atravessam redes (decisão de produto: só estes dois);
2. **é seu** — criou-o, ou foi sincronizado para si (id ou endereço);
3. **está na sua conversa** — um dos endereços que CONFIGUROU (e não o de
   login: Pacote 8) é remetente ou destinatário;
4. **caixa partilhada do seu cargo** — `shared_role` igual ao perfil activo;
5. **Caixa Geral da empresa** — email geral, e o utilizador tem um cargo
   com direito à Caixa Geral NESSA empresa (diretor, CEO, administrativo,
   admin). Um cargo de gestão na Power não abre a Caixa Geral da Domus;
6. **diretor, dentro da sua rede** — o bypass do diretor é dentro da
   rede, não fora (D-26);
7. **email ligado a um processo que pode ver** — é o que faz o separador
   «Emails» do processo mostrar a conversa que um colega teve, e só para a
   equipa (um parceiro não entra por aqui).

Tudo o resto recusa. Falha FECHADA: sem âmbito de rede resolvido não há
regra 6 nem 7.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from fastapi import HTTPException

from database import db

logger = logging.getLogger(__name__)

#: Quem é equipa (e portanto pode ver os emails de um processo da sua rede).
#: Espelha `process_service.can_view_process`; um parceiro ou um cliente não
#: entram pela regra 7.
PAPEIS_DE_EQUIPA = frozenset(
    {"admin", "ceo", "diretor", "administrativo", "consultor", "intermediario", "indexacao"}
)
PAPEIS_QUE_ATRAVESSAM_REDES = frozenset({"admin", "ceo"})

ERRO_SEM_PERMISSAO = "Sem permissão para aceder a este email"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def papeis_do_utilizador(user: Optional[dict]) -> frozenset:
    """Os papéis a considerar: o EFECTIVO; no modo «todos», todos os do utilizador."""
    user = user or {}
    efectivo = _texto(user.get("effective_role") or user.get("role")).lower()
    if efectivo == "__all_roles__":
        from services.auth import get_all_user_roles

        return frozenset(_texto(r).lower() for r in get_all_user_roles(user) if _texto(r))
    return frozenset({efectivo}) if efectivo else frozenset()


def e_email_geral(email: dict) -> bool:
    """O email pertence à Caixa Geral (`shared_role=geral` ou `is_general`)."""
    return _texto(email.get("shared_role")).lower() == "geral" or email.get("is_general") is True


def _e_do_proprio(email: dict, user: dict) -> bool:
    uid = _texto(user.get("id"))
    endereco = _texto(user.get("email")).lower()
    if uid and (email.get("created_by") == uid or email.get("synced_for_user") == uid):
        return True
    return bool(endereco and _texto(email.get("synced_for_user")).lower() == endereco)


def _esta_na_conversa(email: dict, enderecos: Iterable[str]) -> bool:
    remetente = _texto(email.get("from_email")).lower()
    destinatarios = [_texto(a).lower() for a in (email.get("to_emails") or [])]
    return any(
        e and (e in remetente or any(e in d for d in destinatarios))
        for e in (_texto(x).lower() for x in enderecos)
    )


async def _enderecos_configurados(user: dict) -> list[str]:
    """Os endereços que o utilizador CONFIGUROU; o de login só como recurso."""
    enderecos: list[str] = []
    try:
        from services.user_email_config_service import get_user_mailbox_addresses

        enderecos = await get_user_mailbox_addresses(_texto(user.get("id")))
    except Exception as exc:
        logger.warning("[EmailAccess] Falha a resolver contas configuradas: %s", exc)
    if not enderecos and _texto(user.get("email")):
        enderecos = [_texto(user.get("email")).lower()]
    return enderecos


async def _ambito(user: dict):
    """O âmbito de rede de quem pede. Falha FECHADA (âmbito vazio recusa)."""
    from services.tenant_network import TenantScope, resolve_tenant_scope

    try:
        return await resolve_tenant_scope(user)
    except Exception as exc:
        logger.warning("[EmailAccess] Falha a resolver o âmbito de %s: %s", user.get("id"), exc)
        return TenantScope()


async def _empresas_com_caixa_geral(user: dict) -> set[str]:
    from services.webmail_scope import empresas_do_webmail

    return {e.company_id for e in await empresas_do_webmail(user) if e.tem_caixa_geral}


async def pode_ler_email(email: Optional[dict], user: dict, *, papel: Optional[str] = None) -> bool:
    """Este utilizador pode ler este email? Ver as regras no topo do módulo.

    `papel` permite a quem já o resolveu (a rota, com o `X-Active-Role`)
    passá-lo; sem ele usa-se o `effective_role` que o `get_current_user`
    estampou no dicionário.
    """
    if not email or not user:
        return False

    if papel:
        user = {**user, "effective_role": papel}
    papeis = papeis_do_utilizador(user)

    # 1. Atravessam redes.
    if papeis & PAPEIS_QUE_ATRAVESSAM_REDES:
        return True

    # 2./3./4. O que é dele — sem I/O além dos endereços configurados.
    if _e_do_proprio(email, user):
        return True
    if _esta_na_conversa(email, await _enderecos_configurados(user)):
        return True
    partilhada = _texto(email.get("shared_role")).lower()
    if partilhada and partilhada in papeis:
        return True

    # 5. Caixa Geral da empresa do email.
    if e_email_geral(email):
        empresas = await _empresas_com_caixa_geral(user)
        empresa_do_email = _texto(email.get("company_id"))
        # Sem carimbo, a pilha legada resolve-se pela existência de um cargo
        # com direito à Caixa Geral (como a listagem faz pelo endereço).
        if empresas and (not empresa_do_email or empresa_do_email in empresas):
            return True

    # 6./7. Precisam do âmbito de rede.
    e_diretor = "diretor" in papeis
    ligado_a_processo = bool(email.get("process_id")) and bool(papeis & PAPEIS_DE_EQUIPA)
    if not (e_diretor or ligado_a_processo):
        return False
    scope = await _ambito(user)

    if e_diretor:
        from services.tenant_network import documento_no_ambito

        if documento_no_ambito(email, scope):
            return True

    if ligado_a_processo:
        try:
            processo = await db.processes.find_one({"id": email["process_id"]}, {"_id": 0})
        except Exception as exc:
            logger.warning("[EmailAccess] Falha a ler o processo do email: %s", exc)
            processo = None
        if processo:
            from services.document_visibility import user_can_view_process_documents

            return bool(user_can_view_process_documents(user, processo, scope=scope))

    return False


async def exigir_leitura_do_email(
    email: Optional[dict],
    user: dict,
    *,
    papel: Optional[str] = None,
    status_code: int = 403,
    detail: str = ERRO_SEM_PERMISSAO,
) -> None:
    """Levanta quando o utilizador não pode ler o email."""
    if await pode_ler_email(email, user, papel=papel):
        return
    logger.warning(
        "[EmailAccess] Leitura negada: user=%s papel=%s email=%s",
        (user or {}).get("id"), sorted(papeis_do_utilizador(user)), (email or {}).get("id"),
    )
    raise HTTPException(status_code=status_code, detail=detail)


async def carregar_email_legivel(email_id: str, user: dict, *, papel: Optional[str] = None) -> dict:
    """Carrega o email e exige leitura. **404 para inexistente E para alheio.**

    Distinguir os dois confirmaria a existência do id a quem o adivinha — a
    regra das notificações. As rotas legadas que já respondiam 403 mantêm
    o seu código; as que não tinham guarda nenhuma nascem a 404.
    """
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email or not await pode_ler_email(email, user, papel=papel):
        if email:
            logger.warning(
                "[EmailAccess] Leitura negada: user=%s email=%s", (user or {}).get("id"), email_id,
            )
        raise HTTPException(status_code=404, detail="Email não encontrado")
    return email


async def exigir_processo_legivel(process_id: str, user: dict) -> dict:
    """Os emails de um processo só se abrem a quem pode ver o processo.

    Reaproveita a guarda de DOCUMENTOS (D-26): fronteira de rede ANTES do
    bypass de cargo, rede convidada da partilha incluída, e a restrição
    de pré-indexação. Devolve o processo para o chamador não o reler.
    """
    from services.document_visibility import assert_can_view_process_documents_by_id

    return await assert_can_view_process_documents_by_id(user, process_id)
