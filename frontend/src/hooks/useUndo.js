/**
 * useUndo - Hook para implementar funcionalidade de Undo (Desfazer)
 * 
 * Permite que ações sejam revertidas dentro de um período de tempo.
 * Utiliza o sistema de toasts para mostrar um botão "Desfazer".
 * 
 * Uso:
 * const { executeWithUndo } = useUndo();
 * 
 * executeWithUndo({
 *   action: () => deleteItem(id),
 *   undo: () => restoreItem(id, itemData),
 *   message: 'Item eliminado',
 *   undoLabel: 'Desfazer'
 * });
 */
import { useCallback } from 'react';
import { toast } from 'sonner';

// Tempo padrão para desfazer (5 segundos)
const DEFAULT_UNDO_TIMEOUT = 5000;

// Armazenar referências para timeouts (para cancelar)
const pendingActions = new Map();

/**
 * Hook para executar ações com possibilidade de desfazer.
 * 
 * @returns {Object} { executeWithUndo, cancelUndo }
 */
export function useUndo() {
  /**
   * Executa uma ação com possibilidade de desfazer.
   * 
   * @param {Object} options
   * @param {Function} options.action - Função assíncrona que executa a ação principal
   * @param {Function} options.undo - Função assíncrona que reverte a ação
   * @param {string} options.message - Mensagem a mostrar no toast
   * @param {string} [options.undoLabel='Desfazer'] - Texto do botão de desfazer
   * @param {number} [options.timeout=5000] - Tempo em ms para desfazer
   * @param {Function} [options.onCommit] - Callback quando a ação é finalizada (sem undo)
   * @param {Function} [options.onUndo] - Callback quando a ação é desfeita
   * @param {string} [options.type='success'] - Tipo do toast (success, error, warning, info)
   */
  const executeWithUndo = useCallback(async ({
    action,
    undo,
    message,
    undoLabel = 'Desfazer',
    timeout = DEFAULT_UNDO_TIMEOUT,
    onCommit,
    onUndo,
    type = 'success',
    actionId = null, // ID opcional para identificar a ação
  }) => {
    // Gerar ID único para esta ação
    const id = actionId || `undo-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    // Dados para reverter (capturados antes da ação)
    let undoData = null;
    
    try {
      // Executar a ação principal
      const result = await action();
      
      // Se a ação retornou dados para undo, guardá-los
      if (result && result.undoData) {
        undoData = result.undoData;
      }
      
      // Criar função de undo que será executada se o utilizador clicar
      const performUndo = async () => {
        // Limpar o timeout
        if (pendingActions.has(id)) {
          clearTimeout(pendingActions.get(id));
          pendingActions.delete(id);
        }
        
        try {
          await undo(undoData);
          
          toast.success('Ação desfeita', {
            description: 'A alteração foi revertida com sucesso.'
          });
          
          if (onUndo) {
            onUndo();
          }
        } catch (error) {
          console.error('Erro ao desfazer ação:', error);
          toast.error('Erro ao desfazer', {
            description: 'Não foi possível reverter a ação.'
          });
        }
      };
      
      // Mostrar toast com botão de undo
      const toastId = toast[type](message, {
        action: {
          label: undoLabel,
          onClick: performUndo
        },
        duration: timeout,
      });
      
      // Configurar timeout para quando o toast fechar
      const timeoutId = setTimeout(() => {
        // Remover da lista de pendentes
        pendingActions.delete(id);
        
        // Executar callback de commit (ação finalizada)
        if (onCommit) {
          onCommit();
        }
      }, timeout);
      
      // Guardar referência
      pendingActions.set(id, timeoutId);
      
      return { success: true, id, toastId };
      
    } catch (error) {
      console.error('Erro ao executar ação:', error);
      
      // Se a ação falhou, mostrar erro
      toast.error('Erro', {
        description: error.message || 'Ocorreu um erro ao executar a ação.'
      });
      
      return { success: false, error };
    }
  }, []);

  /**
   * Cancela uma ação pendente (impede undo).
   * 
   * @param {string} id - ID da ação a cancelar
   */
  const cancelUndo = useCallback((id) => {
    if (pendingActions.has(id)) {
      clearTimeout(pendingActions.get(id));
      pendingActions.delete(id);
    }
  }, []);

  /**
   * Executa uma ação imediatamente (sem undo).
   * Útil para ações destrutivas que precisam de confirmação.
   */
  const executeImmediately = useCallback(async ({
    action,
    message,
    type = 'success',
  }) => {
    try {
      await action();
      toast[type](message);
      return { success: true };
    } catch (error) {
      console.error('Erro ao executar ação:', error);
      toast.error('Erro', {
        description: error.message || 'Ocorreu um erro.'
      });
      return { success: false, error };
    }
  }, []);

  return {
    executeWithUndo,
    cancelUndo,
    executeImmediately,
  };
}

/**
 * Hook simplificado para ações comuns com undo.
 */
export function useUndoActions() {
  const { executeWithUndo, executeImmediately } = useUndo();

  /**
   * Eliminar um processo com undo.
   */
  const deleteProcessWithUndo = useCallback(async (processId, processName, api) => {
    return executeWithUndo({
      action: async () => {
        // Primeiro, obter dados do processo para poder restaurar
        const response = await api.get(`/processes/${processId}`);
        const processData = response.data;
        
        // Eliminar
        await api.delete(`/processes/${processId}`);
        
        return { undoData: processData };
      },
      undo: async (processData) => {
        // Restaurar o processo
        await api.post('/processes/restore', processData);
      },
      message: `Processo "${processName}" movido para o lixo`,
      undoLabel: 'Restaurar',
      type: 'success',
    });
  }, [executeWithUndo]);

  /**
   * Mover processo para outra fase com undo.
   */
  const moveProcessWithUndo = useCallback(async (processId, oldStatus, newStatus, api) => {
    return executeWithUndo({
      action: async () => {
        await api.put(`/processes/${processId}`, { status: newStatus });
        return { undoData: { oldStatus } };
      },
      undo: async ({ oldStatus }) => {
        await api.put(`/processes/${processId}`, { status: oldStatus });
      },
      message: `Processo movido para "${newStatus}"`,
      undoLabel: 'Desfazer',
      type: 'success',
    });
  }, [executeWithUndo]);

  /**
   * Atribuir consultor/mediador com undo.
   */
  const assignWithUndo = useCallback(async (processId, type, oldUserId, newUserId, newUserName, api) => {
    return executeWithUndo({
      action: async () => {
        const field = type === 'consultor' ? 'consultor_id' : 'mediador_id';
        await api.post(`/processes/${processId}/assign`, {
          [field]: newUserId
        });
        return { undoData: { oldUserId } };
      },
      undo: async ({ oldUserId }) => {
        const field = type === 'consultor' ? 'consultor_id' : 'mediador_id';
        await api.post(`/processes/${processId}/assign`, {
          [field]: oldUserId || ''
        });
      },
      message: `${type === 'consultor' ? 'Consultor' : 'Mediador'} atribuído: ${newUserName}`,
      undoLabel: 'Desfazer',
      type: 'success',
    });
  }, [executeWithUndo]);

  /**
   * Eliminar documento com undo.
   */
  const deleteDocumentWithUndo = useCallback(async (documentId, documentName, api) => {
    return executeWithUndo({
      action: async () => {
        // Obter dados do documento
        const response = await api.get(`/documents/${documentId}`);
        const docData = response.data;
        
        // Eliminar
        await api.delete(`/documents/${documentId}`);
        
        return { undoData: docData };
      },
      undo: async (docData) => {
        // Restaurar documento
        await api.post('/documents/restore', docData);
      },
      message: `Documento "${documentName}" eliminado`,
      undoLabel: 'Restaurar',
      type: 'success',
    });
  }, [executeWithUndo]);

  /**
   * Actualizar dados com undo.
   */
  const updateWithUndo = useCallback(async (endpoint, newData, oldData, message, api) => {
    return executeWithUndo({
      action: async () => {
        await api.put(endpoint, newData);
        return { undoData: oldData };
      },
      undo: async (oldData) => {
        await api.put(endpoint, oldData);
      },
      message,
      undoLabel: 'Desfazer',
      type: 'success',
    });
  }, [executeWithUndo]);

  return {
    deleteProcessWithUndo,
    moveProcessWithUndo,
    assignWithUndo,
    deleteDocumentWithUndo,
    updateWithUndo,
    executeWithUndo,
    executeImmediately,
  };
}

export default useUndo;
