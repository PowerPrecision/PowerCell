/**
 * ====================================================================
 * USE AUDIT STATS QUERY - TanStack Query Hook
 * ====================================================================
 * Hook para os KPIs do cabeçalho da página de Auditoria (GET /audit/stats):
 * alterações hoje, esta semana, aprovações IA e alterações críticas.
 * ====================================================================
 */

import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import { getAuditStats } from '../../services/api';

/**
 * Hook para as estatísticas agregadas de auditoria.
 *
 * @param {Object} options - Opções do hook
 * @param {boolean} options.enabled - Se a query deve executar (default true)
 * @returns {Object} Query result com stats, isLoading, isFetching, isError, etc.
 */
export function useAuditStatsQuery(options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.audit.stats(),
    queryFn: async () => {
      const response = await getAuditStats();
      return response.data;
    },
    enabled,
  });

  return {
    stats: query.data ?? null,
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

export default useAuditStatsQuery;
