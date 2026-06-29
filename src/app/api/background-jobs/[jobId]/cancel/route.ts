import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

// POST /api/background-jobs/[jobId]/cancel
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  try {
    const { jobId } = await params;
    const job = await db.backgroundJob.findUnique({ where: { id: jobId } });

    if (!job) {
      return NextResponse.json({ error: "Job não encontrado" }, { status: 404 });
    }

    if (!["running", "pending", "paused"].includes(job.status)) {
      return NextResponse.json(
        { error: "Job não pode ser cancelado (não está em execução)" },
        { status: 400 }
      );
    }

    const now = new Date();
    const existingStepLog = job.stepLog ? JSON.parse(job.stepLog) : [];
    existingStepLog.push({ ts: now.toISOString(), step: "Cancelado" });

    const updated = await db.backgroundJob.update({
      where: { id: jobId },
      data: {
        status: "cancelled",
        finishedAt: now,
        currentStep: "Cancelado pelo utilizador",
        message: "Cancelado pelo utilizador",
        stepLog: JSON.stringify(existingStepLog.slice(-100)),
      },
    });

    return NextResponse.json({ success: true, job: updated });
  } catch (error) {
    console.error("Error cancelling background job:", error);
    return NextResponse.json({ error: "Erro ao cancelar job" }, { status: 500 });
  }
}
