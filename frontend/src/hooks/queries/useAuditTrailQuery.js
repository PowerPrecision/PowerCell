/**
 * ====================================================================
 * USE AUDIT TRAIL QUERY - TanStack Query Hook
 * ====================================================================
 * Hook para o registo de auditoria do sistema (RGPD — trilha de alterações).
 *
 * FUNCIONALIDADES:
 * - Fetch paginado de eventos de auditoria (GET /audit/trail), com filtros
 *   por processo, origem, período de datas e tipo de acção
 * - Query key inclui os parâmetros efectivos do pedido (filtros + página),
 *   garantindo caching independente por combinação e refetch automático
 *   quando os filtros ou a página mudam
 * - `buildAuditTrailFilterParams` é exportado para reutilização (ex: a
 *   exportação CSV em AuditTrailPage usa os mesmos filtros, sem paginação)
 * ====================================================================
 */

import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import { getAuditTrail } from '../../services/api';

const EMPTY_LIST = Object.freeze([]);

function asArray(data) {
  return Array.isArray(data) ? data : EMPTY_LIST;
}

/**
 * Constrói os parâmetros de filtro (sem paginação) partilhados entre a
 * listagem e a exportação CSV.
 *
 * @param {Object} filters
 * @param {string} [filters.filterProcessId]
 * @param {string} [filters.filterSource] - "all" é tratado como "sem filtro"
 * @param {string} [filters.filterDateFrom] - Data YYYY-MM-DD (início do dia)
 * @param {string} [filters.filterDateTo] - Data YYYY-MM-DD (fim do dia, 23:59:59.999)
 * @param {string} [filters.filterAction]
 * @returns {Object} Parâmetros prontos para a query string (process_id, source, date_from, date_to, action_type)
 */
export function buildAuditTrailFilterParams({
  filterProcessId = '',
  filterSource = 'all',
  filterDateFrom = '',
  filterDateTo = '',
  filterAction = '',
} = {}) {
  const params = {};
  if (filterProcessId.trim()) params.process_id = filterProcessId.trim();
  if (filterSource && filterSource !== 'all') params.source = filterSource;
  if (filterDateFrom) params.date_from = new Date(filterDateFrom).toISOString();
  if (filterDateTo) {
    const d = new Date(filterDateTo);
    d.setHours(23, 59, 59, 999);
    params.date_to = d.toISOString();
  }
  if (filterAction.trim()) params.action_type = filterAction.trim();
  return params;
}

/**
 * Constrói os parâmetros completos (filtros + paginação) para GET /audit/trail.
 *
 * @param {Object} filters - Ver `buildAuditTrailFilterParams`, mais:
 * @param {number} [filters.page=1]
 * @param {number} [filters.pageSize=50]
 * @returns {Object}
 */
export function buildAuditTrailParams({ page = 1, pageSize = 50, ...filters } = {}) {
  return {
    page,
    page_size: pageSize,
    ...buildAuditTrailFilterParams(filters),
  };
}

/**
 * Hook para a listagem paginada de auditoria (GET /audit/trail).
 *
 * @param {Object} filters - Ver `buildAuditTrailParams`
 * @param {Object} options - Opções do hook
 * @param {boolean} options.enabled - Se a query deve executar (default true)
 * @returns {Object} Query result com events, totalPages, total, isLoading, etc.
 */
export function useAuditTrailQuery(filters = {}, options = {}) {
  const { enabled = true } = options;
  const params = buildAuditTrailParams(filters);

  const query = useQuery({
    queryKey: queryKeys.audit.trail(params),
    queryFn: async () => {
      const response = await getAuditTrail(params);
      return response.data;
    },
    enabled,
  });

  const data = query.data;

  return {
    events: asArray(data?.items),
    totalPages: data?.total_pages ?? 0,
    total: data?.total ?? 0,
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

export default useAuditTrailQuery;
