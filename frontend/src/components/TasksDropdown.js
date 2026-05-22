/**
 * TasksDropdown — Dropdown de tarefas pendentes associadas ao utilizador actual.
 *
 * PORQUÊ: Cada utilizador do CRM tem tarefas atribuídas (validar documentos, contactar cliente, etc.).
 * Este dropdown no header permite acesso rápido às tarefas pendentes sem navegar para outra página.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import React, { useState } from "react";
import { useTasks, TaskStatus, TaskTypeLabels } from "../contexts/TasksContext";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Progress } from "./ui/progress";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "./ui/sheet";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "./ui/popover";
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  X,
  ExternalLink,
  ChevronRight,
  FileText,
  Brain,
  Mail,
  Upload,
  Database,
  FileSpreadsheet,
  CloudUpload,
  Zap,
  AlertTriangle,
  User,
  CalendarClock,
} from "lucide-react";
import { cn, safeDateStr } from "../lib/utils";

/**
 * Ícones por tipo de tarefa
 */
const TaskTypeIcons = {
  PDF_GEN: FileText,
  AI_ANALYSIS: Brain,
  EMAIL_SEND: Mail,
  DOCUMENT_UPLOAD: Upload,
  BULK_IMPORT: Database,
  REPORT_GEN: FileSpreadsheet,
  DATA_EXPORT: FileSpreadsheet,
  DOC_CATEGORIZE: Zap,
  TEMPLATE_FILL: FileText,
  S3_UPLOAD: CloudUpload,
  CUSTOM: Activity,
};

/**
 * Cores por status
 */
const StatusColors = {
  pending: "bg-yellow-500/10 text-yellow-600 border-yellow-500/20",
  processing: "bg-blue-500/10 text-blue-600 border-blue-500/20",
  completed: "bg-green-500/10 text-green-600 border-green-500/20",
  failed: "bg-red-500/10 text-red-600 border-red-500/20",
  cancelled: "bg-gray-500/10 text-gray-600 border-gray-500/20",
};

/**
 * Labels por status
 */
const StatusLabels = {
  pending: "Aguardando",
  processing: "Em processamento",
  completed: "Concluído",
  failed: "Falhou",
  cancelled: "Cancelado",
};

/**
 * Formatar data de prazo com indicação visual de atraso.
 * Retorna { text, isOverdue, isToday, isSoon }.
 */
const formatDueDate = (dueDate) => {
  if (!dueDate) return null;
  const now = new Date();
  const due = new Date(safeDateStr(dueDate));
  const diffMs = due - now;
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
  const isOverdue = diffMs < 0;
  const isToday = !isOverdue && diffDays === 0;
  const isSoon = !isOverdue && !isToday && diffDays <= 3;

  let text = '';
  if (isOverdue) {
    const daysLate = Math.abs(diffDays);
    text = daysLate === 0 ? 'Atrasado hoje' : daysLate === 1 ? 'Atrasado 1 dia' : `Atrasado ${daysLate} dias`;
  } else if (isToday) {
    text = 'Entrega hoje';
  } else if (diffDays === 1) {
    text = 'Amanhã';
  } else {
    text = `em ${due.toLocaleDateString('pt-PT', { day: 'numeric', month: 'short' })}`;
  }

  return { text, isOverdue, isToday, isSoon };
};

/**
 * Componente de item de tarefa individual
 */
