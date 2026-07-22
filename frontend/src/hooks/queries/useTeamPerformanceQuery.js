/**
 * ====================================================================
 * USE TEAM PERFORMANCE QUERY - TanStack Query Hook
 * ====================================================================
 * Hook para métricas de desempenho da equipa (Admin/CEO).
 *
 * FUNCIONALIDADES:
 * - Fetch de resumo (summary) + lista de colaboradores (users) para um
 *   período de datas (start_date / end_date)
 * - Caching automático por período (query key inclui as datas), com
 *   refetch automático quando o período seleccionado muda
 * - Normalização defensiva da resposta (summary sempre objecto, users
 *   sempre array) para blindar a UI contra respostas inesperadas
 * ====================================================================
 */

import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import { getTeamPerformance } from '../../services/api';

const EMPTY_LIST = Object.freeze([]);
const EMPTY_SUMMARY = Object.freeze({});

function asArray(data) {
  return Array.isArray(data) ? data : EMPTY_LIST;
}

function asObject(data) {
  return data && typeof data === 'object' && !Array.isArray(data) ? data : EMPTY_SUMMARY;
}

/**
 * Hook para desempenho da equipa num período (GET /admin/team-performance).
 *
 * @param {string} startDate - Data de início (YYYY-MM-DD)
 * @param {string} endDate - Data de fim (YYYY-MM-DD)
 * @param {Object} options - Opções do hook
 * @param {boolean} options.enabled - Se a query deve executar (default true)
 * @returns {Object} Query result com summary, users, periodStart, periodEnd, isLoading, etc.
 */
export function useTeamPerformanceQuery(startDate, endDate, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.teamPerformance.range(startDate, endDate),
    queryFn: async () => {
      const response = await getTeamPerformance({
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });
      return response.data;
    },
    enabled,
    staleTime: 60 * 1000, // 1 minuto
  });

  const data = query.data;

  return {
    summary: asObject(data?.summary),
    users: asArray(data?.users),
    periodStart: data?.period_start ?? null,
    periodEnd: data?.period_end ?? null,
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

export default useTeamPerformanceQuery;
