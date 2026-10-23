"""
GESTÃO AVANÇADA DE PARCEIROS — email, empresa, eliminação e nova palavra-passe
==============================================================================
O que o `partner_accounts` já fazia (convidar, reenviar, nome/telefone, suspender)
continua lá. Aqui vivem as quatro acções de CONTROLO TOTAL do Master, que mexem na
IDENTIDADE, nas CREDENCIAIS ou na EXISTÊNCIA da conta:

  * **alterar o email** (`validar_novo_email`, chamada pelo `run_update_partner`);
  * **mudar de empresa** (`run_change_company`);
  * **eliminar** (`run_delete_partner`) — com a password do Master;
  * **gerar nova palavra-passe** (`run_reset_password`).

TODAS são só do MASTER (a conta, qualquer chapéu): o `require_roles` autoriza o
verbo e o serviço repete a pergunta (defesa em profundidade); o objecto passa por
`carregar_parceiro_gerivel` (404 fora do âmbito — com uma empresa escolhida no
cabeçalho, só os parceiros da rede dela).

REGRAS QUE NÃO SE PODEM PERDER
  1. **Eliminar é SOFT delete e liberta o email.** O `id` fica (processos e
     histórico apontam para ele); a conta deixa de existir para o login, as listas
     e a gestão (`status = deleted`, 404). Saem o hash, o convite, o IP dos termos,
     o telefone, as ligações e o email — que passa a um endereço-marcador único, para
     o índice único do email não bloquear um convite futuro ao mesmo endereço. O
     NOME fica: as atribuições e o histórico continuam a dizer quem foi.
  2. **A password do Master vem ANTES de qualquer escrita** (acção destrutiva).
  3. **A palavra-passe nova só se grava DEPOIS de o email sair** (precedente do
     reenvio de convite do staff): sem entrega, nada muda (502) — senão o parceiro
     ficava sem entrada e sem saber a nova. Nunca vai para o rasto nem para a
     resposta; as sessões abertas caem e o travão de login limpa-se.
  4. **Mudar de empresa substitui as ligações DE CONVITE/GESTÃO e mantém as de
     MERCADO** (as que o próprio parceiro criou ao escolher um destino): a gestão
     não lhe tira as redes com que ele trabalha por escolha. Não reactiva uma
     suspensão — uma conta suspensa continua suspensa na empresa nova.
  5. **Mudar o email invalida o convite pendente** (foi enviado para o endereço
     antigo) e deita abaixo as sessões; num parceiro que nunca activou a conta o
     convite segue logo para o endereço novo.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import Field

from database import db
from services import portal_brute_force
from services.partner_accounts import (
    AMBITO_DO_LOGIN_DO_PARCEIRO,
    ERRO_EMAIL_INDISPONIVEL,
    _Estrito,
    _auditar,
    carregar_parceiro_gerivel,
    normalizar_email,
    publico,
)
from services.partner_security import (
    ESTADO_ACTIVO,
    ESTADO_CONVIDADO,
    ESTADO_ELIMINADO,
    ESTADO_SUSPENSO,
)
from services.role_scope import conta_e_master

logger = logging.getLogger(__name__)

ORIGEM_DE_MERCADO = "marketplace"
ORIGEM_DA_TRANSFERENCIA = "transferencia"
DOMINIO_DO_MARCADOR = "placeholder.internal"
#: O envio é interactivo (o Master espera pelo resultado) mas nunca à espera do SMTP.
TECTO_DO_ENVIO_SEGUNDOS = 15

ERRO_SO_MASTER = "Esta acção é exclusiva do perfil Master."


class PartnerChangeCompany(_Estrito):
    company_id: str = Field(..., min_length=1, max_length=80)


def _exigir_master(actor: dict) -> None:
    if not conta_e_master(actor):
        raise HTTPException(status_code=403, detail=ERRO_SO_MASTER)


# ====================================================================
# PURAS
# ====================================================================
def email_marcador(partner_id: str) -> str:
    """Endereço que nunca recebe correio e é único por parceiro (liberta o email real)."""
    return f"parceiro-eliminado-{partner_id}@{DOMINIO_DO_MARCADOR}"


def gerar_palavra_passe(tamanho: int = 16) -> str:
    """Aleatória (CSPRNG), cumpre a política da casa e evita caracteres que se confundem."""
    minusculas = "abcdefghijkmnopqrstuvwxyz"
    maiusculas = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    digitos = "23456789"
    especiais = "@$!%*?&#"
    todos = minusculas + maiusculas + digitos + especiais
    tamanho = max(tamanho, 12)
    caracteres = [secrets.choice(c) for c in (minusculas, maiusculas, digitos, especiais)]
    caracteres += [secrets.choice(todos) for _ in range(tamanho - len(caracteres))]
    secrets.SystemRandom().shuffle(caracteres)
    return "".join(caracteres)


def calcular_redes_apos_mudanca(redes: list, nova_ligacao: dict) -> list:
    """As ligações do parceiro depois de mudar de empresa. PURA.

    * as de MERCADO (escolhidas pelo parceiro) de OUTRAS redes mantêm-se;
    * as de convite/gestão — e qualquer uma já ligada à rede de destino — são
      substituídas pela nova;
    * a nova herda a SUSPENSÃO: se tudo o que foi substituído estava suspenso, a
      nova nasce suspensa (mudar de empresa não reactiva ninguém).
    """
    ligacoes = [r for r in (redes or []) if isinstance(r, dict)]
    rede_nova = nova_ligacao.get("network_id")
    mantidas, substituidas = [], []
    for r in ligacoes:
        de_mercado = r.get("origem") == ORIGEM_DE_MERCADO
        if de_mercado and r.get("network_id") != rede_nova:
            mantidas.append(r)
        else:
            substituidas.append(r)
    nova = dict(nova_ligacao)
    if substituidas and all((r.get("status") or ESTADO_ACTIVO) == ESTADO_SUSPENSO for r in substituidas):
        nova["status"] = ESTADO_SUSPENSO
    return [*mantidas, nova]


def ja_esta_na_empresa(redes: list, company_id: str) -> bool:
    """Já só tem UMA ligação de convite/gestão e é a esta empresa? (mudar seria um no-op)"""
    de_gestao = [
        r for r in (redes or [])
        if isinstance(r, dict) and r.get("origem") != ORIGEM_DE_MERCADO
    ]
    return len(de_gestao) == 1 and de_gestao[0].get("company_id") == company_id


# ====================================================================
# EMAIL
# ====================================================================
async def validar_novo_email(partner: dict, email: str, actor: dict) -> Optional[str]:
    """O email normalizado a gravar, ou `None` se não muda. SEM ESCRITAS.

    Só o Master (é a identidade de login). O endereço não pode estar em uso por outro
    parceiro nem por um utilizador do staff — a mesma recusa opaca do convite.
    """
    _exigir_master(actor)
    novo = normalizar_email(email)
    if not novo:
        raise HTTPException(status_code=400, detail="Email inválido.")
    if novo == (partner.get("email") or ""):
        return None
    if await db.partners.find_one({"email": novo, "id": {"$ne": partner["id"]}}, {"_id": 0, "id": 1}):
        raise HTTPException(status_code=409, detail=ERRO_EMAIL_INDISPONIVEL)
    outro = await db.users.find_one({"email": novo}, {"_id": 0, "id": 1})
    if outro and outro.get("id") != partner["id"]:
        raise HTTPException(status_code=409, detail=ERRO_EMAIL_INDISPONIVEL)
    return novo


# ====================================================================
# MUDAR DE EMPRESA
# ====================================================================
async def run_change_company(partner_id: str, data: PartnerChangeCompany, actor: dict) -> dict:
    from services.tenant_network import resolve_tenant_stamp

    _exigir_master(actor)
    partner = await carregar_parceiro_gerivel(partner_id, actor)

    company_id = data.company_id.strip()
    empresa = await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1, "name": 1})
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    carimbo = await resolve_tenant_stamp({}, active_company_id=company_id)
    if not carimbo or not carimbo.get("network_id"):
        raise HTTPException(status_code=400, detail="Não foi possível determinar a rede desta empresa.")

    if ja_esta_na_empresa(partner.get("redes"), company_id):
        return {**publico(partner), "alterado": False}

    agora = datetime.now(timezone.utc).isoformat()
    nova = {
        "network_id": carimbo["network_id"],
        "company_id": carimbo.get("company_id") or company_id,
        "company_name": carimbo.get("company_name") or empresa.get("name"),
        "status": ESTADO_ACTIVO,
        "origem": ORIGEM_DA_TRANSFERENCIA,
        "invited_by": actor.get("id"),
        "invited_by_name": actor.get("name"),
        "invited_at": agora,
    }
    redes = calcular_redes_apos_mudanca(partner.get("redes"), nova)
    anteriores = [r.get("company_name") for r in (partner.get("redes") or []) if isinstance(r, dict)]

    await db.partners.update_one(
        {"id": partner_id},
        {"$set": {"redes": redes, "convidado_pela_rede": nova["network_id"], "updated_at": agora}},
    )
    await db.users.update_one(
        {"id": partner_id, "role": "parceiro"},
        {"$set": {"criado_pela_rede": nova["network_id"], "updated_at": agora}},
    )
    await _auditar(
        actor, partner_id, f"Parceiro movido para {nova['company_name']}: {partner.get('name')}",
        "partner_company_change",
        {"para_empresa": nova["company_id"], "para_rede": nova["network_id"], "de_empresas": anteriores},
    )
    actualizado = await db.partners.find_one({"id": partner_id}, {"_id": 0, "password_hash": 0})
    return {**publico(actualizado), "alterado": True}


# ====================================================================
# ELIMINAR
# ====================================================================
async def run_delete_partner(partner_id: str, password: Optional[str], actor: dict) -> dict:
    from services.reauth_password import exigir_password_actual

    _exigir_master(actor)
    partner = await carregar_parceiro_gerivel(partner_id, actor)
    # Acção destrutiva: a password do Master antes de QUALQUER escrita.
    await exigir_password_actual(actor, password)

    agora = datetime.now(timezone.utc).isoformat()
    marcador = email_marcador(partner_id)
    await db.partners.update_one(
        {"id": partner_id},
        {
            "$set": {
                "status": ESTADO_ELIMINADO,
                "email": marcador,
                "phone": None,
                "redes": [],
                "convidado_pela_rede": None,
                "eliminado_em": agora,
                "eliminado_por": actor.get("id"),
                "updated_at": agora,
            },
            "$unset": {"password_hash": "", "invite": "", "terms.ip": ""},
            "$inc": {"token_epoch": 1},
        },
    )
    # A linha-fantasma do directório: o nome fica (atribuições e histórico), o resto não.
    await db.users.update_one(
        {"id": partner_id, "role": "parceiro"},
        {"$set": {"email": marcador, "is_active": False, "partner_eliminado": True, "updated_at": agora}},
    )
    await portal_brute_force.limpar(db, AMBITO_DO_LOGIN_DO_PARCEIRO, partner.get("email"))
    await _auditar(
        actor, partner_id, f"Parceiro eliminado: {partner.get('name')}", "partner_delete",
        {"tinha_ligacoes": len(partner.get("redes") or [])},
    )
    return {"deleted": True, "id": partner_id}


# ====================================================================
# NOVA PALAVRA-PASSE
# ====================================================================
def _corpo_do_email(nome: str, email: str, palavra_passe: str, login_url: str) -> str:
    ligacao = f"\n\nEntre em: {login_url}" if login_url else ""
    return (
        f"Olá {nome},\n\nFoi gerada uma nova palavra-passe para a sua conta do Portal do Parceiro.\n\n"
        f"Email: {email}\nNova palavra-passe: {palavra_passe}{ligacao}\n\n"
        "A palavra-passe anterior deixou de funcionar. Por segurança, altere-a na área «Conta» "
        "depois de entrar. Se não estava à espera desta mensagem, contacte o seu consultor."
    )


async def _enviar_credenciais(nome: str, email: str, palavra_passe: str) -> bool:
    """Envia e DIZ se saiu. Nunca levanta (quem chama traduz a falha num 502)."""
    base = (os.environ.get("FRONTEND_URL") or "").rstrip("/")
    login_url = f"{base}/parceiro/entrar" if base else ""
    try:
        from services.email_service import send_email

        resultado = await asyncio.wait_for(
            send_email(
                account_name="power", to_emails=[email],
                subject="Portal do Parceiro — nova palavra-passe",
                body=_corpo_do_email(nome, email, palavra_passe, login_url),
                force_system=True, system_purpose="NOTIFICATIONS", guardar_copia=False,
            ),
            timeout=TECTO_DO_ENVIO_SEGUNDOS,
        )
        return bool((resultado or {}).get("success"))
    except Exception as exc:  # noqa: BLE001 — a causa vai para o log; a palavra-passe nunca
        logger.warning("[PARCEIRO] Falha a enviar a nova palavra-passe: %s", type(exc).__name__)
        return False


async def run_reset_password(partner_id: str, actor: dict) -> dict:
    from services.auth import hash_password

    _exigir_master(actor)
    partner = await carregar_parceiro_gerivel(partner_id, actor)
    estado = partner.get("status")
    if estado == ESTADO_SUSPENSO:
        raise HTTPException(status_code=409, detail="Conta suspensa.")
    if estado == ESTADO_CONVIDADO:
        raise HTTPException(
            status_code=409,
            detail="Este parceiro ainda não activou a conta: use «Reenviar Convite».",
        )

    palavra_passe = gerar_palavra_passe()
    # O email PRIMEIRO: sem entrega, nada muda.
    if not await _enviar_credenciais(partner.get("name") or "", partner.get("email") or "", palavra_passe):
        raise HTTPException(
            status_code=502,
            detail="Não foi possível enviar o email com a nova palavra-passe. Nada foi alterado.",
        )

    agora = datetime.now(timezone.utc).isoformat()
    await db.partners.update_one(
        {"id": partner_id},
        {
            "$set": {"password_hash": hash_password(palavra_passe), "password_set_at": agora, "updated_at": agora},
            "$inc": {"token_epoch": 1},
        },
    )
    await portal_brute_force.limpar(db, AMBITO_DO_LOGIN_DO_PARCEIRO, partner.get("email"))
    await _auditar(
        actor, partner_id, f"Nova palavra-passe gerada: {partner.get('name')}", "partner_password_reset", {},
    )
    return {"sent": True, "email": partner.get("email")}


__all__ = [
    "PartnerChangeCompany",
    "calcular_redes_apos_mudanca",
    "email_marcador",
    "gerar_palavra_passe",
    "ja_esta_na_empresa",
    "run_change_company",
    "run_delete_partner",
    "run_reset_password",
    "validar_novo_email",
]
