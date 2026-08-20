/**
 * PACOTE DU — Deep linking das tabs do processo (?tab=portal, etc.).
 */

const MAIN_TABS = new Set(["resumo", "documentos", "historico"]);

const INNER_TAB_ALIASES = {
  portal: "mensagens",
  mensagens: "mensagens",
  messages: "mensagens",
  emails: "emails",
  email: "emails",
  visitas: "visitas",
  agenda: "prazos",
  prazos: "prazos",
  cliente: "personal",
  personal: "personal",
  financeiros: "financial",
  financial: "financial",
  imovel: "realestate",
  realestate: "realestate",
  credito: "credit",
  credit: "credit",
};

export function resolveProcessTabsFromQuery(tab) {
  const value = String(tab || "").trim().toLowerCase();
  if (!value) {
    return { mainTab: "resumo", activeTab: "personal" };
  }
  if (MAIN_TABS.has(value)) {
    return { mainTab: value, activeTab: "personal" };
  }
  if (INNER_TAB_ALIASES[value]) {
    return { mainTab: "resumo", activeTab: INNER_TAB_ALIASES[value] };
  }
  return { mainTab: "resumo", activeTab: "personal" };
}

export function processDeepLink(processId, tab) {
  if (!processId) return "/processos";
  const qs = tab ? `?tab=${encodeURIComponent(tab)}` : "";
  return `/processo/${processId}${qs}`;
}
