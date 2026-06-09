import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

// GET /api/background-jobs/[jobId] - Get a specific job
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  try {
    const { jobId } = await params;
    const job = await db.backgroundJob.findUnique({ where: { id: jobId } });

    if (!job) {
      return NextResponse.json(
        { error: "Job não encontrado" },
        { status: 404 }
      );
    }

    return NextResponse.json({
      ...job,
      details: job.details ? JSON.parse(job.details) : {},
      stepLog: job.stepLog ? JSON.parse(job.stepLog) : [],
      errorMessages: job.errorMessages ? JSON.parse(job.errorMessages) : [],
    });
  } catch (error) {
    console.error("Error fetching background job:", error);
    return NextResponse.json(
      { error: "Erro ao carregar job" },
      { status: 500 }
    );
  }
}

// DELETE /api/background-jobs/[jobId] - Delete a specific job
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  try {
    const { jobId } = await params;
    await db.backgroundJob.delete({ where: { id: jobId } });
    return NextResponse.json({ success: true });
  } catch (error) {
    console.error("Error deleting background job:", error);
    return NextResponse.json(
      { error: "Erro ao remover job" },
      { status: 500 }
    );
  }
}
