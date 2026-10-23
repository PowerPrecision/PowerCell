"""
====================================================================
PORTAL DO CLIENTE — O HUB: a identidade é o CLIENTE, o contexto é o PROCESSO (D-42)
====================================================================
Com a identidade global (NIF/Email) o mesmo cliente pode ter processos em
empresas diferentes — «Crédito Habitação · Power Real Estate» e «Crédito
Pessoal · Domus». O Portal tinha um token POR PROCESSO (`sub = process_id`) e,
com ele, só via um. Este módulo acrescenta a camada que faltava:

  * o **token do Hub** (`type = client_hub`, `sub = client_id`) é a credencial
    ancorada ao CLIENTE. Só serve para duas coisas — listar os seus processos
    activos e escolher um;
  * escolher um processo devolve o token de sempre, DESSE processo
    (`access_code_session`, `sub = process_id`). Todas as rotas existentes
    (documentos, mensagens, perfil, tempo real…) continuam a ler o processo do
    token: o contexto do Portal adapta-se ao processo escolhido sem que nenhuma
    delas tenha de saber que existe um Hub. O cliente só vê os documentos e as
    tarefas desse processo.

A SEGURANÇA, EM CINCO REGRAS
  1. **Os tipos não se misturam.** O token do Hub não abre nenhuma rota de
     processo (`get_current_client` só aceita os três tipos de sempre), não abre
     o WebSocket (`TIPOS_DO_PORTAL` não o inclui) nem nenhuma rota de staff; e um
     token de processo não abre o Hub.
  2. **A posse é do servidor.** Escolher um processo que não é do cliente — ou
     que não está no que o token lhe permite — é 404, igual ao de «não existe»:
     nunca se confirma um id alheio. O cliente é titular quando o processo o
     refere em `client_id`, `second_client_id` ou `client_ids`.
  3. **O token diz que redes cobre (`nets`).** O login por Email + Código de
     Acesso é uma credencial do próprio cliente e cobre todas as suas redes.
     O link e a verificação por NIF + nº de processo — que a equipa de UMA
     empresa gera e pode ter na mão — cobrem só a rede do processo a que
     pertencem: a equipa da Power não ganha, por ter um link do cliente, a porta
     para o processo que ele tem na Domus.
  4. **«Ver como cliente» não sobe.** A personificação do staff continua a emitir
     o token de PROCESSO, sem Hub: o consultor vê exactamente o que o cliente vê
     DESSE processo, nunca os das outras empresas.
  5. **Só processos activos.** Um processo numa fase terminal não se oferece (o
     Portal dele está bloqueado); se TODOS estão inactivos, o Hub responde com o
     mesmo 403 do Portal inactivo — nunca com uma lista vazia que pareça «não há
     processos».

LIMITE DITO (e decisão para o dono do produto)
  O código de acesso é um segredo do cliente que a equipa da empresa DONA do
  registo também conhece (vai-lhe no email e vê-o na ficha). Com o Hub, quem o
  usar para entrar em nome do cliente passa a poder escolher também os processos
  que ele tem noutras empresas. A regra 3 fecha isto para links e verificações,
  não para o login por código. O fecho é um segundo factor (código por email) ao
  mudar de empresa — fica registado em `TECHNICAL_DEBT.md`.
====================================================================
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import JWT_ALGORITHM
from database import db
from services.portal_estado import erro_portal_inativo, estado_e_terminal
from services.portal_jwt_secret import descodificar_token_do_portal, segredo_de_assinatura
from services.portal_security import (
    PORTAL_ROLE,
    PORTAL_SESSION_VALIDITY_HOURS,
    create_access_code_session_token,
)
from services.ws_client_identity import TIPO_DO_HUB
from services.workflow_phases import chave_da_rede, fases_por_rede, rede_do_processo, resolver_nome

logger = logging.getLogger(__name__)


#: Os processos de um cliente que se mostram, no máximo (um cliente com mais é dado sujo).
MAX_PROCESSOS_NO_HUB = 50

ROTULOS_DE_TIPO = {
    "credito_habitacao": "Crédito Habitação",
    "credito_pessoal": "Crédito Pessoal",
    "compra_direta": "Compra Directa",
    "refinanciamento": "Refinanciamento",
    "arrendamento": "Arrendamento",
    "seguros": "Seguros",
    "consultoria": "Consultoria",
    "outro": "Outro",
}
ROTULO_DE_TIPO_POR_OMISSAO = "Processo"

_esquema = HTTPBearer(auto_error=False)

PROJECCAO_DO_PROCESSO_DO_HUB = {
    "_id": 0, "id": 1, "process_number": 1, "process_type": 1, "status": 1,
    "company_id": 1, "company_name": 1, "network_id": 1, "created_at": 1,
}


# ====================================================================
# 1. O TOKEN
# ====================================================================
def criar_token_do_hub(
    client_id: str,
    *,
    redes_permitidas: Optional[Iterable[str]] = None,
    processo_de_entrada: Optional[str] = None,
) -> str:
    """Token ancorado ao CLIENTE. ``redes_permitidas=None`` cobre todas as redes dele.

    ``redes_permitidas`` presente (mesmo vazio) RESTRINGE: é o que um link ou uma
    verificação por NIF dá. ``processo_de_entrada`` é o processo a que o link
    levava — só uma pista de interface (o servidor continua a verificar a posse).
    """
    agora = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": client_id,
        "client_id": client_id,
        "role": PORTAL_ROLE,
        "type": TIPO_DO_HUB,
        "iat": agora,
        "exp": agora + timedelta(hours=PORTAL_SESSION_VALIDITY_HOURS),
    }
    if redes_permitidas is not None:
        payload["nets"] = sorted({str(r).strip() for r in redes_permitidas if r and str(r).strip()})
    if processo_de_entrada:
        payload["entrada"] = processo_de_entrada
    return jwt.encode(payload, segredo_de_assinatura(), algorithm=JWT_ALGORITHM)


def redes_do_token(payload: dict) -> Optional[set[str]]:
    """``None`` = todas as redes do cliente; um conjunto (possivelmente vazio) = só essas."""
    if "nets" not in payload:
        return None
    nets = payload.get("nets")
    if not isinstance(nets, (list, tuple, set)):
        # Um valor do tipo errado fecha: «todas» por causa de uma claim estragada seria abrir.
        return set()
    return {str(r) for r in nets if r}


async def get_current_hub(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_esquema),
) -> dict[str, Any]:
    """Dependência das rotas do Hub: só aceita o token do Hub."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Sessão do Portal em falta. Inicie sessão.")
    try:
        payload = descodificar_token_do_portal(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="A sessão expirou. Inicie sessão novamente.")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Sessão inválida.")

    if payload.get("role") != PORTAL_ROLE:
        raise HTTPException(status_code=403, detail="Este token não tem permissão para aceder ao portal.")
    if payload.get("type") != TIPO_DO_HUB:
        raise HTTPException(status_code=403, detail="Token de tipo incorreto para o portal.")

    client_id = payload.get("sub")
    if not client_id or payload.get("client_id") != client_id:
        raise HTTPException(status_code=401, detail="Sessão inválida.")

    cliente = await db.clients.find_one(
        {"id": client_id, "is_deleted": {"$ne": True}}, {"_id": 0, "id": 1, "nome": 1},
    )
    if not cliente:
        raise HTTPException(status_code=401, detail="Sessão inválida.")
    return {"client_id": client_id, "client": cliente, "nets": redes_do_token(payload), "token_payload": payload}


