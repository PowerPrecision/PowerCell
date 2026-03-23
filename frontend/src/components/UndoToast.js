/**
 * UndoToast Component
 * 
 * Componente para mostrar toasts com funcionalidade de undo.
 * Utiliza o sonner para exibição.
 * 
 * Uso:
 * <UndoToast 
 *   message="Item eliminado"
 *   onUndo={() => restoreItem()}
 *   duration={5000}
 * />
 */
import React, { useEffect, useState, useCallback } from 'react';
import { toast } from 'sonner';
import { Undo2, X, Check, AlertCircle } from 'lucide-react';
import { cn } from '../utils/cn';

/**
 * Tipos de toast com cores correspondentes
 */
const TOAST_TYPES = {
  success: {
    bgClass: 'bg-green-50 dark:bg-green-950',
    borderClass: 'border-green-200 dark:border-green-800',
    iconClass: 'text-green-600',
    Icon: Check,
  },
  error: {
    bgClass: 'bg-red-50 dark:bg-red-950',
    borderClass: 'border-red-200 dark:border-red-800',
    iconClass: 'text-red-600',
    Icon: AlertCircle,
  },
  warning: {
    bgClass: 'bg-yellow-50 dark:bg-yellow-950',
    borderClass: 'border-yellow-200 dark:border-yellow-800',
    iconClass: 'text-yellow-600',
    Icon: AlertCircle,
  },
  info: {
    bgClass: 'bg-blue-50 dark:bg-blue-950',
    borderClass: 'border-blue-200 dark:border-blue-800',
    iconClass: 'text-blue-600',
    Icon: AlertCircle,
  },
};

/**
 * Componente interno de toast com botão de undo
 */
export function UndoToastContent({
  message,
  description,
  onUndo,
  undoLabel = 'Desfazer',
  onDismiss,
  type = 'success',
  showProgress = true,
  duration = 5000,
}) {
  const [timeLeft, setTimeLeft] = useState(duration);
  const [isUndoing, setIsUndoing] = useState(false);
  
  const config = TOAST_TYPES[type] || TOAST_TYPES.success;
  const { Icon } = config;

  // Countdown
  useEffect(() => {
    if (!showProgress) return;
    
    const interval = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 100) {
          clearInterval(interval);
          return 0;
        }
        return prev - 100;
      });
    }, 100);

    return () => clearInterval(interval);
  }, [showProgress]);

  const handleUndo = useCallback(async () => {
    setIsUndoing(true);
    try {
      await onUndo?.();
      toast.success('Ação desfeita');
      onDismiss?.();
    } catch (error) {
      toast.error('Erro ao desfazer');
    } finally {
      setIsUndoing(false);
    }
  }, [onUndo, onDismiss]);

  const progress = (timeLeft / duration) * 100;

  return (
    <div className={cn(
      'flex items-start gap-3 p-4 rounded-lg border shadow-lg min-w-[300px] max-w-[400px]',
      config.bgClass,
      config.borderClass
    )}>
      {/* Ícone */}
      <Icon className={cn('h-5 w-5 mt-0.5 flex-shrink-0', config.iconClass)} />
      
      {/* Conteúdo */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
          {message}
        </p>
        {description && (
          <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">
            {description}
          </p>
        )}
        
        {/* Botão de Undo */}
        {onUndo && (
          <button
            onClick={handleUndo}
            disabled={isUndoing}
            className={cn(
              'mt-2 flex items-center gap-1.5 text-xs font-medium',
              'text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <Undo2 className="h-3.5 w-3.5" />
            {isUndoing ? 'A desfazer...' : undoLabel}
          </button>
        )}
      </div>
      
      {/* Botão de fechar */}
      <button
        onClick={onDismiss}
        className="flex-shrink-0 p-1 rounded hover:bg-black/5 dark:hover:bg-white/5"
      >
        <X className="h-4 w-4 text-gray-500" />
      </button>
      
      {/* Barra de progresso */}
      {showProgress && (
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gray-200/50 dark:bg-gray-700/50 rounded-b-lg overflow-hidden">
          <div 
            className="h-full bg-current opacity-30 transition-all duration-100"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}
    </div>
  );
}

/**
 * Função para mostrar um toast com undo
 * 
 * Uso:
 * showUndoToast({
 *   message: 'Item eliminado',
 *   onUndo: () => restoreItem(),
 * });
 */
export function showUndoToast({
  message,
  description,
  onUndo,
  undoLabel = 'Desfazer',
  type = 'success',
  duration = 5000,
}) {
  // Usar o sonner toast com action
  return toast[type](message, {
    description,
    duration,
    action: onUndo ? {
      label: undoLabel,
      onClick: onUndo,
    } : undefined,
  });
}

/**
 * Hook para usar toasts com undo
 */
export function useUndoToast() {
  const show = useCallback((options) => {
    return showUndoToast(options);
  }, []);

  const success = useCallback((message, options = {}) => {
    return showUndoToast({ message, type: 'success', ...options });
  }, []);

  const error = useCallback((message, options = {}) => {
    return showUndoToast({ message, type: 'error', ...options });
  }, []);

  const warning = useCallback((message, options = {}) => {
    return showUndoToast({ message, type: 'warning', ...options });
  }, []);

  const info = useCallback((message, options = {}) => {
    return showUndoToast({ message, type: 'info', ...options });
  }, []);

  return {
    show,
    success,
    error,
    warning,
    info,
  };
}

export default UndoToastContent;
