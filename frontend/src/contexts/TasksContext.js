import { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";
import { toast } from "sonner";
import api from "../services/api";
import { useAuth } from "./AuthContext"; // <-- 1. Importar o hook de autenticação

const TasksContext = createContext(null);

// Intervalo base de polling (5 segundos)
const BASE_POLLING_INTERVAL = 5000;
// Intervalo quando não há tarefas ativas (30 segundos)
const IDLE_POLLING_INTERVAL = 30000;
// Tempo mínimo entre toasts para a mesma tarefa
const TOAST_DEBOUNCE_MS = 1000;

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
const TaskTypeLabels = {
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
 */
export const TasksProvider = ({ children }) => {
  const { user } = useAuth(); // <-- 2. Consumir o estado do utilizador logado

  // Estado das tarefas
  const [tasks, setTasks] = useState([]);
  const [activeCount, setActiveCount] = useState(0);
  const [completedUnacknowledged, setCompletedUnacknowledged] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [lastFetchTime, setLastFetchTime] = useState(null);
  
  // Referências para controlo
  const pollingIntervalRef = useRef(null);
  const lastToastTimeRef = useRef({});
  const previousTaskIdsRef = useRef(new Set());
  
  /**
   * Buscar tarefas ativas do backend
   */
  const fetchActiveTasks = useCallback(async () => {
    if (!user) return; // <-- 3. Abortar a requisição se não estiver logado

    try {
      setIsLoading(true);
      const response = await api.get("/tasks/active");
      const data = response.data;
      
      // Detectar tarefas que mudaram de estado
      const previousTaskIds = previousTaskIdsRef.current;
      const currentTaskIds = new Set(data.tasks.map(t => t.task_id));
      
      // Verificar tarefas concluídas recentemente
      data.tasks.forEach(task => {
        const wasActive = previousTaskIds.has(task.task_id);
        const isNowCompleted = task.status === TaskStatus.COMPLETED;
        const isNowFailed = task.status === TaskStatus.FAILED;
        const isUnacknowledged = !task.acknowledged_at;
        
        if (wasActive && isUnacknowledged) {
          const now = Date.now();
          const lastToast = lastToastTimeRef.current[task.task_id] || 0;
          
          if (now - lastToast > TOAST_DEBOUNCE_MS) {
            lastToastTimeRef.current[task.task_id] = now;
            
            if (isNowCompleted) {
              toast.success(`${task.title} concluída!`, {
                description: task.description || "A tarefa foi concluída com sucesso.",
                action: task.result_url ? {
                  label: "Ver resultado",
                  onClick: () => window.open(task.result_url, "_blank"),
                } : undefined,
              });
            } else if (isNowFailed) {
              toast.error(`${task.title} falhou`, {
                description: task.error_message || "Ocorreu um erro durante a execução.",
              });
            }
          }
        }
      });
      
      // Atualizar estado
      setTasks(data.tasks || []);
      setActiveCount(data.active_count || 0);
      setCompletedUnacknowledged(data.completed_unacknowledged || 0);
      setLastFetchTime(new Date().toISOString());
      
      // Guardar IDs das tarefas atuais para comparação futura
      previousTaskIdsRef.current = currentTaskIds;
      
    } catch (error) {
      console.error("[TasksContext] Erro ao buscar tarefas:", error);
    } finally {
      setIsLoading(false);
    }
  }, [user]); // <-- 4. Adicionar "user" como dependência
  
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
  
  /**
   * Iniciar polling inteligente
   */
  useEffect(() => {
    // <-- 5. Se não houver sessão ativa, limpar qualquer polling existente e não fazer nada
    if (!user) {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      return;
    }

    // Buscar tarefas imediatamente (pois o utilizador está validado)
    fetchActiveTasks();
    
    const setupPolling = () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      
      const interval = activeCount > 0 ? BASE_POLLING_INTERVAL : IDLE_POLLING_INTERVAL;
      pollingIntervalRef.current = setInterval(fetchActiveTasks, interval);
    };
    
    setupPolling();
    
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, [fetchActiveTasks, activeCount, user]); // <-- 6. Adicionar "user" como dependência
  
  /**
   * Listener para visibilidade da página
   */
  useEffect(() => {
    const handleVisibilityChange = () => {
      // <-- 7. Adicionar verificação do user aqui também
      if (document.visibilityState === "visible" && user) {
        fetchActiveTasks();
      }
    };
    
    document.addEventListener("visibilitychange", handleVisibilityChange);
    
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [fetchActiveTasks, user]); // <-- 8. Adicionar "user" como dependência
  
  const value = {
    tasks,
    activeCount,
    completedUnacknowledged,
    isLoading,
    lastFetchTime,
    fetchActiveTasks,
    acknowledgeTask,
    cancelTask,
    getTaskDetails,
    TaskTypes,
    TaskStatus,
    TaskTypeLabels,
  };
  
  return (
    <TasksContext.Provider value={value}>
      {children}
    </TasksContext.Provider>
  );
};

export const useTasks = () => {
  const context = useContext(TasksContext);
  if (!context) {
    throw new Error("useTasks must be used within a TasksProvider");
  }
  return context;
};

export default TasksContext;
