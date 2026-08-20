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
