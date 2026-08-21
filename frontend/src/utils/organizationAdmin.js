/**
 * Helpers do Painel de Organização (Pacote DW) — empresas + UCR.
 */

/** Normaliza a resposta GET /admin/companies para um array. */
export function normalizeCompaniesPayload(payload) {
  let rawData = payload?.data ?? payload;
  if (!Array.isArray(rawData)) {
    rawData = rawData?.items || rawData?.companies || rawData?.results || [];
  }
  return Array.isArray(rawData) ? rawData : [];
}

/**
 * Normaliza um registo UCR vindo da API (aliases camelCase / docs antigos).
 * Garante `id`, `user_id`, `company_id`, `company_name` e `role`.
 */
export function normalizeUcrRecord(raw) {
  if (!raw || typeof raw !== "object") return null;

  const id = raw.id || raw._id || null;
  const userId = raw.user_id || raw.userId || null;
  const role = raw.role || raw.role_name || "";
  const nestedCompany = raw.company && typeof raw.company === "object"
    ? raw.company
    : null;
  const companyId =
    raw.company_id
    || raw.companyId
    || nestedCompany?.id
    || (typeof raw.company === "string" ? raw.company : null)
    || null;
  let companyName =
    raw.company_name
    || raw.companyName
    || nestedCompany?.name
    || nestedCompany?.company_name
    || null;
  if (!companyName && typeof raw.company === "string") {
    companyName = raw.company;
  }

  return {
    ...raw,
    id: id != null ? String(id) : null,
    user_id: userId,
    role,
    company_id: companyId,
    company_name: companyName,
    is_default: Boolean(raw.is_default ?? raw.isDefault),
  };
}

/** Normaliza a resposta GET /admin/user-company-roles para um array. */
export function normalizeRolesPayload(payload) {
  const raw = payload?.data ?? payload;
  let list = [];
  if (Array.isArray(raw)) list = raw;
  else if (Array.isArray(raw?.roles)) list = raw.roles;
  else if (Array.isArray(raw?.items)) list = raw.items;
  else if (Array.isArray(raw?.company_roles)) list = raw.company_roles;
  return list.map(normalizeUcrRecord).filter(Boolean);
}

/** Agrupa UCRs por user_id. */
export function groupRolesByUserId(roles) {
  const map = {};
  for (const role of roles || []) {
    const uid = role.user_id || role.userId;
    if (!uid) continue;
    if (!map[uid]) map[uid] = [];
    map[uid].push(role);
  }
  return map;
}

/**
 * Label canónica do acesso: "Diretor na Empresa Power".
 * `roleLabels` é o mapa amigável (ex: ROLE_SHORT_LABELS).
 */
export function formatUcrAccessLabel(ucr, roleLabels = {}) {
  if (!ucr) return "";
  const roleKey = ucr.role || "";
  const roleLabel = roleLabels[roleKey] || roleKey;
  const company = ucr.company_name || "";
  if (roleLabel && company) return `${roleLabel} na Empresa ${company}`;
  return roleLabel || company || "";
}

/**
 * Empresas para o Select de "Novo acesso": todas as activas.
 * Não exclui uma empresa só porque o utilizador já tem um cargo nela —
 * a exclusão é da combinação exacta Empresa+Cargo (ver rolesForNewAccess).
 */
export function companiesForNewAccess(companies) {
  return (companies || []).filter(isCompanyActive);
}

/** Cargos ainda disponíveis para a empresa seleccionada. */
export function rolesForNewAccess(assignableRoles, companyId, selectedRoles) {
  const roles = assignableRoles || [];
  if (!companyId) return roles;
  const taken = new Set(
    (selectedRoles || [])
      .filter((r) => (r.company_id || r.companyId) === companyId)
      .map((r) => r.role)
      .filter(Boolean),
  );
  return roles.filter((role) => !taken.has(role));
}

export const LAST_UCR_DELETE_MESSAGE =
  "Não é possível eliminar o único acesso do utilizador. Adicione outro primeiro.";

/** Empresa activa se is_active não estiver explicitamente a false. */
export function isCompanyActive(company) {
  if (!company) return true;
  return company.is_active !== false;
}

/** Utilizador activo se is_active não estiver explicitamente a false. */
export function isUserActive(user) {
  if (!user) return true;
  return user.is_active !== false;
}

/**
 * Password temporária para criar/redefinir contas (mostrada ao admin).
 * Garante maiúscula, minúscula, dígito e símbolo.
 */
export function generateTempPassword(length = 12) {
  const upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const lower = "abcdefghijklmnopqrstuvwxyz";
  const digits = "0123456789";
  const symbols = "!@#$%^&*";
  const all = upper + lower + digits + symbols;
  const pick = (set) => set.charAt(Math.floor(Math.random() * set.length));
  const chars = [pick(upper), pick(lower), pick(digits), pick(symbols)];
  for (let i = chars.length; i < length; i += 1) {
    chars.push(pick(all));
  }
  for (let i = chars.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join("");
}
