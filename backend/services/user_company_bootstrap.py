"""
====================================================================
ACESSOS INICIAIS DE UM UTILIZADOR (Atribuição Rápida)
====================================================================
Lote 4, ponto 11.

O DEFEITO
  `run_create_user` gravava a conta e NUNCA criava um UCR. Escrevia
  `user_doc["company"]` — o NOME da empresa, não o `company_id` — e o
  formulário nem esse campo enviava. Entre o "Criar" e o "Gerir Acessos"
  o utilizador era um órfão, e TUDO lê UCRs: ContextSwitcher,
  `get_effective_role_async`, config de email por empresa e, desde o
  ponto 10, o isolamento por rede.

REGRA DE NEGÓCIO
  A empresa é ESTRITAMENTE obrigatória na criação. A excepção são os
  parceiros — contas fantasma sem acesso à plataforma, que não têm
  empresa onde trabalhar.

PORQUE É QUE ISTO É ATÓMICO
  Encadear duas chamadas a partir do frontend daria o mesmo buraco
  quando a segunda falhasse, só que mais difícil de ver. Se os acessos
  não ficarem gravados, a conta é desfeita: sem conta, o admin repete;
  com conta e sem acessos, ninguém dá por isso.
====================================================================
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Sequence

from fastapi import HTTPException

from database import db
from models.user_company_role import CompanyRoleEnum

logger = logging.getLogger(__name__)

# Contas fantasma: existem para serem associadas a processos como
# entidades externas, não para entrar na plataforma.
PAPEIS_SEM_EMPRESA = frozenset({"parceiro"})

# `"default"` é o sentinel de "sem empresa" (ver `auth.py`). Aceitá-lo
# criaria um UCR a apontar para nada e daria o órfão por resolvido.
VALORES_SEM_EMPRESA = frozenset({"", "default", "none", "null"})

EMPRESA_OBRIGATORIA_DETALHE = (
    "Indique pelo menos uma empresa e cargo para o utilizador. "
    "Só os parceiros podem ficar sem empresa."
)


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def normalizar_acessos(
    acessos: Optional[Iterable[Any]],
    *,
    papel_principal: str,
) -> list[dict]:
    """Valida e normaliza as linhas empresa+cargo vindas do formulário.

    Cada linha pode trazer `role` próprio (Consultor numa empresa,
    Intermediário noutra); sem ele, herda o perfil principal da conta.
    """
    normalizados: list[dict] = []
    vistos: set[tuple[str, str]] = set()
    papeis_validos = {e.value for e in CompanyRoleEnum}

    for bruto in acessos or []:
        linha = bruto if isinstance(bruto, dict) else getattr(bruto, "__dict__", {})
        if not isinstance(linha, dict):
            if hasattr(bruto, "model_dump"):
                linha = bruto.model_dump()
            else:
                continue

        company_id = _texto(linha.get("company_id"))
        company_name = _texto(linha.get("company_name"))
        if company_id.lower() in VALORES_SEM_EMPRESA:
            company_id = ""
        if company_name.lower() in VALORES_SEM_EMPRESA:
            company_name = ""
        if not company_id and not company_name:
            continue

        papel = _texto(linha.get("role")) or _texto(papel_principal)
        if papel not in papeis_validos:
            raise HTTPException(
                status_code=400,
                detail=f"Cargo inválido: {papel}. Válidos: {sorted(papeis_validos)}",
            )

        # O índice composto de `user_company_roles` é único em
        # (user_id, company_id, role). Duas linhas iguais fariam a
        # criação rebentar a meio, depois de a conta já existir.
        chave = ((company_id or company_name).lower(), papel)
        if chave in vistos:
            continue
        vistos.add(chave)

        normalizados.append({
            "company_id": company_id or company_name,
            "company_name": company_name,
            "role": papel,
            "is_default": bool(linha.get("is_default")),
        })

    if normalizados and not any(a["is_default"] for a in normalizados):
        # Sem uma empresa por omissão, o login não sabe qual carregar.
        normalizados[0]["is_default"] = True

    primeiro_default = True
    for acesso in normalizados:
        if acesso["is_default"] and primeiro_default:
            primeiro_default = False
        else:
            acesso["is_default"] = False

    return normalizados


def assert_acessos_obrigatorios(papel: str, acessos: Sequence[dict]) -> None:
    """Recusa criar uma conta sem empresa (tolerância zero a órfãos)."""
    if _texto(papel).lower() in PAPEIS_SEM_EMPRESA:
        return
    if not acessos:
        raise HTTPException(status_code=400, detail=EMPRESA_OBRIGATORIA_DETALHE)


async def completar_nomes_das_empresas(acessos: Sequence[dict]) -> list[dict]:
    """Preenche `company_name` a partir da colecção `companies`.

    Tem de correr ANTES de se montar o documento do utilizador: o campo
    legado `users.company` é o NOME da empresa, e `_find_ucr` casa por
    ele. Gravar lá o `company_id` é a mesma confusão id/nome que produziu
    o incidente da conta de envio (2026-09-21) — e aqui passaria
    despercebida, porque o UCR ficava correcto na mesma.
    """
    nomes = await _nomes_das_empresas([a.get("company_id") for a in acessos])
    for acesso in acessos:
        if not acesso.get("company_name"):
            acesso["company_name"] = nomes.get(acesso.get("company_id"), "")
    return list(acessos)


async def criar_acessos_iniciais(user_id: str, acessos: Sequence[dict]) -> list[dict]:
    """Grava os UCRs de uma conta acabada de criar.

    Propaga a excepção de propósito: quem chama desfaz a conta.
    """
    if not acessos:
        return []

    await completar_nomes_das_empresas(acessos)
    agora = datetime.now(timezone.utc).isoformat()

    gravados: list[dict] = []
    for acesso in acessos:
        nome = acesso.get("company_name") or ""
        documento = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "company_id": acesso["company_id"],
            "company_name": nome or acesso["company_id"],
            "role": acesso["role"],
            "is_default": acesso["is_default"],
            "created_at": agora,
            "updated_at": agora,
        }
        await db.user_company_roles.insert_one(documento)
        documento.pop("_id", None)
        gravados.append(documento)

    logger.info(
        "[UTILIZADORES] %d acesso(s) criado(s) para %s na criação da conta.",
        len(gravados), user_id,
    )
    return gravados


async def _nomes_das_empresas(company_ids: Sequence[str]) -> dict[str, str]:
    identificadores = [c for c in dict.fromkeys(company_ids) if c]
    if not identificadores:
        return {}
    try:
        encontradas = await db.companies.find(
            {"id": {"$in": identificadores}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(200)
    except Exception as exc:
        logger.warning("[UTILIZADORES] Falha a ler empresas (%s).", exc)
        return {}
    return {_texto(c.get("id")): _texto(c.get("name")) for c in encontradas}


def empresa_por_omissao(acessos: Sequence[dict]) -> Optional[str]:
    """Nome da empresa por omissão — alimenta o campo legado `users.company`."""
    for acesso in acessos:
        if acesso.get("is_default"):
            return acesso.get("company_name") or acesso.get("company_id")
    return None
