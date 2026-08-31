/**
 * ====================================================================
 * USE PORTAL REQUESTS QUERY - TanStack Query Hook
 * ====================================================================
 * Hook para a lista de pedidos de documentos do Portal do Cliente
 * (`PortalDocumentRequests`). Usa a queryKey `queryKeys.portalRequests.byProcess`
 * para que qualquer mutação relacionada (upload interno no S3FileManager,
 * criar/aceitar/reativar/remover pedido) possa invalidar esta query e
 * fazer o estado reagir em tempo real, sem necessidade de refresh manual.
 * ====================================================================
 */

import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import { getPortalDocRequests } from '../../services/api';

const EMPTY_LIST = Object.freeze([]);

/** 30s — pedidos do portal mudam com frequência (upload do cliente/equipa). */
export const PORTAL_REQUESTS_STALE_TIME_MS = 30 * 1000;

/**
 * Hook para os pedidos de documentos do portal de um processo.
 *
 * @param {string} processId - ID do processo
 * @param {Object} options - Opções do hook
 * @param {boolean} [options.enabled=true] - Se a query deve executar
 */
export function usePortalRequestsQuery(processId, options = {}) {
  const { enabled = true } = options;

  const query = useQuery({
    queryKey: queryKeys.portalRequests.byProcess(processId),
    queryFn: async () => {
      const response = await getPortalDocRequests(processId);
      return Array.isArray(response.data?.documents) ? response.data.documents : EMPTY_LIST;
    },
    enabled: !!processId && enabled,
    staleTime: PORTAL_REQUESTS_STALE_TIME_MS,
  });

  return {
    documents: query.data || EMPTY_LIST,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    query,
  };
}

export default usePortalRequestsQuery;
