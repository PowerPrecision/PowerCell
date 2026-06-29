import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

// POST /api/background-jobs/[jobId]/pause
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

    if (job.status !== "running") {
      return NextResponse.json(
        { error: "Apenas jobs em execução podem ser pausados" },
        { status: 400 }
      );
    }

    const now = new Date();
    const existingStepLog = job.stepLog ? JSON.parse(job.stepLog) : [];
    existingStepLog.push({ ts: now.toISOString(), step: "Pausado" });

    const updated = await db.backgroundJob.update({
      where: { id: jobId },
      data: {
        status: "paused",
        currentStep: "Pausado pelo utilizador",
        stepLog: JSON.stringify(existingStepLog.slice(-100)),
      },
    });

    return NextResponse.json({ success: true, job: updated });
  } catch (error) {
    console.error("Error pausing background job:", error);
    return NextResponse.json({ error: "Erro ao pausar job" }, { status: 500 });
  }
}
