/**
 * fonteLabels — Dicionário central de labels legíveis (PT-PT) para o
 * campo `fonte` (origem) dos clientes.
 *
 * PACOTE 11 (Eixo 3 — "Variáveis em Inglês"): a Lista de Clientes e a
 * ficha do cliente mostravam o valor TÉCNICO do enum do backend
 * ("staff_created", "public_form", "auto_created"...) em vez de uma
 * string legível. Este módulo mapeia todos os valores conhecidos para
 * português; valores desconhecidos são humanizados (underscores →
 * espaços + capitalização) em vez de mostrados crus.
 *
 * Manter sincronizado com: services/client_crud.py (fonte),
 * services/client_find_or_create.py ("auto_created"),
 * services/public_registration.py ("public_form"),
 * frontend/src/components/filters/ClientFilters.jsx (opções de filtro).
 *
 * @module utils/fonteLabels
 */

export const FONTE_LABELS = {
  // Valores técnicos escritos pelo backend
  staff_created: "Criado pela Equipa",
  auto_created: "Criação Automática",
  public_form: "Registo no Portal",
  onboarding_auto: "Onboarding Automático",
  migrated_from_process: "Migração de Processo",
  segundo_titular: "Segundo Titular",
  // Valores legados / manuais (seeds e formulários antigos)
  Manual: "Manual",
  Website: "Website",
  "Indicação": "Indicação",
  Telefone: "Telefone",
  Email: "Email",
  Feira: "Feira",
  Portal: "Portal",
  Trello: "Trello",
  trello: "Trello",
};

/**
 * Devolve a label legível para um valor de `fonte`.
 * Fallback: humaniza o valor técnico (ex.: "novo_canal_x" →
 * "Novo Canal X") para enums adicionados no backend no futuro.
 *
 * @param {string} fonte - valor cru do campo `fonte`.
 * @returns {string} label legível em PT-PT ("—" se vazio).
 */
export const formatFonteLabel = (fonte) => {
  if (fonte === null || fonte === undefined || fonte === "") return "—";
  const raw = String(fonte).trim();
  if (!raw) return "—";
  if (FONTE_LABELS[raw]) return FONTE_LABELS[raw];
  if (FONTE_LABELS[raw.toLowerCase()]) return FONTE_LABELS[raw.toLowerCase()];
  // Humanize fallback: underscores/hífens → espaços, capitaliza palavras.
  return raw
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

export default FONTE_LABELS;