const TaskItem = ({ task, onAcknowledge, onCancel }) => {
  const TaskIcon = TaskTypeIcons[task.task_type] || Activity;
  const isActive = task.status === "pending" || task.status === "processing";
  const dueDateInfo = formatDueDate(task.due_date);

  // Badge de prioridade
  const priorityConfig = {
    alta: { label: 'Alta', className: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800' },
    media: { label: 'Média', className: 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800' },
    baixa: { label: 'Baixa', className: 'bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800/50 dark:text-slate-400 dark:border-slate-700' },
  };
  const priority = priorityConfig[task.priority];

  return (
    <div
      className={cn(
        "p-3 rounded-lg border transition-all",
        task.status === "completed" && !task.acknowledged_at && "bg-green-50/50 dark:bg-green-950/20 border-green-200 dark:border-green-800",
        task.status === "failed" && !task.acknowledged_at && "bg-red-50/50 dark:bg-red-950/20 border-red-200 dark:border-red-800",
        isActive && "bg-blue-50/50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800",
        dueDateInfo?.isOverdue && isActive && "ring-1 ring-red-300 dark:ring-red-700",
      )}
    >
      <div className="flex items-start gap-3">
        {/* Ícone */}
        <div className={cn(
          "p-2 rounded-md shrink-0",
          StatusColors[task.status]
        )}>
          {task.status === "processing" ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : task.status === "completed" ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : task.status === "failed" ? (
            <XCircle className="h-4 w-4" />
          ) : (
            <TaskIcon className="h-4 w-4" />
          )}
        </div>
        
        {/* Conteúdo */}
        <div className="flex-1 min-w-0">
          {/* Título + Prioridade + Cancelar */}
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium truncate">{task.title}</p>
            <div className="flex items-center gap-1 shrink-0">
              {priority && (
                <Badge variant="outline" className={cn("text-[10px] px-1.5 py-0 h-5 font-semibold border", priority.className)}>
                  {priority.label}
                </Badge>
              )}
              {isActive && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 text-muted-foreground hover:text-destructive"
                  onClick={() => onCancel(task.task_id)}
                >
                  <X className="h-3 w-3" />
                </Button>
              )}
            </div>
          </div>

          {/* Cliente / Processo associado */}
          {task.process_name && (
            <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1 truncate">
              <FileText className="h-3 w-3 shrink-0" />
              {task.process_name}
            </p>
          )}

          {/* Descrição (opcional) */}
          {task.description && (
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">
              {task.description}
            </p>
          )}
          
          {/* Barra de progresso */}
          {task.status === "processing" && (
            <div className="mt-2">
              <Progress value={task.progress || 0} className="h-1.5" />
              {task.progress_message && (
                <p className="text-xs text-muted-foreground mt-1">{task.progress_message}</p>
              )}
            </div>
          )}

          {/* Prazo + Meta-dados */}
          <div className="flex items-center gap-2 mt-1.5 flex-wrap">
            {dueDateInfo && (
              <span className={cn(
                "inline-flex items-center gap-1 text-[11px] px-1.5 py-0.5 rounded-full border",
                dueDateInfo.isOverdue
                  ? "bg-red-100 text-red-700 border-red-200 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800"
                  : dueDateInfo.isToday
                    ? "bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900/40 dark:text-orange-300 dark:border-orange-800"
                    : dueDateInfo.isSoon
                      ? "bg-amber-50 text-amber-600 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800"
                      : "bg-muted text-muted-foreground border-border"
              )}>
                <CalendarClock className="h-3 w-3" />
                {dueDateInfo.text}
              </span>
            )}
            {task.assigned_to_name && (
              <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                <User className="h-3 w-3" />
                {task.assigned_to_name}
              </span>
            )}
            <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
              <TaskIcon className="h-3 w-3" />
              {TaskTypeLabels[task.task_type] || task.task_type}
            </span>
          </div>
          
          {/* Ações para tarefas concluídas/falhadas */}
          {(task.status === "completed" || task.status === "failed") && !task.acknowledged_at && (
            <div className="flex items-center gap-2 mt-2">
              <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => onAcknowledge(task.task_id)}>OK</Button>
              {task.result_url && (
                <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => window.open(task.result_url, "_blank")}>
                  <ExternalLink className="h-3 w-3 mr-1" />
                  Ver resultado
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

/**
 * Componente principal do dropdown de tarefas
 */
const TasksDropdown = ({ compact = false }) => {
  const {
    tasks,
    activeCount,
    completedUnacknowledged,
    acknowledgeTask,
    cancelTask,
  } = useTasks();
  
  const [isOpen, setIsOpen] = useState(false);
  
  const totalNotifications = activeCount + completedUnacknowledged;
  
  // Agrupar tarefas por status
  const activeTasks = tasks.filter(t => t.status === "pending" || t.status === "processing");
  const completedTasks = tasks.filter(t => (t.status === "completed" || t.status === "failed") && !t.acknowledged_at);
  
  return (
    <Sheet open={isOpen} onOpenChange={setIsOpen}>
      <SheetTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className={cn(
            "relative h-8 w-8",
            totalNotifications > 0 && "text-primary"
          )}
          title="Tarefas em background"
        >
          {activeCount > 0 ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Activity className="h-4 w-4" />
          )}
          
          {/* Badge de notificações */}
          {totalNotifications > 0 && (
            <Badge
              variant="destructive"
              className={cn(
                "absolute -top-1 -right-1 h-5 w-5 p-0 flex items-center justify-center text-[10px] font-bold",
                activeCount > 0 && "animate-pulse"
              )}
            >
              {totalNotifications > 9 ? "9+" : totalNotifications}
            </Badge>
          )}
        </Button>
      </SheetTrigger>
      
      <SheetContent className="w-full sm:max-w-md p-0 flex flex-col">
        <SheetHeader className="p-4 border-b">
          <SheetTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Centro de Operações
          </SheetTitle>
          <SheetDescription>
            {activeCount > 0 
              ? `${activeCount} tarefa${activeCount > 1 ? "s" : ""} em execução`
              : "Nenhuma tarefa em execução"
            }
          </SheetDescription>
        </SheetHeader>
        
        <div className="flex-1 overflow-y-auto p-4">
          {/* Tarefas ativas */}
          {activeTasks.length > 0 && (
            <div className="mb-4">
              <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                <Loader2 className="h-3 w-3 animate-spin" />
                Em Execução ({activeTasks.length})
              </h4>
              <div className="space-y-2">
                {activeTasks.map(task => (
                  <TaskItem
                    key={task.task_id}
                    task={task}
                    onAcknowledge={acknowledgeTask}
                    onCancel={cancelTask}
                  />
                ))}
              </div>
            </div>
          )}
          
          {/* Tarefas concluídas */}
          {completedTasks.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-muted-foreground mb-2 flex items-center gap-2">
                <CheckCircle2 className="h-3 w-3" />
                Concluídas ({completedTasks.length})
              </h4>
              <div className="space-y-2">
                {completedTasks.map(task => (
                  <TaskItem
                    key={task.task_id}
                    task={task}
                    onAcknowledge={acknowledgeTask}
                    onCancel={cancelTask}
                  />
                ))}
              </div>
            </div>
          )}
          
          {/* Estado vazio */}
          {tasks.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="p-3 rounded-full bg-muted mb-3">
                <Activity className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium">Tudo em ordem</p>
              <p className="text-xs text-muted-foreground mt-1">
                Não há tarefas em execução ou pendentes de confirmação
              </p>
            </div>
          )}
        </div>
        
        {/* Rodapé com ações */}
        {completedUnacknowledged > 1 && (
          <div className="p-4 border-t bg-muted/50">
            <Button
              variant="outline"
              size="sm"
              className="w-full"
              onClick={async () => {
                // Confirmar todas as tarefas concluídas
                for (const task of completedTasks) {
                  await acknowledgeTask(task.task_id);
                }
              }}
            >
              <CheckCircle2 className="h-4 w-4 mr-2" />
              Confirmar todas ({completedUnacknowledged})
            </Button>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
};

export default TasksDropdown;

