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

/** Normaliza a resposta GET /admin/user-company-roles para um array. */
export function normalizeRolesPayload(payload) {
  const raw = payload?.data ?? payload;
  if (Array.isArray(raw)) return raw;
  if (Array.isArray(raw?.roles)) return raw.roles;
  if (Array.isArray(raw?.items)) return raw.items;
  return [];
}

/** Agrupa UCRs por user_id. */
export function groupRolesByUserId(roles) {
  const map = {};
  for (const role of roles || []) {
    const uid = role.user_id;
    if (!uid) continue;
    if (!map[uid]) map[uid] = [];
    map[uid].push(role);
  }
  return map;
}

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
