"""
====================================================================
MIGRAÇÃO: Materializar empresas na coleção central `companies`
====================================================================
PACOTE AK — Script de migração para tabela central de empresas.

PROBLEMA:
  A nova coleção `companies` está vazia em produção, mas existem
  referências a empresas espalhadas por:
    - user_company_roles (company_id + company_name)
    - users (company como string)
    - company_email_configs (company_name)
    - system_config (company_id + settings.company_name)

SOLUÇÃO:
  Este script percorre essas coleções, extrai uma lista única de
  empresas (company_id + company_name), e faz upsert na coleção
  `companies` PRESERVANDO o company_id original como `id`.

  CRÍTICO: O id do documento inserido TEM de ser exatamente o mesmo
  company_id já usado nas outras coleções — senão quebra as referências.

EXECUÇÃO:
  Local (dev):  cd backend && python -m scripts.migrate_companies_central
  Render:       No Render Dashboard → Shell → executar:
                cd /app && python -m scripts.migrate_companies_central

  Flags:
    --dry-run   Mostra o que seria feito sem alterar a BD
    --verbose   Mostra detalhes de cada empresa encontrada
====================================================================
"""
import asyncio
import argparse
import logging
import sys
import os
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional, Any

# Configurar path para imports do backend
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("migrate_companies")

# Empresas de sistema que não devem ser migradas (sentinelas)
SKIP_COMPANY_IDS = {"default", None, ""}
SKIP_COMPANY_NAMES = {"", None, "default", "Global (Padrão)"}


def _dedupe_name(name: Optional[str], company_id: str) -> str:
    """Extrai um nome válido para a empresa, com fallback para o ID."""
    if name and isinstance(name, str) and name.strip():
        return name.strip()
    # Fallback: deduzir nome do ID (ex: "power_real_estate" → "Power Real Estate")
    if company_id and company_id != "default":
        return company_id.replace("_", " ").replace("-", " ").title()
    return "Empresa"


async def scan_user_company_roles() -> Dict[str, str]:
    """
    Percorre user_company_roles e extrai {company_id: company_name}.

    Esta é a fonte mais fiável porque tem ambos os campos estruturados.
    """
    found: Dict[str, str] = {}
    cursor = db.user_company_roles.find(
        {},
        {"_id": 0, "company_id": 1, "company_name": 1, "company": 1},
    )
    docs = await cursor.to_list(500)
    for doc in docs:
        cid = doc.get("company_id") or doc.get("company")
        if not cid or cid in SKIP_COMPANY_IDS:
            continue
        cname = doc.get("company_name") or doc.get("company")
        found[cid] = _dedupe_name(cname, cid)
    logger.info(f"[scan] user_company_roles: {len(found)} empresas únicas")
    return found


async def scan_users() -> Dict[str, str]:
    """
    Percorre users e extrai {company: company_name}.

    O campo `company` nos users é uma string (nome da empresa), não um ID.
    Geramos um ID slugificado a partir do nome para matching.
    """
    found: Dict[str, str] = {}
    cursor = db.users.find(
        {},
        {"_id": 0, "company": 1, "company_id": 1, "email": 1},
    )
    docs = await cursor.to_list(1000)
    for doc in docs:
        # Alguns users têm company_id estruturado
        cid = doc.get("company_id")
        cname = doc.get("company")
        if cid and cid not in SKIP_COMPANY_IDS:
            found[cid] = _dedupe_name(cname, cid)
        elif cname and cname not in SKIP_COMPANY_NAMES:
            # Sem company_id — slugificar nome para usar como ID
            slug = _slugify(cname)
            if slug and slug not in SKIP_COMPANY_IDS:
                found[slug] = _dedupe_name(cname, slug)
    logger.info(f"[scan] users: {len(found)} empresas únicas")
    return found