# ====================================================================
# 2. OS PROCESSOS DO CLIENTE
# ====================================================================
def _rotulo_da_fase(status: Optional[str], fases: list[dict]) -> str:
    if not status:
        return ""
    resolucao = resolver_nome(status, fases)
    nome = resolucao.fase if resolucao.resolvida else status
    for fase in fases:
        if fase.get("name") == nome:
            return str(fase.get("label") or fase.get("name") or status)
    return str(status)


def dto_do_processo(processo: dict, fases: list[dict], empresa: Optional[str]) -> dict[str, Any]:
    """O que o cliente vê de um processo no Hub: lista POSITIVA, nada de notas nem de equipa."""
    tipo = processo.get("process_type") or ""
    return {
        "id": processo.get("id"),
        "numero": processo.get("process_number"),
        "tipo": tipo,
        "tipo_rotulo": ROTULOS_DE_TIPO.get(tipo, ROTULO_DE_TIPO_POR_OMISSAO),
        "empresa": empresa,
        "estado_rotulo": _rotulo_da_fase(processo.get("status"), fases),
    }


async def _nomes_das_empresas(processos: list[dict]) -> dict[str, str]:
    ids = sorted({p["company_id"] for p in processos if p.get("company_id") and not p.get("company_name")})
    if not ids:
        return {}
    encontradas = await db.companies.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(len(ids))
    return {e["id"]: e.get("name") for e in encontradas if e.get("id")}


