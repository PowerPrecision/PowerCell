import { NextResponse } from "next/server";
import { db } from "@/lib/db";

// GET /api/background-jobs/metrics - Get aggregated job metrics
export async function GET() {
  try {
    const jobs = await db.backgroundJob.findMany();

    const totalJobs = jobs.length;
    const byStatus: Record<string, number> = {};
    const byType: Record<string, number> = {};
    const durations: number[] = [];
    let stuckCount = 0;

    for (const job of jobs) {
      // By status
      byStatus[job.status] = (byStatus[job.status] || 0) + 1;

      // By type
      byType[job.type] = (byType[job.type] || 0) + 1;

      // Duration
      if (job.startedAt && job.finishedAt) {
        const duration =
          (job.finishedAt.getTime() - job.startedAt.getTime()) / 1000;
        durations.push(duration);
      }

      // Stuck detection
      if (["running", "pending"].includes(job.status)) {
        const lastUpdate = job.updatedAt;
        const hoursSinceUpdate =
          (Date.now() - lastUpdate.getTime()) / (1000 * 60 * 60);
        if (hoursSinceUpdate > 2) {
          stuckCount++;
        }
      }
    }

    const successCount = byStatus["success"] || 0;
    const successRate = totalJobs > 0 ? Math.round((successCount / totalJobs) * 100) : 0;
    const avgDuration = durations.length > 0 
      ? durations.reduce((a, b) => a + b, 0) / durations.length 
      : 0;

    const formatDuration = (seconds: number): string => {
      if (seconds < 60) return `${seconds.toFixed(1)}s`;
      if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
      return `${(seconds / 3600).toFixed(1)}h`;
    };

    return NextResponse.json({
      period_days: 7,
      total_jobs: totalJobs,
      success_rate: successRate,
      avg_duration_seconds: Math.round(avgDuration * 10) / 10,
      avg_duration_formatted: formatDuration(avgDuration),
      by_status: byStatus,
      by_type: byType,
      stuck_count: stuckCount,
    });
  } catch (error) {
    console.error("Error fetching metrics:", error);
    return NextResponse.json({ error: "Erro ao carregar métricas" }, { status: 500 });
  }
}