async def scan_company_email_configs() -> Dict[str, str]:
    """
    Percorre company_email_configs e extrai {company_name_slug: company_name}.
    """
    found: Dict[str, str] = {}
    cursor = db.company_email_configs.find(
        {},
        {"_id": 0, "company_name": 1, "company_id": 1},
    )
    docs = await cursor.to_list(100)
    for doc in docs:
        cname = doc.get("company_name")
        cid = doc.get("company_id")
        if cid and cid not in SKIP_COMPANY_IDS:
            found[cid] = _dedupe_name(cname, cid)
        elif cname and cname not in SKIP_COMPANY_NAMES:
            slug = _slugify(cname)
            if slug and slug not in SKIP_COMPANY_IDS:
                found[slug] = _dedupe_name(cname, slug)
    logger.info(f"[scan] company_email_configs: {len(found)} empresas únicas")
    return found


async def scan_system_config() -> Dict[str, str]:
    """
    Percorre system_config (settings.company_name) e extrai {company_id: company_name}.
    """
    found: Dict[str, str] = {}
    cursor = db.system_config.find(
        {"company_id": {"$exists": True}},
        {"_id": 0, "company_id": 1, "settings.company_name": 1, "settings.empresa_nome": 1},
    )
    docs = await cursor.to_list(50)
    for doc in docs:
        cid = doc.get("company_id")
        if not cid or cid in SKIP_COMPANY_IDS:
            continue
        settings = doc.get("settings", {}) or {}
        cname = settings.get("company_name") or settings.get("empresa_nome")
        found[cid] = _dedupe_name(cname, cid)
    logger.info(f"[scan] system_config: {len(found)} empresas únicas")
    return found


def _slugify(name: str) -> str:
    """Converte um nome de empresa num slug seguro para usar como ID."""
    if not name:
        return ""
    slug = name.strip().lower()
    # Substituir espaços e caracteres especiais
    for ch in " .,;:!?/\\()[]{}@#$%&*+=":
        slug = slug.replace(ch, "_")
    # Colapsar underscores múltiplos
    while "__" in slug:
        slug = slug.replace("__", "_")
    slug = slug.strip("_")
    return slug or "unknown"


async def collect_all_companies(verbose: bool = False) -> Dict[str, str]:
    """
    Agrega empresas de todas as coleções, garantindo IDs únicos.

    Prioridade de resolução de conflitos de nome:
    1. user_company_roles (mais fiável — tem IDs estruturados)
    2. system_config
    3. company_email_configs
    4. users (apenas nomes — gera slug)

    Returns:
        Dict {company_id: company_name}
    """
    all_companies: Dict[str, str] = {}

    # 1. user_company_roles (prioridade mais alta)
    ucr = await scan_user_company_roles()
    all_companies.update(ucr)

    # 2. system_config
    sc = await scan_system_config()
    for cid, cname in sc.items():
        if cid not in all_companies:
            all_companies[cid] = cname

    # 3. company_email_configs
    cec = await scan_company_email_configs()
    for cid, cname in cec.items():
        if cid not in all_companies:
            all_companies[cid] = cname

    # 4. users (prioridade mais baixa — só nomes)
    usr = await scan_users()
    for cid, cname in usr.items():
        if cid not in all_companies:
            all_companies[cid] = cname

    logger.info(f"[collect] Total único de empresas: {len(all_companies)}")

    if verbose:
        for cid, cname in sorted(all_companies.items()):
            logger.info(f"  • {cid} → {cname}")

    return all_companies


