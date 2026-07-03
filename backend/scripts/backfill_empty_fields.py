#!/usr/bin/env python3
"""
====================================================================
BACKFILL EMPTY FIELDS — PowerCell CRM (v2 — completa)
====================================================================
Script de migração segura que percorre clientes e processos existentes
e preenche campos em falta com dados realistas portugueses (Faker).

REGRAS DE SEGURANÇA:
- NUNCA apaga ou substitui dados que já tenham sido preenchidos.
- Só faz update ($set) se a chave não existir OU for vazia/None.
- Usa update_one individual para logging granular.

USO:
    cd backend
    python scripts/backfill_empty_fields.py                # executar
    python scripts/backfill_empty_fields.py --dry-run      # simular
    python scripts/backfill_empty_fields.py --limit 50     # limitar

PACOTE CO (v2) — campos de dropdown/select adicionados
====================================================================
"""
import asyncio
import os
import sys
import random
import argparse
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

try:
    from faker import Faker
    fake = Faker('pt_PT')
except ImportError:
    print("❌ faker não instalado. Instale com: pip install faker")
    sys.exit(1)

load_dotenv(Path(__file__).parent.parent / '.env')


# ====================================================================
# CATÁLOGOS ESTÁTICOS (dados realistas portugueses)
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
    "Porto", "Vila Nova de Gaia", "Matosinhos", "Maia", "Gondomar",
    "Coimbra", "Braga", "Aveiro", "Faro", "Setúbal", "Leiria", "Funchal",
    "Viseu", "Évora", "Beja", "Portalegre", "Guarda", "Castelo Branco",
    "Viana do Castelo", "Bragança", "Santarém", "Tomar",
]

TIPOLOGIAS = ["T1", "T2", "T3", "T4", "T5+"]
ESTADOS_CIVIS = ["Solteiro", "Casado", "União de Facto", "Divorciado", "Viúvo"]
BANCOS = ["BCP", "Novo Banco", "Santander", "CGD", "ActivoBank", "Bankinter", "Abanca", "Crédito Agrícola"]
TIPOS_CONTRATO = ["efetivo", "termo_certo", "cdi"]
TIPOS_TAXA = ["Fixa", "Variável", "Mista"]
TIPOS_IMOVEL = ["Apartamento", "Moradia", "Terreno", "Loja", "Escritório"]
CERTIFICADOS_ENERGETICOS = ["A", "B", "B-", "C", "D", "E"]
FINALIDADES = ["compra_imovel", "construcao", "refinanciamento", "transferencia_credito"]


# ====================================================================
# GERADORES
# ====================================================================

def gerar_nif() -> str:
    while True:
        nif = str(random.randint(100000000, 999999999))
        total = sum(int(d) * (9 - i) for i, d in enumerate(nif[:8]))
        resto = total % 11
        check = 11 - resto if resto >= 2 else 0
        if int(nif[8]) == check:
            return nif


def gerar_telefone() -> str:
    return f"9{random.randint(10, 69)} {random.randint(100, 999)} {random.randint(1000, 9999)}"


def gerar_cc() -> str:
    return f"{random.randint(10000000, 99999999)}{random.choice('TRSW')}"


def gerar_salario() -> tuple:
    bruto = random.choice([1200, 1400, 1600, 1800, 2000, 2200, 2500, 2800, 3000, 3500])
    liquido = round(bruto * random.uniform(0.72, 0.82), 2)
    return bruto, liquido


def gerar_valor_imovel() -> int:
    return random.choice([120000, 150000, 180000, 200000, 220000, 250000, 280000, 300000, 350000, 400000, 450000])


def is_empty(value) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


# ====================================================================
# BACKFILL: CLIENTES
# ====================================================================

