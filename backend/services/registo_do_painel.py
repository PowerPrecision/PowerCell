"""Rasto das alterações feitas no Painel de Administração (Flavio, Nov 2026).

Duas regras do Flavio (revisão do painel, perguntas 13a e 14a):

* **14a** — cada gravação no painel fica no Registo de auditoria (quem,
  quando, o que mudou), visível ao Admin/CEO da empresa. Antes ficava só uma
  linha no log do servidor, que ninguém da empresa vê.
* **13a** — o Workflow, o Formulário público e as Automações são da REDE
  (Power, Precision e Sistema partilham-nos). Quem é Admin/CEO de uma empresa
  pode alterá-los, mas a Gestão (Diretor e CEO) das OUTRAS empresas da rede
  recebe um aviso no sino — sem Telegram nem som (regra 13 das notificações:
  só apita o que é urgente).

Nada disto pode fazer falhar a gravação: o rasto é tolerante a falhas.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from database import db

logger = logging.getLogger(__name__)

#: O valor que se grava no rasto em vez de uma password/chave.
MASCARA = "••••••••"

#: Partes de nome que marcam um campo como segredo (nunca vão para o rasto).
_SEGREDOS = ("password", "secret", "api_key", "api_token", "access_token", "access_key")

#: Os papéis da «Gestão» de uma empresa que recebem o aviso de alteração da rede.
PAPEIS_DA_GESTAO = ("diretor", "ceo")

#: Tipo das notificações no sino (não está na lista do que apita).
TIPO_DO_AVISO = "painel_rede_alterada"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def e_segredo(campo: str) -> bool:
    nome = _texto(campo).lower()
    return any(parte in nome for parte in _SEGREDOS)


def _curto(valor: Any, limite: int = 300) -> str:
    try:
        texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, default=str)
    except Exception:  # noqa: BLE001
        texto = str(valor)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


def campos_alterados(antes: Optional[dict], depois: Optional[dict]) -> dict[str, tuple[Any, Any]]:
    """`{campo: (antes, depois)}` só do que mudou; os segredos vão mascarados.

    Um segredo reenviado mascarado (o ecrã nunca recebe o valor real) não é
    uma alteração.
    """
    antes = antes or {}
    depois = depois or {}
    mudancas: dict[str, tuple[Any, Any]] = {}
    for campo, novo in depois.items():
        velho = antes.get(campo)
        if novo == velho:
            continue
        if e_segredo(campo):
            if novo in (None, "", MASCARA):
                continue
            mudancas[campo] = (MASCARA if velho else None, MASCARA)
            continue
        mudancas[campo] = (velho, novo)
    return mudancas


async def registar_alteracao(
    user: Optional[dict],
    request: Any,
    *,
    area: str,
    company_id: Optional[str] = None,
    antes: Optional[dict] = None,
    depois: Optional[dict] = None,
    descricao: Optional[str] = None,
) -> Optional[str]:
    """Uma linha no Registo de auditoria por gravação. Devolve o id ou `None`.

    Sem `antes`/`depois` (criar/eliminar), regista só a `descricao`. Com eles,
    só se houver alguma diferença.
    """
    from services.audit_trail_service import log_audit_event

    mudancas = campos_alterados(antes, depois) if depois is not None else {}
    if depois is not None and not mudancas and not descricao:
        return None
    try:
        return await log_audit_event(
            process_id=None,
            user=user or {},
            action=f"Painel de Administração — {area}" + (f": {descricao}" if descricao else ""),
            field=", ".join(sorted(mudancas)) or None,
            old_value=_curto({c: v[0] for c, v in mudancas.items()}) if mudancas else None,
            new_value=_curto({c: v[1] for c, v in mudancas.items()}) if mudancas else None,
            request=request,
            source="web",
            metadata={"painel": True, "area": area, "company_id": company_id or "default"},
        )
    except Exception as exc:  # noqa: BLE001 — o rasto nunca desfaz a gravação
        logger.warning("[registo_do_painel] Falha a registar %s (%s).", area, exc)
        return None


async def _empresa_e_rede_activas(user: dict, request: Any) -> tuple[Optional[str], Optional[str]]:
    """A empresa activa de quem gravou e a rede dela."""
    from services.auth import get_active_company_id_async

    empresa = None
    try:
        empresa = await get_active_company_id_async(request, user) if request is not None else None
    except Exception:  # noqa: BLE001
        empresa = None
    empresa = _texto(empresa) or _texto((user or {}).get("company"))
    if not empresa:
        return None, None
    doc = await db.companies.find_one(
        {"$or": [{"id": empresa}, {"name": empresa}]}, {"_id": 0, "id": 1, "network_id": 1},
    )
    if not doc:
        return empresa, None
    return _texto(doc.get("id")) or empresa, _texto(doc.get("network_id")) or None


async def gestao_das_outras_empresas(rede: str, empresa_de_quem_gravou: Optional[str], *, excluir: Iterable[str] = ()) -> list[str]:
    """Ids dos Diretores/CEO das empresas da rede, menos a de quem gravou e menos `excluir`."""
    empresas = await db.companies.find(
        {"network_id": rede, "is_deleted": {"$ne": True}}, {"_id": 0, "id": 1},
    ).to_list(200)
    outras = [_texto(e.get("id")) for e in empresas if _texto(e.get("id")) and _texto(e.get("id")) != _texto(empresa_de_quem_gravou)]
    if not outras:
        return []
    ucrs = await db.user_company_roles.find(
        {
            "company_id": {"$in": outras},
            "role": {"$in": list(PAPEIS_DA_GESTAO)},
            "is_deleted": {"$ne": True},
            "is_active": {"$ne": False},
        },
        {"_id": 0, "user_id": 1},
    ).to_list(1000)
    fora = {_texto(i) for i in excluir}
    return [uid for uid in dict.fromkeys(_texto(u.get("user_id")) for u in ucrs) if uid and uid not in fora]


async def avisar_alteracao_da_rede(
    user: Optional[dict],
    request: Any,
    *,
    area: str,
    descricao: str,
    link: str = "/system-admin?grupo=operacao",
) -> int:
    """Aviso no sino à Gestão das outras empresas da rede. Devolve quantos avisos criou."""
    try:
        empresa, rede = await _empresa_e_rede_activas(user or {}, request)
        if not rede:
            return 0
        destinatarios = await gestao_das_outras_empresas(rede, empresa, excluir=[(user or {}).get("id")])
        if not destinatarios:
            return 0
        nome = _texto((user or {}).get("name")) or "Alguém"
        nome_empresa = None
        if empresa:
            doc = await db.companies.find_one({"id": empresa}, {"_id": 0, "name": 1})
            nome_empresa = _texto((doc or {}).get("name")) or None
        quem = f"{nome} ({nome_empresa})" if nome_empresa else nome
        mensagem = f"{quem} alterou {area}, que é partilhado pela rede: {descricao}"
        agora = datetime.now(timezone.utc).isoformat()
        await db.notifications.insert_many([
            {
                "id": str(uuid.uuid4()),
                "user_id": uid,
                "message": mensagem,
                "type": TIPO_DO_AVISO,
                "process_id": None,
                "link": link,
                "read": False,
                "urgente": False,
                "alerta": False,
                "created_at": agora,
            }
            for uid in destinatarios
        ])
        return len(destinatarios)
    except Exception as exc:  # noqa: BLE001 — o aviso nunca desfaz a gravação
        logger.warning("[registo_do_painel] Falha a avisar a rede sobre %s (%s).", area, exc)
        return 0


async def registar_alteracao_da_rede(
    user: Optional[dict], request: Any, *, area: str, descricao: str,
) -> None:
    """As duas coisas de uma vez, para o que é partilhado pela rede."""
    await registar_alteracao(user, request, area=area, descricao=descricao)
    await avisar_alteracao_da_rede(user, request, area=area, descricao=descricao)


async def run_com_rasto_da_rede(operacao, user: Optional[dict], request: Any, *, area: str, descricao) -> Any:
    """Corre a gravação e, SÓ se correr bem, deixa o rasto e avisa a rede.

    `descricao` pode ser texto ou uma função do resultado (para dizer o nome da
    fase/regra gravada). Os routers ficam finos: `return await run_com_rasto_da_rede(run_x(...), ...)`.
    """
    resultado = await operacao
    texto = descricao(resultado) if callable(descricao) else descricao
    await registar_alteracao_da_rede(user, request, area=area, descricao=str(texto))
    return resultado
