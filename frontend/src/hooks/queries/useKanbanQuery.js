/**
 * ====================================================================
 * USE KANBAN QUERY - TanStack Query Hook
 * ====================================================================
 * Hook para gestão de dados do Kanban com caching automático.
 * 
 * FUNCIONALIDADES:
 * - Fetch automático com caching
 * - Refetch on window focus
 * - Integração com WebSocket para updates em tempo real
 * - Estados derivados (isLoading, isError, etc.)
 * - Filtro de datas para processos concluídos (completed_days)
 * ====================================================================
 */

/**
 * CORRECÇÃO (Lote 4, ponto 1) — a canalização estava cortada ao meio.
 * O fetcher lia `filters.labels` e montava os parâmetros; o hook
 * destruturava uma lista FIXA de opções, descartava as etiquetas e
 * reconstruía um objecto novo para o `queryFn` — e a chave de cache
 * também as ignorava. Resultado: o filtro de etiquetas do quadro não
 * enviava nada ao servidor e, por não entrar na chave, não provocava
 * sequer um pedido. Hoje os parâmetros E a chave derivam do mesmo
 * `utils/kanbanFiltros.js`, que tem um teste a flipar cada filtro.
 */
import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import { getKanbanBoard } from '../../services/api';
import { normalizarFiltros, parametrosDoKanban } from '../../utils/kanbanFiltros';

/**
 * Fetcher function para dados do Kanban
 */
const fetchKanbanData = async (token, filters) => {
  const params = parametrosDoKanban(filters);

  // Pelo cliente Axios: o interceptor injecta `X-Company-Id` e
  // `X-Active-Role`. Com um `fetch` cru (só `Authorization`), o
  // backend respondia sobre o papel BASE — o ContextSwitcher
  // mudava de cargo e o quadro não acompanhava.
  try {
    const { data } = await getKanbanBoard(params);
    return data;
  } catch (error) {
    // PACOTE AE-2: manter a mensagem do backend para diagnóstico.
    const corpo = error?.response?.data;
    throw new Error(
      corpo?.detail || corpo?.message ||
      (error?.response ? `${error.response.status} ${error.response.statusText}` : null) ||
      'Failed to fetch kanban data'
    );
  }
};

/**
 * Hook para dados do Kanban
 * 
 * @param {Object} options - Opções do hook
 * @param {string} options.token - Token de autenticação
 * @param {string} options.consultorFilter - Filtro de consultor
 * @param {string} options.mediadorFilter - Filtro de mediador
 * @param {string} options.indexacaoFilter - Filtro de indexação
 * @param {string} options.parceiroFilter - Filtro de parceiro
 * @param {boolean} options.enabled - Se a query deve executar
 * @param {number} options.completedDays - Limitar concluídos aos últimos N dias (default 30, 0 = sem limite)
 * @returns {Object} Query result com data, isLoading, isError, etc.
 */
export function useKanbanQuery(options = {}) {
  const { token, enabled = true } = options;

  // Os filtros canónicos: é deste objecto que saem OS DOIS lados
  // (chave de cache e parâmetros do pedido).
  const filters = normalizarFiltros(options);

  const query = useQuery({
    queryKey: queryKeys.processes.kanban(filters),
    queryFn: () => fetchKanbanData(token, filters),
    enabled: !!token && enabled,
    // staleTime de 1 minuto é ideal para Kanban
    // Dados são actualizados via WebSocket, não precisamos de refetch constante
    staleTime: 60 * 1000,
    // PACOTE AE-2: limitar retries para evitar loop de 500s em produção.
    // Se o backend estiver com erro persistente, não adianta refetch infinito.
    retry: 2,
    // Não refetch automaticamente quando a window ganha foco se houver erro
    refetchOnWindowFocus: (query) => !query.state.error,
  });

  return {
    // Dados principais
    kanbanData: query.data || { columns: [], total_processes: 0 },
    columns: query.data?.columns || [],
    totalProcesses: query.data?.total_processes || 0,
    totalInactive: query.data?.total_inactive || 0,
    completedDays: query.data?.completed_days ?? filters.completedDays,
    
    // Estados de loading
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isPending: query.isPending,
    
    // Estados de erro
    isError: query.isError,
    error: query.error,
    
    // Estados de dados
    isSuccess: query.isSuccess,
    isStale: query.isStale,
    dataUpdatedAt: query.dataUpdatedAt,
    
    // Funções de controle
    refetch: query.refetch,
    
    // Query object completo (para uso avançado)
    query,
  };
}

export default useKanbanQuery;
