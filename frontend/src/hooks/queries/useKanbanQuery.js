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

import { useQuery } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';

const API_URL = process.env.REACT_APP_BACKEND_URL;

/**
 * Fetcher function para dados do Kanban
 */
const fetchKanbanData = async (token, filters) => {
  const params = new URLSearchParams();
  
  // view_mode=all: mostrar processos ativos + concluídos/desistências
  params.append('view_mode', filters.viewMode || 'all');
  // Visão global: mostrar todos os processos independentemente do utilizador
  params.append('show_all', 'true');
  
  // Filtro de datas para processos concluídos (últimos N dias, 0 = sem limite)
  if (filters.completedDays !== undefined && filters.completedDays !== null) {
    params.append('completed_days', String(filters.completedDays));
  }
  
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
    let errorDetail = 'Failed to fetch kanban data';
    try {
      const errorData = await response.json();
      errorDetail = errorData?.detail || errorData?.message || errorDetail;
    } catch {
      // Se não for JSON, usar o status text
      errorDetail = `${response.status} ${response.statusText}`;
    }
    throw new Error(errorDetail);
  }

  return response.json();
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
    queryKey: queryKeys.processes.kanban(filters),
    queryFn: () => fetchKanbanData(token, {
      consultorFilter,
      mediadorFilter,
      indexacaoFilter,
      parceiroFilter,
      completedDays,
      viewMode: 'all',
    }),
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
    completedDays: query.data?.completed_days ?? completedDays,
    
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
