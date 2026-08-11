/**
 * ====================================================================
 * USE BACKGROUND JOBS QUERY - TanStack Query Hooks
 * ====================================================================
 * Hooks para o "Centro de Operações" (BackgroundJobsPage): monitorização
 * de importações e análises em massa a correr em background.
 *
 * FUNCIONALIDADES:
 * - Lista de jobs + contagens por estado — GET /ai/bulk/background-jobs
 *   (com polling automático via `refetchInterval` quando `autoRefresh` está
 *   activo, preservando o comportamento original de refresh a cada 5s)
 * - Notificações de jobs bloqueados ("stuck") — GET /ai/bulk/background-jobs/notifications
 * - Métricas agregadas (últimos N dias) — GET /ai/bulk/background-jobs/metrics
 * ====================================================================
 */

import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import {
  getBackgroundJobs,
  getBackgroundJobNotifications,
  getBackgroundJobMetrics,
} from '../../services/api';

const EMPTY_LIST = Object.freeze([]);
const EMPTY_COUNTS = Object.freeze({ running: 0, success: 0, failed: 0, paused: 0, total: 0 });

function asArray(data) {
  return Array.isArray(data) ? data : EMPTY_LIST;
}

const AUTO_REFRESH_INTERVAL_MS = 5000;

/**
 * Hook para a listagem de jobs em background + contagens por estado.
 *
 * @param {Object} options - Opções do hook
 * @param {string|null} options.statusFilter - Filtrar por estado (null = todos)
 * @param {boolean} options.autoRefresh - Se deve fazer polling a cada 5s (default true)
 * @param {boolean} options.enabled - Se a query deve executar (default true)
 * @returns {Object} Query result com jobs, counts, isLoading, etc.
 */
export function useBackgroundJobsQuery(options = {}) {
  const { statusFilter = null, autoRefresh = true, enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.backgroundJobs.list(statusFilter),
    queryFn: async () => {
      const response = await getBackgroundJobs(statusFilter);
      return response.data;
    },
    enabled,
    refetchInterval: autoRefresh ? AUTO_REFRESH_INTERVAL_MS : false,
  });

  const data = query.data;

  return {
    jobs: asArray(data?.jobs),
    counts: data?.counts ?? EMPTY_COUNTS,
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
 * Hook para as notificações de jobs bloqueados ("stuck").
 *
 * @param {Object} options - Opções do hook
 * @param {boolean} options.unreadOnly - Só notificações não lidas (default true)
 * @param {boolean} options.autoRefresh - Se deve fazer polling a cada 5s (default true)
 * @param {boolean} options.enabled - Se a query deve executar (default true)
 * @returns {Object} Query result com notifications, isLoading, etc.
 */
export function useBackgroundJobNotificationsQuery(options = {}) {
  const { unreadOnly = true, autoRefresh = true, enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.backgroundJobs.notifications(),
    queryFn: async () => {
      try {
        const response = await getBackgroundJobNotifications(unreadOnly);
        return asArray(response.data?.notifications);
      } catch {
        return EMPTY_LIST;
      }
    },
    enabled,
    refetchInterval: autoRefresh ? AUTO_REFRESH_INTERVAL_MS : false,
  });

  return {
    notifications: asArray(query.data),
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
 * Hook para as métricas agregadas de jobs (taxa de sucesso, duração média, etc.).
 *
 * @param {Object} options - Opções do hook
 * @param {number} options.days - Período em dias (default 7)
 * @param {boolean} options.enabled - Se a query deve executar (default true)
 * @returns {Object} Query result com metrics, isLoading, etc.
 */
export function useBackgroundJobMetricsQuery(options = {}) {
  const { days = 7, enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.backgroundJobs.metrics(days),
    queryFn: async () => {
      try {
        const response = await getBackgroundJobMetrics(days);
        return response.data;
      } catch {
        return null;
      }
    },
    enabled,
  });

  return {
    metrics: query.data ?? null,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    isSuccess: query.isSuccess,
    refetch: query.refetch,
    query,
  };
}

export default useBackgroundJobsQuery;
