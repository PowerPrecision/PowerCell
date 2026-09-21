/**
 * emailThreads — agrupamento de emails em conversas.
 *
 * PORQUÊ: uma troca de 5 mensagens com o mesmo cliente ocupava 5 linhas
 * da caixa de entrada. Passa a ocupar 1, expansível.
 *
 * A regra de agrupamento é a mesma do backend (`services/email_threading.py`)
 * e segue a RFC 5322, da pista mais fiável para a menos:
 *   1. raiz de `references` — aguenta uma mudança de assunto a meio;
 *   2. `in_reply_to`;
 *   3. o próprio `message_id` (raiz de uma conversa nova);
 *   4. assunto normalizado — último recurso, para servidores que não
 *      devolvem estes cabeçalhos.
 *
 * ÂMBITO: agrupa a PÁGINA carregada (30 emails), não o histórico todo.
 * Uma conversa que atravesse a fronteira da paginação aparece como dois
 * grupos. Agrupar globalmente exigiria mover a paginação para dentro de
 * uma agregação por thread no servidor — mudança bem maior, e que
 * quebraria as contagens por pasta já existentes.
 */

/** Prefixos de resposta/encaminhamento (PT/EN/ES), como no backend. */
const SUBJECT_PREFIX_RE =
  /^\s*(?:(?:re|rv|res|resposta|fw|fwd|enc|encaminhado|reenv)\s*(?:\[\d+\])?\s*:\s*)+/i;

/** Normaliza um Message-ID para a forma `<id@dominio>`. */
export function normalizeMessageId(value) {
  if (!value || typeof value !== 'string') return null;
  const cleaned = value.trim().replace(/^<+|>+$/g, '').trim();
  return cleaned ? `<${cleaned}>` : null;
}

/** Normaliza um `References` (string ou lista) numa lista ordenada e única. */
export function parseReferences(value) {
  if (!value) return [];
  let candidates;
  if (typeof value === 'string') {
    candidates = value.replace(/,/g, ' ').split(/\s+/);
  } else if (Array.isArray(value)) {
    candidates = value;
  } else {
    return [];
  }

  const seen = new Set();
  const result = [];
  candidates.forEach((item) => {
    const norm = normalizeMessageId(typeof item === 'string' ? item : String(item || ''));
    if (norm && !seen.has(norm)) {
      seen.add(norm);
      result.push(norm);
    }
  });
  return result;
}

/** Remove prefixos `Re:`/`Fwd:` repetidos e normaliza espaços. */
export function normalizeSubject(subject) {
  if (!subject || typeof subject !== 'string') return '';
  let current = subject.trim();
  let previous = null;
  while (current !== previous) {
    previous = current;
    current = current.replace(SUBJECT_PREFIX_RE, '').trim();
  }
  return current.replace(/\s+/g, ' ');
}

/** Chave de conversa de um email. */
export function threadKey(email) {
  if (!email || typeof email !== 'object') return '';

  const refs = parseReferences(email.references);
  if (refs.length) return refs[0];

  const parent = normalizeMessageId(email.in_reply_to);
  if (parent) return parent;

  const own = normalizeMessageId(email.message_id);
  if (own) return own;

  const subject = normalizeSubject(email.subject);
  return subject ? `subject:${subject.toLowerCase()}` : '';
}

/** Data comparável de um email (mais recente primeiro). */
function emailTime(email) {
  const raw = email?.sent_at || email?.created_at;
  const parsed = raw ? Date.parse(raw) : NaN;
  return Number.isNaN(parsed) ? 0 : parsed;
}

/**
 * Agrupa uma lista de emails em conversas.
 *
 * Preserva a ordem de chegada da lista: a conversa aparece na posição do
 * seu email mais recente, para o que chegou agora ficar no topo.
 *
 * Um email sem pistas de threading (sem cabeçalhos e sem assunto) fica
 * numa conversa só dele — juntá-los todos numa thread "sem assunto" seria
 * pior do que não agrupar.
 *
 * @param {Array<object>} emails
 * @returns {Array<{key: string, emails: Array<object>, latest: object,
 *   count: number, unreadCount: number, hasAttachments: boolean}>}
 */
export function groupEmailsIntoThreads(emails) {
  if (!Array.isArray(emails) || emails.length === 0) return [];

  const byKey = new Map();
  const order = [];

  emails.forEach((email, index) => {
    if (!email || typeof email !== 'object') return;
    // Sem pista nenhuma, cada email é a sua própria conversa.
    const key = threadKey(email) || `__solo_${email.id ?? index}`;
    if (!byKey.has(key)) {
      byKey.set(key, []);
      order.push(key);
    }
    byKey.get(key).push(email);
  });

  return order.map((key) => {
    const group = byKey.get(key);
    const sorted = [...group].sort((a, b) => emailTime(b) - emailTime(a));
    const latest = sorted[0];
    return {
      key,
      emails: sorted,
      latest,
      count: sorted.length,
      unreadCount: sorted.filter((e) => e?.is_read === false).length,
      hasAttachments: sorted.some(
        (e) => Array.isArray(e?.attachments) && e.attachments.length > 0
      ),
    };
  });
}

/**
 * Destinatários de um "Responder a Todos".
 *
 * Regras: o remetente do original passa a destinatário; os restantes To/Cc
 * originais ficam em Cc; o próprio utilizador é removido (responder a si
 * mesmo é ruído), tal como duplicados e maiúsculas/minúsculas diferentes.
 *
 * @param {object} email — Email original.
 * @param {string} selfEmail — Endereço de quem responde.
 * @returns {{to: string[], cc: string[]}}
 */
export function buildReplyAllRecipients(email, selfEmail) {
  if (!email || typeof email !== 'object') return { to: [], cc: [] };

  const self = (selfEmail || '').trim().toLowerCase();
  const isSent = email.direction === 'sent';
  const asList = (value) => {
    if (Array.isArray(value)) return value;
    if (typeof value === 'string' && value.trim()) {
      return value.split(/[,;]/).map((s) => s.trim());
    }
    return [];
  };

  // Ao responder a um email que NÓS enviámos, os destinatários mantêm-se
  // (é a continuação da mesma conversa, não uma resposta ao próprio).
  const to = isSent
    ? asList(email.to_emails)
    : [email.from_email].filter(Boolean);

  const ccCandidates = [
    ...(isSent ? [] : asList(email.to_emails)),
    ...asList(email.cc_emails),
  ];

  const seen = new Set();
  const cleanTo = [];
  to.forEach((addr) => {
    const norm = String(addr || '').trim();
    const lower = norm.toLowerCase();
    if (!norm || lower === self || seen.has(lower)) return;
    seen.add(lower);
    cleanTo.push(norm);
  });

  const cleanCc = [];
  ccCandidates.forEach((addr) => {
    const norm = String(addr || '').trim();
    const lower = norm.toLowerCase();
    if (!norm || lower === self || seen.has(lower)) return;
    seen.add(lower);
    cleanCc.push(norm);
  });

  return { to: cleanTo, cc: cleanCc };
}

/**
 * Cabeçalhos de threading para uma resposta ao email dado.
 *
 * @param {object} email — Email a que se responde.
 * @returns {{in_reply_to: string|null, references: string[]}}
 */
export function buildReplyThreadHeaders(email) {
  const parent = normalizeMessageId(email?.message_id);
  if (!parent) return { in_reply_to: null, references: [] };

  const chain = parseReferences(email?.references);
  if (!chain.includes(parent)) chain.push(parent);
  return { in_reply_to: parent, references: chain };
}
