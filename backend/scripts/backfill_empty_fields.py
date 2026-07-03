#!/usr/bin/env python3
"""
====================================================================
BACKFILL EMPTY FIELDS — PowerCell CRM
====================================================================
Script de migração segura que percorre clientes e processos existentes
e preenche campos em falta (NIF, telefone, profissão, salário, valor
do imóvel, etc.) com dados realistas portugueses gerados por Faker.

REGRAS DE SEGURANÇA:
- NUNCA apaga ou substitui dados que já tenham sido preenchidos.
- Só faz update ($set) se a chave não existir OU for vazia/None.
- Usa update_one individual (não update_many) para logging granular.
- Conta quantos clientes e processos foram atualizados.

USO:
    cd backend
    python scripts/backfill_empty_fields.py                # executar
    python scripts/backfill_empty_fields.py --dry-run      # simular sem escrever
    python scripts/backfill_empty_fields.py --limit 50     # limitar a 50 docs por coleção

REQUISITOS:
    - backend/.env com MONGO_URL e DB_NAME definidos
    - pip install faker motor python-dotenv

PACOTE CO — Create Data Backfill Script
====================================================================
"""
import asyncio
import os
import sys
import random
import argparse
from pathlib import Path
from datetime import datetime, timezone

# Bootstrap — adicionar backend/ ao path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

try:
    from faker import Faker
    fake = Faker('pt_PT')
except ImportError:
    print("❌ faker não instalado. Instale com: pip install faker")
    sys.exit(1)

# Carregar .env do backend/
load_dotenv(Path(__file__).parent.parent / '.env')

SEED_SCRIPT = "backfill_empty_fields"


# ====================================================================
# GERADORES DE DADOS REALISTAS PORTUGUESES
# ====================================================================

PROFISSOES = [
    "Engenheiro Civil", "Médica", "Professor", "Advogada", "Contabilista",
    "Enfermeiro", "Arquiteta", "Gestor de Vendas", "Programador", "Psicóloga",
    "Farmacêutico", "Designer", "Comercial", "Fisioterapeuta", "Economista",
    "Técnico de Informática", "Enfermeira", "Engenheira Mecânica", "Advogado",
    "Administradora", "Técnico de Laboratório", "Chef de Cozinha", "Eletricista",
    "Cabeleireira", "Motorista", "Operária de Fábrica", "Rececionista",
]

CONCELHOS = [
    "Lisboa", "Sintra", "Cascais", "Oeiras", "Loures", "Amadora", "Odivelas",
    "Porto", "Vila Nova de Gaia", "Matosinhos", "Maia", "Gondomar", "Santa Maria da Feira",
    "Coimbra", "Braga", "Aveiro", "Faro", "Setúbal", "Leiria", "Funchal",
    "Viseu", "Évora", "Beja", "Portalegre", "Guarda", "Castelo Branco",
    "Viana do Castelo", "Bragança", "Santarém", "Tomar",
]

TIPOLOGIAS = ["T1", "T2", "T3", "T4", "T5+"]

ESTADOS_CIVIS = ["Solteiro", "Casado", "União de Facto", "Divorciado", "Viúvo"]


def gerar_nif() -> str:
    """Gera um NIF português válido (9 dígitos com dígito de controlo)."""
    while True:
        nif = str(random.randint(100000000, 999999999))
        total = 0
        for i, digit in enumerate(nif[:8]):
            total += int(digit) * (9 - i)
        resto = total % 11
        check = 11 - resto if resto >= 2 else 0
        if int(nif[8]) == check:
            return nif


def gerar_telefone() -> str:
    """Gera número de telefone português (9X XXX XXXX)."""
    return f"9{random.randint(10, 69)} {random.randint(100, 999)} {random.randint(1000, 9999)}"


def gerar_cc() -> str:
    """Gera número de Cartão de Cidadão (8 dígitos + 1 alfanumérico)."""
    return f"{random.randint(10000000, 99999999)}{random.choice('TRSW')}"


