/**
 * BackgroundJobsPage - Centro de Operações
 * Permite visualizar o estado de importações e outros processos a correr
 * Suporta: Cancelar, Pausar e Retomar jobs
 * Inclui: Dashboard de métricas, notificações de jobs stuck, logs detalhados
 */
import React, { useState, useEffect, useCallback, useRef } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Progress } from "../components/ui/progress";
import { ScrollArea } from "../components/ui/scroll-area";
import { toast } from "sonner";
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
  Eye,
  Terminal,
  ChevronRight,
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "../components/ui/sheet";

import { formatDateTime, safeDate } from "../lib/utils";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Mapeamento de tipos de job para ícones
const JOB_TYPE_ICONS = {
  bulk_import: Upload,
  document_analysis: FileText,
  email_sync: Activity,
  aggregated_import: Upload,
  default: Play,
};

// Mapeamento de status para badges
const STATUS_CONFIG = {
  running: { label: "A correr", variant: "default", className: "bg-blue-500", icon: Loader2 },
  processing: { label: "A processar", variant: "default", className: "bg-blue-500", icon: Loader2 },
  paused: { label: "Pausado", variant: "default", className: "bg-amber-500", icon: Clock },
  success: { label: "Concluído", variant: "default", className: "bg-green-500", icon: CheckCircle },
  completed: { label: "Concluído", variant: "default", className: "bg-green-500", icon: CheckCircle },
  failed: { label: "Falhado", variant: "destructive", icon: XCircle },
  cancelled: { label: "Cancelado", variant: "secondary", className: "bg-gray-500", icon: XCircle },
  pending: { label: "Pendente", variant: "secondary", icon: Clock },
};

