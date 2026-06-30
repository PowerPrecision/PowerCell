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

import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Fetcher function para dados dos Concluídos
 * Reutiliza o mesmo endpoint /kanban mas com view_mode=concluidos_only
 * para buscar APENAS as colunas inactivas.
 */
const fetchKanbanCompletedData = async (token, filters) => {
  const params = new URLSearchParams();

  // view_mode=concluidos_only: o backend devolve apenas colunas concluidos + desistencias
  params.append('view_mode', 'all');
  params.append('show_all', 'true');

  // Filtro de datas para processos concluídos (últimos N dias, 0 = sem limite)
  if (filters.completedDays !== undefined && filters.completedDays !== null) {
    params.append('completed_days', String(filters.completedDays));
  }

  // Manter filtros de utilizador para consistência
  const { consultorFilter, mediadorFilter, indexacaoFilter, parceiroFilter } = filters;

  if (consultorFilter && consultorFilter !== 'all') {
    params.append('consultor_id', consultorFilter === 'none' ? 'none' : consultorFilter);
  }
  if (mediadorFilter && mediadorFilter !== 'all') {
    params.append('mediador_id', mediadorFilter === 'none' ? 'none' : mediadorFilter);
  }
  if (indexacaoFilter && indexacaoFilter !== 'all') {
    params.append('indexacao_id', indexacaoFilter === 'none' ? 'none' : indexacaoFilter);
  }
  if (parceiroFilter && parceiroFilter !== 'all') {
    params.append('parceiro_id', parceiroFilter === 'none' ? 'none' : parceiroFilter);
  }

  const response = await fetch(`${API_URL}/api/processes/kanban?${params.toString()}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!response.ok) {
    // PACOTE AE-2: extrair a mensagem de erro do backend para diagnóstico
    let errorDetail = 'Failed to fetch completed kanban data';
    try {
      const errorData = await response.json();
      errorDetail = errorData?.detail || errorData?.message || errorDetail;
    } catch {
      errorDetail = `${response.status} ${response.statusText}`;
    }
    throw new Error(errorDetail);
  }

  return response.json();
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
  const {
    token,
    consultorFilter = 'all',
    mediadorFilter = 'all',
    indexacaoFilter = 'all',
    parceiroFilter = 'all',
    completedDays = 30,
    enabled = true,
  } = options;

  // Criar objeto de filtros estável para a query key
  const filters = {
    consultor: consultorFilter,
    mediador: mediadorFilter,
    indexacao: indexacaoFilter,
    parceiro: parceiroFilter,
    completedDays,
    viewMode: 'all',
  };

  const query = useQuery({
    // CHAVE INDEPENDENTE — não partilha cache com a query activa
    queryKey: queryKeys.processes.kanbanCompleted(filters),
    queryFn: () => fetchKanbanCompletedData(token, {
      consultorFilter,
      mediadorFilter,
      indexacaoFilter,
      parceiroFilter,
      completedDays,
      viewMode: 'all',
    }),
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