def gerar_salario() -> tuple:
    """Gera salário bruto e líquido realistas (retorna tupla)."""
    bruto = random.choice([1200, 1400, 1600, 1800, 2000, 2200, 2500, 2800, 3000, 3500])
    liquido = round(bruto * random.uniform(0.72, 0.82), 2)
    return bruto, liquido


def gerar_valor_imovel() -> int:
    """Gera valor de imóvel realista."""
    return random.choice([120000, 150000, 180000, 200000, 220000, 250000, 280000, 300000, 350000, 400000, 450000])


def is_empty(value) -> bool:
    """Verifica se um valor está vazio/None/não definido."""
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    if isinstance(value, (int, float)) and value == 0:
        return False  # 0 é válido para valores numéricos (ex: capital_proprio=0)
    return False


# ====================================================================
# BACKFILL: CLIENTES
# ====================================================================

async def backfill_clients(db, dry_run: bool = False, limit: int = 0) -> dict:
    """
    Percorre todos os clientes ativos e preenche campos em falta:
    - dados_pessoais: nif, documento_id, telefone, profissao, estado_civil,
      data_nascimento, naturalidade, nacionalidade, morada_fiscal, sexo
    - contacto: telefone, telefone_secundario, email_secundario
    """
    stats = {"total": 0, "updated": 0, "skipped": 0, "fields_filled": 0}

    query = {"is_active": {"$ne": False}}
    cursor = db.clients.find(query, {"_id": 0, "id": 1, "nome": 1, "dados_pessoais": 1, "contacto": 1})

    async for client in cursor:
        stats["total"] += 1
        if limit and stats["total"] > limit:
            break

        client_id = client.get("id")
        if not client_id:
            stats["skipped"] += 1
            continue

        dp = client.get("dados_pessoais") or {}
        contacto = client.get("contacto") or {}
        updates = {}

        # ── dados_pessoais ──
        if is_empty(dp.get("nif")):
            updates["dados_pessoais.nif"] = gerar_nif()

        if is_empty(dp.get("documento_id")):
            updates["dados_pessoais.documento_id"] = gerar_cc()

        if is_empty(dp.get("telefone")):
            updates["dados_pessoais.telefone"] = gerar_telefone()

        if is_empty(dp.get("profissao")):
            updates["dados_pessoais.profissao"] = random.choice(PROFISSOES)

        if is_empty(dp.get("estado_civil")):
            updates["dados_pessoais.estado_civil"] = random.choice(ESTADOS_CIVIS)

        if is_empty(dp.get("data_nascimento")):
            updates["dados_pessoais.data_nascimento"] = fake.date_between(start_date='-55y', end_date='-25y').strftime("%d/%m/%Y")

        if is_empty(dp.get("naturalidade")):
            updates["dados_pessoais.naturalidade"] = random.choice(CONCELHOS)

        if is_empty(dp.get("nacionalidade")):
            updates["dados_pessoais.nacionalidade"] = "Portuguesa"

        if is_empty(dp.get("morada_fiscal")):
            concelho = random.choice(CONCELHOS)
            updates["dados_pessoais.morada_fiscal"] = f"Rua {fake.street_name()}, {random.randint(1, 200)}, {concelho}"

        if is_empty(dp.get("sexo")):
            updates["dados_pessoais.sexo"] = random.choice(["M", "F"])

        # ── contacto ──
        if is_empty(contacto.get("telefone")):
            updates["contacto.telefone"] = gerar_telefone()

        if is_empty(contacto.get("telefone_secundario")):
            # 30% de probabilidade de ter telefone secundário
            if random.random() < 0.3:
                updates["contacto.telefone_secundario"] = gerar_telefone()

        if is_empty(contacto.get("email_secundario")):
            # 20% de probabilidade de ter email secundário
            if random.random() < 0.2:
                primeiro_nome = (client.get("nome") or "cliente").split()[0].lower()
                updates["contacto.email_secundario"] = f"{primeiro_nome}.sec@emailpt.pt"

        if not updates:
            stats["skipped"] += 1
            continue

        # Executar update
        if not dry_run:
            await db.clients.update_one(
                {"id": client_id},
                {"$set": updates}
            )

        stats["updated"] += 1
        stats["fields_filled"] += len(updates)

        if dry_run:
            print(f"  [DRY] Cliente {client_id[:8]}... ({client.get('nome', '?')}): {len(updates)} campos a preencher")
        elif stats["updated"] % 50 == 0:
            print(f"  ✅ {stats['updated']} clientes atualizados...")

    return stats


