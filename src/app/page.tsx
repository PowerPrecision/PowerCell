"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Activity,
  RefreshCw,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  Trash2,
  Play,
  Pause,
  AlertTriangle,
  FileText,
  Upload,
  Zap,
  Ban,
  BarChart3,
  TrendingUp,
  Timer,
  Terminal,
  ChevronRight,
  Mail,
  FileDown,
  Database,
} from "lucide-react";
import { toast } from "sonner";

// ── Types ──────────────────────────────────────────────────
interface StepLogEntry {
  ts: string;
  step: string;
}

interface BackgroundJob {
  id: string;
  type: string;
  status: string;
  progress: number;
  total: number;
  processed: number;
  errors: number;
  currentStep: string | null;
  message: string | null;
  errorLog: string | null;
  userEmail: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  createdAt: string;
  updatedAt: string;
  details: Record<string, string>;
  stepLog: StepLogEntry[];
  errorMessages: string[];
}

interface JobCounts {
  running: number;
  paused: number;
  success: number;
  failed: number;
  total: number;
}

interface Metrics {
  period_days: number;
  total_jobs: number;
  success_rate: number;
  avg_duration_seconds: number;
  avg_duration_formatted: string;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
  stuck_count: number;
}

// ── Constants ──────────────────────────────────────────────
const JOB_TYPE_CONFIG: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  bulk_import: { label: "Importação Massiva", icon: Upload, color: "text-blue-600" },
  document_analysis: { label: "Análise de Documentos", icon: FileText, color: "text-purple-600" },
  email_sync: { label: "Sincronização de Email", icon: Mail, color: "text-teal-600" },
  aggregated_import: { label: "Importação Agregada", icon: Database, color: "text-orange-600" },
  data_export: { label: "Exportação de Dados", icon: FileDown, color: "text-green-600" },
};

const STATUS_CONFIG: Record<string, { label: string; className: string; icon: React.ElementType }> = {
  running: { label: "A correr", className: "bg-blue-500 hover:bg-blue-500", icon: Loader2 },
  paused: { label: "Pausado", className: "bg-amber-500 hover:bg-amber-500", icon: Clock },
  success: { label: "Concluído", className: "bg-green-500 hover:bg-green-500", icon: CheckCircle },
  failed: { label: "Falhado", className: "bg-red-500 hover:bg-red-500", icon: XCircle },
  cancelled: { label: "Cancelado", className: "bg-gray-500 hover:bg-gray-500", icon: Ban },
  pending: { label: "Pendente", className: "bg-gray-400 hover:bg-gray-400", icon: Clock },
};

// ── Helpers ────────────────────────────────────────────────
function safeDate(isoString: string | null | undefined): Date | null {
  if (!isoString) return null;
  try {
    const d = new Date(isoString);
    return isNaN(d.getTime()) ? null : d;
  } catch {
    return null;
  }
}

