import { NextResponse } from "next/server";
import { db } from "@/lib/db";

// POST /api/background-jobs/clear-all - Remove ALL jobs
export async function POST() {
  try {
    const result = await db.backgroundJob.deleteMany({});
    return NextResponse.json({ deleted: result.count });
  } catch (error) {
    console.error("Error clearing all background jobs:", error);
    return NextResponse.json({ error: "Erro ao limpar jobs" }, { status: 500 });
  }
}
