/**
 * ====================================================================
 * USE KANBAN REALTIME - WebSocket + React Query Integration
 * ====================================================================
 * Hook que integra WebSocket com React Query para updates em tempo real.
 * 
 * ESTRATÉGIA DE CACHE UPDATE:
 * - Não usamos invalidateQueries (evita refetch pesado)
 * - Usamos setQueryData para updates otimistas
 * - O React re-renderiza automaticamente os componentes afetados
 * 
 * FLUXO:
 * 1. WebSocket recebe evento (PROCESS_STATUS_CHANGED, etc.)
 * 2. Handler atualiza o cache diretamente via setQueryData
 * 3. React detecta mudança e re-renderiza apenas o cartão afetado
 * ====================================================================
 */

import { useEffect, useCallback, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '../../lib/queryClient';
import { useWebSocket, WSEventType } from '../useWebSocket';

/**
 * Hook para sincronização em tempo real do Kanban
 * 
 * @param {Object} options - Opções do hook
 * @param {Object} options.filters - Filtros ativos do Kanban
 * @param {Function} options.onNotification - Callback para notificações
 * @param {string|number} options.userId - ID do utilizador atual (para sender exclusion)
 * @returns {Object} Estado de conexão e funções de controle
 */
export function useKanbanRealtime(options = {}) {
  const {
    filters = {},
    onNotification,
    userId,
  } = options;

  const queryClient = useQueryClient();
  const filtersRef = useRef(filters);
  const pendingMovesRef = useRef(new Set());
  const [lockedProcesses, setLockedProcesses] = useState({});
  
  // Manter filters atualizados no ref
  useEffect(() => {
    filtersRef.current = filters;
  }, [filters]);

  /**
   * Atualiza o cache do Kanban quando um processo é criado
   */
  const handleProcessCreated = useCallback((payload) => {
    if (!payload || !payload.process_id) return;

    const currentFilters = filtersRef.current;
    const queryKey = queryKeys.processes.kanban(currentFilters);

    queryClient.setQueryData(queryKey, (oldData) => {
      if (!oldData) return oldData;

      const targetStatus = payload.status || 'clientes_espera';
      const newColumns = oldData.columns.map(col => ({ ...col, processes: [...col.processes] }));
      
      const targetColIndex = newColumns.findIndex(col => col.name === targetStatus);
      if (targetColIndex >= 0) {
        const newProcess = {
          id: payload.process_id,
          process_number: payload.process_number,
          client_name: payload.client_name || 'Novo Cliente',
          status: targetStatus,
          priority: payload.priority,
          process_type: payload.process_type,
          consultor_names: payload.consultor_names || [],
          mediador_names: payload.mediador_names || [],
          updated_at: payload.updated_at,
        };
        newColumns[targetColIndex].processes.unshift(newProcess);
        newColumns[targetColIndex].count += 1;
      }

      onNotification?.({
        type: 'info',
        message: `Novo processo: ${payload.client_name || 'Novo Cliente'}`,
      });

      return {
        ...oldData,
        columns: newColumns,
        total_processes: (oldData.total_processes || 0) + 1,
      };
    });
  }, [queryClient, onNotification]);

  /**
   * Atualiza o cache do Kanban quando o status de um processo muda
   */
  const handleProcessStatusChanged = useCallback((payload) => {
    if (!payload || !payload.process_id) return;

    const currentFilters = filtersRef.current;
    const queryKey = queryKeys.processes.kanban(currentFilters);

    queryClient.setQueryData(queryKey, (oldData) => {
      if (!oldData) return oldData;

      const sourceStatus = payload.old_status;
      const targetStatus = payload.status;
      const newColumns = oldData.columns.map(col => ({ ...col, processes: [...col.processes] }));
      let movedProcess = null;

      // Remover da coluna de origem
      const sourceColIndex = newColumns.findIndex(col => col.name === sourceStatus);
      if (sourceColIndex >= 0) {
        const processIndex = newColumns[sourceColIndex].processes.findIndex(
          p => p.id === payload.process_id
        );
        if (processIndex >= 0) {
          movedProcess = {
            ...newColumns[sourceColIndex].processes[processIndex],
            status: targetStatus,
            updated_at: payload.updated_at,
          };
          newColumns[sourceColIndex].processes.splice(processIndex, 1);
          newColumns[sourceColIndex].count -= 1;
        }
      }

      // Adicionar à coluna de destino
      const targetColIndex = newColumns.findIndex(col => col.name === targetStatus);
      if (targetColIndex >= 0) {
        if (movedProcess) {
          newColumns[targetColIndex].processes.unshift(movedProcess);
          newColumns[targetColIndex].count += 1;
        } else {
          // Processo não estava na cache, adicionar como novo
          newColumns[targetColIndex].processes.unshift({
            id: payload.process_id,
            process_number: payload.process_number,
            client_name: payload.client_name || 'Cliente',
            status: targetStatus,
            updated_at: payload.updated_at,
          });
          newColumns[targetColIndex].count += 1;
        }
      }

      return { ...oldData, columns: newColumns };
    });

    // Também invalidar o detalhe do processo para forçar refetch
    // quando o utilizador abrir os detalhes
    queryClient.invalidateQueries({
      queryKey: queryKeys.processes.detail(payload.process_id),
    });
  }, [queryClient]);

  /**
   * Atualiza o cache do Kanban quando um processo é atualizado
   */
  const handleProcessUpdated = useCallback((payload) => {
    if (!payload || !payload.process_id) return;

    const currentFilters = filtersRef.current;
    const queryKey = queryKeys.processes.kanban(currentFilters);

    queryClient.setQueryData(queryKey, (oldData) => {
      if (!oldData) return oldData;

      const newColumns = oldData.columns.map(col => ({ ...col, processes: [...col.processes] }));

      for (const col of newColumns) {
        const processIndex = col.processes.findIndex(p => p.id === payload.process_id);
        if (processIndex >= 0) {
          col.processes[processIndex] = {
            ...col.processes[processIndex],
            ...(payload.client_name && { client_name: payload.client_name }),
            ...(payload.priority && { priority: payload.priority }),
            ...(payload.consultor_names && { consultor_names: payload.consultor_names }),
            ...(payload.mediador_names && { mediador_names: payload.mediador_names }),
            updated_at: payload.updated_at,
          };
          break;
        }
      }

      return { ...oldData, columns: newColumns };
    });

    // Invalidar detalhes do processo
    queryClient.invalidateQueries({
      queryKey: queryKeys.processes.detail(payload.process_id),
    });
  }, [queryClient]);

  /**
   * Handler para atribuição de processo
   */
  const handleProcessAssigned = useCallback((payload) => {
    // Similar ao handleProcessUpdated
    handleProcessUpdated(payload);
  }, [handleProcessUpdated]);

  /**
   * Handler centralizado para eventos do WebSocket
   */
  const handleProcessUpdate = useCallback((eventType, payload) => {
    switch (eventType) {
      case WSEventType.PROCESS_CREATED:
        handleProcessCreated(payload);
        break;
      case WSEventType.PROCESS_STATUS_CHANGED:
        handleProcessStatusChanged(payload);
        break;
      case WSEventType.PROCESS_UPDATED:
        handleProcessUpdated(payload);
        break;
      case WSEventType.PROCESS_ASSIGNED:
        handleProcessAssigned(payload);
        break;
      default:
        break;
    }
  }, [handleProcessCreated, handleProcessStatusChanged, handleProcessUpdated, handleProcessAssigned]);

  // Conectar ao WebSocket
  const { isConnected, on, off, sendMessage } = useWebSocket({
    onProcessUpdate: handleProcessUpdate,
    autoConnect: true,
  });

  // Subscrever aos eventos do WebSocket
  useEffect(() => {
    const unsubscribers = [
      on(WSEventType.PROCESS_CREATED, (data) => handleProcessUpdate(WSEventType.PROCESS_CREATED, data)),
      on(WSEventType.PROCESS_STATUS_CHANGED, (data) => handleProcessUpdate(WSEventType.PROCESS_STATUS_CHANGED, data)),
      on(WSEventType.PROCESS_UPDATED, (data) => handleProcessUpdate(WSEventType.PROCESS_UPDATED, data)),
      on(WSEventType.PROCESS_ASSIGNED, (data) => handleProcessUpdate(WSEventType.PROCESS_ASSIGNED, data)),

      // Listen for PROCESS_MOVED from other users (real-time sync)
      // This is idempotent — safe if PROCESS_STATUS_CHANGED already processed the same move
      on(WSEventType.PROCESS_MOVED, (payload) => {
          // Skip if this move was initiated by the current user (optimistic update handles it)
          if (payload.user_id === userId) return;

          queryClient.setQueryData(
              queryKeys.processes.kanban(filtersRef.current),
              (oldData) => {
                  if (!oldData?.columns) return oldData;

                  return {
                      ...oldData,
                      columns: oldData.columns.map((col) => {
                          // Remove from old column (only if still present — idempotent)
                          if (col.name === payload.old_status) {
                              const stillExists = col.processes.some((p) => p.id === payload.process_id);
                              if (!stillExists) return col; // Already removed by PROCESS_STATUS_CHANGED
                              return {
                                  ...col,
                                  processes: col.processes.filter((p) => p.id !== payload.process_id),
                                  count: Math.max(0, col.count - 1),
                              };
                          }
                          // Add to new column (avoid duplicates — idempotent)
                          if (col.name === payload.new_status) {
                              const alreadyExists = col.processes.some((p) => p.id === payload.process_id);
                              if (alreadyExists) {
                                  // Just update fields, don't change count
                                  return {
                                      ...col,
                                      processes: col.processes.map((p) =>
                                          p.id === payload.process_id
                                              ? { ...p, status: payload.new_status, updated_at: new Date().toISOString() }
                                              : p
                                      ),
                                  };
                              }
                              // Find process data from old column
                              const oldColumn = oldData.columns.find((c) => c.name === payload.old_status);
                              const processData = oldColumn?.processes.find((p) => p.id === payload.process_id);
                              return {
                                  ...col,
                                  processes: [
                                      {
                                          ...(processData || { id: payload.process_id }),
                                          status: payload.new_status,
                                          client_name: payload.client_name,
                                          process_number: payload.process_number,
                                          updated_at: new Date().toISOString(),
                                      },
                                      ...col.processes,
                                  ],
                                  count: col.count + 1,
                              };
                          }
                          return col;
                      }),
                  };
              }
          );
      }),

      // Listen for PROCESS_LOCKED from other users
      on(WSEventType.PROCESS_LOCKED, (payload) => {
          if (payload.user_id === userId) return; // Don't lock for self
          setLockedProcesses((prev) => ({
              ...prev,
              [payload.process_id]: { user_name: payload.user_name, user_id: payload.user_id },
          }));
      }),

      // Listen for PROCESS_UNLOCKED
      on(WSEventType.PROCESS_UNLOCKED, (payload) => {
          setLockedProcesses((prev) => {
              const next = { ...prev };
              delete next[payload.process_id];
              return next;
          });
      }),
    ];

    return () => {
      unsubscribers.forEach(unsub => unsub?.());
    };
  }, [on, handleProcessUpdate, userId, queryClient]);

  return {
    isConnected,
    lockedProcesses,
    sendMessage,
    // Função para forçar invalidação manual
    invalidateKanban: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.processes.kanban(filtersRef.current),
      });
    },
    // Pending move tracking for optimistic updates
    addPendingMove: (processId) => pendingMovesRef.current.add(processId),
    removePendingMove: (processId) => pendingMovesRef.current.delete(processId),
    isPendingMove: (processId) => pendingMovesRef.current.has(processId),
  };
}

export default useKanbanRealtime;
