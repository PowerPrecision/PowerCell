"""Resolução do logótipo e do NOME da empresa para emails transaccionais.

PACOTE 11 (Eixo 2 — "Logo no Email Base"): os emails transaccionais base
(welcome, convites, confirmações) saíam SEM a imagem/logo da empresa no
header — apenas texto hardcoded. Este helper injecta o ``company.logo_url``
nos templates HTML do backend.

PACOTE 12 (Eixo 2 — branding EXCLUSIVO da empresa activa): os templates
usam agora ``company_name`` + ``logo_url`` da empresa ACTIVA da sessão em
vez do dual-brand hardcoded ("Power Real Estate & Precision Crédito").
``resolve_active_company_branding(company_id)`` devolve o par
``(company_name, logo_url)`` e ``resolve_company_logo_url`` passou a
aceitar ``company_id`` opcional para uma resolução scoped.

Fontes de resolução (por ordem de prioridade):
1. ``db.system_config`` — documento ``company:<company_id>`` (secção
   ``settings``, campos ``company_name``/``logo_url``) — configuração
   própria da empresa;
2. ``db.companies`` — documento pelo ``id`` (campos name/logo_url);
3. Fallback global (empresa desconhecida ou company_id ausente):
   ``system_config`` documento ``main`` → primeira empresa activa.

Valores relativos (chaves S3) são resolvidos para URL pré-assinado via
``services.companies_crud_api_helpers.resolve_logo_url`` (7 dias de
validade — suficiente para emails transaccionais).

Degradação graciosa: BD indisponível / branding ausente → ``(None, None)``
(o template usa o default). Nunca levanta excepção.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def _clean_company_name(value) -> Optional[str]:
    """Normaliza um nome de empresa (string não vazia ou None)."""
    if not value:
        return None
    text = str(value).strip()
    return text or None


async def _system_config_branding(doc_id: str) -> Tuple[Optional[str], Optional[str]]:
    """(company_name, logo_url) lidos de um documento do system_config pelo _id.

    Leitura directa da colecção (mesma convenção de ``_id`` de
    ``services.system_config._config_doc_id``: ``main`` para a global,
    ``company:<id>`` por empresa) — deliberadamente NÃO usamos
    ``get_system_config(company_id)`` porque esse helper herda/copia a
    config GLOBAL quando a empresa não tem config própria, o que devolveria
    o branding de outra empresa em vez de cair para ``db.companies``.
    """
    from database import db
    from services.companies_crud_api_helpers import resolve_logo_url

    try:
        config = await db.system_config.find_one(
            {"_id": doc_id},
            {"_id": 0, "settings.company_name": 1, "settings.logo_url": 1},
        )
    except Exception as e:
        logger.debug(f"[EMAIL-BRANDING] system_config ({doc_id}) indisponível: {e}")
        return None, None
    if not config:
        return None, None
    settings = config.get("settings") or {}
    name = _clean_company_name(settings.get("company_name"))
    logo = resolve_logo_url(settings.get("logo_url"))
    return name, logo


async def _company_doc_branding(query: dict) -> Tuple[Optional[str], Optional[str]]:
    """(name, logo_url) de um documento de ``db.companies`` pela query dada."""
    from database import db
    from services.companies_crud_api_helpers import resolve_logo_url

    try:
        company = await db.companies.find_one(
            query, {"_id": 0, "name": 1, "logo_url": 1},
        )
    except Exception as e:
        logger.debug(f"[EMAIL-BRANDING] companies indisponível: {e}")
        return None, None
    if not company:
        return None, None
    name = _clean_company_name(company.get("name"))
    logo = resolve_logo_url(company.get("logo_url"))
    return name, logo


async def resolve_active_company_branding(
    company_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """PACOTE 12 — ``(company_name, logo_url)`` da empresa ACTIVA, ou ``(None, None)``.

    Fontes (por ordem):
    1. ``system_config`` company-scoped (``company:<company_id>``);
    2. ``db.companies`` pelo ``id``;
    3. Fallback global (company_id ausente/desconhecido): ``system_config``
       ``main`` → primeira empresa activa.

    O logo relativo (chave S3) é resolvido para URL pré-assinado (7 dias).
    Nunca levanta excepção — o chamador decide o fallback (constante
    COMPANY_NAME, etc.).
    """
    if company_id:
        # 1) SystemConfig próprio da empresa (branding configurado no
        #    /system-config scoped da empresa activa)
        name, logo = await _system_config_branding(f"company:{company_id}")
        if name or logo:
            return name, logo

        # 2) Documento da empresa em db.companies
        name, logo = await _company_doc_branding({"id": company_id})
        if name or logo:
            return name, logo

    # 3) Fallback global — company_id ausente ou desconhecido
    name, logo = await _system_config_branding("main")
    if name or logo:
        return name, logo

    name, logo = await _company_doc_branding(
        {"is_active": {"$ne": False}, "logo_url": {"$nin": [None, ""]}}
    )
    if name or logo:
        return name, logo

    return None, None


async def resolve_company_logo_url(company_id: Optional[str] = None) -> Optional[str]:
    """URL absoluto (ou pré-assinado S3) do logo da empresa, ou None.

    PACOTE 12 — quando ``company_id`` é fornecido, a resolução é SCOPED a
    essa empresa (system_config ``company:<id>`` → ``db.companies`` por id
    → system_config global): o fallback histórico da "primeira empresa
    activa" NÃO se aplica, porque devolveria o logo de OUTRA empresa.
    Sem argumento mantém o comportamento histórico (system_config global
    → primeira empresa activa com logo).
    """
    if company_id:
        name, logo = await _system_config_branding(f"company:{company_id}")
        if logo:
            return logo
        name, logo = await _company_doc_branding({"id": company_id})
        if logo:
            return logo
        # Último recurso: config global (não é o logo de outra empresa)
        name, logo = await _system_config_branding("main")
        return logo

    # Comportamento histórico (sem company_id)
    name, logo = await _system_config_branding("main")
    if logo:
        return logo
    name, logo = await _company_doc_branding(
        {"is_active": {"$ne": False}, "logo_url": {"$nin": [None, ""]}}
    )
    return logo


def build_email_header_logo_html(logo_url: Optional[str], *, alt: str = "") -> str:
    """Fragmento HTML ``<img>`` do logo para o header de emails.

    Devolve string vazia quando não há logo — os templates inserem o
    fragmento tal qual, sem condicionais no f-string caller.
    """
    if not logo_url:
        return ""
    alt_attr = (alt or "Logótipo da empresa").replace('"', "'")
    return (
        f'<img src="{logo_url}" alt="{alt_attr}" '
        f'style="max-height: 56px; max-width: 180px; width: auto; '
        f'display: block; margin: 0 auto 10px auto; border-radius: 6px;" />'
    )
