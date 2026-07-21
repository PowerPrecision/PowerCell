/**
 * ====================================================================
 * USE PROCESS QUERY - TanStack Query Hooks
 * ====================================================================
 * Hooks para gestão de dados de Processos com caching automático.
 * 
 * FUNCIONALIDADES:
 * - Fetch de detalhes do processo
 * - Fetch de histórico (timeline)
 * - Fetch de atividades/comentários
 * - Invalidação automática via mutations
 * ====================================================================
 */

import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import {
  getProcess,
  getHistory,
  getActivities,
  getProcessTasks,
  getDeadlines,
  getWorkflowStatuses,
} from '../../services/api';

/**
 * Hook para detalhes de um processo específico
 * 
 * @param {string|number} processId - ID do processo
 * @param {Object} options - Opções do hook
 * @param {boolean} options.enabled - Se a query deve executar
 * @returns {Object} Query result com process, isLoading, etc.
 */
export function useProcessQuery(processId, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.processes.detail(processId),
    queryFn: async () => {
      const response = await getProcess(processId);
      return response.data;
    },
    enabled: !!processId && enabled,
    staleTime: 60 * 1000, // 1 minuto
  });

  return {
    process: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    query,
  };
}

/**
 * Hook para histórico/timeline de um processo
 * 
 * @param {string|number} processId - ID do processo
 * @param {Object} options - Opções do hook
 * @returns {Object} Query result com history, isLoading, etc.
 */
export function useProcessHistoryQuery(processId, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.history.byProcess(processId),
    queryFn: async () => {
      const response = await getHistory(processId);
      return response.data;
    },
    enabled: !!processId && enabled,
    staleTime: 30 * 1000, // 30 segundos - histórico muda mais frequentemente
  });

  return {
    history: query.data || [],
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    query,
  };
}

/**
 * Hook para atividades/comentários de um processo
 * 
 * @param {string|number} processId - ID do processo
 * @param {Object} options - Opções do hook
 * @returns {Object} Query result com activities, isLoading, etc.
 */
export function useProcessActivitiesQuery(processId, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.activities.byProcess(processId),
    queryFn: async () => {
      const response = await getActivities(processId);
      return response.data;
    },
    enabled: !!processId && enabled,
    staleTime: 30 * 1000, // 30 segundos
  });

  return {
    activities: query.data || [],
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    query,
  };
}

/**
 * Hook para tarefas de um processo
 * 
 * @param {string|number} processId - ID do processo
 * @param {Object} options - Opções do hook
 * @returns {Object} Query result com tasks, isLoading, etc.
 */
export function useProcessTasksQuery(processId, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.tasks.byProcess(processId),
    queryFn: async () => {
      const response = await getProcessTasks(processId);
      return response.data;
    },
    enabled: !!processId && enabled,
    staleTime: 60 * 1000, // 1 minuto
  });

  return {
    tasks: query.data || [],
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    query,
  };
}

/**
 * Hook para prazos/deadlines de um processo
 */
export function useProcessDeadlinesQuery(processId, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.deadlines.byProcess(processId),
    queryFn: async () => {
      const response = await getDeadlines(processId);
      return Array.isArray(response.data) ? response.data : [];
    },
    enabled: !!processId && enabled,
    staleTime: 30 * 1000,
  });

  return {
    deadlines: query.data || [],
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    query,
  };
}

/**
 * Hook para lista de workflow statuses (global)
 */
export function useWorkflowStatusesQuery(options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.workflowStatuses.list(),
    queryFn: async () => {
      const response = await getWorkflowStatuses();
      return Array.isArray(response.data) ? response.data : [];
    },
    enabled,
    staleTime: 5 * 60 * 1000,
  });

  return {
    workflowStatuses: query.data || [],
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    query,
  };
}

/**
 * Hook combinado para todos os dados de um processo
 * Inclui: detalhes, histórico, atividades, tarefas
 * 
 * @param {string|Number} processId - ID do processo
 * @param {Object} options - Opções do hook
 * @returns {Object} Dados combinados e estados
 */
export function useProcessFullData(processId, options = {}) {
  const { enabled = true } = options;

  const processQuery = useProcessQuery(processId, { enabled });
  const historyQuery = useProcessHistoryQuery(processId, { enabled });
  const activitiesQuery = useProcessActivitiesQuery(processId, { enabled });
  const tasksQuery = useProcessTasksQuery(processId, { enabled });
  const deadlinesQuery = useProcessDeadlinesQuery(processId, { enabled });
  const statusesQuery = useWorkflowStatusesQuery({ enabled });

  return {
    // Dados
    process: processQuery.process,
    history: historyQuery.history,
    activities: activitiesQuery.activities,
    tasks: tasksQuery.tasks,
    deadlines: deadlinesQuery.deadlines,
    workflowStatuses: statusesQuery.workflowStatuses,
    
    // Estados combinados
    isLoading: processQuery.isLoading || historyQuery.isLoading || activitiesQuery.isLoading,
    isFetching: processQuery.isFetching || historyQuery.isFetching || activitiesQuery.isFetching,
    isError: processQuery.isError || historyQuery.isError || activitiesQuery.isError,
    isSuccess: processQuery.isSuccess && historyQuery.isSuccess && activitiesQuery.isSuccess,
    
    // Erros
    error: processQuery.error || historyQuery.error || activitiesQuery.error,
    
    // Funções
    refetchAll: async () => {
      await Promise.all([
        processQuery.refetch(),
        historyQuery.refetch(),
        activitiesQuery.refetch(),
        tasksQuery.refetch(),
        deadlinesQuery.refetch(),
        statusesQuery.refetch(),
      ]);
    },
    
    // Queries individuais (para uso avançado)
    processQuery,
    historyQuery,
    activitiesQuery,
    tasksQuery,
    deadlinesQuery,
    statusesQuery,
  };
}

export default useProcessQuery;
