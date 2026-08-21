/**
 * Helpers do Painel de Organização (Pacote DW) — empresas + UCR.
 */

/**
 * Empresa da API (GET /admin/companies) → { id, name, ... }.
 * Aceita id/name canónicos e aliases company_id / company_name.
 */
export function normalizeCompanyEntity(raw) {
  if (!raw || typeof raw !== "object") return null;
  const id = raw.id || raw.company_id || raw.companyId || null;
  const name = raw.name || raw.company_name || raw.companyName || "";
  if (!id && !name) return null;
  const stableId = id != null ? String(id) : String(name);
  return {
    ...raw,
    id: stableId,
    name: name || stableId,
    company_id: raw.company_id || stableId,
    company_name: raw.company_name || name || stableId,
  };
}

/** Normaliza a resposta GET /admin/companies para um array. */
export function normalizeCompaniesPayload(payload) {
  let rawData = payload?.data ?? payload;
  if (!Array.isArray(rawData)) {
    rawData = rawData?.items || rawData?.companies || rawData?.results || [];
  }
  if (!Array.isArray(rawData)) return [];
  return rawData.map(normalizeCompanyEntity).filter(Boolean);
}

/**
 * Registo UCR → keys estáveis para a UI (id, company_name, role / role_name).
 * Aceita aliases camelCase, `_id` legado e `company` aninhada.
 */
export function normalizeUcrRecord(raw) {
  if (!raw || typeof raw !== "object") return null;

  const nestedCompany = raw.company && typeof raw.company === "object"
    ? raw.company
    : null;
  const id = raw.id || raw._id || raw.role_id || null;
  const userId = raw.user_id || raw.userId || null;
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
    || "";
  if (!companyName && typeof raw.company === "string") {
    companyName = raw.company;
  }
  const roleName = raw.role || raw.role_name || raw.roleName || "";

  return {
    ...raw,
    id: id != null ? String(id) : id,
    user_id: userId,
    company_id: companyId != null ? String(companyId) : companyId,
    company_name: companyName,
    role: roleName,
    role_name: roleName,
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
  const roleKey = ucr.role || ucr.role_name || "";
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
      .filter((r) => String(r.company_id || r.companyId) === String(companyId))
      .map((r) => r.role || r.role_name)
      .filter(Boolean),
  );
  return roles.filter((role) => !taken.has(role));
}

export const LAST_UCR_DELETE_MESSAGE =
  "Não é possível remover o único acesso deste utilizador. Um utilizador tem de ter pelo menos um acesso UCR.";

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
