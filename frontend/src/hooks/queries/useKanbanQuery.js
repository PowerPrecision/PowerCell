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
  
  // Incluir processos concluídos e desistências no Kanban
  // (a coluna "Concluídos" e "Desistências" devem estar visíveis)
  params.append('view_mode', 'all');
  // Visão global: mostrar todos os processos independentemente do utilizador
  params.append('show_all', 'true');
  
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
    throw new Error('Failed to fetch kanban data');
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
 * @returns {Object} Query result com data, isLoading, isError, etc.
 */
export function useKanbanQuery(options = {}) {
  const {
    token,
    consultorFilter = 'all',
    mediadorFilter = 'all',
    indexacaoFilter = 'all',
    parceiroFilter = 'all',
    enabled = true,
  } = options;

  // Criar objeto de filtros estável para a query key
  const filters = {
    consultor: consultorFilter,
    mediador: mediadorFilter,
    indexacao: indexacaoFilter,
    parceiro: parceiroFilter,
  };

  const query = useQuery({
    queryKey: queryKeys.processes.kanban(filters),
    queryFn: () => fetchKanbanData(token, {
      consultorFilter,
      mediadorFilter,
      indexacaoFilter,
      parceiroFilter,
    }),
    enabled: !!token && enabled,
    // staleTime de 1 minuto é ideal para Kanban
    // Dados são actualizados via WebSocket, não precisamos de refetch constante
    staleTime: 60 * 1000,
    // Não refetch automaticamente quando a window ganha foco
    // porque já temos WebSocket para updates em tempo real
    // Mas mantemos refetchOnWindowFocus: true (default) para casos
    // onde o WebSocket pode ter perdido eventos
  });

  return {
    // Dados principais
    kanbanData: query.data || { columns: [], total_processes: 0 },
    columns: query.data?.columns || [],
    totalProcesses: query.data?.total_processes || 0,
    
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
