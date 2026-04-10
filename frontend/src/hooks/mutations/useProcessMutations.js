/**
 * ====================================================================
 * USE PROCESS MUTATIONS - TanStack Query Mutation Hooks
 * ====================================================================
 * Hooks para operações de escrita (mutations) com invalidação automática.
 * 
 * PADRÃO:
 * 1. useMutation para a operação de escrita
 * 2. Optimistic update para feedback imediato
 * 3. onSettled para invalidar queries relacionadas
 * 4. Rollback automático em caso de erro
 * ====================================================================
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import { toast } from 'sonner';
import { moveProcessKanban, updateProcess, assignProcess, createActivity } from '../../services/api';

/**
 * Hook para mover processo no Kanban (Drag & Drop)
 * 
 * @param {Object} options - Opções do hook
 * @returns {Object} Mutation object com mutate, isPending, etc.
 */
export function useMoveProcessMutation(options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError } = options;

  return useMutation({
    mutationFn: async ({ processId, newStatus, oldStatus }) => {
      const response = await moveProcessKanban(processId, newStatus);
      return response.data;
    },
    
    // Optimistic update - atualiza a UI antes da resposta do servidor
    onMutate: async ({ processId, newStatus, oldStatus }) => {
      // Cancelar queries em flight para evitar race conditions
      await queryClient.cancelQueries({ queryKey: queryKeys.processes.all });
      
      // Snapshot do estado anterior para rollback
      const previousKanban = queryClient.getQueryData(queryKeys.processes.kanban({}));
      
      // Optimistic update
      queryClient.setQueryData(queryKeys.processes.kanban({}), (oldData) => {
        if (!oldData) return oldData;
        
        const newColumns = oldData.columns.map(col => {
          // Remover da coluna antiga
          if (col.name === oldStatus) {
            return {
              ...col,
              processes: col.processes.filter(p => p.id !== processId),
              count: col.count - 1,
            };
          }
          // Adicionar à coluna nova
          if (col.name === newStatus) {
            const process = oldData.columns
              .find(c => c.name === oldStatus)
              ?.processes.find(p => p.id === processId);
            return {
              ...col,
              processes: process ? [...col.processes, { ...process, status: newStatus }] : col.processes,
              count: col.count + 1,
            };
          }
          return col;
        });
        
        return { ...oldData, columns: newColumns };
      });
      
      return { previousKanban };
    },
    
    // Sucesso - mostrar toast e invalidar
    onSuccess: (data, variables, context) => {
      toast.success('Processo movido com sucesso');
      onSuccess?.(data, variables, context);
    },
    
    // Erro - rollback e mostrar toast
    onError: (error, variables, context) => {
      // Rollback para o estado anterior
      if (context?.previousKanban) {
        queryClient.setQueryData(queryKeys.processes.kanban({}), context.previousKanban);
      }
      toast.error('Erro ao mover processo');
      onError?.(error, variables, context);
    },
    
    // Sempre invalidar para garantir sincronização
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.kanban({}) });
    },
  });
}

/**
 * Hook para atualizar dados do processo
 * 
 * @param {string|number} processId - ID do processo
 * @param {Object} options - Opções do hook
 * @returns {Object} Mutation object
 */
export function useUpdateProcessMutation(processId, options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError } = options;

  return useMutation({
    mutationFn: async (data) => {
      const response = await updateProcess(processId, data);
      return response.data;
    },
    
    onMutate: async (newData) => {
      await queryClient.cancelQueries({ queryKey: queryKeys.processes.detail(processId) });
      
      const previousProcess = queryClient.getQueryData(queryKeys.processes.detail(processId));
      
      // Optimistic update
      queryClient.setQueryData(queryKeys.processes.detail(processId), (old) => ({
        ...old,
        ...newData,
      }));
      
      return { previousProcess };
    },
    
    onSuccess: (data, variables, context) => {
      toast.success('Processo atualizado');
      onSuccess?.(data, variables, context);
    },
    
    onError: (error, variables, context) => {
      if (context?.previousProcess) {
        queryClient.setQueryData(queryKeys.processes.detail(processId), context.previousProcess);
      }
      toast.error('Erro ao atualizar processo');
      onError?.(error, variables, context);
    },
    
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.detail(processId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.kanban({}) });
    },
  });
}

/**
 * Hook para atribuir consultor/mediador ao processo
 * 
 * @param {string|number} processId - ID do processo
 * @param {Object} options - Opções do hook
 * @returns {Object} Mutation object
 */
export function useAssignProcessMutation(processId, options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError } = options;

  return useMutation({
    mutationFn: async ({ consultorId, mediadorId, indexacaoId }) => {
      const response = await assignProcess(processId, consultorId, mediadorId, indexacaoId);
      return response.data;
    },
    
    onSuccess: (data, variables, context) => {
      toast.success('Atribuição atualizada');
      // Invalidar queries relacionadas
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.detail(processId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.kanban({}) });
      onSuccess?.(data, variables, context);
    },
    
    onError: (error, variables, context) => {
      toast.error('Erro ao atribuir processo');
      onError?.(error, variables, context);
    },
  });
}

/**
 * Hook para adicionar atividade/comentário ao processo
 * Invalida automaticamente o histórico (Filme da Lead)
 * 
 * @param {string|number} processId - ID do processo
 * @param {Object} options - Opções do hook
 * @returns {Object} Mutation object
 */
export function useAddActivityMutation(processId, options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError } = options;

  return useMutation({
    mutationFn: async (data) => {
      const response = await createActivity({
        ...data,
        process_id: processId,
      });
      return response.data;
    },
    
    onSuccess: (data, variables, context) => {
      toast.success('Atividade adicionada');
      // Invalidar histórico para atualizar o "Filme da Lead"
      queryClient.invalidateQueries({ queryKey: queryKeys.history.byProcess(processId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.activities.byProcess(processId) });
      onSuccess?.(data, variables, context);
    },
    
    onError: (error, variables, context) => {
      toast.error('Erro ao adicionar atividade');
      onError?.(error, variables, context);
    },
  });
}

/**
 * Hook combinado com todas as mutations de processo
 * 
 * @param {string|number} processId - ID do processo
 * @param {Object} options - Opções do hook
 * @returns {Object} Todas as mutations
 */
export function useProcessMutations(processId, options = {}) {
  const moveProcess = useMoveProcessMutation();
  const updateProcess = useUpdateProcessMutation(processId);
  const assignProcess = useAssignProcessMutation(processId);
  const addActivity = useAddActivityMutation(processId);

  return {
    moveProcess,
    updateProcess,
    assignProcess,
    addActivity,
    
    // Loading state combinado
    isAnyPending: 
      moveProcess.isPending ||
      updateProcess.isPending ||
      assignProcess.isPending ||
      addActivity.isPending,
  };
}

export default useProcessMutations;
