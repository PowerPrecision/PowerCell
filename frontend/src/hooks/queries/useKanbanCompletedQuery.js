/**
 * ====================================================================
 * USE KANBAN COMPLETED QUERY - TanStack Query Hook (Isolado)
 * ====================================================================
 * Hook DEDICADO para buscar apenas os processos concluídos/desistências.
 *
 * PROBLEMA RESOLVIDO:
 * Antes, o filtro `completedDays` fazia parte da query key global do Kanban.
 * Quando o utilizador mudava o período de datas nos Concluídos, a query key
 * mudava e o React Query fazia fetch de TODAS as colunas (activas + inactivas),
 * provocando re-render total do quadro inteiro.
 *
 * SOLUÇÃO:
 * Query key INDEPENDENTE: ['processes', 'kanban-completed', { completedDays, ...filtros }]
 * Quando o `completedDays` muda, APENAS esta query é disparada. A query das
 * colunas activas (useKanbanQuery) não é afectada e os dados em cache são
 * servidos instantaneamente sem re-fetch.
 *
 * FUNCIONALIDADES:
 * - Fetch segmentado: apenas status concluidos + desistencias
 * - Cache key independente da query activa
 * - staleTime de 1 minuto (alinhado com useKanbanQuery)
 * - Skeleton loading apenas na coluna de Concluídos
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
 * Fetcher function para dados dos Concluídos
 * Reutiliza o mesmo endpoint /kanban mas com view_mode=concluidos_only
 * para buscar APENAS as colunas inactivas.
 */
const fetchKanbanCompletedData = async (token, filters) => {
  const params = parametrosDoKanban(filters);

  // Pelo cliente Axios: o interceptor injecta `X-Company-Id` e
  // `X-Active-Role`. Com um `fetch` cru (só `Authorization`), o
  // backend respondia sobre o papel BASE — o ContextSwitcher
  // mudava de cargo e o quadro não acompanhava.
  try {
    const { data } = await getKanbanBoard(params);
    return data;
  } catch (error) {
    const corpo = error?.response?.data;
    throw new Error(
      corpo?.detail || corpo?.message ||
      (error?.response ? `${error.response.status} ${error.response.statusText}` : null) ||
      'Failed to fetch completed kanban data'
    );
  }
};

/**
 * Hook para dados dos Concluídos (query segmentada e isolada)
 *
 * @param {Object} options - Opções do hook
 * @param {string} options.token - Token de autenticação
 * @param {string} options.consultorFilter - Filtro de consultor
 * @param {string} options.mediadorFilter - Filtro de mediador
 * @param {string} options.indexacaoFilter - Filtro de indexação
 * @param {string} options.parceiroFilter - Filtro de parceiro
 * @param {number} options.completedDays - Limitar concluídos aos últimos N dias (default 30, 0 = sem limite)
 * @param {boolean} options.enabled - Se a query deve executar
 * @returns {Object} Query result com data, isLoading, isFetching, etc.
 */
export function useKanbanCompletedQuery(options = {}) {
  const { token, enabled = true } = options;

  // Os filtros canónicos: é deste objecto que saem OS DOIS lados
  // (chave de cache e parâmetros do pedido).
  const filters = normalizarFiltros(options);

  const query = useQuery({
    // CHAVE INDEPENDENTE — não partilha cache com a query activa
    queryKey: queryKeys.processes.kanbanCompleted(filters),
    queryFn: () => fetchKanbanCompletedData(token, filters),
    enabled: !!token && enabled,
    staleTime: 60 * 1000, // 1 minuto (alinhado com useKanbanQuery)
    refetchOnWindowFocus: true,
  });

  // Extrair apenas as colunas concluidos + desistencias da resposta
  const inactiveColumns = (query.data?.columns || []).filter(
    col => col.name === 'concluidos' || col.name === 'desistencias'
  );

  return {
    // Dados principais (apenas colunas inactivas)
    completedData: query.data || { columns: [], total_processes: 0 },
    columns: inactiveColumns,
    totalInactive: query.data?.total_inactive || 0,

    // Estados de loading — estes são usados APENAS para o skeleton na coluna Concluídos
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isPending: query.isPending,

    // Estados de erro
    isError: query.isError,
    error: query.error,

    // Estados de dados
    isSuccess: query.isSuccess,

    // Funções de controle
    refetch: query.refetch,

    // Query object completo
    query,
  };
}

export default useKanbanCompletedQuery;
