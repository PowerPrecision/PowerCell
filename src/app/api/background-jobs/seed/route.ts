import { NextResponse } from "next/server";
import { db } from "@/lib/db";

// POST /api/background-jobs/seed - Seed demo background jobs
export async function POST() {
  try {
    // Clear existing
    await db.backgroundJob.deleteMany({});

    const now = new Date();
    const jobs = [
      // Running import
      {
        type: "bulk_import",
        status: "running",
        progress: 45,
        total: 250,
        processed: 112,
        errors: 3,
        currentStep: "A processar ficheiro clientes_marcos.xlsx (linha 112/250)",
        userEmail: "admin@sistema.pt",
        startedAt: new Date(now.getTime() - 5 * 60 * 1000),
        details: JSON.stringify({ folder: "S3://imports/2026-07/", source: "Excel Upload" }),
        stepLog: JSON.stringify([
          { ts: new Date(now.getTime() - 5 * 60 * 1000).toISOString(), step: "Iniciando..." },
          { ts: new Date(now.getTime() - 4.8 * 60 * 1000).toISOString(), step: "A validar ficheiro Excel..." },
          { ts: new Date(now.getTime() - 4.5 * 60 * 1000).toISOString(), step: "Ficheiro validado: 250 registos encontrados" },
          { ts: new Date(now.getTime() - 4 * 60 * 1000).toISOString(), step: "A processar ficheiro clientes_marcos.xlsx..." },
          { ts: new Date(now.getTime() - 3 * 60 * 1000).toISOString(), step: "50/250 processados — 3 erros encontrados" },
          { ts: new Date(now.getTime() - 1.5 * 60 * 1000).toISOString(), step: "112/250 processados" },
          { ts: new Date(now.getTime() - 30 * 1000).toISOString(), step: "A processar ficheiro clientes_marcos.xlsx (linha 112/250)" },
        ]),
        errorMessages: JSON.stringify([
          "Linha 45: NIF inválido '12345678'",
          "Linha 78: Email em falta",
          "Linha 103: Processo duplicado P-2026-0045",
        ]),
      },
      // Running document analysis
      {
        type: "document_analysis",
        status: "running",
        progress: 72,
        total: 50,
        processed: 36,
        errors: 1,
        currentStep: "A analisar documento CC_Tiago_Silva.pdf com IA",
        userEmail: "pedroborges@powerealestate.pt",
        startedAt: new Date(now.getTime() - 12 * 60 * 1000),
        details: JSON.stringify({ folder: "S3://documents/analysis/", source: "Auto-Análise" }),
        stepLog: JSON.stringify([
          { ts: new Date(now.getTime() - 12 * 60 * 1000).toISOString(), step: "Iniciando..." },
          { ts: new Date(now.getTime() - 11.5 * 60 * 1000).toISOString(), step: "A carregar documentos do S3..." },
          { ts: new Date(now.getTime() - 11 * 60 * 1000).toISOString(), step: "50 documentos encontrados para análise" },
          { ts: new Date(now.getTime() - 10 * 60 * 1000).toISOString(), step: "A iniciar análise com GPT-4o-mini..." },
          { ts: new Date(now.getTime() - 5 * 60 * 1000).toISOString(), step: "25/50 analisados" },
          { ts: new Date(now.getTime() - 2 * 60 * 1000).toISOString(), step: "36/50 analisados — 1 erro" },
          { ts: new Date(now.getTime() - 15 * 1000).toISOString(), step: "A analisar documento CC_Tiago_Silva.pdf com IA" },
        ]),
        errorMessages: JSON.stringify([
          "Documento IRS_2024.pdf: PDF corrompido, não foi possível extrair texto",
        ]),
      },
      // Paused job
      {
        type: "aggregated_import",
        status: "paused",
        progress: 28,
        total: 1000,
        processed: 280,
        errors: 12,
        currentStep: "Pausado pelo utilizador",
        userEmail: "admin@sistema.pt",
        startedAt: new Date(now.getTime() - 45 * 60 * 1000),
        details: JSON.stringify({ folder: "S3://imports/aggregated/", source: "Importação Agregada" }),
        stepLog: JSON.stringify([
          { ts: new Date(now.getTime() - 45 * 60 * 1000).toISOString(), step: "Iniciando..." },
          { ts: new Date(now.getTime() - 44 * 60 * 1000).toISOString(), step: "A carregar dados agregados..." },
          { ts: new Date(now.getTime() - 43 * 60 * 1000).toISOString(), step: "1000 registos para processar" },
          { ts: new Date(now.getTime() - 30 * 60 * 1000).toISOString(), step: "150/1000 processados" },
          { ts: new Date(now.getTime() - 20 * 60 * 1000).toISOString(), step: "280/1000 processados — 12 erros" },
          { ts: new Date(now.getTime() - 15 * 60 * 1000).toISOString(), step: "Pausado" },
        ]),
        errorMessages: JSON.stringify([
          "Linha 34: Formato de data inválido",
          "Linha 56: NIF duplicado",
          "Linha 89: Campo obrigatório em falta",
          "Linha 102: Morada demasiado longa",
          "Linha 145: Telefone inválido",
          "Linha 178: Email inválido",
          "Linha 201: Processo sem cliente associado",
          "Linha 234: Tipo de processo desconhecido",
          "Linha 256: Valor do empréstimo inválido",
          "Linha 267: Banco não reconhecido",
          "Linha 278: Data de nascimento no futuro",
          "Linha 279: Nome com caracteres inválidos",
        ]),
      },
      // Completed job
      {
        type: "email_sync",
        status: "success",
        progress: 100,
        total: 45,
        processed: 45,
        errors: 0,
        currentStep: "Concluído",
        userEmail: "tiagoborges@powerealestate.pt",
        startedAt: new Date(now.getTime() - 120 * 60 * 1000),
        finishedAt: new Date(now.getTime() - 118 * 60 * 1000),
        message: "Sincronização concluída: 45 emails processados",
        details: JSON.stringify({ source: "IMAP Sync" }),
        stepLog: JSON.stringify([
          { ts: new Date(now.getTime() - 120 * 60 * 1000).toISOString(), step: "Iniciando..." },
          { ts: new Date(now.getTime() - 119.5 * 60 * 1000).toISOString(), step: "A ligar ao servidor IMAP..." },
          { ts: new Date(now.getTime() - 119 * 60 * 1000).toISOString(), step: "45 emails encontrados" },
          { ts: new Date(now.getTime() - 118.5 * 60 * 1000).toISOString(), step: "A processar emails..." },
          { ts: new Date(now.getTime() - 118 * 60 * 1000).toISOString(), step: "Concluído" },
        ]),
        errorMessages: JSON.stringify([]),
      },
      // Failed job
      {
        type: "bulk_import",
        status: "failed",
        progress: 15,
        total: 500,
        processed: 75,
        errors: 75,
        currentStep: "Falhado",
        userEmail: "admin@sistema.pt",
        startedAt: new Date(now.getTime() - 3 * 60 * 60 * 1000),
        finishedAt: new Date(now.getTime() - 2.9 * 60 * 60 * 1000),
        message: "Importação falhou: ficheiro Excel corrompido",
        errorLog: "O ficheiro 'dados_clientes_v2.xlsx' está corrompido e não pode ser lido. Erro: Unexpected end of archive at byte 45213. O ficheiro pode ter sido interrompido durante o upload.",
        details: JSON.stringify({ folder: "S3://imports/failed/", source: "Excel Upload" }),
        stepLog: JSON.stringify([
          { ts: new Date(now.getTime() - 3 * 60 * 60 * 1000).toISOString(), step: "Iniciando..." },
          { ts: new Date(now.getTime() - 2.95 * 60 * 60 * 1000).toISOString(), step: "A validar ficheiro Excel..." },
          { ts: new Date(now.getTime() - 2.93 * 60 * 60 * 1000).toISOString(), step: "A processar dados..." },
          { ts: new Date(now.getTime() - 2.9 * 60 * 60 * 1000).toISOString(), step: "Falhado" },
        ]),
        errorMessages: JSON.stringify([
          "Erro de parsing na linha 1: Unexpected end of archive",
          "O ficheiro pode estar corrompido",
        ]),
      },
      // Another completed job
      {
        type: "data_export",
        status: "success",
        progress: 100,
        total: 1,
        processed: 1,
        errors: 0,
        currentStep: "Concluído",
        userEmail: "pedroborges@powerealestate.pt",
        startedAt: new Date(now.getTime() - 24 * 60 * 60 * 1000),
        finishedAt: new Date(now.getTime() - 24 * 60 * 60 * 1000 + 30000),
        message: "Exportação concluída: relatório_semanal.xlsx",
        details: JSON.stringify({ source: "Exportação Manual" }),
        stepLog: JSON.stringify([
          { ts: new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString(), step: "Iniciando..." },
          { ts: new Date(now.getTime() - 24 * 60 * 60 * 1000 + 5000).toISOString(), step: "A gerar relatório semanal..." },
          { ts: new Date(now.getTime() - 24 * 60 * 60 * 1000 + 25000).toISOString(), step: "A enviar para S3..." },
          { ts: new Date(now.getTime() - 24 * 60 * 60 * 1000 + 30000).toISOString(), step: "Concluído" },
        ]),
        errorMessages: JSON.stringify([]),
      },
      // Cancelled job
      {
        type: "document_analysis",
        status: "cancelled",
        progress: 10,
        total: 30,
        processed: 3,
        errors: 0,
        currentStep: "Cancelado pelo utilizador",
        userEmail: "admin@sistema.pt",
        startedAt: new Date(now.getTime() - 6 * 60 * 60 * 1000),
        finishedAt: new Date(now.getTime() - 5.8 * 60 * 60 * 1000),
        message: "Cancelado pelo utilizador",
        details: JSON.stringify({ source: "Auto-Análise" }),
        stepLog: JSON.stringify([
          { ts: new Date(now.getTime() - 6 * 60 * 60 * 1000).toISOString(), step: "Iniciando..." },
          { ts: new Date(now.getTime() - 5.9 * 60 * 60 * 1000).toISOString(), step: "3/30 analisados" },
          { ts: new Date(now.getTime() - 5.8 * 60 * 60 * 1000).toISOString(), step: "Cancelado" },
        ]),
        errorMessages: JSON.stringify([]),
      },
    ];

    for (const jobData of jobs) {
      await db.backgroundJob.create({ data: jobData });
    }

    return NextResponse.json({ seeded: jobs.length });
  } catch (error) {
    console.error("Error seeding background jobs:", error);
    return NextResponse.json({ error: "Erro ao criar dados de demonstração" }, { status: 500 });
  }
}
