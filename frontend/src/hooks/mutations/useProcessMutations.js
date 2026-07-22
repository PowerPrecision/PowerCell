/**
 * ====================================================================
 * USE PROCESS MUTATIONS - TanStack Query Mutation Hooks
 * ====================================================================
 * Hooks para operações de escrita (mutations) com invalidação automática.
 *
 * PADRÃO:
 * 1. useMutation para a operação de escrita
 * 2. Optimistic update para feedback imediato (merge nested seguro)
 * 3. onSettled para invalidar queries relacionadas
 * 4. Rollback automático em caso de erro
 *
 * Payload de updateProcess passa por sanitizeProcessUpdatePayload para
 * NÃO enviar arrays vazios / campos proibidos (documents, onedrive_links, …).
 * ====================================================================
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { queryKeys, invalidateProcessDetailsQueries } from '../../lib/queryClient';
import { toast } from 'sonner';
import {
  moveProcessKanban,
  updateProcess,
  updateClient,
  assignProcess,
  createActivity,
  deleteActivity,
  createDeadline,
  updateDeadline,
  deleteDeadline,
} from '../../services/api';
import {
  mergeProcessOptimistic,
  sanitizeProcessUpdatePayload,
  sanitizeClientUpdatePayload,
} from '../../pages/processDetails/processUpdatePayload';

function notifySuccess(options, message) {
  if (options?.silent) return;
  toast.success(message);
}

function notifyError(options, message) {
  if (options?.silent) return;
  toast.error(message);
}

/**
 * Hook para mover processo no Kanban (Drag & Drop)
 */
export function useMoveProcessMutation(addPendingMove, removePendingMove, options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError, onSettled, filters = {} } = options;

  return useMutation({
    mutationFn: async ({ processId, newStatus, oldStatus }) => {
      const response = await moveProcessKanban(processId, newStatus);
      return response.data;
    },

    onMutate: async ({ processId, newStatus, oldStatus }) => {
      const previousKanban = queryClient.getQueryData(queryKeys.processes.kanban(filters));

      queryClient.setQueryData(queryKeys.processes.kanban(filters), (oldData) => {
        if (!oldData) return oldData;

        const newColumns = oldData.columns.map(col => {
          if (col.name === oldStatus) {
            return {
              ...col,
              processes: col.processes.filter(p => p.id !== processId),
              count: col.count - 1,
            };
          }
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

      addPendingMove?.(processId);
      queryClient.cancelQueries({ queryKey: queryKeys.processes.all }).catch(() => {});

      return { previousKanban };
    },

    onSuccess: (data, variables, context) => {
      notifySuccess(options, 'Processo movido com sucesso');
      onSuccess?.(data, variables, context);
    },

    onError: (error, variables, context) => {
      if (context?.previousKanban) {
        queryClient.setQueryData(queryKeys.processes.kanban(filters), context.previousKanban);
      }
      notifyError(options, 'Erro ao mover processo');
      onError?.(error, variables, context);
    },

    onSettled: (_data, _error, variables) => {
      removePendingMove?.(variables.processId);
      onSettled?.(_data, _error, variables);
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.kanban(filters) });
    },
  });
}

/**
 * Hook para actualizar dados do processo (payload sanitizado).
 *
 * mutate / mutateAsync aceitam:
 * - objecto de campos directo, OU
 * - `{ payload, allowEmptyArrays }` para overrides por chamada
 *
 * @param {string|number} processId
 * @param {Object} options
 * @param {boolean} [options.silent] — sem toast (a página mostra o seu)
 * @param {string[]} [options.allowEmptyArrays] — default; ex.: ['labels']
 * @param {string} [options.clientId] — invalidar client detail no settle
 */
export function useUpdateProcessMutation(processId, options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError, onSettled, allowEmptyArrays: defaultAllowEmpty, clientId } = options;

  const resolveInput = (input) => {
    if (input && typeof input === 'object' && Object.prototype.hasOwnProperty.call(input, 'payload')) {
      return {
        data: input.payload,
        allowEmptyArrays: input.allowEmptyArrays ?? defaultAllowEmpty,
      };
    }
    return { data: input, allowEmptyArrays: defaultAllowEmpty };
  };

  return useMutation({
    mutationFn: async (input) => {
      const { data, allowEmptyArrays } = resolveInput(input);
      const safe = sanitizeProcessUpdatePayload(data, { allowEmptyArrays });
      const response = await updateProcess(processId, safe);
      return response.data;
    },

    onMutate: async (input) => {
      const { data, allowEmptyArrays } = resolveInput(input);
      await queryClient.cancelQueries({ queryKey: queryKeys.processes.detail(processId) });

      const previousProcess = queryClient.getQueryData(queryKeys.processes.detail(processId));
      const safe = sanitizeProcessUpdatePayload(data, { allowEmptyArrays });

      queryClient.setQueryData(queryKeys.processes.detail(processId), (old) =>
        mergeProcessOptimistic(old, safe)
      );

      return { previousProcess };
    },

    onSuccess: (data, variables, context) => {
      notifySuccess(options, 'Processo atualizado');
      onSuccess?.(data, variables, context);
    },

    onError: (error, variables, context) => {
      if (context?.previousProcess) {
        queryClient.setQueryData(queryKeys.processes.detail(processId), context.previousProcess);
      }
      notifyError(options, 'Erro ao atualizar processo');
      onError?.(error, variables, context);
    },

    onSettled: async (data, error, variables, context) => {
      await invalidateProcessDetailsQueries(queryClient, processId, {
        clientId: clientId || undefined,
      });
      onSettled?.(data, error, variables, context);
    },
  });
}

