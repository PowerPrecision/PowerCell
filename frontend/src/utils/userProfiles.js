/**
 * Perfis UCR (user_company_roles) do utilizador autenticado.
 *
 * O backend expõe a lista em GET /auth/me como `companies` (e alias
 * `company_roles`). Alguns payloads de login / docs antigos usam
 * `company_id` vs `companyId`, ou omitem UCRs e só trazem
 * `additional_roles` — o header (ContextSwitcher) já mostra esses
 * perfis, mas a Área Pessoal filtrava só `user.companies` com
 * `company_id !== "default"` e ficava vazia.
 */

import {
  ROLE_ICONS,
  ROLE_LABELS,
  isSelectableRole,
  normalizeRole,
} from "./roleUtils.js";

/**
 * Lista crua de associações empresa+role vinda da API.
 * Aceita `companies`, `company_roles` ou `user_company_roles`.
 */
export function getUserCompanyRecords(user) {
  if (!user || typeof user !== "object") return [];
  const raw =
    user.companies ||
    user.company_roles ||
    user.user_company_roles ||
    [];
  return Array.isArray(raw) ? raw : [];
}

/**
 * Normaliza um registo UCR / perfil para um shape estável.
 * @returns {{ role: string, company_id: string|null, company_name: string|null, is_default: boolean }|null}
 */
export function normalizeCompanyRecord(raw, fallbacks = {}) {
  if (raw == null) return null;
  if (typeof raw === "string") {
    const role = normalizeRole(raw);
    if (!isSelectableRole(role)) return null;
    return {
      role,
      company_id: fallbacks.companyId || null,
      company_name: fallbacks.companyName || null,
      is_default: false,
      display_name: null,
      professional_phone: null,
      job_title: null,
      signature: null,
    };
  }
  if (typeof raw !== "object") return null;

  const role = normalizeRole(raw.role || raw.role_name);
  if (!isSelectableRole(role)) return null;

  const companyId =
    raw.company_id ||
    raw.companyId ||
    raw.company ||
    fallbacks.companyId ||
    null;
  const companyName =
    raw.company_name ||
    raw.companyName ||
    (typeof raw.company === "string" && raw.company !== companyId ? raw.company : null) ||
    fallbacks.companyName ||
    null;

  return {
    role,
    company_id: companyId || null,
    company_name: companyName || null,
    is_default: Boolean(raw.is_default ?? raw.isDefault),
    id: raw.id || raw._id || null,
    display_name: raw.display_name ?? raw.displayName ?? null,
    professional_phone: raw.professional_phone ?? raw.professionalPhone ?? null,
    job_title: raw.job_title ?? raw.jobTitle ?? null,
    signature: raw.signature ?? raw.email_signature ?? null,
  };
}

/**
 * Perfis seleccionáveis (header + Área Pessoal), alinhados com o ContextSwitcher.
 *
 * 1. UCRs reais (`companies` / `company_roles`)
 * 2. `additional_roles` não cobertos por nenhum UCR
 * 3. Role primário se ainda faltar
 * 4. Sem UCRs: role primário + additional_roles (company_id pode ser null)
 */
export function buildUserProfileItems(user, options = {}) {
  if (!user) return [];

  const effectiveCompanyId = options.effectiveCompanyId || null;
  const fallbackCompanyId = effectiveCompanyId || user.company || null;
  const fallbackName = user.company_name || user.company || null;

  const companies = getUserCompanyRecords(user)
    .map((c) => normalizeCompanyRecord(c, { companyId: fallbackCompanyId, companyName: fallbackName }))
    .filter(Boolean);

  const additionalRoles = Array.isArray(user.additional_roles)
    ? user.additional_roles
    : [];
  const primaryRole = user.role;

  const activeCompanyName =
    companies.find((c) => c.company_id && c.company_id === effectiveCompanyId)?.company_name ||
    fallbackName ||
    "";

  let profileItems = [];

  if (companies.length > 0) {
    profileItems = [...companies];
    const companyRoles = new Set(companies.map((c) => c.role));

    for (const role of additionalRoles) {
      const normalized = normalizeRole(role);
      if (!isSelectableRole(normalized) || companyRoles.has(normalized)) continue;
      profileItems.push({
        role: normalized,
        company_id: fallbackCompanyId,
        company_name: activeCompanyName || null,
        is_default: false,
        display_name: null,
        professional_phone: null,
        job_title: null,
        signature: null,
      });
    }

    if (isSelectableRole(primaryRole)) {
      const normalized = normalizeRole(primaryRole);
      const extraNormalized = additionalRoles.map((r) => normalizeRole(r));
      if (!companyRoles.has(normalized) && !extraNormalized.includes(normalized)) {
        profileItems.unshift({
          role: normalized,
          company_id: fallbackCompanyId,
          company_name: activeCompanyName || null,
          is_default: false,
          display_name: null,
          professional_phone: null,
          job_title: null,
          signature: null,
        });
      }
    }
  } else {
    const allRoles = [
      primaryRole,
      ...additionalRoles.filter((r) => r !== primaryRole),
    ];
    profileItems = allRoles
      .map((role) =>
        normalizeCompanyRecord(role, {
          companyId: fallbackCompanyId,
          companyName: fallbackName,
        })
      )
      .filter(Boolean);
  }

  const seen = new Set();
  return profileItems.filter((p) => {
    const key = `${p.role}__${p.company_id || ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * Tabs da Área Pessoal — um ProfileRoleTab por perfil válido.
 */
export function buildProfileRoleTabs(user, options = {}) {
  return buildUserProfileItems(user, options).map((p) => {
    const companyId = p.company_id || "default";
    const companyName = p.company_name || p.company_id || user?.company || "Empresa";
    return {
      value: `${p.role}__${companyId}`,
      id: p.id || `${p.role}__${companyId}`,
      role: p.role,
      companyId,
      companyName,
      label: `${ROLE_LABELS[p.role] || p.role} @ ${companyName}`,
      icon: ROLE_ICONS[p.role],
      roleData: {
        display_name: p.display_name ?? "",
        professional_phone: p.professional_phone ?? "",
        job_title: p.job_title ?? "",
        signature: p.signature ?? "",
      },
    };
  });
}

/** Roles presentes no user (primário + additional + UCRs) — para validar activeRole. */
export function collectUserRoles(user) {
  if (!user) return [];
  const fromCompanies = getUserCompanyRecords(user)
    .map((c) => normalizeRole(c?.role || c?.role_name))
    .filter((r) => isSelectableRole(r));
  const extra = Array.isArray(user.additional_roles)
    ? user.additional_roles.map((r) => normalizeRole(r))
    : [];
  const all = [normalizeRole(user.role), ...extra, ...fromCompanies];
  return [...new Set(all.filter(Boolean))];
}