async def backfill_clients(db, dry_run: bool = False, limit: int = 0) -> dict:
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

        # ── dados_pessoais: campos de texto ──
        if is_empty(dp.get("nif")):
            updates["dados_pessoais.nif"] = gerar_nif()
        if is_empty(dp.get("documento_id")):
            updates["dados_pessoais.documento_id"] = gerar_cc()
        if is_empty(dp.get("telefone")):
            updates["dados_pessoais.telefone"] = gerar_telefone()
        if is_empty(dp.get("data_nascimento")):
            updates["dados_pessoais.data_nascimento"] = fake.date_between(start_date='-55y', end_date='-25y').strftime("%d/%m/%Y")
        if is_empty(dp.get("naturalidade")):
            updates["dados_pessoais.naturalidade"] = random.choice(CONCELHOS)
        if is_empty(dp.get("nacionalidade")):
            updates["dados_pessoais.nacionalidade"] = "Portuguesa"
        if is_empty(dp.get("morada_fiscal")):
            concelho = random.choice(CONCELHOS)
            updates["dados_pessoais.morada_fiscal"] = f"Rua {fake.street_name()}, {random.randint(1, 200)}, {concelho}"
        if is_empty(dp.get("nome_pai")):
            updates["dados_pessoais.nome_pai"] = fake.name_male()
        if is_empty(dp.get("nome_mae")):
            updates["dados_pessoais.nome_mae"] = fake.name_female()
        if is_empty(dp.get("data_validade_cc")):
            updates["dados_pessoais.data_validade_cc"] = fake.date_between(start_date='+1y', end_date='+10y').strftime("%d/%m/%Y")

        # ── dados_pessoais: campos de SELECT/DROPDOWN ──
        if is_empty(dp.get("profissao")):
            updates["dados_pessoais.profissao"] = random.choice(PROFISSOES)
        if is_empty(dp.get("estado_civil")):
            updates["dados_pessoais.estado_civil"] = random.choice(ESTADOS_CIVIS)
        if is_empty(dp.get("sexo")):
            updates["dados_pessoais.sexo"] = random.choice(["M", "F"])

        # ── contacto ──
        if is_empty(contacto.get("telefone")):
            updates["contacto.telefone"] = gerar_telefone()
        if is_empty(contacto.get("telefone_secundario")) and random.random() < 0.3:
            updates["contacto.telefone_secundario"] = gerar_telefone()
        if is_empty(contacto.get("email_secundario")) and random.random() < 0.2:
            primeiro_nome = (client.get("nome") or "cliente").split()[0].lower()
            updates["contacto.email_secundario"] = f"{primeiro_nome}.sec@emailpt.pt"

        if not updates:
            stats["skipped"] += 1
            continue

        if not dry_run:
            await db.clients.update_one({"id": client_id}, {"$set": updates})

        stats["updated"] += 1
        stats["fields_filled"] += len(updates)

        if dry_run:
            print(f"  [DRY] Cliente {client_id[:8]}... ({client.get('nome', '?')}): {len(updates)} campos")
        elif stats["updated"] % 50 == 0:
            print(f"  ✅ {stats['updated']} clientes atualizados...")

    return stats


# ====================================================================
# BACKFILL: PROCESSOS
# ====================================================================

