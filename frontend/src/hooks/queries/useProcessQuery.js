/**
 * ====================================================================
 * USE PROCESS QUERY - TanStack Query Hooks
 * ====================================================================
 * Hooks para gestão de dados de Processos com caching automático.
 *
 * FUNCIONALIDADES:
 * - Fetch de detalhes do processo + cliente
 * - Fetch de histórico / atividades / deadlines / workflow
 * - Bundle useProcessFullData para ProcessDetails
 * ====================================================================
 */

import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import {
  getProcess,
  getHistory,
  getActivities,
  getProcessTasks,
  getDeadlines,
  getWorkflowStatuses,
  getClient,
} from '../../services/api';

const EMPTY_LIST = Object.freeze([]);

/** 60s — evita refetch em cada navegação/foco; alinhado com queryClient default. */
export const PROCESS_STALE_TIME_MS = 60 * 1000;
/** 5 minutos — mantém o bundle em memória ao sair e voltar a ProcessDetails. */
export const PROCESS_GC_TIME_MS = 5 * 60 * 1000;

function asArray(data) {
  return Array.isArray(data) ? data : EMPTY_LIST;
}

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
    staleTime: PROCESS_STALE_TIME_MS,
    gcTime: PROCESS_GC_TIME_MS,
  });

  return {
    process: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    dataUpdatedAt: query.dataUpdatedAt,
    query,
  };
}

/**
 * Hook para cliente associado ao processo (GET /clients/{id})
 */
export function useClientQuery(clientId, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.clients.detail(clientId),
    queryFn: async () => {
      const response = await getClient(clientId);
      return response.data;
    },
    enabled: !!clientId && enabled,
    staleTime: PROCESS_STALE_TIME_MS,
    gcTime: PROCESS_GC_TIME_MS,
  });

  return {
    client: query.data || null,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    dataUpdatedAt: query.dataUpdatedAt,
    query,
  };
}

/**
 * Hook para histórico/timeline de um processo
 */
export function useProcessHistoryQuery(processId, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.history.byProcess(processId),
    queryFn: async () => {
      try {
        const response = await getHistory(processId);
        return asArray(response.data);
      } catch {
        return EMPTY_LIST;
      }
    },
    enabled: !!processId && enabled,
    staleTime: PROCESS_STALE_TIME_MS,
    gcTime: PROCESS_GC_TIME_MS,
  });

  return {
    history: asArray(query.data),
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
 */
export function useProcessActivitiesQuery(processId, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.activities.byProcess(processId),
    queryFn: async () => {
      try {
        const response = await getActivities(processId);
        return asArray(response.data);
      } catch {
        return EMPTY_LIST;
      }
    },
    enabled: !!processId && enabled,
    staleTime: PROCESS_STALE_TIME_MS,
    gcTime: PROCESS_GC_TIME_MS,
  });

  return {
    activities: asArray(query.data),
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
 */
export function useProcessTasksQuery(processId, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.tasks.byProcess(processId),
    queryFn: async () => {
      const response = await getProcessTasks(processId);
      return asArray(response.data);
    },
    enabled: !!processId && enabled,
    staleTime: PROCESS_STALE_TIME_MS,
    gcTime: PROCESS_GC_TIME_MS,
  });

  return {
    tasks: asArray(query.data),
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
      try {
        const response = await getDeadlines(processId);
        return asArray(response.data);
      } catch {
        return EMPTY_LIST;
      }
    },
    enabled: !!processId && enabled,
    staleTime: PROCESS_STALE_TIME_MS,
    gcTime: PROCESS_GC_TIME_MS,
  });

  return {
    deadlines: asArray(query.data),
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
      try {
        const response = await getWorkflowStatuses();
        return asArray(response.data);
      } catch {
        return EMPTY_LIST;
      }
    },
    enabled,
    staleTime: 5 * 60 * 1000,
  });

  return {
    workflowStatuses: asArray(query.data),
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
 * Hook combinado para ProcessDetails (live subscription).
 */
export function useProcessFullData(processId, options = {}) {
  const { enabled = true } = options;

  const processQuery = useProcessQuery(processId, { enabled });
  const historyQuery = useProcessHistoryQuery(processId, { enabled });
  const activitiesQuery = useProcessActivitiesQuery(processId, { enabled });
  const tasksQuery = useProcessTasksQuery(processId, { enabled });
  const deadlinesQuery = useProcessDeadlinesQuery(processId, { enabled });
  const statusesQuery = useWorkflowStatusesQuery({ enabled });
  const clientQuery = useClientQuery(processQuery.process?.client_id, {
    enabled: enabled && !!processQuery.process?.client_id,
  });

  return {
    process: processQuery.process,
    client: clientQuery.client,
    history: historyQuery.history,
    activities: activitiesQuery.activities,
    tasks: tasksQuery.tasks,
    deadlines: deadlinesQuery.deadlines,
    workflowStatuses: statusesQuery.workflowStatuses,

    isLoading: processQuery.isLoading || (
      !!processQuery.process?.client_id && clientQuery.isLoading
    ),
    isFetching: processQuery.isFetching || historyQuery.isFetching
      || activitiesQuery.isFetching || deadlinesQuery.isFetching
      || clientQuery.isFetching,
    isError: processQuery.isError,
    isSuccess: processQuery.isSuccess,

    error: processQuery.error,

    refetchAll: async () => {
      await Promise.all([
        processQuery.refetch(),
        historyQuery.refetch(),
        activitiesQuery.refetch(),
        tasksQuery.refetch(),
        deadlinesQuery.refetch(),
        statusesQuery.refetch(),
        (clientQuery.client || processQuery.process?.client_id)
          ? clientQuery.refetch()
          : Promise.resolve(),
      ]);
    },

    processQuery,
    clientQuery,
    historyQuery,
    activitiesQuery,
    tasksQuery,
    deadlinesQuery,
    statusesQuery,
  };
}

export default useProcessQuery;