async def processos_do_cliente(client_id: str, redes_permitidas: Optional[set[str]]) -> tuple[list[dict], list[dict]]:
    """``(activos, inactivos)`` do cliente, já dentro do que o token permite. Os activos em DTO."""
    consulta = {
        "$or": [{"client_id": client_id}, {"second_client_id": client_id}, {"client_ids": client_id}],
        "is_deleted": {"$ne": True},
    }
    processos = await db.processes.find(consulta, PROJECCAO_DO_PROCESSO_DO_HUB).to_list(MAX_PROCESSOS_NO_HUB)
    if redes_permitidas is not None:
        processos = [p for p in processos if (rede_do_processo(p) or "") in redes_permitidas]
    if not processos:
        return [], []

    fases_das_redes = await fases_por_rede(rede_do_processo(p) for p in processos)
    empresas = await _nomes_das_empresas(processos)
    activos: list[dict] = []
    inactivos: list[dict] = []
    for p in sorted(processos, key=lambda x: str(x.get("created_at") or ""), reverse=True):
        fases = fases_das_redes[chave_da_rede(rede_do_processo(p))]
        if estado_e_terminal(p.get("status"), fases):
            inactivos.append(p)
            continue
        nome_da_empresa = p.get("company_name") or empresas.get(p.get("company_id"))
        activos.append(dto_do_processo(p, fases, nome_da_empresa))
    return activos, inactivos


async def listar_para_o_hub(hub: dict) -> dict[str, Any]:
    """A resposta de `GET /portal/hub`. Todos inactivos = o 403 do Portal inactivo, nunca uma lista vazia."""
    activos, inactivos = await processos_do_cliente(hub["client_id"], hub["nets"])
    if not activos and inactivos:
        raise erro_portal_inativo()
    return {
        "cliente_nome": (hub.get("client") or {}).get("nome") or "",
        "processos": activos,
        "entrada": hub["token_payload"].get("entrada"),
    }


# ====================================================================
# 3. ESCOLHER UM PROCESSO
# ====================================================================
async def seleccionar_processo(hub: dict, process_id: str) -> dict[str, Any]:
    """Emite o token de processo para um processo DO cliente. 404 para tudo o resto.

    A posse e o âmbito saem da MESMA função que a listagem (`processos_do_cliente`): um
    processo que a lista não mostra não se escolhe, e não há segunda regra para divergir.
    """
    process_id = (process_id or "").strip()
    activos, inactivos = await processos_do_cliente(hub["client_id"], hub["nets"])
    escolhido = next((p for p in activos if p["id"] == process_id), None)
    if not escolhido:
        if any(p.get("id") == process_id for p in inactivos):
            # É dele e está suspenso: o mesmo aviso que o Portal dá (não revela nada de alheio).
            raise erro_portal_inativo()
        raise HTTPException(status_code=404, detail="Processo não encontrado.")

    token = create_access_code_session_token(process_id=process_id, client_id=hub["client_id"])
    logger.info(
        "[PORTAL-HUB] Cliente %s escolheu o processo %s (empresa %s).",
        hub["client_id"], process_id, escolhido.get("empresa"),
    )
    return {
        "token": token,
        "process_id": process_id,
        "client_id": hub["client_id"],
        "token_type": "access_code_session",
        "expires_in": PORTAL_SESSION_VALIDITY_HOURS * 60 * 60,
        "processo": escolhido,
    }


# ====================================================================
# 4. ACRESCENTAR O HUB A UMA RESPOSTA DE LOGIN
# ====================================================================
async def anexar_hub(
    resposta: dict,
    client_id: Optional[str],
    *,
    redes_permitidas: Optional[Iterable[str]],
    processo_de_entrada: Optional[str] = None,
) -> dict:
    """Acrescenta ``hub_token`` e ``processos`` a uma resposta de login/resolve. NUNCA levanta.

    O login já correu e já escolheu o processo por omissão; o Hub é um acrescento. Se falhar,
    a resposta sai como sempre saiu — um soluço do Hub não pode deixar o cliente à porta.
    """
    resposta.setdefault("processos", [])
    if not client_id:
        return resposta
    try:
        redes = None if redes_permitidas is None else set(redes_permitidas)
        activos, _inactivos = await processos_do_cliente(client_id, redes)
        resposta["processos"] = activos
        if activos:
            resposta["hub_token"] = criar_token_do_hub(
                client_id, redes_permitidas=redes, processo_de_entrada=processo_de_entrada,
            )
    except Exception as exc:  # noqa: BLE001 — o acrescento nunca derruba o login
        logger.warning("[PORTAL-HUB] Não foi possível montar o Hub do cliente %s: %s", client_id, exc)
        resposta["processos"] = []
        resposta.pop("hub_token", None)
    return resposta


__all__ = [
    "TIPO_DO_HUB",
    "anexar_hub",
    "criar_token_do_hub",
    "dto_do_processo",
    "get_current_hub",
    "listar_para_o_hub",
    "processos_do_cliente",
    "redes_do_token",
    "seleccionar_processo",
]
