/**
 * PACOTE FK — React Query para staff elegível em dropdowns de atribuição.
 * GET /users?for_assignment=true
 */
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "../../lib/queryClient";
import { getUsers, getWorkflowStatuses } from "../../services/api";

const EMPTY_LIST = Object.freeze([]);

/**
 * Staff para o filtro "Atribuído a" (exclui admin/indexação).
 */
export function useAssignmentUsersQuery(options = {}) {
  const { enabled = true } = options;
  const query = useQuery({
    queryKey: queryKeys.users.forAssignment(),
    queryFn: async () => {
      const res = await getUsers(undefined, { forAssignment: true });
      const data = res?.data;
      return Array.isArray(data) ? data : EMPTY_LIST;
    },
    enabled,
    staleTime: 60 * 1000,
  });

  return {
    users: Array.isArray(query.data) ? query.data : EMPTY_LIST,
    isLoading: query.isLoading,
    isError: query.isError,
    query,
  };
}

/**
 * Fases do workflow para o filtro "Estado do Processo".
 */
export function useWorkflowStatusesQuery(options = {}) {
  const { enabled = true } = options;
  const query = useQuery({
    queryKey: queryKeys.workflowStatuses.list(),
    queryFn: async () => {
      const res = await getWorkflowStatuses();
      const data = res?.data;
      return Array.isArray(data) ? data : EMPTY_LIST;
    },
    enabled,
    staleTime: 5 * 60 * 1000,
  });

  return {
    statuses: Array.isArray(query.data) ? query.data : EMPTY_LIST,
    isLoading: query.isLoading,
    query,
  };
}
