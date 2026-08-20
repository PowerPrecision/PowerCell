/**
 * Pacote DR — selector unificado de caixa do Webmail (Pessoal / Geral / Indexação).
 * Substitui os botões de tab "Caixa Pessoal" vs "Caixa Geral".
 */

/**
 * @param {{
 *   personalAccounts?: Array<{ email_address?: string, label?: string, is_caixa_geral?: boolean }>,
 *   showGeneral?: boolean,
 *   isIndexacao?: boolean,
 *   unreadByBox?: { personal?: number, general?: number },
 * }} opts
 * @returns {Array<{ value: string, label: string, unread: number }>}
 */
export function buildMailboxOptions({
  personalAccounts = [],
  showGeneral: _showGeneral = false,
  isIndexacao = false,
  unreadByBox = {},
} = {}) {
  if (isIndexacao) {
    return [
      {
        value: "shared_indexacao",
        label: "Caixa de Indexação (Partilhada)",
        unread: Number(unreadByBox.personal) || 0,
      },
    ];
  }

  const options = [];
  const seen = new Set();
  let hasCaixaGeralWithEmail = false;

  for (const item of personalAccounts) {
    const email = (item?.email_address || "").trim();
    if (!email || seen.has(email)) continue;
    seen.add(email);
    if (item.is_caixa_geral) {
      hasCaixaGeralWithEmail = true;
      options.push({
        value: `personal:${email}`,
        label: `Caixa Geral (${email})`,
        unread: Number(unreadByBox.general) || 0,
      });
    } else {
      const name = item.label && item.label !== email ? item.label : email;
      options.push({
        value: `personal:${email}`,
        label: `Caixa Pessoal (${name})`,
        unread: Number(unreadByBox.personal) || 0,
      });
    }
  }

  // PACOTE DV — não injetar uma "Caixa Geral" fantasma sem email.
  // A conta geral só existe se o backend a injectar com geral@empresa.pt.

  if (options.length === 0) {
    options.push({
      value: "personal:",
      label: "Caixa Pessoal",
      unread: Number(unreadByBox.personal) || 0,
    });
  }

  return options;
}

/**
 * Valor actual do Select a partir do estado do Webmail.
 */
export function resolveMailboxSelection({
  activeBox,
  selectedMailbox,
  isIndexacao = false,
} = {}) {
  if (isIndexacao || activeBox === "shared_indexacao") return "shared_indexacao";
  if (activeBox === "general") return "general";
  if (selectedMailbox) return `personal:${selectedMailbox}`;
  return "personal:";
}

/**
 * Aplica a escolha do Select ao estado (activeBox + mailbox).
 * @returns {{ activeBox: string, selectedMailbox?: string }}
 */
export function applyMailboxSelection(value) {
  if (value === "general") return { activeBox: "general" };
  if (value === "shared_indexacao") return { activeBox: "shared_indexacao" };
  if (typeof value === "string" && value.startsWith("personal:")) {
    const email = value.slice("personal:".length);
    return { activeBox: "personal", selectedMailbox: email };
  }
  return { activeBox: "personal", selectedMailbox: value || "" };
}