/**
 * Hook para actualizar o cliente ligado ao processo.
 * mutateAsync({ clientId, data })
 */
export function useUpdateClientMutation(options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError, onSettled, processId } = options;

  return useMutation({
    mutationFn: async ({ clientId, data }) => {
      if (!clientId) throw new Error('clientId em falta');
      const safe = sanitizeClientUpdatePayload(data);
      if (Object.keys(safe).length === 0) {
        return { skipped: true };
      }
      const response = await updateClient(clientId, safe);
      return response.data;
    },

    onSuccess: (data, variables, context) => {
      if (!data?.skipped) {
        notifySuccess(options, 'Cliente atualizado');
      }
      onSuccess?.(data, variables, context);
    },

    onError: (error, variables, context) => {
      notifyError(options, 'Erro ao atualizar cliente');
      onError?.(error, variables, context);
    },

    onSettled: async (data, error, variables, context) => {
      const cid = variables?.clientId;
      if (cid) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.clients.detail(cid) });
      }
      if (processId) {
        await queryClient.invalidateQueries({ queryKey: queryKeys.processes.detail(processId) });
      }
      onSettled?.(data, error, variables, context);
    },
  });
}

/**
 * Hook para atribuir consultor/mediador/indexação/parceiro (multi-assignee).
 */
export function useAssignProcessMutation(processId, options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError } = options;

  return useMutation({
    mutationFn: async (payload) => {
      // Compat: legacy (consultorId, mediadorId, indexacaoId) positional via object
      const response = await assignProcess(processId, payload);
      return response.data;
    },

    onSuccess: (data, variables, context) => {
      notifySuccess(options, 'Atribuição atualizada');
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.detail(processId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.kanban({}) });
      onSuccess?.(data, variables, context);
    },

    onError: (error, variables, context) => {
      notifyError(options, 'Erro ao atribuir processo');
      onError?.(error, variables, context);
    },
  });
}

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
      notifySuccess(options, 'Atividade adicionada');
      queryClient.invalidateQueries({ queryKey: queryKeys.history.byProcess(processId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.activities.byProcess(processId) });
      onSuccess?.(data, variables, context);
    },

    onError: (error, variables, context) => {
      notifyError(options, 'Erro ao adicionar atividade');
      onError?.(error, variables, context);
    },
  });
}

export function useDeleteActivityMutation(processId, options = {}) {
  const queryClient = useQueryClient();
  const { onSuccess, onError } = options;

  return useMutation({
    mutationFn: async (activityId) => {
      const response = await deleteActivity(activityId);
      return response.data;
    },
    onSuccess: (data, variables, context) => {
      notifySuccess(options, 'Comentário eliminado');
      queryClient.invalidateQueries({ queryKey: queryKeys.history.byProcess(processId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.activities.byProcess(processId) });
      onSuccess?.(data, variables, context);
    },
    onError: (error, variables, context) => {
      notifyError(options, 'Erro ao eliminar comentário');
      onError?.(error, variables, context);
    },
  });
}

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
      notifySuccess(options, 'Prazo criado com sucesso!');
      invalidate();
      onSuccess?.(data, variables, context);
    },
    onError: (error, variables, context) => {
      notifyError(options, 'Erro ao criar prazo');
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
      notifyError(options, 'Erro ao atualizar prazo');
      onError?.(error, variables, context);
    },
  });

  const remove = useMutation({
    mutationFn: async (deadlineId) => {
      const response = await deleteDeadline(deadlineId);
      return response.data;
    },
    onSuccess: (data, variables, context) => {
      notifySuccess(options, 'Prazo eliminado');
      invalidate();
      onSuccess?.(data, variables, context);
    },
    onError: (error, variables, context) => {
      notifyError(options, 'Erro ao eliminar prazo');
      onError?.(error, variables, context);
    },
  });

  return { create, update, remove };
}

/**
 * Hook combinado com todas as mutations de processo.
 */
export function useProcessMutations(processId, options = {}) {
  const clientId = options.clientId;
  const shared = { silent: options.silent, ...options };

  const moveProcess = useMoveProcessMutation(
    options.addPendingMove,
    options.removePendingMove,
    { ...shared, filters: options.filters }
  );
  const updateProcessMut = useUpdateProcessMutation(processId, {
    ...shared,
    clientId,
    allowEmptyArrays: options.allowEmptyArrays,
  });
  const updateClientMut = useUpdateClientMutation({
    ...shared,
    processId,
  });
  const assignProcessMut = useAssignProcessMutation(processId, shared);
  const addActivity = useAddActivityMutation(processId, shared);
  const deleteActivityMut = useDeleteActivityMutation(processId, shared);
  const deadlines = useProcessDeadlineMutations(processId, shared);

  return {
    moveProcess,
    updateProcess: updateProcessMut,
    updateClient: updateClientMut,
    assignProcess: assignProcessMut,
    addActivity,
    deleteActivity: deleteActivityMut,
    deadlines,

    isAnyPending:
      moveProcess.isPending ||
      updateProcessMut.isPending ||
      updateClientMut.isPending ||
      assignProcessMut.isPending ||
      addActivity.isPending ||
      deleteActivityMut.isPending ||
      deadlines.create.isPending ||
      deadlines.update.isPending ||
      deadlines.remove.isPending,
  };
}

export default useProcessMutations;
