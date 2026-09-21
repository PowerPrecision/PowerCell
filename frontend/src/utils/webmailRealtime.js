/**
 * webmailRealtime — inserção de um email novo na lista, sem ida à rede.
 *
 * PORQUÊ: o evento `new_email` chegava ao Webmail e disparava um
 * `invalidateQueries`, ou seja, um GET completo à lista. Isso é um
 * round-trip inteiro para mostrar uma linha que o próprio evento já
 * transporta — e, em cima disso, devolve a lista à página 1 e pode
 * apagar o estado de leitura optimista de outra linha.
 *
 * Aqui a linha entra directamente na cache do React Query. O refetch fica
 * como rede de segurança para o caso de o payload vir incompleto.
 *
 * Lógica pura (sem React, sem fetch) para ser testável à parte — a mesma
 * convenção de `taskEvents.js` e `processDelta.js`.
 */

/** Campos do payload `new_email` que a linha da lista sabe mostrar. */
export const EMAIL_EVENT_FIELDS = Object.freeze([
  'from_email',
  'subject',
  'account',
  'direction',
  'sent_at',
  'created_at',
  'to_emails',
  'is_read',
  'process_id',
]);

/**
 * Converte o payload do evento numa linha da lista do Webmail.
 *
 * @param {object} payload — `data` do evento `new_email`.
 * @returns {object|null} Linha, ou null se o evento não identificar o email.
 */
export function eventToEmailRow(payload) {
  if (!payload || typeof payload !== 'object') return null;
  const id = payload.email_id || payload.id;
  if (!id) return null;

  const row = { id: String(id) };
  EMAIL_EVENT_FIELDS.forEach((field) => {
    if (payload[field] !== undefined && payload[field] !== null) {
      row[field] = payload[field];
    }
  });

  // Defaults que a lista assume existirem.
  if (row.is_read === undefined) row.is_read = false;
  if (!row.subject) row.subject = '(sem assunto)';
  if (!row.sent_at && row.created_at) row.sent_at = row.created_at;
  // `preview` é calculado no servidor a partir do corpo, que o evento não
  // transporta de propósito. Fica vazio até o próximo refetch — melhor do
  // que segurar a linha inteira à espera de um GET.
  if (row.preview === undefined) row.preview = '';
  row.is_realtime = true;
  return row;
}

/**
 * Decide se um email novo pertence à lista que o utilizador está a ver.
 *
 * Conservador de propósito: em caso de dúvida NÃO insere, porque uma linha
 * a mais no sítio errado (um email recebido a aparecer em "Enviados") é
 * pior do que esperar pelo refetch.
 *
 * @param {object} payload — `data` do evento.
 * @param {object} view — Estado actual da lista.
 * @param {string} view.folder — Pasta aberta (`inbox`, `sent`, ...).
 * @param {number} [view.page=1] — Página aberta.
 * @param {string} [view.search] — Pesquisa activa.
 * @param {string} [view.mailbox] — Caixa seleccionada.
 * @returns {boolean}
 */
export function shouldInsertEmail(payload, view = {}) {
  if (!payload || typeof payload !== 'object') return false;
  if (!(payload.email_id || payload.id)) return false;

  const { folder = 'inbox', page = 1, search = '', mailbox = '' } = view;

  // Só a primeira página é o topo da lista. Inserir na página 3 punha o
  // email fora de ordem e desalinhava a paginação.
  if (Number(page) > 1) return false;

  // Com pesquisa activa não sabemos se o email corresponde aos termos —
  // essa decisão é do servidor.
  if (search && String(search).trim()) return false;

  // A pasta do evento tem de ser a que está aberta.
  const eventFolder = payload.folder || (payload.direction === 'sent' ? 'sent' : 'inbox');
  if (eventFolder !== folder) return false;

  // Caixa: o evento diz a conta a que o email chegou. Se o utilizador está
  // a ver uma caixa específica, só entra se for a mesma.
  if (mailbox && payload.account && payload.account !== mailbox) return false;

  return true;
}

/**
 * Insere a linha no topo do resultado em cache.
 *
 * Idempotente: um email que já esteja na lista (refetch concorrente, ou o
 * mesmo evento entregue duas vezes numa reconexão) não é duplicado nem
 * volta a contar para os não-lidos.
 *
 * @param {object|undefined} old — Resultado em cache (`{emails, total, ...}`).
 * @param {object} payload — `data` do evento.
 * @returns {object|undefined} Novo resultado, ou o MESMO objecto se nada mudou.
 */
export function insertEmailIntoList(old, payload) {
  if (!old || !Array.isArray(old.emails)) return old;

  const row = eventToEmailRow(payload);
  if (!row) return old;

  if (old.emails.some((item) => String(item?.id) === row.id)) return old;

  const next = {
    ...old,
    emails: [row, ...old.emails],
  };
  if (typeof old.total === 'number') next.total = old.total + 1;
  if (typeof old.unread_count === 'number' && !row.is_read) {
    next.unread_count = old.unread_count + 1;
  }
  return next;
}
