"""Contactos de email: sugerir ao escrever, gerir à mão (Bloco 2, Lote 12).

O PEDIDO: «quando se vai enviar um e-mail, sugerir os contactos já usados» e
poder geri-los.

AS REGRAS (cada uma tem teste)
==============================
1. **O livro de endereços é do UTILIZADOR e da EMPRESA onde trabalha.** Quem
   tem dois perfis em redes diferentes (a Carla) não pode ver sugeridos, ao
   escrever pela Domus, os clientes da Power — o endereço de um cliente é
   dado pessoal dele e a ilha é uma ilha. A chave é
   `(user_id, company_id, address)`.
2. **Aprende-se ao ENVIAR com sucesso**, no envio real (`execute_pending_email_send`),
   e não ao clicar em enviar: um envio cancelado dentro da janela de
   «desfazer» não pode deixar contactos para trás. Aprender nunca faz o
   envio falhar.
3. **Arranque a frio:** sem nenhum contacto, semeia-se a partir do correio
   ENVIADO pelo próprio, na empresa activa. Sem empresa activa não se
   semeia — um email sem carimbo de empresa não prova a que ilha pertence.
4. **Remover é esconder**, não apagar: se se apagasse, o próprio envio
   seguinte voltava a aprendê-lo e o utilizador nunca se livrava dele. Um
   contacto escondido volta quando se lhe ESCREVE de novo (o utilizador
   mudou de ideias, e foi ele a escrever).
5. **Os endereços do próprio nunca são sugeridos**, nem os que não são
   endereços (a comparação de endereços é exacta e em minúsculas).
6. **Pesquisa por prefixo do endereço, do nome ou de uma palavra do nome**;
   favoritos primeiro, depois mais usados, depois mais recentes.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any, Iterable, Optional

from database import db

logger = logging.getLogger(__name__)

COLECCAO = "email_contacts"
LIMITE_POR_OMISSAO = 8
LIMITE_MAXIMO = 50
LIMITE_DE_SEMENTE = 300

_ENDERECO_VALIDO = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]{2,}$")


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def empresa_da_chave(company_id: Any) -> str:
    """`None`, vazio e «default» são a MESMA coisa: sem empresa."""
    cid = _texto(company_id)
    return "" if cid.lower() in ("", "none", "default") else cid


def separar_contacto(valor: Any) -> tuple[str, str]:
    """`"Ana Costa <ana@x.pt>"` → `("ana@x.pt", "Ana Costa")`. Inválido → `("", "")`."""
    nome, endereco = parseaddr(_texto(valor))
    endereco = endereco.strip().lower()
    if not _ENDERECO_VALIDO.match(endereco):
        return "", ""
    return endereco, nome.strip().strip('"')


def _contactos_de(valores: Iterable[Any]) -> dict[str, str]:
    """endereço → nome (o primeiro nome não vazio), sem repetidos."""
    vistos: dict[str, str] = {}
    for valor in valores or []:
        endereco, nome = separar_contacto(valor)
        if endereco and (endereco not in vistos or (nome and not vistos[endereco])):
            vistos[endereco] = nome
    return vistos


def _chave(user_id: str, company_id: Any, endereco: str) -> dict:
    return {"user_id": _texto(user_id), "company_id": empresa_da_chave(company_id), "address": endereco}


async def registar_contactos_usados(
    user_id: str, company_id: Any, valores: Iterable[Any],
) -> int:
    """Conta um uso para cada destinatário. Nunca propaga."""
    if not _texto(user_id):
        return 0
    agora = datetime.now(timezone.utc).isoformat()
    gravados = 0
    try:
        for endereco, nome in _contactos_de(valores).items():
            chave = _chave(user_id, company_id, endereco)
            atual = await db[COLECCAO].find_one(chave, {"_id": 0})
            if atual:
                alteracoes: dict[str, Any] = {
                    "use_count": int(atual.get("use_count") or 0) + 1,
                    "last_used_at": agora,
                    "hidden": False,  # regra 4: voltou a ser usado
                }
                if nome and not atual.get("name"):
                    alteracoes["name"] = nome
                await db[COLECCAO].update_one(chave, {"$set": alteracoes})
            else:
                await db[COLECCAO].insert_one({
                    "id": str(uuid.uuid4()), **chave, "name": nome, "favorite": False,
                    "hidden": False, "use_count": 1, "last_used_at": agora, "created_at": agora,
                })
            gravados += 1
    except Exception as exc:
        logger.warning("[EMAIL-CONTACTS] Não foi possível registar os contactos de %s: %s", user_id, exc)
    return gravados


async def _semear_do_enviado(user: dict, company_id: Any, proprios: set[str]) -> None:
    """Regra 3: arranque a frio a partir do correio enviado pelo próprio."""
    cid = empresa_da_chave(company_id)
    if not cid:
        return
    uid = _texto(user.get("id"))
    meu = _texto(user.get("email")).lower()
    try:
        enviados = await db.emails.find(
            {"direction": "sent", "company_id": cid,
             "$or": [{"created_by": uid}, {"synced_for_user": uid}, {"synced_for_user": meu}]},
            {"_id": 0, "to_emails": 1, "cc_emails": 1, "sent_at": 1},
        ).sort("sent_at", -1).limit(LIMITE_DE_SEMENTE).to_list(LIMITE_DE_SEMENTE)
    except Exception as exc:
        logger.warning("[EMAIL-CONTACTS] Falha a semear contactos de %s: %s", uid, exc)
        return
    valores = [v for e in enviados for v in [*(e.get("to_emails") or []), *(e.get("cc_emails") or [])]]
    valores = [v for v in valores if separar_contacto(v)[0] not in proprios]
    await registar_contactos_usados(uid, cid, valores)


def _corresponde(contacto: dict, q: str) -> bool:
    if not q:
        return True
    q = q.lower()
    endereco = _texto(contacto.get("address")).lower()
    nome = _texto(contacto.get("name")).lower()
    return (
        endereco.startswith(q)
        or nome.startswith(q)
        or any(p.startswith(q) for p in re.split(r"\s+", nome) if p)
    )


async def listar_contactos(
    user: dict, company_id: Any, *, q: str = "", limite: int = LIMITE_POR_OMISSAO,
) -> list[dict]:
    """Os contactos sugeríveis, já ordenados (regras 5 e 6)."""
    from services.email_access import _enderecos_configurados

    limite = max(1, min(int(limite or LIMITE_POR_OMISSAO), LIMITE_MAXIMO))
    proprios = {_texto(user.get("email")).lower(), *await _enderecos_configurados(user)}
    chave_base = {"user_id": _texto(user.get("id")), "company_id": empresa_da_chave(company_id)}

    existentes = await db[COLECCAO].count_documents(chave_base)
    if existentes == 0:
        await _semear_do_enviado(user, company_id, proprios)

    linhas = await db[COLECCAO].find(
        {**chave_base, "hidden": {"$ne": True}}, {"_id": 0},
    ).to_list(2000)
    escolhidas = [
        c for c in linhas
        if _texto(c.get("address")).lower() not in proprios and _corresponde(c, _texto(q))
    ]
    escolhidas.sort(key=lambda c: _texto(c.get("last_used_at")), reverse=True)
    escolhidas.sort(key=lambda c: int(c.get("use_count") or 0), reverse=True)
    escolhidas.sort(key=lambda c: not c.get("favorite"))
    return [
        {
            "address": c["address"], "name": c.get("name") or "",
            "favorite": bool(c.get("favorite")), "use_count": int(c.get("use_count") or 0),
            "last_used_at": c.get("last_used_at"),
        }
        for c in escolhidas[:limite]
    ]


async def guardar_contacto(
    user: dict, company_id: Any, *, address: str, name: Optional[str] = None,
    favorite: Optional[bool] = None,
) -> dict:
    """Cria ou actualiza à mão (nome, favorito). Levanta `ValueError` se o endereço não serve."""
    endereco, nome_do_endereco = separar_contacto(address)
    if not endereco:
        raise ValueError("Endereço de email inválido.")
    chave = _chave(user.get("id"), company_id, endereco)
    agora = datetime.now(timezone.utc).isoformat()
    atual = await db[COLECCAO].find_one(chave, {"_id": 0})
    campos: dict[str, Any] = {"hidden": False}
    if name is not None:
        campos["name"] = _texto(name)[:120]
    elif not atual:
        campos["name"] = nome_do_endereco
    if favorite is not None:
        campos["favorite"] = bool(favorite)
    if atual:
        await db[COLECCAO].update_one(chave, {"$set": campos})
    else:
        await db[COLECCAO].insert_one({
            "id": str(uuid.uuid4()), **chave, "name": "", "favorite": False,
            "use_count": 0, "last_used_at": None, "created_at": agora, **campos,
        })
    final = {**(atual or {}), **campos}
    return {
        "address": endereco, "name": final.get("name") or "",
        "favorite": bool(final.get("favorite")), "use_count": int(final.get("use_count") or 0),
    }


async def esconder_contacto(user: dict, company_id: Any, address: str) -> bool:
    """Regra 4: remover é esconder. `False` se o contacto não existia."""
    endereco, _ = separar_contacto(address)
    if not endereco:
        return False
    resultado = await db[COLECCAO].update_one(
        _chave(user.get("id"), company_id, endereco), {"$set": {"hidden": True, "favorite": False}},
    )
    return bool(getattr(resultado, "matched_count", 0))
