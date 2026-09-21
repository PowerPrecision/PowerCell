/**
 * processDelta — merge do delta de processo recebido por WebSocket.
 *
 * PORQUÊ: o backend difunde um payload LEVE quando um processo muda
 * (`services/process_broadcast.build_process_delta_payload`) em vez do
 * documento inteiro. Quem tem o processo aberto funde esse delta no estado
 * local, sem refetch.
 *
 * BUG QUE ISTO FECHA: a auto-atribuição pós-indexação gravava campos com
 * nomes que nenhum leitor do frontend conhecia (`consultant_id` em vez de
 * `consultor_names`/`assigned_consultor_ids`), e o cartão de Atribuição
 * ficava em branco apesar de a atribuição ter corrido bem. A lista de
 * campos abaixo é o contrato explícito entre os dois lados — um desencontro
 * de nomes passa a ser apanhado por teste, não descoberto em produção.
 */

/**
 * Campos que o delta pode transportar e que a página aplica ao estado.
 *
 * Deliberadamente restrita: um delta nunca traz o processo todo, e copiar
 * cegamente tudo o que chega permitiria a um payload inesperado sobrepor
 * campos que o utilizador está a editar no formulário.
 */
export const PROCESS_DELTA_FIELDS = Object.freeze([
  'assigned_consultor_ids',
  'consultor_names',
  'assigned_mediador_ids',
  'mediador_names',
  'status',
  'prioridade',
  'updated_at',
]);

/**
 * Extrai do delta apenas os campos aplicáveis a este processo.
 *
 * @param {object|null|undefined} delta — `data` do evento `process_updated`.
 * @param {string} processId — Id do processo aberto no ecrã.
 * @returns {object} Patch a fundir (vazio quando não há nada a aplicar).
 */
export function buildProcessPatch(delta, processId) {
  if (!delta || typeof delta !== 'object') return {};
  if (!processId || delta.process_id !== processId) return {};

  const patch = {};
  PROCESS_DELTA_FIELDS.forEach((field) => {
    const value = delta[field];
    if (value !== undefined && value !== null) patch[field] = value;
  });
  return patch;
}

/**
 * Funde o delta num processo, devolvendo a MESMA referência quando nada muda.
 *
 * @param {object|null} process — Estado actual.
 * @param {object|null|undefined} delta — `data` do evento.
 * @param {string} processId — Id do processo aberto.
 * @returns {object|null} Processo novo, ou o mesmo objecto se não houve patch.
 */
export function applyProcessDelta(process, delta, processId) {
  if (!process) return process;
  const patch = buildProcessPatch(delta, processId);
  if (Object.keys(patch).length === 0) return process;
  return { ...process, ...patch };
}