function formatDateTime(isoString: string | null | undefined): string {
  const d = safeDate(isoString);
  if (!d) return "—";
  return d.toLocaleString("pt-PT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTimeOnly(isoString: string | null | undefined): string {
  const d = safeDate(isoString);
  if (!d) return "";
  return d.toLocaleString("pt-PT", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatDuration(isoStart: string | null | undefined, isoEnd: string | null | undefined): string {
  if (!isoStart) return "—";
  const start = safeDate(isoStart);
  if (!start) return "—";
  const end = isoEnd ? (safeDate(isoEnd) || new Date()) : new Date();
  const diffMs = end.getTime() - start.getTime();
  if (diffMs < 0) return "0s";
  const totalSecs = Math.floor(diffMs / 1000);
  const hrs = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  const secs = totalSecs % 60;
  if (hrs > 0) return `${String(hrs).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

// ── Elapsed Timer Component ────────────────────────────────
function ElapsedTimer({ startedAt, finishedAt }: { startedAt: string | null; finishedAt: string | null }) {
  const [elapsed, setElapsed] = useState(() => formatDuration(startedAt, finishedAt));
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    // Clear any existing interval
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (!startedAt || finishedAt) {
      // Use a microtask to avoid synchronous setState in effect
      queueMicrotask(() => setElapsed(formatDuration(startedAt, finishedAt)));
      return;
    }

    // Start a new interval for live timer
    intervalRef.current = setInterval(() => {
      setElapsed(formatDuration(startedAt, null));
    }, 1000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [startedAt, finishedAt]);

  return (
    <span className="flex items-center gap-1">
      <Timer className="h-3.5 w-3.5" />
      {elapsed}
    </span>
  );
}

// ── Job Card Component ─────────────────────────────────────
function JobCard({
  job,
  onDelete,
  onCancel,
  onPause,
  onResume,
  onViewDetails,
}: {
  job: BackgroundJob;
  onDelete: (id: string) => void;
  onCancel: (id: string) => void;
  onPause: (id: string) => void;
  onResume: (id: string) => void;
  onViewDetails: (job: BackgroundJob) => void;
}) {
  const typeConfig = JOB_TYPE_CONFIG[job.type] || { label: job.type, icon: Play, color: "text-gray-600" };
  const statusConfig = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
  const Icon = typeConfig.icon;
  const StatusIcon = statusConfig.icon;
  const [actionLoading, setActionLoading] = useState(false);

  const isRunning = job.status === "running";
  const isPaused = job.status === "paused";
  const isActive = isRunning || isPaused;

  const iconBg =
    isRunning ? "bg-blue-100 dark:bg-blue-900/30" :
    job.status === "success" ? "bg-green-100 dark:bg-green-900/30" :
    job.status === "failed" ? "bg-red-100 dark:bg-red-900/30" :
    isPaused ? "bg-amber-100 dark:bg-amber-900/30" :
    "bg-gray-100 dark:bg-gray-800";

  const iconColor =
    isRunning ? "text-blue-600" :
    job.status === "success" ? "text-green-600" :
    job.status === "failed" ? "text-red-600" :
    isPaused ? "text-amber-600" :
    "text-gray-600";

  return (
    <Card className={`transition-all ${isRunning ? 'border-blue-300 shadow-md dark:border-blue-700' : isPaused ? 'border-amber-300 dark:border-amber-700' : ''}`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          {/* Icon + Info */}
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <div className={`p-2.5 rounded-lg shrink-0 ${iconBg}`}>
              <Icon className={`h-5 w-5 ${iconColor}`} />
            </div>

            <div className="flex-1 min-w-0">
              {/* Type + Status */}
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-medium text-sm">{typeConfig.label}</h4>
                <Badge className={`text-xs text-white ${statusConfig.className}`}>
                  <StatusIcon className={`h-3 w-3 mr-1 ${isRunning ? 'animate-spin' : ''}`} />
                  {statusConfig.label}
                </Badge>
              </div>

              {/* Meta: start + elapsed */}
              <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                <span>Início: {formatDateTime(job.startedAt)}</span>
                <ElapsedTimer startedAt={job.startedAt} finishedAt={job.finishedAt} />
                {job.finishedAt && <span>Fim: {formatDateTime(job.finishedAt)}</span>}
              </div>

              {/* Progress Bar */}
              {(job.total > 0 || job.progress > 0) && (
                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs mb-1.5">
                    <span className="text-muted-foreground">
                      {job.processed ?? 0} de {job.total || "?"} processados
                    </span>
                    <span className="font-semibold">{job.progress ?? 0}%</span>
                  </div>
                  <Progress
                    value={job.progress ?? 0}
                    className={`h-2.5 ${isRunning ? 'animate-pulse' : ''}`}
                  />
                </div>
              )}

              {/* Current Step */}
              {job.currentStep && isActive && (
                <div className="mt-2 flex items-start gap-1.5">
                  <ChevronRight className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${isRunning ? 'text-blue-500' : 'text-amber-500'}`} />
                  <p className="text-xs italic text-muted-foreground leading-relaxed">
                    {job.currentStep}
                  </p>
                </div>
              )}

              {/* Errors count */}
              {job.errors > 0 && (
                <div className="flex items-center gap-1 mt-2 text-xs text-amber-600">
                  <AlertTriangle className="h-3 w-3" />
                  {job.errors} erro(s) durante processamento
                </div>
              )}

              {/* Message for completed jobs */}
              {job.message && !isActive && (
                <p className={`mt-2 text-xs ${job.status === 'failed' ? 'text-red-600' : 'text-muted-foreground'}`}>
                  {job.message}
                </p>
              )}

              {/* Error log for failed jobs */}
              {job.errorLog && job.status === 'failed' && (
                <div className="mt-2 p-2 bg-red-50 dark:bg-red-950/30 rounded text-xs text-red-700 dark:text-red-400 font-mono break-all">
                  {job.errorLog}
                </div>
              )}

              {/* Details */}
              {job.details && Object.keys(job.details).length > 0 && (
                <div className="mt-2 text-xs text-muted-foreground">
                  {job.details.folder && <span>Pasta: {job.details.folder}</span>}
                  {job.details.source && <span className="ml-2">Fonte: {job.details.source}</span>}
                </div>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 shrink-0">
            {isRunning && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-amber-600 hover:text-amber-700 hover:bg-amber-50"
                  onClick={async () => { setActionLoading(true); await onPause(job.id); setActionLoading(false); }}
                  disabled={actionLoading}
                >
                  {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Pause className="h-4 w-4 mr-1" />Pausar</>}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  onClick={async () => { setActionLoading(true); await onCancel(job.id); setActionLoading(false); }}
                  disabled={actionLoading}
                >
                  {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <><XCircle className="h-4 w-4 mr-1" />Cancelar</>}
                </Button>
              </>
            )}

            {isPaused && (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-green-600 hover:text-green-700 hover:bg-green-50"
                  onClick={async () => { setActionLoading(true); await onResume(job.id); setActionLoading(false); }}
                  disabled={actionLoading}
                >
                  {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Play className="h-4 w-4 mr-1" />Retomar</>}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-600 hover:text-red-700 hover:bg-red-50"
                  onClick={async () => { setActionLoading(true); await onCancel(job.id); setActionLoading(false); }}
                  disabled={actionLoading}
                >
                  <XCircle className="h-4 w-4 mr-1" />
                  Cancelar
                </Button>
              </>
            )}

            {/* View details button */}
            <Button
              variant="ghost"
              size="sm"
              className="text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/30"
              onClick={() => onViewDetails(job)}
              title="Ver detalhes e logs"
            >
              <Terminal className="h-4 w-4" />
            </Button>

            {!['running', 'paused'].includes(job.status) && (
              <Button
                variant="ghost"
                size="sm"
                className="text-muted-foreground hover:text-destructive"
                onClick={() => onDelete(job.id)}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Job Detail Dialog (Terminal-style log viewer) ──────────
function JobDetailDialog({
  job,
  open,
  onOpenChange,
}: {
  job: BackgroundJob | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!job) return null;

  const stepLog = job.stepLog || [];
  const typeConfig = JOB_TYPE_CONFIG[job.type] || { label: job.type, icon: Play };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh] p-0 flex flex-col gap-0">
        <DialogHeader className="p-6 pb-4 border-b">
          <DialogTitle className="flex items-center gap-2">
            <Terminal className="h-5 w-5 text-green-500" />
            Logs do Processo
          </DialogTitle>
          <DialogDescription>
            {typeConfig.label} — {job.id.slice(0, 8)}...
          </DialogDescription>
        </DialogHeader>

        {/* Job summary bar */}
        <div className="px-6 py-3 border-b bg-muted/30">
          <div className="flex items-center gap-3 text-sm">
            <Badge className={`${STATUS_CONFIG[job.status]?.className || ""} text-white`}>
              {STATUS_CONFIG[job.status]?.label || job.status}
            </Badge>
            {job.total > 0 && (
              <span className="text-muted-foreground">
                {job.processed ?? 0}/{job.total} processados ({job.progress ?? 0}%)
              </span>
            )}
            {job.startedAt && (
              <span className="text-muted-foreground">
                <Timer className="h-3 w-3 inline mr-1" />
                {formatDuration(job.startedAt, job.finishedAt)}
              </span>
            )}
          </div>
          {job.currentStep && (
            <p className="text-xs italic text-muted-foreground mt-1.5">
              → {job.currentStep}
            </p>
          )}
        </div>

        {/* Terminal-style log */}
        <ScrollArea className="flex-1 max-h-[50vh]">
          <div className="p-4">
            <div className="bg-gray-950 dark:bg-gray-900 rounded-lg border border-gray-800 font-mono text-xs overflow-hidden">
              {/* Terminal header */}
              <div className="flex items-center gap-1.5 px-3 py-2 border-b border-gray-800 bg-gray-900 dark:bg-gray-800">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
                <div className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
                <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
                <span className="ml-2 text-gray-400 text-[10px]">job-{job.id.slice(0, 8)}.log</span>
              </div>

              {/* Terminal body */}
              <div className="p-3 space-y-1.5 max-h-[40vh] overflow-y-auto">
                {stepLog.length > 0 ? stepLog.map((entry, idx) => {
                  const isLast = idx === stepLog.length - 1;
                  const isFailed = entry.step === "Falhado";
                  const isSuccess = entry.step === "Concluído";
                  return (
                    <div key={idx} className={`flex gap-2 ${isLast ? "opacity-100" : "opacity-70"}`}>
                      <span className="text-gray-500 shrink-0 select-none">
                        {formatTimeOnly(entry.ts)}
                      </span>
                      <span className={
                        isFailed ? "text-red-400" :
                        isSuccess ? "text-green-400" :
                        isLast ? "text-blue-400" :
                        "text-gray-300"
                      }>
                        {isLast && !isFailed && !isSuccess ? "▸ " : "  "}
                        {entry.step}
                      </span>
                    </div>
                  );
                }) : (
                  <div className="text-gray-500 italic">Sem registos de log disponíveis</div>
                )}

                {/* Error message */}
                {job.errorLog && (
                  <div className="mt-2 pt-2 border-t border-gray-700">
                    <span className="text-red-400">✗ ERRO: {job.errorLog}</span>
                  </div>
                )}
                {job.message && job.status === 'failed' && !job.errorLog && (
                  <div className="mt-2 pt-2 border-t border-gray-700">
                    <span className="text-red-400">✗ ERRO: {job.message}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Error messages list */}
            {job.errorMessages && job.errorMessages.length > 0 && (
              <div className="mt-4">
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">
                  Mensagens de Erro ({job.errorMessages.length})
                </h4>
                <div className="bg-red-50 dark:bg-red-950/20 rounded-lg border border-red-200 dark:border-red-800 p-3 space-y-1">
                  {job.errorMessages.slice(0, 20).map((msg, idx) => (
                    <p key={idx} className="text-xs text-red-700 dark:text-red-400 font-mono break-all">
                      {msg}
                    </p>
                  ))}
                  {job.errorMessages.length > 20 && (
                    <p className="text-xs text-muted-foreground italic">
                      ...e mais {job.errorMessages.length - 20} mensagens
                    </p>
                  )}
                </div>
              </div>
            )}

            {/* Raw details */}
            {job.details && Object.keys(job.details).length > 0 && (
              <div className="mt-4">
                <h4 className="text-xs font-semibold text-muted-foreground mb-2">Detalhes</h4>
                <pre className="text-xs bg-muted p-3 rounded-lg overflow-x-auto">
                  {JSON.stringify(job.details, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}

// ── Metrics Dashboard ──────────────────────────────────────
function MetricsDashboard({ metrics }: { metrics: Metrics | null }) {
  if (!metrics) return null;

  return (
    <Card className="bg-gradient-to-r from-blue-50 to-teal-50 dark:from-blue-950/30 dark:to-teal-950/30 border-blue-200 dark:border-blue-800">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-blue-600" />
          Métricas (últimos {metrics.period_days} dias)
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              <TrendingUp className="h-4 w-4" />
              Taxa de Sucesso
            </div>
            <div className={`text-2xl font-bold ${metrics.success_rate >= 80 ? 'text-green-600' : metrics.success_rate >= 50 ? 'text-amber-600' : 'text-red-600'}`}>
              {metrics.success_rate}%
            </div>
            <Progress value={metrics.success_rate} className="h-2 mt-2" />
          </div>

          <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              <Timer className="h-4 w-4" />
              Tempo Médio
            </div>
            <div className="text-2xl font-bold text-blue-600">
              {metrics.avg_duration_formatted || '—'}
            </div>
          </div>

          <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              <Activity className="h-4 w-4" />
              Total de Jobs
            </div>
            <div className="text-2xl font-bold">{metrics.total_jobs}</div>
          </div>

          <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
            <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
              <AlertTriangle className="h-4 w-4" />
              Jobs Stuck
            </div>
            <div className={`text-2xl font-bold ${metrics.stuck_count > 0 ? 'text-amber-600' : 'text-green-600'}`}>
              {metrics.stuck_count}
            </div>
          </div>
        </div>

        <div className="grid md:grid-cols-2 gap-4">
          <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
            <h4 className="font-medium mb-3">Por Status</h4>
            <div className="space-y-2">
              {Object.entries(metrics.by_status || {}).map(([status, count]) => (
                <div key={status} className="flex items-center justify-between">
                  <span className="text-sm">{STATUS_CONFIG[status]?.label || status}</span>
                  <Badge variant="outline">{count as number}</Badge>
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
            <h4 className="font-medium mb-3">Por Tipo</h4>
            <div className="space-y-2">
              {Object.entries(metrics.by_type || {}).map(([type, count]) => (
                <div key={type} className="flex items-center justify-between text-sm">
                  <span>{JOB_TYPE_CONFIG[type]?.label || type.replace(/_/g, ' ')}</span>
                  <Badge variant="outline">{count as number}</Badge>
                </div>
              ))}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ════════════════════════════════════════════════════════════
// Main Page Component
// ════════════════════════════════════════════════════════════
export default function CentroDeOperacoes() {
  const [jobs, setJobs] = useState<BackgroundJob[]>([]);
  const [counts, setCounts] = useState<JobCounts>({ running: 0, success: 0, failed: 0, paused: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [showMetrics, setShowMetrics] = useState(false);
  const [selectedJob, setSelectedJob] = useState<BackgroundJob | null>(null);
  const [showDetailDialog, setShowDetailDialog] = useState(false);
  const [seeded, setSeeded] = useState(false);

  // Fetch jobs
  const fetchJobs = useCallback(async () => {
    try {
      const url = statusFilter
        ? `/api/background-jobs?status=${statusFilter}`
        : `/api/background-jobs`;

      const response = await fetch(url);
      if (response.ok) {
        const data = await response.json();
        setJobs(data.jobs || []);
        setCounts(data.counts || { running: 0, success: 0, failed: 0, paused: 0, total: 0 });
      }
    } catch (error) {
      console.error("Erro ao carregar jobs:", error);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  // Fetch metrics
  const fetchMetrics = useCallback(async () => {
    try {
      const response = await fetch("/api/background-jobs/metrics");
      if (response.ok) {
        const data = await response.json();
        setMetrics(data);
      }
    } catch (error) {
      console.error("Erro ao carregar métricas:", error);
    }
  }, []);

  // Seed demo data
  const seedData = useCallback(async () => {
    try {
      const response = await fetch("/api/background-jobs/seed", { method: "POST" });
      if (response.ok) {
        setSeeded(true);
        await fetchJobs();
        await fetchMetrics();
        toast.success("Dados de demonstração criados");
      }
    } catch (error) {
      console.error("Erro ao criar dados:", error);
    }
  }, [fetchJobs, fetchMetrics]);

  // Initial load + auto-seed if no jobs
  useEffect(() => {
    const init = async () => {
      await fetchJobs();
      await fetchMetrics();
    };
    init();
  }, [fetchJobs, fetchMetrics]);

  // Auto-seed if no jobs found
  useEffect(() => {
    if (!loading && counts.total === 0 && !seeded) {
      seedData();
    }
  }, [loading, counts.total, seeded, seedData]);

  // Auto-refresh
  useEffect(() => {
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchJobs();
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [fetchJobs, autoRefresh]);

  // Actions
  const handleDelete = async (jobId: string) => {
    try {
      const response = await fetch(`/api/background-jobs/${jobId}`, { method: "DELETE" });
      if (response.ok) {
        toast.success("Job removido");
        fetchJobs();
        fetchMetrics();
      }
    } catch {
      toast.error("Erro ao remover job");
    }
  };

  const handleCancel = async (jobId: string) => {
    try {
      const response = await fetch(`/api/background-jobs/${jobId}/cancel`, { method: "POST" });
      if (response.ok) {
        toast.success("Processo cancelado");
        fetchJobs();
      } else {
        const data = await response.json();
        toast.error(data.error || "Não foi possível cancelar o processo");
      }
    } catch {
      toast.error("Erro ao cancelar processo");
    }
  };

  const handlePause = async (jobId: string) => {
    try {
      const response = await fetch(`/api/background-jobs/${jobId}/pause`, { method: "POST" });
      if (response.ok) {
        toast.success("Processo pausado");
        fetchJobs();
      } else {
        const data = await response.json();
        toast.error(data.error || "Não foi possível pausar o processo");
      }
    } catch {
      toast.error("Erro ao pausar processo");
    }
  };

  const handleResume = async (jobId: string) => {
    try {
      const response = await fetch(`/api/background-jobs/${jobId}/resume`, { method: "POST" });
      if (response.ok) {
        toast.success("Processo retomado");
        fetchJobs();
      } else {
        const data = await response.json();
        toast.error(data.error || "Não foi possível retomar o processo");
      }
    } catch {
      toast.error("Erro ao retomar processo");
    }
  };

  const handleClearFinished = async () => {
    if (!window.confirm("Tem a certeza que deseja limpar todos os jobs terminados?")) return;
    try {
      const response = await fetch("/api/background-jobs", { method: "DELETE" });
      if (response.ok) {
        const data = await response.json();
        toast.success(`${data.deleted || 0} jobs removidos`);
        fetchJobs();
        fetchMetrics();
      }
    } catch {
      toast.error("Erro ao limpar jobs");
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm("⚠️ ATENÇÃO: Isto irá limpar TODOS os jobs, incluindo os que estão a correr!\n\nTem a certeza?")) return;
    try {
      const response = await fetch("/api/background-jobs/clear-all", { method: "POST" });
      if (response.ok) {
        const data = await response.json();
        toast.success(`${data.deleted || 0} jobs removidos`);
        fetchJobs();
        fetchMetrics();
      }
    } catch {
      toast.error("Erro ao limpar todos os jobs");
    }
  };

  const handleViewDetails = (job: BackgroundJob) => {
    setSelectedJob(job);
    setShowDetailDialog(true);
  };

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="border-b bg-card">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <h1 className="text-2xl font-bold flex items-center gap-2">
                <Activity className="h-6 w-6" />
                Centro de Operações
              </h1>
              <p className="text-muted-foreground text-sm mt-1">
                Monitorize importações e processos em tempo real
              </p>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowMetrics(!showMetrics)}
                className={showMetrics ? "bg-blue-50 border-blue-300 dark:bg-blue-900/30" : ""}
              >
                <BarChart3 className="h-4 w-4 mr-2" />
                {showMetrics ? "Ocultar Métricas" : "Métricas"}
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setAutoRefresh(!autoRefresh)}
                className={autoRefresh ? "bg-green-50 border-green-300 dark:bg-green-900/30" : ""}
              >
                {autoRefresh ? (
                  <><RefreshCw className="h-4 w-4 mr-2 animate-spin" /> Auto</>
                ) : (
                  <><RefreshCw className="h-4 w-4 mr-2" /> OFF</>
                )}
              </Button>
              <Button variant="outline" size="sm" onClick={fetchJobs}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Recarregar
              </Button>
              {counts.total - counts.running > 0 && (
                <Button variant="outline" size="sm" onClick={handleClearFinished}>
                  <Trash2 className="h-4 w-4 mr-2" />
                  Limpar Terminados
                </Button>
              )}
              {counts.total > 0 && (
                <Button variant="outline" size="sm" onClick={handleClearAll} className="text-destructive hover:text-destructive">
                  <Zap className="h-4 w-4 mr-2" />
                  Limpar Tudo
                </Button>
              )}
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 max-w-7xl mx-auto px-4 sm:px-6 py-6 w-full space-y-6">
        {/* Metrics Dashboard */}
        {showMetrics && <MetricsDashboard metrics={metrics} />}

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card
            className={`cursor-pointer transition-all ${statusFilter === null ? 'ring-2 ring-primary' : 'hover:shadow-md'}`}
            onClick={() => setStatusFilter(null)}
          >
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{counts.total}</div>
              <p className="text-sm text-muted-foreground">Total</p>
            </CardContent>
          </Card>
          <Card
            className={`cursor-pointer transition-all ${statusFilter === 'running' ? 'ring-2 ring-blue-500' : 'hover:shadow-md'}`}
            onClick={() => setStatusFilter(statusFilter === 'running' ? null : 'running')}
          >
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-blue-600 flex items-center gap-2">
                {counts.running}
                {counts.running > 0 && <Loader2 className="h-5 w-5 animate-spin" />}
              </div>
              <p className="text-sm text-muted-foreground">A correr</p>
            </CardContent>
          </Card>
          <Card
            className={`cursor-pointer transition-all ${statusFilter === 'success' ? 'ring-2 ring-green-500' : 'hover:shadow-md'}`}
            onClick={() => setStatusFilter(statusFilter === 'success' ? null : 'success')}
          >
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-green-600">{counts.success}</div>
              <p className="text-sm text-muted-foreground">Concluídos</p>
            </CardContent>
          </Card>
          <Card
            className={`cursor-pointer transition-all ${statusFilter === 'paused' ? 'ring-2 ring-amber-500' : 'hover:shadow-md'}`}
            onClick={() => setStatusFilter(statusFilter === 'paused' ? null : 'paused')}
          >
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-amber-600 flex items-center gap-2">
                {counts.paused || 0}
                {(counts.paused || 0) > 0 && <Pause className="h-5 w-5" />}
              </div>
              <p className="text-sm text-muted-foreground">Pausados</p>
            </CardContent>
          </Card>
          <Card
            className={`cursor-pointer transition-all ${statusFilter === 'failed,cancelled' ? 'ring-2 ring-red-500' : 'hover:shadow-md'}`}
            onClick={() => setStatusFilter(statusFilter === 'failed,cancelled' ? null : 'failed,cancelled')}
          >
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-red-600">{counts.failed}</div>
              <p className="text-sm text-muted-foreground">Falhados</p>
            </CardContent>
          </Card>
        </div>

        {/* Jobs List */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              {statusFilter ? (
                <>
                  Filtro: {statusFilter === 'failed,cancelled' ? 'Falhados/Cancelados' : (STATUS_CONFIG[statusFilter]?.label || statusFilter)}
                  <Button variant="ghost" size="sm" onClick={() => setStatusFilter(null)}>
                    <XCircle className="h-4 w-4" />
                  </Button>
                </>
              ) : (
                "Todos os Processos"
              )}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : jobs.length === 0 ? (
              <div className="text-center py-12">
                <Activity className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                <h3 className="text-lg font-medium mb-2">Nenhum processo em background</h3>
                <p className="text-muted-foreground mb-4">
                  Quando forem iniciadas importações ou outros processos, aparecerão aqui.
                </p>
                <Button variant="outline" onClick={seedData}>
                  <Database className="h-4 w-4 mr-2" />
                  Criar dados de demonstração
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {jobs.map((job) => (
                  <JobCard
                    key={job.id}
                    job={job}
                    onDelete={handleDelete}
                    onCancel={handleCancel}
                    onPause={handlePause}
                    onResume={handleResume}
                    onViewDetails={handleViewDetails}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </main>

      {/* Footer */}
      <footer className="border-t bg-card mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>PowerCell CRM — Centro de Operações</span>
            <div className="flex items-center gap-4">
              {autoRefresh && (
                <span className="flex items-center gap-1">
                  <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                  Auto-refresh ativo (5s)
                </span>
              )}
              <span>Última atualização: {new Date().toLocaleTimeString("pt-PT")}</span>
            </div>
          </div>
        </div>
      </footer>

      {/* Job Detail Dialog */}
      <JobDetailDialog
        job={selectedJob}
        open={showDetailDialog}
        onOpenChange={setShowDetailDialog}
      />
    </div>
  );
}
