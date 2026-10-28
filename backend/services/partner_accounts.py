"""
====================================================================
PORTAL DO PARCEIRO — CONTAS: convite, palavra-passe e login (V1)
====================================================================
`db.partners` é a identidade. Uma pessoa individual, convidada por um
Admin/CEO da rede (ou pelo Master), que define a palavra-passe ela mesma
a partir de um link de uso único. **Sem registo público, sem Google.**

O ESQUEMA (pensado para mais do que uma rede)
  {
    id, name, email (minúsculas, único), phone,
    status:      "invited" | "active" | "suspended"      # conta
    redes: [ {network_id, company_id, company_name,
              status: "active" | "suspended",
              invited_by, invited_by_name, invited_at} ] # uma por rede
    password_hash, password_set_at, token_epoch, last_login_at,
    invite: {token_hash, expires_at, sent_at} | ausente,
    terms:  {version, accepted_at, ip},
    created_at, updated_at
  }

  A V1 convida para UMA rede, mas a visibilidade já lê `redes` como lista
  (`partner_security.ids_das_redes_activas`): ligar o mesmo parceiro a uma
  segunda rede é acrescentar um elemento, não migrar o esquema. A
  suspensão é POR LIGAÇÃO — o Admin da rede A suspende a ligação à rede
  A e não mexe na ligação à rede B, que não é dele.

A ENTRADA NO DIRECTÓRIO (`users`)
  O staff atribui um parceiro a um processo por `assigned_parceiro_id`,
  e todo o maquinário de atribuição (`apply_single_assignee_param`,
  histórico, enriquecimento do nome) resolve o id em `db.users`. Por isso
  cada parceiro tem, com o MESMO `id`, uma linha-fantasma em `users`
  (`role: "parceiro"`, sem palavra-passe): é só o directório. **Não
  autentica ninguém** — o `login-v2` recusa contas sem palavra-passe — e a
  autoridade de login é `db.partners`. Adoptar uma conta-fantasma que já
  existia (`adopt_user_id`) mantém o `id`, e com ele os processos que já
  apontam para ela, sem reescrever nenhum.

AS REGRAS DO LOGIN
  * o travão por IDENTIDADE (o email) corre ANTES de olhar para a
    credencial — o código de resposta é informação sobre ela;
  * a mesma mensagem e o mesmo custo (bcrypt contra um hash falso) para
    «não existe», «sem palavra-passe» e «palavra-passe errada»;
  * o estado (suspenso, sem rede activa) só se diz DEPOIS de a
    palavra-passe estar provada;
  * o sucesso limpa o contador.
====================================================================
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database import db
from services.partner_security import (
    ESTADO_ACTIVO,
    ESTADO_CONVIDADO,
    ESTADO_ELIMINADO,
    ESTADO_SUSPENSO,
    conta_com_acesso,
    create_partner_token,
    exigir_portal_ligado,
    hash_de_token,
)
from services import portal_brute_force
from utils.input_sanitization import sanitize_email, sanitize_name, sanitize_phone

logger = logging.getLogger(__name__)

AMBITO_DO_LOGIN_DO_PARCEIRO = "partner_login"
VALIDADE_DO_CONVITE_DIAS = 7
#: A versão dos termos que o parceiro aceita ao activar a conta. O texto é
#: decisão de produto; o que fica aqui é a PROVA de qual versão foi aceite.
VERSAO_DOS_TERMOS = "2026-10"

ERRO_CREDENCIAIS = "Email ou palavra-passe incorrectos."
ERRO_CONVITE = "Convite inválido ou expirado."
ERRO_EMAIL_INDISPONIVEL = "Este email não pode ser usado para um parceiro."
ERRO_CONTA_INDISPONIVEL = "Conta indisponível. Contacte o seu consultor."


# ====================================================================
# MODELOS DE PEDIDO — `extra="forbid"`: nada entra que não esteja escrito
# ====================================================================
class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PartnerLogin(_Estrito):
    email: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=1, max_length=128)


class PartnerAcceptInvite(_Estrito):
    token: str = Field(..., min_length=16, max_length=128)
    password: str = Field(..., min_length=1, max_length=128)
    accept_terms: bool = False


class PartnerChangePassword(_Estrito):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=1, max_length=128)


class PartnerInvite(_Estrito):
    name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=3, max_length=100)
    phone: Optional[str] = Field(None, max_length=30)
    #: Opcional (Lote 5): um parceiro é um operador EXTERNO e independente — não
    #: «veste a camisola» de uma empresa. Sem empresa não há ligação a nenhuma
    #: rede à partida: a primeira lead que submeter a uma empresa de destino cria
    #: a ligação de mercado (`acrescentar_ligacao_de_mercado`).
    company_id: Optional[str] = Field(None, max_length=80)
    #: Conta-fantasma (`users.role == "parceiro"`) a adoptar: o parceiro
    #: herda o `id` e com ele os processos que já apontam para ela.
    adopt_user_id: Optional[str] = Field(None, max_length=80)


class PartnerUpdate(_Estrito):
    name: Optional[str] = Field(None, min_length=2, max_length=120)
    phone: Optional[str] = Field(None, max_length=30)
    #: Só o Master (a identidade de login muda). Invalida o convite pendente e as sessões abertas.
    email: Optional[str] = Field(None, min_length=3, max_length=100)
    #: Suspende/reactiva as ligações às redes DE QUEM ACTUA.
    suspended: Optional[bool] = None


# ====================================================================
# PURAS
# ====================================================================
def normalizar_email(valor: Any) -> str:
    return sanitize_email(str(valor or ""))


def agora_iso(agora: Optional[datetime] = None) -> str:
    return (agora or datetime.now(timezone.utc)).isoformat()


def _para_data(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        lido = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return lido if lido.tzinfo else lido.replace(tzinfo=timezone.utc)


def convite_vigente(partner: Optional[dict], *, agora: Optional[datetime] = None) -> bool:
    """O convite existe e ainda não expirou. Data ilegível = expirado."""
    convite = (partner or {}).get("invite") or {}
    if not convite.get("token_hash"):
        return False
    ate = _para_data(convite.get("expires_at"))
    return bool(ate and ate > (agora or datetime.now(timezone.utc)))


def publico(partner: Optional[dict]) -> dict:
    """O que se mostra de um parceiro — lista POSITIVA, nunca o documento.

    Nunca sai o hash da palavra-passe, o convite, a geração do token nem os
    termos (IP incluído).
    """
    partner = partner or {}
    return {
        "id": partner.get("id"),
        "name": partner.get("name"),
        "email": partner.get("email"),
        "phone": partner.get("phone"),
        "status": partner.get("status"),
        "redes": [
            {
                "network_id": r.get("network_id"),
                "company_id": r.get("company_id"),
                "company_name": r.get("company_name"),
                "status": r.get("status") or ESTADO_ACTIVO,
            }
            for r in (partner.get("redes") or [])
            if isinstance(r, dict)
        ],
        "invite_pending": convite_vigente(partner),
        "created_at": partner.get("created_at"),
        "last_login_at": partner.get("last_login_at"),
    }


def novo_documento_de_parceiro(
    *,
    partner_id: str,
    name: str,
    email: str,
    phone: Optional[str],
    ligacao: Optional[dict],
    token_hash: str,
    agora: datetime,
    convidado_pela_rede: Optional[str] = None,
) -> dict:
    return {
        "id": partner_id,
        "name": name,
        "email": email,
        "phone": phone or None,
        "status": ESTADO_CONVIDADO,
        # Sem ligação = agente independente (lista vazia, nunca ausente: a
        # leitura distingue «nunca esteve ligado» de «todas suspensas»).
        "redes": [ligacao] if ligacao else [],
        # A rede de QUEM CONVIDOU: sem ligações, é o que mantém o parceiro
        # visível (e gerível) por quem o trouxe. Não dá acesso a dados.
        "convidado_pela_rede": convidado_pela_rede or None,
        "token_epoch": 0,
        "invite": {
            "token_hash": token_hash,
            "expires_at": (agora + timedelta(days=VALIDADE_DO_CONVITE_DIAS)).isoformat(),
            "sent_at": agora.isoformat(),
        },
        "created_at": agora.isoformat(),
        "updated_at": agora.isoformat(),
    }


def validar_palavra_passe(password: str) -> None:
    from services.auth import validate_password_strength

    valida, motivo = validate_password_strength(password or "")
    if not valida:
        raise HTTPException(status_code=400, detail=motivo)


@lru_cache(maxsize=1)
def _hash_falso() -> str:
    """Um hash bcrypt válido que nunca corresponde a nada.

    Verifica-se contra ele quando a conta não existe: o tempo de resposta
    não distingue «não existe» de «palavra-passe errada».
    """
    from services.auth import hash_password

    return hash_password(secrets.token_urlsafe(24))


def _verificar(password: str, hash_guardado: Optional[str]) -> bool:
    """Só bcrypt. O SHA-256 legado do `verify_password` do staff NÃO entra:
    esta família nasce sem dívida.

    Sem hash utilizável verifica-se contra o hash falso (mesmo custo) e a
    resposta é SEMPRE falsa.
    """
    from services.auth import pwd_context

    utilizavel = (hash_guardado or "").startswith(("$2a$", "$2b$", "$2y$"))
    alvo = hash_guardado if utilizavel else _hash_falso()
    try:
        correcta = bool(pwd_context.verify(password, alvo))
    except Exception:  # noqa: BLE001 — hash ilegível = não corresponde
        return False
    return correcta and utilizavel


# ====================================================================
# LOGIN
# ====================================================================
async def run_partner_login(data: PartnerLogin) -> dict:
    exigir_portal_ligado()
    email = normalizar_email(data.email)
    if not email:
        # Não é um email: nada a travar (e nenhuma chave nova no registo de
        # tentativas — texto arbitrário como identidade seria amplificação
        # de escrita).
        _verificar(data.password, None)
        raise HTTPException(status_code=401, detail=ERRO_CREDENCIAIS)

    # 1. O travão primeiro: o código de resposta de uma verificação é
    #    informação sobre a credencial.
    await portal_brute_force.exigir_sem_bloqueio(db, AMBITO_DO_LOGIN_DO_PARCEIRO, email)

    partner = await db.partners.find_one({"email": email}, {"_id": 0})
    correcta = _verificar(data.password, (partner or {}).get("password_hash"))

    if not partner or not correcta:
        await portal_brute_force.registar_falha(db, AMBITO_DO_LOGIN_DO_PARCEIRO, email)
        raise HTTPException(status_code=401, detail=ERRO_CREDENCIAIS)

    # 2. Credencial provada: agora, e só agora, diz-se o estado.
    if partner.get("status") != ESTADO_ACTIVO or not conta_com_acesso(partner):
        logger.warning("[PARCEIRO] Login recusado a %s (estado=%s).", partner["id"], partner.get("status"))
        raise HTTPException(status_code=403, detail=ERRO_CONTA_INDISPONIVEL)

    await portal_brute_force.limpar(db, AMBITO_DO_LOGIN_DO_PARCEIRO, email)
    agora = agora_iso()
    await db.partners.update_one({"id": partner["id"]}, {"$set": {"last_login_at": agora}})
    return _sessao(partner)


def _sessao(partner: dict) -> dict:
    from services.partner_security import HORAS_DE_VALIDADE

    return {
        "access_token": create_partner_token(partner),
        "token_type": "bearer",
        "expires_in": HORAS_DE_VALIDADE * 3600,
        "partner": publico(partner),
    }


# ====================================================================
# CONVITE → ACTIVAÇÃO
# ====================================================================
async def _parceiro_do_convite(token: str) -> dict:
    partner = await db.partners.find_one({"invite.token_hash": hash_de_token(token)}, {"_id": 0})
    if not partner or not convite_vigente(partner):
        raise HTTPException(status_code=400, detail=ERRO_CONVITE)
    if partner.get("status") == ESTADO_SUSPENSO:
        raise HTTPException(status_code=400, detail=ERRO_CONVITE)
    return partner


async def run_get_invite(token: str) -> dict:
    """O que o ecrã de activação precisa para se apresentar. Quem tem o
    token tem o email do convite — é o link que lhe foi enviado."""
    partner = await _parceiro_do_convite(token)
    return {
        "name": partner.get("name"),
        "email": partner.get("email"),
        "first_access": partner.get("status") == ESTADO_CONVIDADO,
        "terms_version": VERSAO_DOS_TERMOS,
    }


async def run_accept_invite(data: PartnerAcceptInvite, *, ip: str = "") -> dict:
    exigir_portal_ligado()
    partner = await _parceiro_do_convite(data.token)
    primeiro_acesso = partner.get("status") == ESTADO_CONVIDADO

    if primeiro_acesso and not data.accept_terms:
        raise HTTPException(status_code=400, detail="É necessário aceitar os termos para activar a conta.")
    validar_palavra_passe(data.password)

    from services.auth import hash_password

    agora = agora_iso()
    definir = {
        "password_hash": hash_password(data.password),
        "password_set_at": agora,
        "status": ESTADO_ACTIVO,
        "updated_at": agora,
    }
    if primeiro_acesso:
        definir["terms"] = {"version": VERSAO_DOS_TERMOS, "accepted_at": agora, "ip": (ip or "")[:45]}

    # Reivindicação atómica: o filtro inclui o hash do token, pelo que dois
    # pedidos simultâneos com o mesmo link não ganham os dois.
    resultado = await db.partners.update_one(
        {"id": partner["id"], "invite.token_hash": hash_de_token(data.token)},
        {"$set": definir, "$unset": {"invite": ""}, "$inc": {"token_epoch": 1}},
    )
    if not getattr(resultado, "modified_count", 0):
        raise HTTPException(status_code=400, detail=ERRO_CONVITE)

    # Uma palavra-passe nova também limpa um travão que tenha ficado armado.
    await portal_brute_force.limpar(db, AMBITO_DO_LOGIN_DO_PARCEIRO, partner.get("email"))

    partner = await db.partners.find_one({"id": partner["id"]}, {"_id": 0})
    if not conta_com_acesso(partner):
        raise HTTPException(status_code=403, detail=ERRO_CONTA_INDISPONIVEL)
    return _sessao(partner)


async def run_change_password(partner: dict, data: PartnerChangePassword) -> dict:
    exigir_portal_ligado()
    completo = await db.partners.find_one({"id": partner["id"]}, {"_id": 0, "password_hash": 1})
    await portal_brute_force.exigir_sem_bloqueio(db, AMBITO_DO_LOGIN_DO_PARCEIRO, partner.get("email"))
    if not _verificar(data.current_password, (completo or {}).get("password_hash")):
        await portal_brute_force.registar_falha(db, AMBITO_DO_LOGIN_DO_PARCEIRO, partner.get("email"))
        raise HTTPException(status_code=400, detail="A palavra-passe actual não está correcta.")
    validar_palavra_passe(data.new_password)

    from services.auth import hash_password

    agora = agora_iso()
    await db.partners.update_one(
        {"id": partner["id"]},
        {
            "$set": {"password_hash": hash_password(data.new_password), "password_set_at": agora, "updated_at": agora},
            "$inc": {"token_epoch": 1},
        },
    )
    await portal_brute_force.limpar(db, AMBITO_DO_LOGIN_DO_PARCEIRO, partner.get("email"))
    atualizado = await db.partners.find_one({"id": partner["id"]}, {"_id": 0})
    return _sessao(atualizado)


# ====================================================================
# GESTÃO PELA EQUIPA (Admin/CEO da rede, Master) — plano do STAFF
# ====================================================================
async def parceiro_no_ambito(partner: Optional[dict], actor: dict) -> bool:
    """Alguma das redes deste parceiro cai no âmbito de quem actua?

    Reutiliza o predicado de posse do CRM (`documento_no_ambito`) sobre um
    documento que só leva a rede: é a mesma resposta que as listagens dão.
    """
    from services.role_scope import fronteira_levantada
    from services.tenant_network import resolve_tenant_scope

    if not partner or partner.get("status") == ESTADO_ELIMINADO:
        return False
    # O Master COM empresa escolhida é estreitado à rede dela (como em todas as listagens);
    # sem empresa (vista «Sistema») não tem fronteira.
    if fronteira_levantada(actor) or _sem_rede_visivel_ao_master(partner, actor):
        return True
    scope = await resolve_tenant_scope(actor or {})
    return _no_ambito_do_actor(partner, scope)


def _sem_rede(partner: dict) -> bool:
    """Nenhuma ligação com rede e nenhuma rede do convite (PURA).

    É o independente que o Master convidou sem empresa: não cai no âmbito de
    NENHUMA empresa, logo nenhuma vista estreitada o mostra.
    """
    ligacoes = [r for r in (partner.get("redes") or []) if isinstance(r, dict) and r.get("network_id")]
    return not ligacoes and not str(partner.get("convidado_pela_rede") or "").strip()


def _sem_rede_visivel_ao_master(partner: dict, actor: dict) -> bool:
    """O Master vê o parceiro sem rede em QUALQUER vista (PURA).

    Só ele o pode gerir; escondê-lo quando há empresa escolhida deixava-o
    invisível — e o convite seguinte para o mesmo email dava 409 sem que se
    encontrasse a conta. Não alarga nada a um perfil local.
    """
    from services.role_scope import utilizador_e_global

    return utilizador_e_global(actor) and _sem_rede(partner)


def _no_ambito_do_actor(partner: dict, scope: Any) -> bool:
    """Alguma ligação do parceiro — ou, se não tem nenhuma, a rede de quem o
    convidou — cai no âmbito? (PURA)

    O agente independente não tem ligações: sem a rede do convite ninguém o
    veria nem o poderia suspender, e uma conta que ninguém gere é a que
    ninguém consegue travar. A rede do convite só vale ENQUANTO ele não tem
    ligações — a partir da primeira, mandam as ligações (a suspensão é por
    ligação, e a rede que convidou não passa a gerir as das outras).
    """
    from services.tenant_network import CAMPO_REDE, documento_no_ambito

    ligacoes = [r for r in (partner.get("redes") or []) if isinstance(r, dict)]
    if any(
        documento_no_ambito({CAMPO_REDE: r.get("network_id")}, scope)
        for r in ligacoes
        if r.get("network_id")
    ):
        return True
    rede_do_convite = str(partner.get("convidado_pela_rede") or "").strip()
    return bool(not ligacoes and rede_do_convite and documento_no_ambito({CAMPO_REDE: rede_do_convite}, scope))


async def acrescentar_ligacao_de_mercado(partner_id: str, ligacao: dict) -> None:
    """Liga o parceiro à rede de uma empresa de destino que ele escolheu (marketplace B2B).

    O parceiro é um agente livre: escolhe a empresa de destino de cada lead entre as que
    têm Index. A primeira escolha de uma rede cria a LIGAÇÃO dele a ela — é essa lista que
    a visibilidade lê («relação ∧ rede activa»), pelo que nada do resto do modelo muda, e
    a gestão dessa rede pode suspendê-la como a qualquer outra. Nunca reactiva uma
    ligação existente (suspensa ou não): quem chama já verificou que não há nenhuma.
    """
    agora = datetime.now(timezone.utc).isoformat()
    entrada = {
        "network_id": ligacao["network_id"],
        "company_id": ligacao.get("company_id"),
        "company_name": ligacao.get("company_name"),
        "status": ESTADO_ACTIVO,
        "origem": "marketplace",
        "invited_at": agora,
    }
    await db.partners.update_one(
        {"id": partner_id},
        {"$push": {"redes": entrada}, "$set": {"updated_at": agora}},
    )


async def contacto_do_parceiro(partner_id: str) -> Optional[dict]:
    """``{email, name}`` de um parceiro, para o avisar (ex.: lead devolvida).

    Vive aqui porque `db.partners` só é acedida pelos módulos de identidade
    (inventário em `test_parceiro_inventarios.py`). Devolve só o contacto —
    nunca o hash nem o estado da conta.
    """
    if not partner_id:
        return None
    parceiro = await db.partners.find_one({"id": str(partner_id)}, {"_id": 0, "email": 1, "name": 1, "status": 1})
    if not parceiro or not parceiro.get("email") or parceiro.get("status") == ESTADO_ELIMINADO:
        return None
    return {"email": parceiro["email"], "name": parceiro.get("name")}


async def parceiro_activo(partner_id: str) -> Optional[dict]:
    """``{id, name, email}`` de um parceiro com a conta ACTIVA e com acesso, ou None.

    Para a conversa do Index com o parceiro que carregou o processo: só se escreve a quem pode entrar
    no portal para ler. Nunca devolve o hash nem o estado da conta.
    """
    if not partner_id:
        return None
    parceiro = await db.partners.find_one({"id": str(partner_id)}, {"_id": 0, "password_hash": 0, "invite": 0})
    if not parceiro or parceiro.get("status") != ESTADO_ACTIVO or not conta_com_acesso(parceiro):
        return None
    return {"id": parceiro["id"], "name": parceiro.get("name") or "Parceiro", "email": parceiro.get("email")}


async def carregar_parceiro_gerivel(partner_id: str, actor: dict) -> dict:
    """O parceiro, se quem actua o pode gerir. **404** caso contrário —
    igual ao de «não existe» (nunca 403: seria um directório de contas)."""
    partner = await db.partners.find_one({"id": partner_id}, {"_id": 0, "password_hash": 0})
    # `parceiro_no_ambito` recusa o eliminado: para a gestão ele deixou de existir.
    if not partner or not await parceiro_no_ambito(partner, actor):
        raise HTTPException(status_code=404, detail="Parceiro não encontrado")
    return partner


def _redes_do_ambito(partner: dict, scope: Any, global_: bool) -> list[int]:
    from services.tenant_network import CAMPO_REDE, documento_no_ambito

    indices = []
    for i, r in enumerate(partner.get("redes") or []):
        if isinstance(r, dict) and (global_ or documento_no_ambito({CAMPO_REDE: r.get("network_id")}, scope)):
            indices.append(i)
    return indices


async def _garantir_directorio(
    partner_id: str, name: str, email: str, agora: str, criado_pela_rede: Optional[str] = None,
) -> None:
    """A linha-fantasma em `users` (ver o cabeçalho). Idempotente."""
    existente = await db.users.find_one({"id": partner_id}, {"_id": 0, "role": 1, "name": 1})
    if existente:
        if existente.get("role") != "parceiro":
            raise HTTPException(status_code=409, detail=ERRO_EMAIL_INDISPONIVEL)
        return
    await db.users.insert_one(
        {
            "id": partner_id,
            "name": name,
            "email": email,
            "role": "parceiro",
            "is_active": True,
            "partner_directory": True,
            **({"criado_pela_rede": criado_pela_rede} if criado_pela_rede else {}),
            "created_at": agora,
            "updated_at": agora,
        }
    )


async def rede_de_quem_convida(actor: dict) -> Optional[str]:
    """A rede de QUEM CONVIDA, para um parceiro sem empresa.

    Um perfil local tem uma (ou mais); fica a primeira do seu âmbito. O Master
    (sem fronteira) não tem rede própria: o parceiro fica só no âmbito global,
    que é o dele. Nunca levanta: sem rede conhecida o parceiro é criado na
    mesma e só o Master o gere.
    """
    try:
        from services.tenant_network import resolve_tenant_scope

        scope = await resolve_tenant_scope(actor or {})
        redes = [str(r).strip() for r in (getattr(scope, "network_ids", ()) or ()) if str(r).strip()]
        return redes[0] if redes else None
    except Exception as exc:  # noqa: BLE001 — informação de gestão, nunca bloqueia o convite
        logger.warning("[PARCEIRO] Sem rede para o convidante %s: %s", (actor or {}).get("id"), exc)
        return None


async def run_invite_partner(data: PartnerInvite, actor: dict) -> dict:
    from services.tenant_network import resolve_tenant_stamp
    from services.user_management_scope import exigir_empresas_concediveis

    email = normalizar_email(data.email)
    nome = sanitize_name(data.name)
    if not email:
        raise HTTPException(status_code=400, detail="Email inválido.")
    if len(nome) < 2:
        raise HTTPException(status_code=400, detail="Nome inválido.")
    telefone = sanitize_phone(data.phone) if data.phone else None

    company_id = (data.company_id or "").strip()
    empresa = None
    carimbo = None
    if company_id:
        # A empresa tem de existir e estar no âmbito de quem convida (404 nos
        # dois casos, igual): um Admin não convida para a rede de outro.
        empresa = await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1, "name": 1})
        if not empresa:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        await exigir_empresas_concediveis(actor, [company_id])

        carimbo = await resolve_tenant_stamp({}, active_company_id=company_id)
        if not carimbo or not carimbo.get("network_id"):
            raise HTTPException(status_code=400, detail="Não foi possível determinar a rede desta empresa.")
    # Sem empresa (agente independente) a rede de quem convida fica registada
    # para que o parceiro continue gerível por ela — ver `_no_ambito_do_actor`.
    rede_do_convite = (carimbo or {}).get("network_id") or await rede_de_quem_convida(actor)

    # Email já usado por um parceiro OU por um utilizador do staff: a mesma
    # recusa, sem dizer qual — nunca se liga uma conta de parceiro à de um
    # colaborador com o mesmo endereço (a escalada entre planos).
    fantasma = None
    if data.adopt_user_id:
        fantasma = await db.users.find_one({"id": data.adopt_user_id.strip()}, {"_id": 0})
        if not fantasma or fantasma.get("role") != "parceiro" or fantasma.get("password") or fantasma.get("hashed_password"):
            raise HTTPException(status_code=404, detail="Conta a adoptar não encontrada")
        if await db.partners.find_one({"id": fantasma["id"]}, {"_id": 0, "id": 1}):
            raise HTTPException(status_code=409, detail=ERRO_EMAIL_INDISPONIVEL)
        if (fantasma.get("email") or "").strip().lower() not in ("", email):
            raise HTTPException(status_code=409, detail=ERRO_EMAIL_INDISPONIVEL)

    if await db.partners.find_one({"email": email}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=409, detail=ERRO_EMAIL_INDISPONIVEL)
    outro = await db.users.find_one({"email": email}, {"_id": 0, "id": 1})
    if outro and (not fantasma or outro.get("id") != fantasma["id"]):
        raise HTTPException(status_code=409, detail=ERRO_EMAIL_INDISPONIVEL)

    agora = datetime.now(timezone.utc)
    partner_id = fantasma["id"] if fantasma else str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    ligacao = None
    if carimbo:
        ligacao = {
            "network_id": carimbo["network_id"],
            "company_id": carimbo.get("company_id") or company_id,
            "company_name": carimbo.get("company_name") or empresa.get("name"),
            "status": ESTADO_ACTIVO,
            "invited_by": actor.get("id"),
            "invited_by_name": actor.get("name"),
            "invited_at": agora.isoformat(),
        }
    doc = novo_documento_de_parceiro(
        partner_id=partner_id, name=nome, email=email, phone=telefone,
        ligacao=ligacao, token_hash=hash_de_token(token), agora=agora,
        convidado_pela_rede=rede_do_convite,
    )
    await db.partners.insert_one(dict(doc))
    await _garantir_directorio(partner_id, nome, email, agora.isoformat(), rede_do_convite)

    await _auditar(
        actor, partner_id, f"Parceiro convidado: {nome}", "partner_invite",
        {"network_id": (ligacao or {}).get("network_id"), "independente": ligacao is None},
    )
    _enviar_convite_em_segundo_plano(nome, email, token)

    return {
        "partner": publico(doc),
        # O token sai UMA vez, para o convidante: se o email falhar, copia o
        # link. Na base de dados só existe o hash.
        "invite_token": token,
        "invite_path": f"/parceiro/convite/{token}",
        "expires_at": doc["invite"]["expires_at"],
    }


async def run_resend_invite(partner_id: str, actor: dict) -> dict:
    """Novo link (e invalida o anterior). Serve também de «repor acesso»:
    sobre uma conta activa, a palavra-passe só muda quando o parceiro usar
    o link."""
    partner = await carregar_parceiro_gerivel(partner_id, actor)
    if partner.get("status") == ESTADO_SUSPENSO:
        raise HTTPException(status_code=409, detail="Conta suspensa.")

    agora = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    novo = {
        "token_hash": hash_de_token(token),
        "expires_at": (agora + timedelta(days=VALIDADE_DO_CONVITE_DIAS)).isoformat(),
        "sent_at": agora.isoformat(),
    }
    await db.partners.update_one({"id": partner_id}, {"$set": {"invite": novo, "updated_at": agora.isoformat()}})
    await _auditar(actor, partner_id, f"Convite de parceiro reenviado: {partner.get('name')}", "partner_invite_resend", {})
    _enviar_convite_em_segundo_plano(partner.get("name") or "", partner.get("email") or "", token)
    return {"invite_token": token, "invite_path": f"/parceiro/convite/{token}", "expires_at": novo["expires_at"]}


async def run_update_partner(partner_id: str, data: PartnerUpdate, actor: dict) -> dict:
    from services.role_scope import fronteira_levantada
    from services.tenant_network import resolve_tenant_scope

    partner = await carregar_parceiro_gerivel(partner_id, actor)
    agora = agora_iso()
    definir: dict[str, Any] = {"updated_at": agora}
    # O email é a identidade de login: valida-se (e recusa-se) ANTES de gravar o que quer que seja.
    novo_email = None
    if data.email is not None:
        from services import partner_accounts_admin

        novo_email = await partner_accounts_admin.validar_novo_email(partner, data.email, actor)

    if data.name is not None:
        nome = sanitize_name(data.name)
        if len(nome) < 2:
            raise HTTPException(status_code=400, detail="Nome inválido.")
        definir["name"] = nome
    if data.phone is not None:
        definir["phone"] = sanitize_phone(data.phone) or None

    incremento = False
    if novo_email:
        definir["email"] = novo_email
        incremento = True  # a identidade mudou: as sessões abertas caem
    if data.suspended is not None:
        eglobal = fronteira_levantada(actor)
        scope = None if eglobal else await resolve_tenant_scope(actor or {})
        novo_estado = ESTADO_SUSPENSO if data.suspended else ESTADO_ACTIVO
        # Reescreve-se a LISTA inteira (e não `redes.0.status`): é uma
        # operação rara de administração, e a posição de uma ligação não é
        # um identificador estável se alguém acrescentar outra entretanto.
        redes = [dict(r) if isinstance(r, dict) else r for r in (partner.get("redes") or [])]
        if redes:
            for i in _redes_do_ambito(partner, scope, eglobal):
                redes[i]["status"] = novo_estado
            definir["redes"] = redes
        else:
            # Agente independente: não há ligações onde pôr a suspensão, logo
            # é a CONTA que se suspende. Reactivar devolve-o ao estado que
            # tinha (convidado, se nunca definiu a palavra-passe).
            definir["status"] = (
                ESTADO_SUSPENSO if data.suspended
                else (ESTADO_ACTIVO if partner.get("password_set_at") or partner.get("terms") else ESTADO_CONVIDADO)
            )
        incremento = incremento or bool(data.suspended)

    operacao: dict[str, Any] = {"$set": definir}
    if incremento:
        # Suspender (ou mudar o email) mata as sessões abertas na hora.
        operacao["$inc"] = {"token_epoch": 1}
    if novo_email:
        # O convite pendente foi enviado para o endereço antigo: não pode activar a conta do novo.
        operacao["$unset"] = {"invite": ""}
    await db.partners.update_one({"id": partner_id}, operacao)

    if data.name is not None:
        await db.users.update_one({"id": partner_id, "role": "parceiro"}, {"$set": {"name": definir["name"]}})
    novo_convite = None
    if novo_email:
        await db.users.update_one({"id": partner_id, "role": "parceiro"}, {"$set": {"email": novo_email}})
        await _auditar(
            actor, partner_id, f"Email do parceiro alterado: {partner.get('name')}", "partner_email_change",
            {"convite_pendente_anulado": bool((partner.get("invite") or {}).get("token_hash"))},
        )
        if partner.get("status") == ESTADO_CONVIDADO:
            # Nunca activou a conta: o convite segue para o endereço novo.
            novo_convite = await run_resend_invite(partner_id, actor)
    if data.suspended is not None:
        await _auditar(
            actor, partner_id,
            f"Parceiro {'suspenso' if data.suspended else 'reactivado'}: {partner.get('name')}",
            "partner_suspend" if data.suspended else "partner_reactivate", {},
        )
    actualizado = await db.partners.find_one({"id": partner_id}, {"_id": 0, "password_hash": 0})
    resposta = publico(actualizado)
    if novo_convite:
        resposta["invite_path"] = novo_convite["invite_path"]
    return resposta


async def run_list_partners(actor: dict) -> dict:
    from services.role_scope import fronteira_levantada
    from services.tenant_network import resolve_tenant_scope

    # Master com empresa escolhida: só os parceiros da rede dela (a vista é estrita).
    eglobal = fronteira_levantada(actor)
    scope = None if eglobal else await resolve_tenant_scope(actor or {})
    docs = await db.partners.find({"status": {"$ne": ESTADO_ELIMINADO}}, {"_id": 0, "password_hash": 0}).to_list(2000)
    visiveis = [
        p for p in docs
        if eglobal or _sem_rede_visivel_ao_master(p, actor) or _no_ambito_do_actor(p, scope)
    ]
    visiveis.sort(key=lambda p: (p.get("name") or "").lower())
    return {"partners": [publico(p) for p in visiveis], "total": len(visiveis)}


async def run_list_partner_options(actor: dict) -> dict:
    """Parceiros para os FILTROS «Por Parceiro» (P4): ``id`` + ``nome``, e mais nada.

    Os dropdowns liam-nos da lista de utilizadores (`role == parceiro`), que desde o QA-9 não os traz
    (têm o seu separador) — e os parceiros do Portal nunca estiveram lá, vivem em `db.partners`: o
    filtro do Dashboard ficava vazio. Aqui sai quem o actor VÊ (a mesma regra da lista de gestão),
    aberto a todo o staff: um consultor filtra por parceiro sem poder ver o email nem as ligações
    dele. Contas antigas (utilizadores de role `parceiro`) entram se ainda forem referidas por
    processos, deduplicadas por id.
    """
    from services.role_scope import fronteira_levantada
    from services.tenant_network import resolve_tenant_scope

    eglobal = fronteira_levantada(actor)
    scope = None if eglobal else await resolve_tenant_scope(actor or {})
    docs = await db.partners.find(
        {"status": {"$ne": ESTADO_ELIMINADO}},
        {"_id": 0, "id": 1, "name": 1, "redes": 1, "convidado_pela_rede": 1},
    ).to_list(2000)
    opcoes: dict[str, str] = {
        str(p["id"]): str(p.get("name") or "").strip() or "Parceiro"
        for p in docs
        if p.get("id") and (eglobal or _sem_rede_visivel_ao_master(p, actor) or _no_ambito_do_actor(p, scope))
    }
    from services.admin_users_scope import build_users_scope_query, empresas_da_empresa_activa

    consulta = {"role": {"$in": ["parceiro", "partner"]}, "partner_eliminado": {"$ne": True}}
    ambito = await build_users_scope_query(await empresas_da_empresa_activa(actor or {}))
    if ambito:
        consulta = {"$and": [consulta, ambito]}
    for u in await db.users.find(consulta, {"_id": 0, "id": 1, "name": 1}).to_list(2000):
        if u.get("id") and str(u["id"]) not in opcoes:
            opcoes[str(u["id"])] = str(u.get("name") or "").strip() or "Parceiro"
    lista = sorted(({"id": i, "name": n} for i, n in opcoes.items()), key=lambda o: o["name"].lower())
    return {"partners": lista, "total": len(lista)}


async def run_get_partner(partner_id: str, actor: dict) -> dict:
    return publico(await carregar_parceiro_gerivel(partner_id, actor))


# ====================================================================
# EFEITOS LATERAIS QUE NUNCA FAZEM FALHAR A OPERAÇÃO
# ====================================================================
async def _auditar(actor: dict, partner_id: str, accao: str, campo: str, metadata: dict) -> None:
    try:
        from services.audit_trail_service import log_audit_event

        await log_audit_event(
            process_id=partner_id, user=actor, action=accao, field=campo,
            old_value=None, new_value=None, source="web",
            metadata={"partner_id": partner_id, **metadata},
        )
    except Exception as exc:  # noqa: BLE001 — observar nunca é interceptar
        logger.warning("[PARCEIRO] Falha a registar a auditoria de %s: %s", partner_id, exc)


def _enviar_convite_em_segundo_plano(nome: str, email: str, token: str) -> None:
    """O email nunca bloqueia o pedido (regra da casa). Sem `FRONTEND_URL` não
    se envia um link de adivinhar: o convidante tem o link na resposta."""
    base = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    if not base or not email:
        logger.warning("[PARCEIRO] Sem FRONTEND_URL: o convite de %s não foi enviado por email.", email)
        return
    from services.background_tasks import spawn_background_task

    spawn_background_task(_enviar_convite(nome, email, f"{base}/parceiro/convite/{token}"), name=f"partner-invite:{email}")


async def _enviar_convite(nome: str, email: str, link: str) -> None:
    try:
        from services.email_service import send_email

        corpo = (
            f"Olá {nome},\n\nFoi convidado(a) para o Portal do Parceiro. "
            f"Defina a sua palavra-passe através deste link (válido {VALIDADE_DO_CONVITE_DIAS} dias, uso único):\n\n"
            f"{link}\n\nSe não estava à espera deste convite, ignore esta mensagem."
        )
        await send_email(
            account_name="power", to_emails=[email],
            subject="Convite — Portal do Parceiro", body=corpo,
            force_system=True, system_purpose="NOTIFICATIONS",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO] Falha a enviar o convite a %s: %s", email, exc)


__all__ = [
    "AMBITO_DO_LOGIN_DO_PARCEIRO",
    "PartnerAcceptInvite",
    "PartnerChangePassword",
    "PartnerInvite",
    "PartnerLogin",
    "PartnerUpdate",
    "VERSAO_DOS_TERMOS",
    "carregar_parceiro_gerivel",
    "convite_vigente",
    "normalizar_email",
    "parceiro_no_ambito",
    "publico",
    "run_accept_invite",
    "run_change_password",
    "run_get_invite",
    "run_get_partner",
    "run_invite_partner",
    "run_list_partners",
    "run_partner_login",
    "run_resend_invite",
    "run_update_partner",
]
