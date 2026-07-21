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
import {
  moveProcessKanban,
  updateProcess,
  assignProcess,
  createActivity,
  deleteActivity,
  createDeadline,
  updateDeadline,
  deleteDeadline,
} from '../../services/api';

/**
 * Hook para mover processo no Kanban (Drag & Drop)
 * 
 * @param {Function} addPendingMove - Callback para adicionar processo à lista de moves pendentes
 * @param {Function} removePendingMove - Callback para remover processo da lista de moves pendentes
 * @param {Object} options - Opções do hook
 * @param {Object} options.filters - Filtros ativos do Kanban para invalidação correta
 * @returns {Object} Mutation object com mutate, isPending, etc.
 */
export function useMoveProcessMutation(addPendingMove, removePendingMove, options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError, onSettled, filters = {} } = options;

  return useMutation({
    mutationFn: async ({ processId, newStatus, oldStatus }) => {
      const response = await moveProcessKanban(processId, newStatus);
      return response.data;
    },

    // PACOTE DB — Optimistic update REFORÇADO: setQueryData é executado
    // SÍNCRONO e PRIMEIRO (antes do cancelQueries com await) para garantir
    // que o cartão se move VISUALMENTE no momento do drop, sem delay.
    onMutate: async ({ processId, newStatus, oldStatus }) => {
      // Snapshot do estado anterior para rollback (síncrono)
      const previousKanban = queryClient.getQueryData(queryKeys.processes.kanban(filters));

      // Optimistic update IMEDIATO (síncrono — nenhuma await antes disto)
      queryClient.setQueryData(queryKeys.processes.kanban(filters), (oldData) => {
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

      // Track pending move for real-time sync exclusion (síncrono)
      addPendingMove?.(processId);

      // Cancelar queries em flight DEPOIS do setQueryData (fire-and-forget,
      // sem await) para não bloquear o optimistic update visual.
      queryClient.cancelQueries({ queryKey: queryKeys.processes.all }).catch(() => {});

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
        queryClient.setQueryData(queryKeys.processes.kanban(filters), context.previousKanban);
      }
      toast.error('Erro ao mover processo');
      onError?.(error, variables, context);
    },

    // Sempre invalidar para garantir sincronização
    onSettled: (_data, _error, variables) => {
      // Remove from pending moves after settled
      removePendingMove?.(variables.processId);
      // PACOTE DB — callback extra para limpar estado local de optimistic move
      onSettled?.(_data, _error, variables);
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.kanban(filters) });
    },
  });
}

/**
 * Hook para actualizar dados do processo
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
      // Invalidar histórico para actualizar o "Filme da Lead"
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
 * Hook para eliminar atividade/comentário
 */
export function useDeleteActivityMutation(processId, options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError } = options;

  return useMutation({
    mutationFn: async (activityId) => {
      const response = await deleteActivity(activityId);
      return response.data;
    },
    onSuccess: (data, variables, context) => {
      toast.success('Comentário eliminado');
      queryClient.invalidateQueries({ queryKey: queryKeys.history.byProcess(processId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.activities.byProcess(processId) });
      onSuccess?.(data, variables, context);
    },
    onError: (error, variables, context) => {
      toast.error('Erro ao eliminar comentário');
      onError?.(error, variables, context);
    },
  });
}

/**
 * Hook para criar/actualizar/eliminar deadlines do processo
 */
export function useProcessDeadlineMutations(processId, options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError } = options;

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.deadlines.byProcess(processId) });
    queryClient.invalidateQueries({ queryKey: queryKeys.processes.detail(processId) });
  };

  const create = useMutation({
    mutationFn: async (data) => {
      const response = await createDeadline({ ...data, process_id: processId });
      return response.data;
    },
    onSuccess: (data, variables, context) => {
      toast.success('Prazo criado com sucesso!');
      invalidate();
      onSuccess?.(data, variables, context);
    },
    onError: (error, variables, context) => {
      toast.error('Erro ao criar prazo');
      onError?.(error, variables, context);
    },
  });

  const update = useMutation({
    mutationFn: async ({ deadlineId, data }) => {
      const response = await updateDeadline(deadlineId, data);
      return response.data;
    },
    onSuccess: (data, variables, context) => {
      invalidate();
      onSuccess?.(data, variables, context);
    },
    onError: (error, variables, context) => {
      toast.error('Erro ao atualizar prazo');
      onError?.(error, variables, context);
    },
  });

  const remove = useMutation({
    mutationFn: async (deadlineId) => {
      const response = await deleteDeadline(deadlineId);
      return response.data;
    },
    onSuccess: (data, variables, context) => {
      toast.success('Prazo eliminado');
      invalidate();
      onSuccess?.(data, variables, context);
    },
    onError: (error, variables, context) => {
      toast.error('Erro ao eliminar prazo');
      onError?.(error, variables, context);
    },
  });

  return { create, update, remove };
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
  const deleteActivityMut = useDeleteActivityMutation(processId);
  const deadlines = useProcessDeadlineMutations(processId);

  return {
    moveProcess,
    updateProcess,
    assignProcess,
    addActivity,
    deleteActivity: deleteActivityMut,
    deadlines,
    
    // Loading state combinado
    isAnyPending: 
      moveProcess.isPending ||
      updateProcess.isPending ||
      assignProcess.isPending ||
      addActivity.isPending ||
      deleteActivityMut.isPending ||
      deadlines.create.isPending ||
      deadlines.update.isPending ||
      deadlines.remove.isPending,
  };
}

export default useProcessMutations;
