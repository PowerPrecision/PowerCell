#!/usr/bin/env python3
"""
==============================================
MIGRATION: portal_label e visible_in_portal
==============================================
Atualiza os workflow_statuses existentes na BD com os novos campos:
- portal_label: Nome client-facing para o Portal do Cliente
- visible_in_portal: Se a etapa aparece no stepper do portal

Uso:
    cd /app/backend
    python migrate_portal_labels.py

Este script é idempotente — pode ser executado várias vezes sem efeitos colaterais.
==============================================
"""
import asyncio
import os
from pathlib import Path
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Mapeamento name → portal_label + visible_in_portal
# Estes são os valores padrão para os 14 statuses originais.
# O admin pode personalizar depois via UI.
DEFAULTS = {
    "clientes_espera":    {"portal_label": "Em Espera",                   "visible_in_portal": True},
    "fase_documental":    {"portal_label": "Recolha de Documentos",        "visible_in_portal": True},
    "fase_documental_ii": {"portal_label": "Documentação Complementar",   "visible_in_portal": True},
    "enviado_bruno":      {"portal_label": "Análise do Processo",         "visible_in_portal": True},
    "enviado_luis":       {"portal_label": "Validação Interna",           "visible_in_portal": True},
    "enviado_bcp_rui":    {"portal_label": "Análise Bancária",            "visible_in_portal": True},
    "entradas_precision": {"portal_label": "Em Processamento",            "visible_in_portal": True},
    "fase_bancaria":      {"portal_label": "Aprovação Bancária",          "visible_in_portal": True},
    "fase_visitas":       {"portal_label": "Visitas ao Imóvel",           "visible_in_portal": True},
    "ch_aprovado":        {"portal_label": "Crédito Aprovado",            "visible_in_portal": True},
    "fase_escritura":     {"portal_label": "Preparação da Escritura",     "visible_in_portal": True},
    "escritura_agendada": {"portal_label": "Escritura Agendada",          "visible_in_portal": True},
    "concluidos":         {"portal_label": None,                          "visible_in_portal": False},
    "desistencias":       {"portal_label": None,                          "visible_in_portal": False},
}


async def migrate():
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    print("=" * 50)
    print("Migration: portal_label + visible_in_portal")
    print("=" * 50)

    # Buscar todos os statuses
    all_statuses = await db.workflow_statuses.find({}).to_list(length=None)
    print(f"\nEncontrados {len(all_statuses)} workflow statuses")

    updated = 0
    skipped = 0
    added = 0

    for status in all_statuses:
        name = status.get("name", "")
        defaults = DEFAULTS.get(name)

        if not defaults:
            # Status personalizado — não nos defaults
            # Apenas garantir que visible_in_portal existe (default true)
            if "visible_in_portal" not in status:
                await db.workflow_statuses.update_one(
                    {"_id": status["_id"]},
                    {"$set": {"visible_in_portal": True}}
                )
                added += 1
                print(f"  [SET] '{status.get('label', name)}' → visible_in_portal=True (novo campo)")
            else:
                skipped += 1
                print(f"  [SKIP] '{status.get('label', name)}' — status personalizado, já tem campos")
            continue

        # Verificar se precisa de atualização
        needs_update = False
        updates = {}

        if "portal_label" not in status:
            updates["portal_label"] = defaults["portal_label"]
            needs_update = True

        if "visible_in_portal" not in status:
            updates["visible_in_portal"] = defaults["visible_in_portal"]
            needs_update = True

        if needs_update:
            await db.workflow_statuses.update_one(
                {"_id": status["_id"]},
                {"$set": updates}
            )
            portal_label = defaults["portal_label"] or "(none)"
            visible = defaults["visible_in_portal"]
            print(f"  [OK] '{status.get('label', name)}' → portal_label='{portal_label}', visible={visible}")
            added += 1
        else:
            print(f"  [SKIP] '{status.get('label', name)}' — já tem os campos")
            skipped += 1

    print()
    print("-" * 50)
    print(f"Atualizados: {added}")
    print(f"Ignorados (já tinham campos): {skipped}")
    print("-" * 50)

    # Verificação final
    final_count = await db.workflow_statuses.count_documents({})
    with_portal = await db.workflow_statuses.count_documents({"portal_label": {"$exists": True}})
    with_visible = await db.workflow_statuses.count_documents({"visible_in_portal": {"$exists": True}})

    print(f"\nVerificação final:")
    print(f"  Total de statuses: {final_count}")
    print(f"  Com portal_label:  {with_portal}")
    print(f"  Com visible_in_portal: {with_visible}")

    client.close()
    print("\n✅ Migration concluída com sucesso!")


if __name__ == "__main__":
    asyncio.run(migrate())
