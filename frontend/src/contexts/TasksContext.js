/**
 * TasksContext — Contexto de tarefas assíncronas com circuit breaker e polling inteligente.
 *
 * PORQUÊ: O PowerCell executa operações demoradas em segundo plano (geração de PDF,
 * análise IA de documentos, envio de emails, upload S3, etc.). Este contexto fornece
 * uma camada unificada para monitorizar essas tarefas, mostrar progresso ao utilizador
 * e notificar quando terminam. Sem ele, cada componente teria de gerir o seu próprio
 * estado de polling, duplicando pedidos e criando inconsistências.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Circuit breaker: após 3 falhas consecutivas no endpoint de polling, para
 *   automaticamente por 60 segundos para evitar spam de erros no console.
 * - Polling inteligente: 5 segundos quando há tarefas activas, 30 segundos em idle,
 *   com retoma imediata quando a aba volta a ser visível (visibilitychange listener).
 * - Toast com debounce: cada tarefa só gera um toast por mudança de estado,
 *   evitando notificações duplicadas.
 * - Tipos de tarefas definidos em TaskTypes (PDF_GEN, AI_ANALYSIS, EMAIL_SEND, etc.)
 *   com labels amigáveis em português para facilitar a identificação.
 * - Contador de referência (reference counting) implícito via useEffect cleanup.
 *
 * @context {TasksContext} — Fornecido via TasksProvider em App.js
 * @context {AuthContext} — Consome user para filtrar tarefas por utilizador
 * @hook {useTasks} — Hook para consumir o contexto em componentes React
 *
 * @example
 * // No componente raiz
 * <TasksProvider>
 *   <AppRoutes />
 * </TasksProvider>
 *
 * // Mostrar contagem de tarefas activas no header
 * const { activeCount, tasks } = useTasks();
 */
import { createContext, useState, useEffect, useCallback, useRef, useContext, useMemo } from "react";
import { toast } from "sonner";
import api from "../services/api";
import { useAuth } from "./AuthContext";

const TasksContext = createContext(null);

// Intervalo base de polling (5 segundos)
const BASE_POLLING_INTERVAL = 5000;
// Intervalo quando não há tarefas ativas (30 segundos)
const IDLE_POLLING_INTERVAL = 30000;
// Tempo mínimo entre toasts para a mesma tarefa
// 60s — evita loops de toast entre polls (backend auto-acknowledge é a defesa primária)
// Circuit breaker: número de falhas consecutivas antes de parar polling
const MAX_CONSECUTIVE_FAILURES = 3;
// Circuit breaker: tempo de espera antes de retomar polling após circuit breaker (60s)
const CIRCUIT_BREAKER_COOLDOWN = 60000;

/**
 * Tipos de tarefas assíncronas
 */
export const TaskTypes = {
  PDF_GEN: "PDF_GEN",
  AI_ANALYSIS: "AI_ANALYSIS",
  EMAIL_SEND: "EMAIL_SEND",
  DOCUMENT_UPLOAD: "DOCUMENT_UPLOAD",
  BULK_IMPORT: "BULK_IMPORT",
  REPORT_GEN: "REPORT_GEN",
  DATA_EXPORT: "DATA_EXPORT",
  DOC_CATEGORIZE: "DOC_CATEGORIZE",
  TEMPLATE_FILL: "TEMPLATE_FILL",
  S3_UPLOAD: "S3_UPLOAD",
  CUSTOM: "CUSTOM",
};

/**
 * Status de tarefas
 */
export const TaskStatus = {
  PENDING: "pending",
  PROCESSING: "processing",
  COMPLETED: "completed",
  FAILED: "failed",
  CANCELLED: "cancelled",
};

/**
 * Labels amigáveis para tipos de tarefas
 */
