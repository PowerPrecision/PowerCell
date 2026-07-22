/**
 * ====================================================================
 * USE CLIENT REGISTRATIONS QUERY - TanStack Query Hooks
 * ====================================================================
 * Hooks para a página de administração de Registos de Clientes
 * (formulário público de registo).
 *
 * FUNCIONALIDADES:
 * - Listagem paginada e filtrável (pesquisa + estado) — GET /admin/client-registrations
 * - Estatísticas agregadas (hoje / semana / mês) — GET /admin/client-registrations/stats/summary
 * - `useClientRegistrationMutations` para editar/eliminar um registo, com
 *   invalidação automática da listagem + estatísticas após cada mutação
 * ====================================================================
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import {
  getClientRegistrations,
  getClientRegistrationsStats,
  updateClientRegistration,
  deleteClientRegistration,
} from '../../services/api';

const EMPTY_LIST = Object.freeze([]);

function asArray(data) {
  return Array.isArray(data) ? data : EMPTY_LIST;
}

/**
 * Constrói os parâmetros de pedido para GET /admin/client-registrations.
 *
 * @param {Object} filters
 * @param {string} [filters.search]
 * @param {string} [filters.statusFilter]
 * @param {number} [filters.page=1]
 * @param {number} [filters.limit=15]
 * @returns {Object}
 */
export function buildClientRegistrationsParams({
  search = '',
  statusFilter = '',
  page = 1,
  limit = 15,
} = {}) {
  const params = { page, limit };
  if (search) params.search = search;
  if (statusFilter) params.status = statusFilter;
  return params;
}

/**
 * Hook para a listagem paginada de registos de clientes.
 *
 * @param {Object} filters - Ver `buildClientRegistrationsParams`
 * @param {Object} options - Opções do hook
 * @param {boolean} options.enabled - Se a query deve executar (default true)
 * @returns {Object} Query result com registrations, total, totalPages, isLoading, etc.
 */
export function useClientRegistrationsQuery(filters = {}, options = {}) {
  const { enabled = true } = options;
  const params = buildClientRegistrationsParams(filters);

  const query = useQuery({
    queryKey: queryKeys.clientRegistrations.list(params),
    queryFn: async () => {
      const response = await getClientRegistrations(params);
      return response.data;
    },
    enabled,
  });

  const data = query.data;

  return {
    registrations: asArray(data?.registrations),
    total: data?.total ?? 0,
    totalPages: data?.pages ?? 1,
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
 * Hook para as estatísticas agregadas de registos de clientes.
 *
 * @param {Object} options - Opções do hook
 * @param {boolean} options.enabled - Se a query deve executar (default true)
 * @returns {Object} Query result com stats, isLoading, etc.
 */
export function useClientRegistrationsStatsQuery(options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.clientRegistrations.stats(),
    queryFn: async () => {
      const response = await getClientRegistrationsStats();
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

/**
 * Hook de mutações (editar / eliminar) para um registo de cliente, com
 * invalidação automática da listagem e das estatísticas após sucesso.
 *
 * @returns {Object} { updateRegistration, deleteRegistration } — mutation objects do TanStack Query
 */
export function useClientRegistrationMutations() {
  const queryClient = useQueryClient();

  const invalidateAll = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.clientRegistrations.all });
  };

  const updateRegistration = useMutation({
    mutationFn: ({ processId, data }) => updateClientRegistration(processId, data),
    onSuccess: invalidateAll,
  });

  const deleteRegistration = useMutation({
    mutationFn: (processId) => deleteClientRegistration(processId),
    onSuccess: invalidateAll,
  });

  return { updateRegistration, deleteRegistration };
}

export default useClientRegistrationsQuery;
