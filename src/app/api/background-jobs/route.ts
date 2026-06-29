import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

// GET /api/background-jobs - List all background jobs with counts
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const statusParam = searchParams.get("status");

    // Support multiple statuses via comma separation (e.g. "failed,cancelled")
    let where: Record<string, unknown> = {};
    if (statusParam) {
      const statuses = statusParam.split(",");
      if (statuses.length === 1) {
        where = { status: statuses[0] };
      } else {
        where = { status: { in: statuses } };
      }
    }

    const jobs = await db.backgroundJob.findMany({
      where,
      orderBy: { createdAt: "desc" },
      take: 50,
    });

    const allJobs = await db.backgroundJob.findMany();
    const counts = {
      running: allJobs.filter((j) => j.status === "running").length,
      paused: allJobs.filter((j) => j.status === "paused").length,
      success: allJobs.filter((j) => j.status === "success").length,
      failed: allJobs.filter(
        (j) => j.status === "failed" || j.status === "cancelled"
      ).length,
      total: allJobs.length,
    };

    // Parse JSON fields for each job
    const parsedJobs = jobs.map((job) => ({
      ...job,
      details: job.details ? JSON.parse(job.details) : {},
      stepLog: job.stepLog ? JSON.parse(job.stepLog) : [],
      errorMessages: job.errorMessages ? JSON.parse(job.errorMessages) : [],
    }));

    return NextResponse.json({ jobs: parsedJobs, counts });
  } catch (error) {
    console.error("Error fetching background jobs:", error);
    return NextResponse.json(
      { error: "Erro ao carregar jobs" },
      { status: 500 }
    );
  }
}

// DELETE /api/background-jobs - Clear all finished jobs
export async function DELETE() {
  try {
    const result = await db.backgroundJob.deleteMany({
      where: {
        status: { in: ["success", "failed", "cancelled"] },
      },
    });

    return NextResponse.json({ deleted: result.count });
  } catch (error) {
    console.error("Error clearing background jobs:", error);
    return NextResponse.json(
      { error: "Erro ao limpar jobs" },
      { status: 500 }
    );
  }
}

// POST /api/background-jobs - Create a new background job (for seeding/testing)
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { type, userEmail, total, details } = body;

    const now = new Date();
    const job = await db.backgroundJob.create({
      data: {
        type: type || "bulk_import",
        status: "running",
        progress: 0,
        total: total || 0,
        processed: 0,
        errors: 0,
        currentStep: "Iniciando...",
        userEmail: userEmail || "admin@sistema.pt",
        startedAt: now,
        details: details ? JSON.stringify(details) : null,
        stepLog: JSON.stringify([
          { ts: now.toISOString(), step: "Iniciando..." },
        ]),
        errorMessages: JSON.stringify([]),
      },
    });

    return NextResponse.json(job, { status: 201 });
  } catch (error) {
    console.error("Error creating background job:", error);
    return NextResponse.json(
      { error: "Erro ao criar job" },
      { status: 500 }
    );
  }
}