# ====================================================================
# BACKFILL: PROCESSOS
# ====================================================================

async def backfill_processes(db, dry_run: bool = False, limit: int = 0) -> dict:
    """
    Percorre todos os processos não eliminados e preenche:
    - financial_data: salario_bruto, salario_liquido, tipo_contrato, empresa
    - real_estate_data: valor_imovel, tipologia, concelho/localidade
    - credit_data: montante_financiado (calculado), prazo_meses, spread, banco
    """
    stats = {"total": 0, "updated": 0, "skipped": 0, "fields_filled": 0}

    query = {"is_deleted": {"$ne": True}}
    cursor = db.processes.find(query, {"_id": 0, "id": 1, "process_number": 1, "client_name": 1,
                                       "financial_data": 1, "real_estate_data": 1, "credit_data": 1})

    async for process in cursor:
        stats["total"] += 1
        if limit and stats["total"] > limit:
            break

        process_id = process.get("id")
        if not process_id:
            stats["skipped"] += 1
            continue

        fd = process.get("financial_data") or {}
        red = process.get("real_estate_data") or {}
        cd = process.get("credit_data") or {}
        updates = {}

        # ── financial_data ──
        if is_empty(fd.get("salario_bruto")):
            bruto, liquido = gerar_salario()
            updates["financial_data.salario_bruto"] = bruto
            if is_empty(fd.get("salario_liquido")):
                updates["financial_data.salario_liquido"] = liquido
            if is_empty(fd.get("vencimento_mensal")):
                updates["financial_data.vencimento_mensal"] = bruto
            if is_empty(fd.get("rendimento_total")):
                updates["financial_data.rendimento_total"] = bruto

        if is_empty(fd.get("tipo_contrato")):
            updates["financial_data.tipo_contrato"] = random.choice(["efetivo", "termo_certo", "cdi"])

        if is_empty(fd.get("empresa")):
            updates["financial_data.empresa"] = fake.company()

        if is_empty(fd.get("capitais_proprios")):
            updates["financial_data.capitais_proprios"] = random.choice([0, 15000, 30000, 50000, 75000])

        # ── real_estate_data ──
        valor_imovel = red.get("valor_imovel")
        if is_empty(valor_imovel):
            valor_imovel = gerar_valor_imovel()
            updates["real_estate_data.valor_imovel"] = valor_imovel

        if is_empty(red.get("tipologia")):
            updates["real_estate_data.tipologia"] = random.choice(TIPOLOGIAS)

        if is_empty(red.get("concelho")):
            concelho = random.choice(CONCELHOS)
            updates["real_estate_data.concelho"] = concelho
            if is_empty(red.get("localidade")):
                updates["real_estate_data.localidade"] = concelho
            if is_empty(red.get("localizacao")):
                updates["real_estate_data.localizacao"] = concelho

        if is_empty(red.get("tipo_imovel")):
            updates["real_estate_data.tipo_imovel"] = "Apartamento"

        if is_empty(red.get("codigo_postal")):
            updates["real_estate_data.codigo_postal"] = f"{random.randint(1000, 4999)}-{random.randint(100, 999)}"

        # ── credit_data ──
        if is_empty(cd.get("montante_financiado")) and not is_empty(valor_imovel):
            capitais = fd.get("capitais_proprios") or 0
            montante = max(int(valor_imovel) - int(capitais), 50000)
            updates["credit_data.montante_financiado"] = montante
            if is_empty(cd.get("requested_amount")):
                updates["credit_data.requested_amount"] = montante

        if is_empty(cd.get("prazo_meses")):
            prazo_anos = random.choice([15, 20, 25, 30])
            updates["credit_data.prazo_meses"] = prazo_anos * 12
            if is_empty(cd.get("loan_term_years")):
                updates["credit_data.loan_term_years"] = prazo_anos

        if is_empty(cd.get("spread")):
            updates["credit_data.spread"] = round(random.uniform(0.5, 1.5), 2)

        if is_empty(cd.get("banco")):
            updates["credit_data.banco"] = random.choice(["BCP", "Novo Banco", "Santander", "CGD", "ActivoBank", "Bankinter"])
            if is_empty(cd.get("bank_name")):
                updates["credit_data.bank_name"] = updates["credit_data.banco"]

        if is_empty(cd.get("tipo_taxa")):
            updates["credit_data.tipo_taxa"] = random.choice(["Fixa", "Variável", "Mista"])

        if not updates:
            stats["skipped"] += 1
            continue

        # Executar update
        if not dry_run:
            await db.processes.update_one(
                {"id": process_id},
                {"$set": updates}
            )

        stats["updated"] += 1
        stats["fields_filled"] += len(updates)

        if dry_run:
            print(f"  [DRY] Processo #{process.get('process_number', '?')} ({process.get('client_name', '?')}): {len(updates)} campos a preencher")
        elif stats["updated"] % 50 == 0:
            print(f"  ✅ {stats['updated']} processos atualizados...")

    return stats