async def upsert_companies(
    companies: Dict[str, str],
    dry_run: bool = False,
) -> Dict[str, int]:
    """
    Faz upsert de cada empresa na coleção `companies`.

    CRÍTICO: O `id` do documento é o `company_id` original — preserva
    todas as referências existentes em user_company_roles, users, etc.

    Para empresas já existentes (match por id), NÃO sobrescreve campos
    já preenchidos (apenas preenche campos em falta).

    Returns:
        Dict com {created, updated, skipped, errors}
    """
    stats = {"created": 0, "updated": 0, "skipped": 0, "errors": 0}
    now = datetime.now(timezone.utc).isoformat()

    for cid, cname in companies.items():
        try:
            existing = await db.companies.find_one({"id": cid}, {"_id": 0})

            if existing:
                # Já existe — preencher campos em falta sem sobrescrever
                update_fields: Dict[str, Any] = {"updated_at": now}
                for field, default in [
                    ("name", cname),
                    ("nif", None),
                    ("address", None),
                    ("phone", None),
                    ("email", None),
                    ("website", None),
                    ("logo_url", None),
                    ("email_sync_enabled", False),
                ]:
                    if field not in existing or existing.get(field) is None:
                        update_fields[field] = default

                if dry_run:
                    logger.info(f"[dry-run] ATUALIZARIA: {cid} ({cname}) — {len(update_fields)-1} campos")
                    stats["updated"] += 1
                    continue

                result = await db.companies.update_one(
                    {"id": cid},
                    {"$set": update_fields},
                )
                if result.modified_count > 0:
                    logger.info(f"[update] {cid} ({cname}) — campos preenchidos")
                    stats["updated"] += 1
                else:
                    stats["skipped"] += 1
            else:
                # Não existe — inserir novo documento
                doc = {
                    "id": cid,  # CRÍTICO: preserva o company_id original
                    "name": cname,
                    "nif": None,
                    "address": None,
                    "phone": None,
                    "email": None,
                    "website": None,
                    "logo_url": None,
                    "email_sync_enabled": False,
                    "created_at": now,
                    "updated_at": now,
                }

                if dry_run:
                    logger.info(f"[dry-run] CRIARIA: {cid} ({cname})")
                    stats["created"] += 1
                    continue

                await db.companies.insert_one(doc)
                logger.info(f"[create] {cid} ({cname})")
                stats["created"] += 1

        except Exception as e:
            logger.error(f"[error] Falha ao processar {cid} ({cname}): {e}")
            stats["errors"] += 1

    return stats


async def verify_migration() -> None:
    """
    Verifica o resultado da migração cruzando com as coleções originais.
    """
    total_companies = await db.companies.count_documents({})
    logger.info(f"[verify] Total documentos em `companies`: {total_companies}")

    # Verificar que user_company_roles referencia empresas que existem
    ucr_docs = await db.user_company_roles.find(
        {},
        {"_id": 0, "company_id": 1},
    ).to_list(500)
    ucr_ids = {d.get("company_id") for d in ucr_docs if d.get("company_id")}
    missing = []
    for cid in ucr_ids:
        exists = await db.companies.find_one({"id": cid}, {"_id": 1})
        if not exists:
            missing.append(cid)
    if missing:
        logger.warning(f"[verify] {len(missing)} company_ids em user_company_roles sem match em companies: {missing}")
    else:
        logger.info(f"[verify] ✅ Todos os {len(ucr_ids)} company_ids de user_company_roles têm match em companies")


async def main():
    parser = argparse.ArgumentParser(description="Migrar empresas para a coleção central `companies`")
    parser.add_argument("--dry-run", action="store_true", help="Simular sem alterar a BD")
    parser.add_argument("--verbose", action="store_true", help="Mostrar detalhes de cada empresa")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("MIGRAÇÃO: Tabela Central de Empresas (Pacote AK)")
    logger.info("=" * 60)
    if args.dry_run:
        logger.info("⚠️  MODO DRY-RUN — nenhuma alteração será feita")
    logger.info("")

    # 1. Scan + collect
    logger.info("Fase 1: Scanning de coleções...")
    companies = await collect_all_companies(verbose=args.verbose)
    if not companies:
        logger.warning("Nenhuma empresa encontrada. Abortar.")
        return
    logger.info(f"Total de empresas únicas a migrar: {len(companies)}")
    logger.info("")

    # 2. Upsert
    logger.info("Fase 2: Upsert na coleção `companies`...")
    stats = await upsert_companies(companies, dry_run=args.dry_run)
    logger.info("")
    logger.info(f"Resultado: {stats['created']} criadas, {stats['updated']} atualizadas, {stats['skipped']} ignoradas, {stats['errors']} erros")

    # 3. Verificação (mesmo em dry-run para ver estado atual)
    if not args.dry_run:
        logger.info("")
        logger.info("Fase 3: Verificação...")
        await verify_migration()

    logger.info("")
    logger.info("✅ Migração concluída.")


if __name__ == "__main__":
    asyncio.run(main())
