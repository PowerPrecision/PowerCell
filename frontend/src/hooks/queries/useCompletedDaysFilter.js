/**
 * ====================================================================
 * USE COMPLETED DAYS FILTER - Custom Hook (Estado Isolado)
 * ====================================================================
 * Hook que isola o estado do filtro de datas dos Concluídos.
 *
 * PROBLEMA RESOLVIDO:
 * Antes, o `completedDays` vivia no estado global do KanbanBoard.
 * Quando o utilizador mudava o período, o setState no KanbanBoard
 * provocava re-render de TODO o quadro (incluindo colunas activas).
 *
 * SOLUÇÃO:
 * O estado do filtro vive dentro deste hook, que é usado APENAS
 * pela query dos Concluídos (useKanbanCompletedQuery). Quando o
 * utilizador muda o período, apenas a query dos Concluídos é
 * disparada — as colunas activas permanecem inalteradas.
 *
 * FUNCIONALIDADES:
 * - useState isolado para completedDays (default 30)
 * - Callback memoizado para alteração do filtro
 * - Reset para o valor default
 * ====================================================================
 */

import { useState, useCallback } from 'react';

const DEFAULT_COMPLETED_DAYS = 30;

/**
 * Hook para gestão isolada do filtro de datas dos Concluídos.
 *
 * @param {Object} options - Opções do hook
 * @param {number} options.defaultDays - Valor default do filtro (default: 30)
 * @returns {Object} Estado e handlers do filtro
 *
 * @example
 * const { completedDays, setCompletedDays, resetCompletedDays } = useCompletedDaysFilter();
 *
 * // No Select da coluna Concluídos:
 * <Select value={String(completedDays)} onValueChange={(v) => setCompletedDays(Number(v))}>
 *
 * // Na query isolada:
 * useKanbanCompletedQuery({ completedDays, ... });
 */
export function useCompletedDaysFilter(options = {}) {
  const { defaultDays = DEFAULT_COMPLETED_DAYS } = options;

  const [completedDays, setCompletedDays] = useState(defaultDays);

  const handleCompletedDaysChange = useCallback((days) => {
    setCompletedDays(Number(days));
  }, []);

  const resetCompletedDays = useCallback(() => {
    setCompletedDays(defaultDays);
  }, [defaultDays]);

  return {
    completedDays,
    setCompletedDays: handleCompletedDaysChange,
    resetCompletedDays,
  };
}

export default useCompletedDaysFilter;