async def backfill_processes(db, dry_run: bool = False, limit: int = 0) -> dict:
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

        # ════════════════════════════════════════════════════════════
        # financial_data
        # ════════════════════════════════════════════════════════════
        if is_empty(fd.get("salario_bruto")):
            bruto, liquido = gerar_salario()
            updates["financial_data.salario_bruto"] = bruto
            if is_empty(fd.get("salario_liquido")):
                updates["financial_data.salario_liquido"] = liquido
            if is_empty(fd.get("vencimento_mensal")):
                updates["financial_data.vencimento_mensal"] = bruto
            if is_empty(fd.get("rendimento_total")):
                updates["financial_data.rendimento_total"] = bruto

        # SELECT: tipo_contrato
        if is_empty(fd.get("tipo_contrato")):
            updates["financial_data.tipo_contrato"] = random.choice(TIPOS_CONTRATO)

        if is_empty(fd.get("empresa")):
            updates["financial_data.empresa"] = fake.company()

        if is_empty(fd.get("antiguidade_anos")):
            updates["financial_data.antiguidade_anos"] = random.randint(1, 20)

        if is_empty(fd.get("irs_taxa_retencao")):
            updates["financial_data.irs_taxa_retencao"] = random.choice([0.18, 0.23, 0.28, 0.35])

        if is_empty(fd.get("capitais_proprios")):
            capital = random.choice([0, 15000, 30000, 50000, 75000])
            updates["financial_data.capitais_proprios"] = capital
            if is_empty(fd.get("valor_entrada")):
                updates["financial_data.valor_entrada"] = round(capital * random.uniform(0.8, 1.0), 2)

        # SELECT: dependentes (número)
        if is_empty(fd.get("dependentes")):
            updates["financial_data.dependentes"] = random.randint(0, 3)

        # Campos de despesas
        renda = random.choice([0, 350, 600, 850, 1200])
        prestacao_auto = random.choice([0, 180, 250, 320, 450])
        outros_creditos = random.choice([0, 100, 200, 350])

        if is_empty(fd.get("renda_mensal")):
            updates["financial_data.renda_mensal"] = renda
        if is_empty(fd.get("prestacao_auto")):
            updates["financial_data.prestacao_auto"] = prestacao_auto
        if is_empty(fd.get("outros_creditos")):
            updates["financial_data.outros_creditos"] = outros_creditos
        if is_empty(fd.get("despesas_total")):
            updates["financial_data.despesas_total"] = renda + prestacao_auto + outros_creditos

        # ════════════════════════════════════════════════════════════
        # real_estate_data
        # ════════════════════════════════════════════════════════════
        valor_imovel = red.get("valor_imovel")
        if is_empty(valor_imovel):
            valor_imovel = gerar_valor_imovel()
            updates["real_estate_data.valor_imovel"] = valor_imovel

        # SELECT: tipologia
        if is_empty(red.get("tipologia")):
            updates["real_estate_data.tipologia"] = random.choice(TIPOLOGIAS)

        # SELECT: tipo_imovel
        if is_empty(red.get("tipo_imovel")):
            updates["real_estate_data.tipo_imovel"] = random.choice(TIPOS_IMOVEL)

        # SELECT: finalidade
        if is_empty(red.get("finalidade")):
            updates["real_estate_data.finalidade"] = random.choice(FINALIDADES)

        # SELECT: certificado_energetico
        if is_empty(red.get("certificado_energetico")):
            updates["real_estate_data.certificado_energetico"] = random.choice(CERTIFICADOS_ENERGETICOS)

        # SELECT: num_quartos (número)
        if is_empty(red.get("num_quartos")):
            updates["real_estate_data.num_quartos"] = random.randint(1, 5)

        # Booleanos
        if is_empty(red.get("ja_tem_imovel")):
            updates["real_estate_data.ja_tem_imovel"] = True
        if is_empty(red.get("has_property")):
            updates["real_estate_data.has_property"] = True
        if is_empty(red.get("ja_tem_casa_escolhida")):
            updates["real_estate_data.ja_tem_casa_escolhida"] = True

        # Localização
        if is_empty(red.get("concelho")):
            concelho = random.choice(CONCELHOS)
            updates["real_estate_data.concelho"] = concelho
            if is_empty(red.get("localidade")):
                updates["real_estate_data.localidade"] = concelho
            if is_empty(red.get("localizacao")):
                updates["real_estate_data.localizacao"] = concelho
            if is_empty(red.get("freguesia")):
                updates["real_estate_data.freguesia"] = f"União de Freguesias de {concelho}"

        if is_empty(red.get("codigo_postal")):
            updates["real_estate_data.codigo_postal"] = f"{random.randint(1000, 4999)}-{random.randint(100, 999)}"

        # Áreas
        if is_empty(red.get("area_bruta")):
            updates["real_estate_data.area_bruta"] = random.randint(75, 250)
        if is_empty(red.get("area_util")):
            updates["real_estate_data.area_util"] = random.randint(60, 200)

        # SELECT: estacionamento (número)
        if is_empty(red.get("estacionamento")):
            updates["real_estate_data.estacionamento"] = random.randint(0, 2)

        # SELECT: arrecadação (número)
        if is_empty(red.get("arrecadacao")):
            updates["real_estate_data.arrecadacao"] = random.choice([0, 1])

        if is_empty(red.get("valor_patrimonial")):
            if valor_imovel:
                updates["real_estate_data.valor_patrimonial"] = round(int(valor_imovel) * 0.85, 2)

        # ════════════════════════════════════════════════════════════
        # credit_data
        # ════════════════════════════════════════════════════════════
        # Montante financiado (calculado = valor_imovel - capitais_proprios)
        if is_empty(cd.get("montante_financiado")) and not is_empty(valor_imovel):
            capitais = fd.get("capitais_proprios") or 0
            if isinstance(capitais, (int, float)):
                montante = max(int(valor_imovel) - int(capitais), 50000)
            else:
                montante = max(int(valor_imovel) - 0, 50000)
            updates["credit_data.montante_financiado"] = montante
            if is_empty(cd.get("requested_amount")):
                updates["credit_data.requested_amount"] = montante

        # SELECT: prazo_meses + loan_term_years
        if is_empty(cd.get("prazo_meses")):
            prazo_anos = random.choice([15, 20, 25, 30])
            updates["credit_data.prazo_meses"] = prazo_anos * 12
            if is_empty(cd.get("loan_term_years")):
                updates["credit_data.loan_term_years"] = prazo_anos

        # SELECT: spread
        if is_empty(cd.get("spread")):
            updates["credit_data.spread"] = round(random.uniform(0.5, 1.5), 2)

        # SELECT: banco
        if is_empty(cd.get("banco")):
            banco = random.choice(BANCOS)
            updates["credit_data.banco"] = banco
            if is_empty(cd.get("bank_name")):
                updates["credit_data.bank_name"] = banco

        # SELECT: tipo_taxa
        if is_empty(cd.get("tipo_taxa")):
            updates["credit_data.tipo_taxa"] = random.choice(TIPOS_TAXA)

        # Taxa de juro
        if is_empty(cd.get("interest_rate")):
            spread_val = cd.get("spread") or updates.get("credit_data.spread") or 1.0
            euribor = round(random.uniform(0.5, 3.5), 2)
            updates["credit_data.interest_rate"] = round(euribor + spread_val, 2)
            if is_empty(cd.get("taxa_anual")):
                updates["credit_data.taxa_anual"] = updates["credit_data.interest_rate"]

        # Prestação mensal (calculada por fórmula de amortização francesa)
        if is_empty(cd.get("monthly_payment")) and not is_empty(cd.get("montante_financiado") or updates.get("credit_data.montante_financiado")):
            montante = cd.get("montante_financiado") or updates.get("credit_data.montante_financiado")
            prazo = cd.get("prazo_meses") or updates.get("credit_data.prazo_meses") or 300
            taxa = cd.get("interest_rate") or updates.get("credit_data.interest_rate") or 3.0
            taxa_mensal = float(taxa) / 100 / 12
            num_prest = int(prazo)
            if taxa_mensal > 0 and num_prest > 0:
                prestacao = round(float(montante) * (taxa_mensal * (1 + taxa_mensal) ** num_prest) / ((1 + taxa_mensal) ** num_prest - 1), 2)
                updates["credit_data.monthly_payment"] = prestacao
                if is_empty(cd.get("prestacao_mensal")):
                    updates["credit_data.prestacao_mensal"] = prestacao

        # Compliance
        if is_empty(cd.get("admission_year")):
            updates["credit_data.admission_year"] = random.randint(2010, 2024)
        if is_empty(cd.get("is_ppe")):
            updates["credit_data.is_ppe"] = random.random() < 0.05
        if is_empty(cd.get("is_fpe")):
            updates["credit_data.is_fpe"] = random.random() < 0.03

        if not updates:
            stats["skipped"] += 1
            continue

        if not dry_run:
            await db.processes.update_one({"id": process_id}, {"$set": updates})

        stats["updated"] += 1
        stats["fields_filled"] += len(updates)

        if dry_run:
            print(f"  [DRY] Processo #{process.get('process_number', '?')} ({process.get('client_name', '?')}): {len(updates)} campos")
        elif stats["updated"] % 50 == 0:
            print(f"  ✅ {stats['updated']} processos atualizados...")

    return stats


# ====================================================================
# MAIN
# ====================================================================

def print_summary(clients_stats: dict, processes_stats: dict, dry_run: bool):
    mode = "DRY RUN (simulação)" if dry_run else "EXECUÇÃO REAL"
    print("\n" + "=" * 60)
    print(f"  BACKFILL EMPTY FIELDS v2 — {mode}")
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
    parser = argparse.ArgumentParser(description="Backfill Empty Fields v2 — PowerCell CRM")
    parser.add_argument("--dry-run", action="store_true", help="Simular sem escrever na BD")
    parser.add_argument("--limit", type=int, default=0, help="Limitar N docs por coleção (0 = sem limite)")
    args = parser.parse_args()

    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        print("❌ MONGO_URL e DB_NAME devem estar definidos no backend/.env")
        sys.exit(1)

    mongo_client = AsyncIOMotorClient(mongo_url)
    db = mongo_client[db_name]

    async def _run():
        print(f"🚀 Backfill Empty Fields v2 — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
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