# ====================================================================
# MAIN
# ====================================================================

def print_summary(clients_stats: dict, processes_stats: dict, dry_run: bool):
    """Imprime um resumo bonito no terminal."""
    mode = "DRY RUN (simulação)" if dry_run else "EXECUÇÃO REAL"
    print("\n" + "=" * 60)
    print(f"  BACKFILL EMPTY FIELDS — {mode}")
    print("=" * 60)

    print("\n📋 CLIENTES:")
    print(f"   Total percorridos:  {clients_stats['total']}")
    print(f"   Atualizados:        {clients_stats['updated']}")
    print(f"   Ignorados (ok):     {clients_stats['skipped']}")
    print(f"   Campos preenchidos: {clients_stats['fields_filled']}")

    print("\n📁 PROCESSOS:")
    print(f"   Total percorridos:  {processes_stats['total']}")
    print(f"   Atualizados:        {processes_stats['updated']}")
    print(f"   Ignorados (ok):     {processes_stats['skipped']}")
    print(f"   Campos preenchidos: {processes_stats['fields_filled']}")

    total_updated = clients_stats["updated"] + processes_stats["updated"]
    total_fields = clients_stats["fields_filled"] + processes_stats["fields_filled"]
    print(f"\n📊 TOTAL: {total_updated} documentos atualizados, {total_fields} campos preenchidos")

    if dry_run:
        print("\n⚠️  DRY RUN — nenhum dado foi alterado. Execute sem --dry-run para aplicar.")
    else:
        print("\n✅ Backfill concluído com sucesso!")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Backfill Empty Fields — PowerCell CRM")
    parser.add_argument("--dry-run", action="store_true", help="Simular sem escrever na BD")
    parser.add_argument("--limit", type=int, default=0, help="Limitar N docs por coleção (0 = sem limite)")
    args = parser.parse_args()

    # Validar variáveis de ambiente
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("❌ MONGO_URL e DB_NAME devem estar definidos no backend/.env")
        sys.exit(1)

    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]

    async def _run():
        print(f"🚀 Backfill Empty Fields — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
        print(f"   BD: {db_name}")
        print(f"   Dry run: {args.dry_run}")
        print(f"   Limit: {args.limit or 'sem limite'}\n")

        print("📋 A processar clientes...")
        clients_stats = await backfill_clients(db, dry_run=args.dry_run, limit=args.limit)

        print("\n📁 A processar processos...")
        processes_stats = await backfill_processes(db, dry_run=args.dry_run, limit=args.limit)

        print_summary(clients_stats, processes_stats, args.dry_run)

    asyncio.run(_run())
    mongo_client.close()


if __name__ == "__main__":
    main()
