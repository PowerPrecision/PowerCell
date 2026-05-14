/**
 * BackgroundJobsPage - Página de Processos em Background
 * Permite visualizar o estado de importações e outros processos a correr
 * Suporta: Cancelar, Pausar e Retomar jobs
 * Inclui: Dashboard de métricas e notificações de jobs stuck
 */
import React, { useState, useEffect, useCallback } from "react";
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
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";

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
  paused: { label: "Pausado", variant: "default", className: "bg-amber-500", icon: Clock },
  success: { label: "Concluído", variant: "default", className: "bg-green-500", icon: CheckCircle },
  failed: { label: "Falhado", variant: "destructive", icon: XCircle },
  cancelled: { label: "Cancelado", variant: "secondary", className: "bg-gray-500", icon: XCircle },
  pending: { label: "Pendente", variant: "secondary", icon: Clock },
};

// Componente de Job Individual
const JobCard = ({ job, onDelete, onCancel, onPause, onResume, onViewDetails }) => {
  const Icon = JOB_TYPE_ICONS[job.job_type] || JOB_TYPE_ICONS[job.type] || JOB_TYPE_ICONS.default;
  const statusConfig = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
  const StatusIcon = statusConfig.icon;
  const [actionLoading, setActionLoading] = useState(false);
  
  const formatDate = (isoString) => {
    if (!isoString) return "-";
    const date = new Date(isoString);
    return date.toLocaleString("pt-PT", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit"
    });
  };

  const getDuration = () => {
    if (!job.started_at) return "-";
    const start = new Date(job.started_at);
    const end = job.finished_at ? new Date(job.finished_at) : new Date();
    const diffMs = end - start;
    const diffSecs = Math.floor(diffMs / 1000);
    
    if (diffSecs < 60) return `${diffSecs}s`;
    const diffMins = Math.floor(diffSecs / 60);
    if (diffMins < 60) return `${diffMins}m ${diffSecs % 60}s`;
    const diffHours = Math.floor(diffMins / 60);
    return `${diffHours}h ${diffMins % 60}m`;
  };

  return (
    <Card className={`transition-all ${job.status === 'running' ? 'border-blue-300 shadow-md' : ''}`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-4">
          {/* Ícone e Info Principal */}
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <div className={`p-2.5 rounded-lg shrink-0 ${
              job.status === 'running' ? 'bg-blue-100 dark:bg-blue-900/30' :
              job.status === 'success' ? 'bg-green-100 dark:bg-green-900/30' :
              job.status === 'failed' ? 'bg-red-100 dark:bg-red-900/30' :
              'bg-gray-100 dark:bg-gray-800'
            }`}>
              <Icon className={`h-5 w-5 ${
                job.status === 'running' ? 'text-blue-600' :
                job.status === 'success' ? 'text-green-600' :
                job.status === 'failed' ? 'text-red-600' :
                'text-gray-600'
              }`} />
            </div>
            
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h4 className="font-medium text-sm">
                  {job.type === 'bulk_import' ? 'Importação Massiva' :
                   job.type === 'document_analysis' ? 'Análise de Documentos' :
                   job.type === 'email_sync' ? 'Sincronização de Email' :
                   job.type}
                </h4>
                <Badge 
                  variant={statusConfig.variant}
                  className={`text-xs ${statusConfig.className || ''}`}
                >
                  <StatusIcon className={`h-3 w-3 mr-1 ${job.status === 'running' ? 'animate-spin' : ''}`} />
                  {statusConfig.label}
                </Badge>
              </div>
              
              {/* Detalhes */}
              <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                <span>Início: {formatDate(job.started_at)}</span>
                {job.finished_at && <span>Fim: {formatDate(job.finished_at)}</span>}
                <span>Duração: {getDuration()}</span>
              </div>
              
              {/* Progresso */}
              {job.status === 'running' && job.total > 0 && (
                <div className="mt-3">
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span>{job.processed} de {job.total} processados</span>
                    <span>{job.progress}%</span>
                  </div>
                  <Progress value={job.progress} className="h-2" />
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
              {job.message && (
                <p className={`mt-2 text-xs ${
                  job.status === 'failed' ? 'text-red-600' : 'text-muted-foreground'
                }`}>
                  {job.message}
                </p>
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
            {/* Botões para jobs em execução */}
            {job.status === 'running' && (
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
                  {actionLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <Pause className="h-4 w-4 mr-1" />
                      Pausar
                    </>
                  )}
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
                  {actionLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <XCircle className="h-4 w-4 mr-1" />
                      Cancelar
                    </>
                  )}
                </Button>
              </>
            )}
            
            {/* Botão para retomar jobs pausados */}
            {job.status === 'paused' && (
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
                  {actionLoading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <Play className="h-4 w-4 mr-1" />
                      Retomar
                    </>
                  )}
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
            
            {/* Botão de ver detalhes */}
            <Button 
              variant="ghost" 
              size="sm"
              className="text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/30"
              onClick={() => onViewDetails(job)}
              title="Ver detalhes"
            >
              <Eye className="h-4 w-4" />
            </Button>
            
            {/* Botão de eliminar para jobs terminados */}
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
  const [showJobDetails, setShowJobDetails] = useState(false);

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

  // Buscar notificações de jobs stuck
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

  // Buscar métricas
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

  // Limpar notificações
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

  // Fetch inicial e auto-refresh
  useEffect(() => {
    fetchJobs();
    fetchNotifications();
    fetchMetrics();
    
    if (autoRefresh) {
      const interval = setInterval(() => {
        fetchJobs();
        fetchNotifications();
      }, 5000); // Refresh a cada 5 segundos
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
    if (!window.confirm("Tem a certeza que deseja limpar todos os jobs terminados?")) {
      return;
    }
    
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        fetchJobs();
      }
    } catch (error) {
      toast.error("Erro ao limpar jobs");
    }
  };

  // Limpar jobs stuck (bloqueados há muito tempo)
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
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs/cleanup-stuck?max_age_hours=${hoursNum}`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        if (data.stuck_jobs_found > 0) {
          toast.success(`${data.jobs_cleaned} jobs bloqueados foram limpos`);
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

  // Limpar TODOS os jobs (incluindo em execução)
  const handleClearAllJobs = async () => {
    if (!window.confirm("⚠️ ATENÇÃO: Isto irá limpar TODOS os jobs, incluindo os que estão a correr!\n\nTem a certeza?")) {
      return;
    }
    
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/ai/bulk/background-jobs/clear-all`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        fetchJobs();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao limpar todos os jobs");
      }
    } catch (error) {
      toast.error("Erro ao limpar todos os jobs");
    }
  };

  // Ver detalhes do job
  const handleViewDetails = (job) => {
    setSelectedJob(job);
    setShowJobDetails(true);
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
              Processos em Background
            </h1>
            <p className="text-muted-foreground">
              Monitorize importações e outros processos a correr no sistema
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
              {showMetrics ? "Ocultar Métricas" : "Ver Métricas"}
            </Button>
            <Button 
              variant="outline" 
              size="sm"
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={autoRefresh ? "bg-green-50 border-green-300 dark:bg-green-900/30" : ""}
            >
              {autoRefresh ? (
                <><RefreshCw className="h-4 w-4 mr-2 animate-spin" /> Auto-refresh</>
              ) : (
                <><RefreshCw className="h-4 w-4 mr-2" /> Auto-refresh OFF</>
              )}
            </Button>
            <Button variant="outline" onClick={fetchJobs}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Recarregar
            </Button>
            {counts.running > 0 && (
              <Button 
                variant="outline" 
                onClick={handleCleanupStuck}
                className="border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-600 dark:text-amber-400 dark:hover:bg-amber-900/30"
                title="Limpar jobs bloqueados há muito tempo"
              >
                <Zap className="h-4 w-4 mr-2" />
                Limpar Bloqueados
              </Button>
            )}
            {counts.total - counts.running > 0 && (
              <Button variant="outline" onClick={handleClearAll}>
                <Trash2 className="h-4 w-4 mr-2" />
                Limpar Terminados
              </Button>
            )}
            {counts.total > 0 && (
              <Button 
                variant="outline" 
                onClick={handleClearAllJobs}
                className="border-red-300 text-red-700 hover:bg-red-50 dark:border-red-600 dark:text-red-400 dark:hover:bg-red-900/30"
                title="Limpar TODOS os jobs (incluindo em execução)"
              >
                <Ban className="h-4 w-4 mr-2" />
                Limpar Tudo
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
                Dashboard de Métricas (últimos {metrics.period_days} dias)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                {/* Taxa de Sucesso */}
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
                
                {/* Tempo Médio */}
                <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                    <Timer className="h-4 w-4" />
                    Tempo Médio
                  </div>
                  <div className="text-2xl font-bold text-blue-600">
                    {metrics.avg_duration_formatted || '-'}
                  </div>
                </div>
                
                {/* Total de Jobs */}
                <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                    <Activity className="h-4 w-4" />
                    Total de Jobs
                  </div>
                  <div className="text-2xl font-bold">
                    {metrics.total_jobs}
                  </div>
                </div>
                
                {/* Jobs Stuck */}
                <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                    <AlertTriangle className="h-4 w-4" />
                    Jobs Stuck
                  </div>
                  <div className={`text-2xl font-bold ${metrics.stuck_count > 0 ? 'text-amber-600' : 'text-green-600'}`}>
                    {metrics.stuck_count} ({metrics.stuck_percentage}%)
                  </div>
                </div>
              </div>
              
              {/* Por Status */}
              <div className="grid md:grid-cols-2 gap-4">
                <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
                  <h4 className="font-medium mb-3">Por Status</h4>
                  <div className="space-y-2">
                    {Object.entries(metrics.by_status || {}).map(([status, count]) => (
                      <div key={status} className="flex items-center justify-between">
                        <span className="text-sm capitalize">{status}</span>
                        <Badge variant={status === 'success' || status === 'completed' ? 'default' : status === 'failed' ? 'destructive' : 'secondary'}>
                          {count}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>
                
                {/* Jobs Mais Lentos */}
                <div className="bg-white dark:bg-gray-900 rounded-lg p-4 border">
                  <h4 className="font-medium mb-3">Jobs Mais Lentos</h4>
                  <div className="space-y-2">
                    {(metrics.slowest_jobs || []).slice(0, 5).map((job, idx) => (
                      <div key={idx} className="flex items-center justify-between text-sm">
                        <span className="truncate max-w-[180px]" title={job.name}>{job.name || job.id?.slice(0,8)}</span>
                        <span className="text-muted-foreground">{job.duration_formatted}</span>
                      </div>
                    ))}
                    {(!metrics.slowest_jobs || metrics.slowest_jobs.length === 0) && (
                      <p className="text-sm text-muted-foreground">Sem dados</p>
                    )}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Stats */}
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

        {/* Modal de Detalhes do Job */}
        <Dialog open={showJobDetails} onOpenChange={setShowJobDetails}>
          <DialogContent className="max-w-2xl max-h-[80vh]">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Detalhes do Processo
              </DialogTitle>
              <DialogDescription className="sr-only">
                Informações detalhadas do processo em background.
              </DialogDescription>
            </DialogHeader>
            {selectedJob && (
              <ScrollArea className="max-h-[60vh] pr-4">
                <div className="space-y-4">
                  {/* Info básica */}
                  <div className="grid grid-cols-2 gap-4">
                    <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                      <p className="text-xs text-muted-foreground">ID</p>
                      <p className="font-mono text-sm break-all">{selectedJob.id}</p>
                    </div>
                    <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                      <p className="text-xs text-muted-foreground">Tipo</p>
                      <p className="text-sm">{selectedJob.job_type || selectedJob.type || 'N/A'}</p>
                    </div>
                    <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                      <p className="text-xs text-muted-foreground">Status</p>
                      <Badge className={STATUS_CONFIG[selectedJob.status]?.className}>
                        {STATUS_CONFIG[selectedJob.status]?.label || selectedJob.status}
                      </Badge>
                    </div>
                    <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                      <p className="text-xs text-muted-foreground">Progresso</p>
                      <p className="text-sm">{selectedJob.processed_files || 0} / {selectedJob.total_files || '?'}</p>
                    </div>
                  </div>

                  {/* Timestamps */}
                  <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                    <p className="text-xs text-muted-foreground mb-2">Timestamps</p>
                    <div className="space-y-1 text-sm">
                      {selectedJob.created_at && (
                        <p><span className="text-muted-foreground">Criado:</span> {new Date(selectedJob.created_at).toLocaleString('pt-PT')}</p>
                      )}
                      {selectedJob.started_at && (
                        <p><span className="text-muted-foreground">Iniciado:</span> {new Date(selectedJob.started_at).toLocaleString('pt-PT')}</p>
                      )}
                      {selectedJob.updated_at && (
                        <p><span className="text-muted-foreground">Actualizado:</span> {new Date(selectedJob.updated_at).toLocaleString('pt-PT')}</p>
                      )}
                      {selectedJob.finished_at && (
                        <p><span className="text-muted-foreground">Terminado:</span> {new Date(selectedJob.finished_at).toLocaleString('pt-PT')}</p>
                      )}
                    </div>
                  </div>

                  {/* Mensagem/Erro */}
                  {(selectedJob.message || selectedJob.error) && (
                    <div className={`p-3 rounded-lg ${selectedJob.error ? 'bg-red-50 dark:bg-red-950/50 border border-red-200 dark:border-red-800' : 'bg-gray-50 dark:bg-gray-800'}`}>
                      <p className="text-xs text-muted-foreground mb-1">{selectedJob.error ? 'Erro' : 'Mensagem'}</p>
                      <p className={`text-sm ${selectedJob.error ? 'text-red-600 dark:text-red-400' : ''}`}>
                        {selectedJob.error || selectedJob.message}
                      </p>
                    </div>
                  )}

                  {/* Detalhes */}
                  {selectedJob.details && Object.keys(selectedJob.details).length > 0 && (
                    <div className="p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                      <p className="text-xs text-muted-foreground mb-2">Detalhes</p>
                      <pre className="text-xs bg-white dark:bg-gray-900 p-2 rounded overflow-x-auto">
                        {JSON.stringify(selectedJob.details, null, 2)}
                      </pre>
                    </div>
                  )}

                  {/* Stats de erros */}
                  {selectedJob.errors > 0 && (
                    <div className="p-3 bg-amber-50 dark:bg-amber-950/50 rounded-lg border border-amber-200 dark:border-amber-800">
                      <p className="text-xs text-amber-700 dark:text-amber-400">
                        <AlertTriangle className="h-3 w-3 inline mr-1" />
                        {selectedJob.errors} erro(s) durante o processamento
                      </p>
                    </div>
                  )}
                </div>
              </ScrollArea>
            )}
          </DialogContent>
        </Dialog>
      </div>
  );
};

export default BackgroundJobsPage;
