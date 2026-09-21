/**
 * useTaskEvents — subscrição aos eventos `task_*` do WebSocket.
 *
 * PORQUÊ: o PowerCell descobria o estado das tarefas pesadas por polling —
 * `TasksContext` a cada 5s, o Centro de Operações a cada 5s, o painel do
 * processo a cada 10s. Isso significa até 5 segundos de atraso a mostrar
 * uma barra de progresso, e um pedido HTTP por cliente por intervalo mesmo
 * quando nada muda.
 *
 * O backend passou a publicar `task_started` / `task_progress` /
 * `task_completed` / `task_failed` num canal Redis
 * (`services/redis_pubsub.py`), que o WebSocket entrega **apenas ao dono da
 * tarefa**. Este hook é a ponta desse fio no React: os componentes reagem
 * ao evento em vez de perguntarem repetidamente.
 *
 * O POLLING NÃO DESAPARECE — MUDA DE PAPEL:
 *   Deixa de ser o mecanismo primário e passa a ser a rede de segurança.
 *   Com WebSocket ligado, o polling pára. Se o WebSocket cair (rede, token,
 *   Redis em baixo num worker), o polling retoma sozinho. Apagá-lo por
 *   completo deixaria a UI cega numa falha de ligação — por isso o hook
 *   devolve `isConnected`: é com ele que o chamador decide.
 *
 * A lógica pura de merge vive em `utils/taskEvents.js` (testada à parte).
 */

import { useEffect, useRef } from 'react';
import useWebSocket from './useWebSocket';
import { isFromSource, TASK_EVENT_TYPES } from '../utils/taskEvents';

export {
  applyTaskEvent,
  countActiveTasks,
  isFromSource,
  TASK_EVENT_TYPES,
  TASK_SOURCE,
  taskEventToPatch,
} from '../utils/taskEvents';

/**
 * Subscreve os eventos `task_*` e chama `onTaskEvent(payload, type)`.
 *
 * O handler é guardado numa ref, pelo que não precisa de ser estável: a
 * subscrição é feita uma só vez e sobrevive a re-renders.
 *
 * @param {(payload: object, eventType: string) => void} onTaskEvent
 * @param {object} [options]
 * @param {string} [options.source] — Filtrar por origem (`TASK_SOURCE.*`).
 * @param {boolean} [options.enabled=true] — Desliga a subscrição quando falso.
 * @returns {{isConnected: boolean}} Estado da ligação — use-o para decidir
 *   se o polling de fallback deve correr.
 */
export function useTaskEvents(onTaskEvent, options = {}) {
  const { source = null, enabled = true } = options;
  const { isConnected, on } = useWebSocket();

  const handlerRef = useRef(onTaskEvent);
  useEffect(() => {
    handlerRef.current = onTaskEvent;
  }, [onTaskEvent]);

  useEffect(() => {
    if (!enabled || typeof on !== 'function') return undefined;

    const unsubscribers = TASK_EVENT_TYPES.map((eventType) =>
      on(eventType, (payload) => {
        if (source && !isFromSource(payload, source)) return;
        const handler = handlerRef.current;
        if (typeof handler === 'function') handler(payload, eventType);
      })
    );

    return () => {
      unsubscribers.forEach((off) => {
        if (typeof off === 'function') off();
      });
    };
  }, [on, source, enabled]);

  return { isConnected };
}

export default useTaskEvents;