// ── Helper: Formatar duração ──────────────────────────────
function formatDuration(isoStart, isoEnd) {
  if (!isoStart) return "—";
  const start = safeDate(isoStart);
  if (!start) return "—";
  const end = isoEnd ? (safeDate(isoEnd) || new Date()) : new Date();
  const diffMs = end - start;
  if (diffMs < 0) return "0s";
  const totalSecs = Math.floor(diffMs / 1000);
  const hrs = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  const secs = totalSecs % 60;
  if (hrs > 0) return `${String(hrs).padStart(2, "0")}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  return `${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

// ── Componente: Contador de tempo decorrido (live) ────────
const ElapsedTimer = ({ startedAt, finishedAt }) => {
  const [elapsed, setElapsed] = useState(() => formatDuration(startedAt, finishedAt));

  useEffect(() => {
    if (!startedAt || finishedAt) {
      setElapsed(formatDuration(startedAt, finishedAt));
      return;
    }
    // Actualizar a cada segundo enquanto o job está a correr
    const interval = setInterval(() => {
      setElapsed(formatDuration(startedAt, null));
    }, 1000);
    return () => clearInterval(interval);
  }, [startedAt, finishedAt]);

  return (
    <span className="flex items-center gap-1">
      <Timer className="h-3.5 w-3.5" />
      {elapsed}
    </span>
  );
};

// ════════════════════════════════════════════════════════════
// Componente de Job Individual (Card Expandido)
// ════════════════════════════════════════════════════════════
const JobCard = ({ job, onDelete, onCancel, onPause, onResume, onViewDetails }) => {
  const Icon = JOB_TYPE_ICONS[job.job_type] || JOB_TYPE_ICONS[job.type] || JOB_TYPE_ICONS.default;
  const statusConfig = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
  const StatusIcon = statusConfig.icon;
  const [actionLoading, setActionLoading] = useState(false);

  const formatDate = (isoString) => {
    if (!isoString) return "-";
    return formatDateTime(isoString);
  };

  const isRunning = job.status === "running" || job.status === "processing";
  const isPaused = job.status === "paused";
  const isActive = isRunning || isPaused;
  const isCompleted = job.status === "success" || job.status === "completed";

  // Cor da barra de progresso baseada no estado
  const progressColor = isRunning
    ? "bg-blue-500"
    : isPaused
    ? "bg-amber-500"
    : isCompleted
    ? "bg-green-500"
    : "bg-red-500";

  return (
    <Card className={`transition-all ${isRunning ? 'border-blue-300 shadow-md dark:border-blue-700' : isPaused ? 'border-amber-300 dark:border-amber-700' : isCompleted ? 'border-green-200 dark:border-green-800' : ''}`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          {/* Ícone e Info Principal */}
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <div className={`p-2.5 rounded-lg shrink-0 ${
              isRunning ? 'bg-blue-100 dark:bg-blue-900/30' :
              isCompleted ? 'bg-green-100 dark:bg-green-900/30' :
              job.status === 'failed' ? 'bg-red-100 dark:bg-red-900/30' :
              isPaused ? 'bg-amber-100 dark:bg-amber-900/30' :
              'bg-gray-100 dark:bg-gray-800'
            }`}>
              <Icon className={`h-5 w-5 ${
                isRunning ? 'text-blue-600' :
                isCompleted ? 'text-green-600' :
                job.status === 'failed' ? 'text-red-600' :
                isPaused ? 'text-amber-600' :
                'text-gray-600'
              }`} />
            </div>
            
            <div className="flex-1 min-w-0">
              {/* Header: tipo + status badge */}
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-medium text-sm">
                  {['bulk_import', 'excel_import'].includes(job.type) ? 'Importação Massiva' :
                   job.type === 'document_analysis' ? 'Análise de Documentos' :
                   job.type === 'email_sync' ? 'Sincronização de Email' :
                   ['aggregated_import', 'async_import', 'sync_import'].includes(job.type) ? 'Importação Agregada' :
                   job.type === 'bulk_analysis' ? 'Análise em Massa' :
                   job.type === 'data_export' ? 'Exportação de Dados' :
                   job.type === 'pdf_gen' ? 'Geração de PDF' :
                   job.type}
                </h4>
                <Badge 
                  variant={statusConfig.variant}
                  className={`text-xs ${statusConfig.className || ''}`}
                >
                  <StatusIcon className={`h-3 w-3 mr-1 ${isRunning ? 'animate-spin' : ''}`} />
                  {statusConfig.label}
                </Badge>
              </div>
              
              {/* Meta info: início + tempo decorrido */}
              <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                <span>Início: {formatDate(job.started_at || job.created_at)}</span>
                <ElapsedTimer startedAt={job.started_at || job.created_at} finishedAt={job.finished_at || job.completed_at} />
                {(job.finished_at || job.completed_at) && <span>Fim: {formatDate(job.finished_at || job.completed_at)}</span>}
              </div>

              {/* ══ PROGRESS BAR ══ */}
              {(() => {
                // Compatibilidade: progress pode ser número ou objecto
                const progressVal = typeof job.progress === 'object' && job.progress !== null
                  ? (job.progress.percentage ?? 0)
                  : (job.progress ?? 0);
                const progressMsg = typeof job.progress === 'object' && job.progress !== null
                  ? job.progress.message : null;
                const totalItems = typeof job.progress === 'object' && job.progress !== null
                  ? (job.progress.total ?? 0) : (job.total ?? 0);
                const processedItems = typeof job.progress === 'object' && job.progress !== null
                  ? (job.progress.current ?? 0) : (job.processed ?? 0);
                const showProgress = totalItems > 0 || progressVal > 0;
                if (!showProgress) return null;
                return (
                  <div className="mt-3">
                    <div className="flex items-center justify-between text-xs mb-1.5">
                      <span className="text-muted-foreground">
                        {processedItems} de {totalItems || "?"} processados
                      </span>
                      <span className="font-semibold">{progressVal}%</span>
                    </div>
                    <div className="relative">
                      <Progress 
                        value={progressVal} 
                        className={`h-2.5 ${isRunning ? 'animate-pulse' : ''}`} 
                      />
                    </div>
                    {progressMsg && <p className="text-xs text-muted-foreground mt-1">{progressMsg}</p>}
                  </div>
                );
              })()}

              {/* ══ CURRENT STEP — itálico abaixo da barra ══ */}
              {(job.current_step || (typeof job.progress === 'object' && job.progress?.message)) && isActive && (
                <div className="mt-2 flex items-start gap-1.5">
                  <ChevronRight className={`h-3.5 w-3.5 mt-0.5 shrink-0 ${isRunning ? 'text-blue-500' : 'text-amber-500'}`} />
                  <p className="text-xs italic text-muted-foreground leading-relaxed">
                    {job.current_step || job.progress?.message}
                  </p>
                </div>
              )}

              {/* Erros */}
              {job.errors > 0 && (
                <div className="flex items-center gap-1 mt-2 text-xs text-amber-600">
                  <AlertTriangle className="h-3 w-3" />
                  {job.errors} erro(s) durante processamento
                </div>
              )}
              
              {/* Mensagem de erro/sucesso */}
              {job.message && !isActive && (
                <p className={`mt-2 text-xs ${
                  job.status === 'failed' ? 'text-red-600' : 'text-muted-foreground'
                }`}>
                  {job.message}
                </p>
              )}

              {/* Error log (para jobs falhados) */}
              {job.error_log && job.status === 'failed' && (
                <div className="mt-2 p-2 bg-red-50 dark:bg-red-950/30 rounded text-xs text-red-700 dark:text-red-400 font-mono break-all">
                  {job.error_log}
                </div>
              )}
              
              {/* Detalhes adicionais */}
              {job.details && Object.keys(job.details).length > 0 && (
                <div className="mt-2 text-xs text-muted-foreground">
                  {job.details.folder && <span>Pasta: {job.details.folder}</span>}
                  {job.details.source && <span className="ml-2">Fonte: {job.details.source}</span>}
                </div>
              )}
            </div>
          </div>
          
          {/* Acções */}
          <div className="flex items-center gap-2 shrink-0">
            {isRunning && (
              <>
                <Button 
                  variant="outline" 
                  size="sm"
                  className="text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                  onClick={async () => {
                    setActionLoading(true);
                    await onPause(job.id);
                    setActionLoading(false);
                  }}
                  disabled={actionLoading}
                >
                  {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Pause className="h-4 w-4 mr-1" />Pausar</>}
                </Button>
                <Button 
                  variant="outline" 
                  size="sm"
                  className="text-amber-600 hover:text-amber-700 hover:bg-amber-50"
                  onClick={async () => {
                    setActionLoading(true);
                    await onCancel(job.id);
                    setActionLoading(false);
                  }}
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
                  onClick={async () => {
                    setActionLoading(true);
                    await onResume(job.id);
                    setActionLoading(false);
                  }}
                  disabled={actionLoading}
                >
                  {actionLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <><Play className="h-4 w-4 mr-1" />Retomar</>}
                </Button>
                <Button 
                  variant="outline" 
                  size="sm"
                  className="text-amber-600 hover:text-amber-700 hover:bg-amber-50"
                  onClick={async () => {
                    setActionLoading(true);
                    await onCancel(job.id);
                    setActionLoading(false);
                  }}
                  disabled={actionLoading}
                >
                  <XCircle className="h-4 w-4 mr-1" />
                  Cancelar
                </Button>
              </>
            )}
            
            {/* Botão de ver detalhes (logs) */}
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
};

// ════════════════════════════════════════════════════════════
// Componente: Painel de Logs (Mini-Terminal)
// ════════════════════════════════════════════════════════════
const JobLogSheet = ({ job, open, onOpenChange }) => {
  if (!job) return null;

  const stepLog = job.step_log || [];
  const formatDate = (isoString) => {
    if (!isoString) return "";
    const date = safeDate(isoString);
    if (!date) return "";
    return date.toLocaleString("pt-PT", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      fractionalSecondDigits: 1,
    });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[480px] sm:max-w-[540px] sm:w-[540px] p-0 flex flex-col">
        <SheetHeader className="p-6 pb-4 border-b">
          <SheetTitle className="flex items-center gap-2">
            <Terminal className="h-5 w-5 text-green-500" />
            Logs do Processo
          </SheetTitle>
          <SheetDescription>
            {['bulk_import', 'excel_import'].includes(job.type) ? 'Importação Massiva' :
             job.type === 'document_analysis' ? 'Análise de Documentos' :
             job.type === 'email_sync' ? 'Sincronização de Email' :
             ['aggregated_import', 'async_import', 'sync_import'].includes(job.type) ? 'Importação Agregada' :
             job.type === 'bulk_analysis' ? 'Análise em Massa' :
             job.type === 'data_export' ? 'Exportação de Dados' :
             job.type === 'pdf_gen' ? 'Geração de PDF' :
             job.type} — {job.id?.slice(0, 8)}...
          </SheetDescription>
        </SheetHeader>

        {/* Job summary */}
        <div className="px-6 py-3 border-b bg-muted/30">
          <div className="flex items-center gap-3 text-sm">
            <Badge className={STATUS_CONFIG[job.status]?.className || ""}>
              {STATUS_CONFIG[job.status]?.label || job.status}
            </Badge>
            {(() => {
              const progressVal = typeof job.progress === 'object' && job.progress !== null
                ? (job.progress.percentage ?? 0) : (job.progress ?? 0);
              const totalItems = typeof job.progress === 'object' && job.progress !== null
                ? (job.progress.total ?? 0) : (job.total ?? 0);
              const processedItems = typeof job.progress === 'object' && job.progress !== null
                ? (job.progress.current ?? 0) : (job.processed ?? 0);
              return totalItems > 0 ? (
                <span className="text-muted-foreground">
                  {processedItems}/{totalItems} processados ({progressVal}%)
                </span>
              ) : null;
            })()}
            {(job.started_at || job.created_at) && (
              <span className="text-muted-foreground">
                <Timer className="h-3 w-3 inline mr-1" />
                {formatDuration(job.started_at || job.created_at, job.finished_at || job.completed_at)}
              </span>
            )}
          </div>
          {(job.current_step || (typeof job.progress === 'object' && job.progress?.message)) && (
            <p className="text-xs italic text-muted-foreground mt-1.5">
              → {job.current_step || job.progress?.message}
            </p>
          )}
        </div>

        {/* Terminal-style log */}
        <div className="flex-1 overflow-hidden">
          <ScrollArea className="h-full">
            <div className="p-4">
              <div className="bg-gray-950 dark:bg-gray-900 rounded-lg border border-gray-800 font-mono text-xs overflow-hidden">
                {/* Terminal header */}
                <div className="flex items-center gap-1.5 px-3 py-2 border-b border-gray-800 bg-gray-900 dark:bg-gray-800">
                  <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
                  <div className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
                  <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
                  <span className="ml-2 text-gray-400 text-[10px]">job-{job.id?.slice(0, 8)}.log</span>
                </div>
                
                {/* Terminal body */}
                <div className="p-3 space-y-1.5 max-h-[50vh] overflow-y-auto">
                  {stepLog.length > 0 ? stepLog.map((entry, idx) => {
                    const isLast = idx === stepLog.length - 1;
                    const isFailed = entry.step === "Falhado";
                    const isSuccess = entry.step === "Concluído";
                    return (
                      <div key={idx} className={`flex gap-2 ${isLast ? "opacity-100" : "opacity-70"}`}>
                        <span className="text-gray-500 shrink-0 select-none">
                          {formatDate(entry.ts)}
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
                  
                  {/* Mensagem de erro no final */}
                  {job.error_log && (
                    <div className="mt-2 pt-2 border-t border-gray-700">
                      <span className="text-red-400">✗ ERRO: {job.error_log}</span>
                    </div>
                  )}
                  {job.message && job.status === 'failed' && !job.error_log && (
                    <div className="mt-2 pt-2 border-t border-gray-700">
                      <span className="text-red-400">✗ ERRO: {job.message}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Error messages list */}
              {job.error_messages && job.error_messages.length > 0 && (
                <div className="mt-4">
                  <h4 className="text-xs font-semibold text-muted-foreground mb-2">
                    Mensagens de Erro ({job.error_messages.length})
                  </h4>
                  <div className="bg-red-50 dark:bg-red-950/20 rounded-lg border border-red-200 dark:border-red-800 p-3 space-y-1">
                    {job.error_messages.slice(0, 20).map((msg, idx) => (
                      <p key={idx} className="text-xs text-red-700 dark:text-red-400 font-mono break-all">
                        {msg}
                      </p>
                    ))}
                    {job.error_messages.length > 20 && (
                      <p className="text-xs text-muted-foreground italic">
                        ...e mais {job.error_messages.length - 20} mensagens
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
        </div>
      </SheetContent>
    </Sheet>
  );
};

// ════════════════════════════════════════════════════════════
// Componente Principal
// ════════════════════════════════════════════════════════════
const BackgroundJobsPage = ({ embedded = false }) => {
  const wrapLayout = (children) => embedded ? children : <DashboardLayout>{children}</DashboardLayout>;
  const [jobs, setJobs] = useState([]);
  const [counts, setCounts] = useState({ running: 0, success: 0, failed: 0, paused: 0, total: 0 });
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [stuckNotifications, setStuckNotifications] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [showMetrics, setShowMetrics] = useState(false);
  const [selectedJob, setSelectedJob] = useState(null);
  const [showLogSheet, setShowLogSheet] = useState(false);

  const fetchJobs = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const url = statusFilter 
        ? `${API_URL}/api/ai/bulk/background-jobs?status=${statusFilter}`
        : `${API_URL}/api/ai/bulk/background-jobs`;
      
      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
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

  const fetchNotifications = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs/notifications?unread_only=true`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setStuckNotifications(data.notifications || []);
      }
    } catch (error) {
      console.error("Erro ao carregar notificações:", error);
    }
  }, []);

  const fetchMetrics = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs/metrics?days=7`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setMetrics(data);
      }
    } catch (error) {
      console.error("Erro ao carregar métricas:", error);
    }
  }, []);

  const handleClearNotifications = async () => {
    try {
      const token = localStorage.getItem("token");
      await fetch(`${API_URL}/api/ai/bulk/background-jobs/notifications/clear`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      setStuckNotifications([]);
      toast.success("Notificações limpas");
    } catch (error) {
      toast.error("Erro ao limpar notificações");
    }
  };

  useEffect(() => {
    fetchJobs();
    fetchNotifications();
    fetchMetrics();
    
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchJobs();
        fetchNotifications();
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [fetchJobs, fetchNotifications, fetchMetrics, autoRefresh]);

  const handleDelete = async (jobId) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs/${jobId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        toast.success("Job removido");
        fetchJobs();
      }
    } catch (error) {
      toast.error("Erro ao remover job");
    }
  };

  const handleCancel = async (jobId) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs/${jobId}/cancel`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        toast.success("Processo cancelado");
        fetchJobs();
      } else {
        toast.error("Não foi possível cancelar o processo");
      }
    } catch (error) {
      toast.error("Erro ao cancelar processo");
    }
  };

  const handlePause = async (jobId) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs/${jobId}/pause`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        toast.success("Processo pausado");
        fetchJobs();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Não foi possível pausar o processo");
      }
    } catch (error) {
      toast.error("Erro ao pausar processo");
    }
  };

  const handleResume = async (jobId) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs/${jobId}/resume`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        toast.success("Processo retomado");
        fetchJobs();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Não foi possível retomar o processo");
      }
    } catch (error) {
      toast.error("Erro ao retomar processo");
    }
  };

  const handleClearAll = async () => {
    if (!window.confirm("Tem a certeza que deseja limpar todos os jobs terminados?")) return;
    
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        toast.success(`${data.deleted || 0} jobs removidos`);
        fetchJobs();
      }
    } catch (error) {
      toast.error("Erro ao limpar jobs");
    }
  };

  const handleCleanupStuck = async () => {
    const hours = window.prompt("Limpar jobs sem actividade há quantas horas?", "2");
    if (!hours) return;
    
    const hoursNum = parseInt(hours);
    if (isNaN(hoursNum) || hoursNum < 1) {
      toast.error("Por favor introduza um número válido de horas");
      return;
    }
    
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs/cleanup-stuck?hours=${hoursNum}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.cleaned > 0) {
          toast.success(`${data.cleaned} jobs bloqueados foram limpos`);
        } else {
          toast.info("Nenhum job bloqueado encontrado");
        }
        fetchJobs();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao limpar jobs bloqueados");
      }
    } catch (error) {
      toast.error("Erro ao limpar jobs bloqueados");
    }
  };

  const handleClearAllJobs = async () => {
    if (!window.confirm("⚠️ ATENÇÃO: Isto irá limpar TODOS os jobs, incluindo os que estão a correr!\n\nTem a certeza?")) return;
    
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs/clear-all`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        toast.success(`${(data.deleted_db || 0) + (data.deleted_memory || 0)} jobs removidos`);
        fetchJobs();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao limpar todos os jobs");
      }
    } catch (error) {
      toast.error("Erro ao limpar todos os jobs");
    }
  };

  const handleViewDetails = (job) => {
    setSelectedJob(job);
    setShowLogSheet(true);
  };

  return wrapLayout(
      <div className="space-y-6">
        {/* Alerta de Jobs Stuck */}
        {stuckNotifications.length > 0 && (
          <div className="bg-amber-50 dark:bg-amber-950/50 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
            <div className="flex items-start justify-between">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5" />
                <div>
                  <h3 className="font-medium text-amber-800 dark:text-amber-300">
                    {stuckNotifications.length} {stuckNotifications.length === 1 ? 'Job bloqueado detectado' : 'Jobs bloqueados detectados'}
                  </h3>
                  <p className="text-sm text-amber-700 dark:text-amber-400 mt-1">
                    {stuckNotifications.length === 1 
                      ? stuckNotifications[0].message
                      : `${stuckNotifications.length} jobs foram marcados como falhados automaticamente por estarem sem actividade.`
                    }
                  </p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClearNotifications}
                className="text-amber-700 hover:text-amber-900 dark:text-amber-400"
              >
                <XCircle className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Activity className="h-6 w-6" />
              Centro de Operações
            </h1>
            <p className="text-muted-foreground">
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
            {counts.running > 0 && (
              <Button 
                variant="outline" 
                size="sm"
                onClick={handleCleanupStuck}
                className="border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-600 dark:text-amber-400"
                title="Limpar jobs bloqueados há muito tempo"
              >
                <Zap className="h-4 w-4 mr-2" />
                Limpar Bloqueados
              </Button>
            )}
            {counts.total - counts.running > 0 && (
              <Button variant="outline" size="sm" onClick={handleClearAll}>
                <Trash2 className="h-4 w-4 mr-2" />
                Limpar Terminados
              </Button>
            )}
          </div>
        </div>

        {/* Dashboard de Métricas */}
        {showMetrics && metrics && (
          <Card className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30 border-blue-200 dark:border-blue-800">
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
                    {metrics.avg_duration_formatted || '-'}
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
                        <span className="text-sm capitalize">{STATUS_CONFIG[status]?.label || status}</span>
                        <Badge variant={status === 'success' ? 'default' : status === 'failed' ? 'destructive' : 'secondary'}>
                          {count}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
                  <h4 className="font-medium mb-3">Por Tipo</h4>
                  <div className="space-y-2">
                    {Object.entries(metrics.by_type || {}).map(([type, count]) => (
                      <div key={type} className="flex items-center justify-between text-sm">
                        <span className="capitalize">{type.replace(/_/g, ' ')}</span>
                        <Badge variant="outline">{count}</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

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
            className={`cursor-pointer transition-all ${statusFilter === 'failed' ? 'ring-2 ring-red-500' : 'hover:shadow-md'}`}
            onClick={() => setStatusFilter(statusFilter === 'failed' ? null : 'failed')}
          >
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-red-600">{counts.failed}</div>
              <p className="text-sm text-muted-foreground">Falhados</p>
            </CardContent>
          </Card>
        </div>

        {/* Lista de Jobs */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              {statusFilter ? (
                <>
                  Filtro: {STATUS_CONFIG[statusFilter]?.label}
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
                <p className="text-muted-foreground">
                  Os processos de importação e análise aparecerão aqui.
                </p>
              </div>
            ) : (
              <ScrollArea className="h-[300px] sm:h-[500px] pr-2">
                <div className="space-y-3">
                  {jobs.map(job => (
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
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        {/* Sheet de Logs (Mini-Terminal) */}
        <JobLogSheet 
          job={selectedJob}
          open={showLogSheet}
          onOpenChange={setShowLogSheet}
        />
      </div>
  );
};

export default BackgroundJobsPage;
