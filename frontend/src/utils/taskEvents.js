/**
 * taskEvents — lógica pura de reactividade a eventos de tarefa.
 *
 * ÉPICO "Refatorização para Event-Driven": o backend publica
 * `task_started` / `task_progress` / `task_completed` / `task_failed` num
 * canal Redis (`services/redis_pubsub.py`) e o WebSocket entrega-os APENAS
 * ao dono da tarefa. Este módulo é o motor de merge desses eventos no
 * estado do React.
 *
 * PORQUÊ SEPARADO DO HOOK: sem imports de React nem do WebSocket, estas
 * funções são exercitáveis com `node --test` (mesma convenção de
 * `utils/mortgageCalculations.js`). O hook `hooks/useTaskEvents.js` é só a
 * ligação à subscrição.
 *
 * ISOLAMENTO: o roteamento por utilizador é feito no servidor
 * (`websocket_manager.route_system_event`), que só escreve nos sockets do
 * destinatário. O cliente nunca recebe eventos de outro utilizador, pelo
 * que não há (nem deve haver) filtragem por `user_id` aqui.
 */

/** Tipos de evento de tarefa emitidos pelo backend. */
export const TASK_EVENT_TYPES = Object.freeze([
  'task_started',
  'task_progress',
  'task_completed',
  'task_failed',
]);

/** Origem da tarefa — decide que vista reage ao evento. */
export const TASK_SOURCE = Object.freeze({
  TASK_LOG: 'task_log',               // colecção `task_logs` (TasksContext)
  BACKGROUND_JOB: 'background_job',   // colecção `background_jobs` (Centro de Operações)
});

/** Estados considerados "em curso" (a tarefa ainda está viva). */
const ACTIVE_STATUSES = Object.freeze(['pending', 'processing', 'running']);

/**
 * Traduz o payload do evento para a forma de um registo de `task_logs`.
 *
 * O evento usa nomes curtos (`message`, `error`, `result`); a lista de
 * tarefas usa os nomes da API (`progress_message`, `error_message`,
 * `result_data`). Campos ausentes no evento são omitidos — nunca escritos
 * como `undefined` — para que o merge preserve o que já se sabia.
 *
 * @param {object} payload — `data` do evento WebSocket.
 * @returns {object} Campos a fundir no registo da tarefa.
 */
export function taskEventToPatch(payload) {
  if (!payload || typeof payload !== 'object') return {};

  const mapping = {
    task_id: payload.task_id,
    status: payload.status,
    progress: payload.progress,
    progress_message: payload.message,
    title: payload.title,
    task_type: payload.task_type,
    process_id: payload.process_id,
    error_message: payload.error,
    result_data: payload.result,
  };

  const patch = {};
  Object.entries(mapping).forEach(([key, value]) => {
    if (value !== undefined && value !== null) patch[key] = value;
  });
  return patch;
}

/**
 * Aplica um evento de tarefa a uma lista, devolvendo uma lista nova.
 *
 * Função pura: é aqui que vive a lógica de merge, para poder ser testada
 * sem React nem WebSocket.
 *
 * - Tarefa conhecida → merge do patch por cima do registo existente.
 * - Tarefa desconhecida → inserida à cabeça (é o `task_started` de algo que
 *   nasceu agora noutro separador ou noutro dispositivo).
 * - Evento sem `task_id` → lista devolvida inalterada (mesma referência,
 *   para não provocar re-render desnecessário).
 *
 * @param {Array<object>} tasks — Lista actual.
 * @param {object} payload — `data` do evento.
 * @returns {Array<object>} Lista nova (ou a mesma se nada mudou).
 */
export function applyTaskEvent(tasks, payload) {
  const list = Array.isArray(tasks) ? tasks : [];
  const patch = taskEventToPatch(payload);
  if (!patch.task_id) return list;

  const index = list.findIndex((t) => t?.task_id === patch.task_id);
  if (index === -1) {
    return [{ ...patch }, ...list];
  }

  const next = list.slice();
  next[index] = { ...list[index], ...patch };
  return next;
}

/**
 * Conta as tarefas em curso numa lista.
 *
 * @param {Array<object>} tasks
 * @returns {number}
 */
export function countActiveTasks(tasks) {
  if (!Array.isArray(tasks)) return 0;
  return tasks.filter((t) => ACTIVE_STATUSES.includes(t?.status)).length;
}

/**
 * True se o evento diz respeito a esta origem de tarefas.
 *
 * Eventos sem `source` são aceites por qualquer vista (retrocompatibilidade
 * com um backend anterior a este épico).
 *
 * @param {object} payload
 * @param {string} source — Um valor de `TASK_SOURCE`.
 * @returns {boolean}
 */
export function isFromSource(payload, source) {
  const value = payload?.source;
  return !value || value === source;
}
