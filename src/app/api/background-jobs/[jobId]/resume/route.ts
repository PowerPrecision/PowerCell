import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

// POST /api/background-jobs/[jobId]/resume
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

    if (job.status !== "paused") {
      return NextResponse.json(
        { error: "Apenas jobs pausados podem ser retomados" },
        { status: 400 }
      );
    }

    const now = new Date();
    const existingStepLog = job.stepLog ? JSON.parse(job.stepLog) : [];
    existingStepLog.push({ ts: now.toISOString(), step: "Retomado" });

    const updated = await db.backgroundJob.update({
      where: { id: jobId },
      data: {
        status: "running",
        currentStep: "A retomar processamento...",
        stepLog: JSON.stringify(existingStepLog.slice(-100)),
      },
    });

    return NextResponse.json({ success: true, job: updated });
  } catch (error) {
    console.error("Error resuming background job:", error);
    return NextResponse.json({ error: "Erro ao retomar job" }, { status: 500 });
  }
}