export const TaskTypeLabels = {
  PDF_GEN: "Geração de PDF",
  AI_ANALYSIS: "Análise com IA",
  EMAIL_SEND: "Envio de Email",
  DOCUMENT_UPLOAD: "Upload de Documento",
  BULK_IMPORT: "Importação em Massa",
  REPORT_GEN: "Geração de Relatório",
  DATA_EXPORT: "Exportação de Dados",
  DOC_CATEGORIZE: "Categorização de Documento",
  TEMPLATE_FILL: "Preenchimento de Template",
  S3_UPLOAD: "Upload para Cloud",
  CUSTOM: "Tarefa Personalizada",
};

/**
 * Provider para o contexto de tarefas assíncronas
 * 
 * Inclui circuit breaker para parar polling quando o endpoint
 * retorna erros persistentes (404, 500, etc.), evitando spam de console.
 */
export function TasksProvider({ children }) {
  const { user } = useAuth();

  // Estado das tarefas
  const [tasks, setTasks] = useState([]);
  const [activeCount, setActiveCount] = useState(0);
  const [completedUnacknowledged, setCompletedUnacknowledged] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [, setLastFetchTime] = useState(null);
  
  // Referências para controlo
  const pollingIntervalRef = useRef(null);
  const previousTaskIdsRef = useRef(new Set());
  const toastedTaskIdsRef = useRef(new Set()); // Permanent dedup: completion already toasted
  const loadingToastIdsRef = useRef([]); // Ordered list of active loading toast ids (cap 5)
  const consecutiveFailuresRef = useRef(0);
  const circuitBreakerActiveRef = useRef(false);
  const circuitBreakerTimeoutRef = useRef(null);

  const MAX_LOADING_TOASTS = 5;

  const toastIdFor = (taskId) => `bg-task-${taskId}`;

  /**
   * Ensure a sticky loading toast exists for an active task (cap 5).
   * Updates progress on the same id while the task is still pending/processing.
   */
  const upsertLoadingToast = useCallback((task) => {
    const id = toastIdFor(task.task_id);
    const queue = loadingToastIdsRef.current;

    if (!queue.includes(id)) {
      // Cap: dismiss oldest loading toast if at limit
      while (queue.length >= MAX_LOADING_TOASTS) {
        const oldest = queue.shift();
        toast.dismiss(oldest);
      }
      queue.push(id);
    }

    toast.loading(task.title, {
      id,
      description: task.progress_message || "Em curso…",
      duration: Infinity,
    });
  }, []);

  /**
   * Morph sticky toast to success/error and stop tracking it as loading.
   */
  const finalizeToast = useCallback((task, kind) => {
    const id = toastIdFor(task.task_id);
    loadingToastIdsRef.current = loadingToastIdsRef.current.filter((x) => x !== id);

    if (kind === "success") {
      toast.success(`${task.title} concluída!`, {
        id,
        description: task.description || "A tarefa foi concluída com sucesso.",
        duration: Infinity,
        action: task.result_url
          ? {
              label: "Ver resultado",
              onClick: () => window.open(task.result_url, "_blank"),
            }
          : undefined,
      });
    } else {
      toast.error(`${task.title} falhou`, {
        id,
        description: task.error_message || "Ocorreu um erro durante a execução.",
        duration: Infinity,
      });
    }
  }, []);

  /**
   * Parar polling (limpa intervalo e circuit breaker timeout)
   */
  const stopPolling = useCallback(() => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    if (circuitBreakerTimeoutRef.current) {
      clearTimeout(circuitBreakerTimeoutRef.current);
      circuitBreakerTimeoutRef.current = null;
    }
  }, []);

  /**
   * Ativar circuit breaker: parar polling e agendar retomada
   */
  const activateCircuitBreaker = useCallback(() => {
    circuitBreakerActiveRef.current = true;
    stopPolling();
    console.warn(
      `[TasksContext] Circuit breaker ativado após ${MAX_CONSECUTIVE_FAILURES} falhas consecutivas. ` +
      `Polling pausado por ${CIRCUIT_BREAKER_COOLDOWN / 1000}s.`
    );

    // Agendar retomada automática do polling
    circuitBreakerTimeoutRef.current = setTimeout(() => {
      circuitBreakerActiveRef.current = false;
      consecutiveFailuresRef.current = 0;
      // Retomar polling será feito pelo useEffect
    }, CIRCUIT_BREAKER_COOLDOWN);
  }, [stopPolling]);

  /**
   * Buscar tarefas ativas do backend
   */
  const fetchActiveTasks = useCallback(async () => {
    if (!user) return;

    // Respeitar circuit breaker
    if (circuitBreakerActiveRef.current) return;

    try {
      setIsLoading(true);
      const response = await api.get("/tasks/active");
      const data = response.data;
      
      // Reset circuit breaker em sucesso
      if (consecutiveFailuresRef.current > 0) {
        consecutiveFailuresRef.current = 0;
      }
      
      // Detectar tarefas que mudaram de estado
      const currentTaskIds = new Set(data.tasks.map(t => t.task_id));
      
      // Sticky toasts: loading → morph success/error (same id)
      data.tasks.forEach(task => {
        const isActive =
          task.status === TaskStatus.PENDING ||
          task.status === TaskStatus.PROCESSING;
        const isNowCompleted = task.status === TaskStatus.COMPLETED;
        const isNowFailed = task.status === TaskStatus.FAILED;
        const isUnacknowledged = !task.acknowledged_at;

        if (isActive) {
          upsertLoadingToast(task);
          return;
        }

        // Permanent dedup: skip if already toasted completion for this task
        if (toastedTaskIdsRef.current.has(task.task_id)) return;

        // Morph sticky toast on terminal status. Same toast id survives navigation
        // (Toaster is outside BrowserRouter). Always morph — deterministic id.
        if (isUnacknowledged && (isNowCompleted || isNowFailed)) {
          toastedTaskIdsRef.current.add(task.task_id);
          if (toastedTaskIdsRef.current.size > 200) {
            const arr = [...toastedTaskIdsRef.current];
            toastedTaskIdsRef.current = new Set(arr.slice(-200));
          }
          finalizeToast(task, isNowCompleted ? "success" : "error");
        }
      });

      // Tasks that left /tasks/active without a terminal toast: NEVER auto-dismiss.
      // Sticky BG toasts must survive page changes and list churn; user closes via X.
      const activeOrTerminalIds = new Set(data.tasks.map(t => toastIdFor(t.task_id)));
      loadingToastIdsRef.current = loadingToastIdsRef.current.filter((id) => {
        if (activeOrTerminalIds.has(id)) return true;
        return false; // stop tracking for the loading cap — keep toast visible
      });
      
      // Actualizar estado
      setTasks(data.tasks || []);
      setActiveCount(data.active_count || 0);
      setCompletedUnacknowledged(data.completed_unacknowledged || 0);
      setLastFetchTime(new Date().toISOString());
      
      // Guardar IDs das tarefas atuais para comparação futura
      previousTaskIdsRef.current = currentTaskIds;
      
    } catch (error) {
      consecutiveFailuresRef.current++;

      // Log apenas na primeira falha e quando o circuit breaker ativar
      if (consecutiveFailuresRef.current === 1) {
        console.error("[TasksContext] Erro ao buscar tarefas:", error);
      }

      if (consecutiveFailuresRef.current >= MAX_CONSECUTIVE_FAILURES) {
        activateCircuitBreaker();
      }
    } finally {
      setIsLoading(false);
    }
  }, [user, activateCircuitBreaker, upsertLoadingToast, finalizeToast]);
  
  /**
   * Confirmar visualização de uma tarefa
   */
  const acknowledgeTask = useCallback(async (taskId) => {
    try {
      await api.post(`/tasks/${taskId}/acknowledge`);
      setTasks(prev => prev.filter(t => t.task_id !== taskId));
      setCompletedUnacknowledged(prev => Math.max(0, prev - 1));
    } catch (error) {
      console.error("[TasksContext] Erro ao confirmar tarefa:", error);
    }
  }, []);
  
  /**
   * Cancelar uma tarefa pendente
   */
  const cancelTask = useCallback(async (taskId) => {
    try {
      await api.delete(`/tasks/${taskId}/cancel`);
      setTasks(prev => prev.filter(t => t.task_id !== taskId));
      setActiveCount(prev => Math.max(0, prev - 1));
      const id = toastIdFor(taskId);
      loadingToastIdsRef.current = loadingToastIdsRef.current.filter((x) => x !== id);
      toast.dismiss(id);
      toast.info("Tarefa cancelada");
    } catch (error) {
      console.error("[TasksContext] Erro ao cancelar tarefa:", error);
      toast.error("Não foi possível cancelar a tarefa");
    }
  }, []);
  
  /**
   * Obter detalhes de uma tarefa
   */
  const getTaskDetails = useCallback(async (taskId) => {
    try {
      const response = await api.get(`/tasks/${taskId}`);
      return response.data;
    } catch (error) {
      console.error("[TasksContext] Erro ao obter detalhes da tarefa:", error);
      return null;
    }
  }, []);
  
  // Ref to track current polling interval so we can restart it when activeCount changes
  const activeCountRef = useRef(0);

  // Keep activeCountRef in sync with state
  useEffect(() => {
    activeCountRef.current = activeCount;
  }, [activeCount]);

  /**
   * Start polling with the appropriate interval based on active task count.
   * Does NOT include activeCount in its dependency array to prevent infinite loop.
   */
  const startPolling = useCallback(() => {
    stopPolling();
    const interval = activeCountRef.current > 0 ? BASE_POLLING_INTERVAL : IDLE_POLLING_INTERVAL;
    pollingIntervalRef.current = setInterval(fetchActiveTasks, interval);
  }, [fetchActiveTasks, stopPolling]);

  /**
   * Iniciar polling inteligente com circuit breaker
   */
  useEffect(() => {
    if (!user) {
      stopPolling();
      return;
    }

    // Não iniciar polling se circuit breaker está ativo
    if (circuitBreakerActiveRef.current) {
      return;
    }

    // Buscar tarefas imediatamente
    fetchActiveTasks();
    startPolling();
    
    return () => {
      stopPolling();
    };
  }, [fetchActiveTasks, user, stopPolling, startPolling]);

  // Restart polling with different interval when activeCount changes
  // (active tasks → fast polling, no active tasks → slow polling)
  useEffect(() => {
    if (!user) return;
    if (circuitBreakerActiveRef.current) return;
    startPolling();
  }, [activeCount, startPolling, user]);
  
  /**
   * Listener para visibilidade da página
   */
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible" && user) {
        fetchActiveTasks();
      }
    };
    
    document.addEventListener("visibilitychange", handleVisibilityChange);
    
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [fetchActiveTasks, user]);
  
  // NOTE: lastFetchTime is intentionally EXCLUDED from the context value
  // to prevent all consumers from re-rendering on every poll cycle (every 5-30s).
  // It was only used for debugging and is not needed by any consumer component.
  const value = useMemo(() => ({
    tasks,
    activeCount,
    completedUnacknowledged,
    isLoading,
    fetchActiveTasks,
    acknowledgeTask,
    cancelTask,
    getTaskDetails,
    TaskTypes,
    TaskStatus,
    TaskTypeLabels,
  }), [tasks, activeCount, completedUnacknowledged, isLoading, fetchActiveTasks, acknowledgeTask, cancelTask, getTaskDetails]);
  
  return (
    <TasksContext.Provider value={value}>
      {children}
    </TasksContext.Provider>
  );
}

export const useTasks = () => {
  const context = useContext(TasksContext);
  if (!context) {
    throw new Error("useTasks must be used within a TasksProvider");
  }
  return context;
};

export default TasksContext;
