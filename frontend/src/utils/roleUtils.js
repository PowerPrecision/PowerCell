/**
 * ====================================================================
 * ROLE UTILITIES — PowerCell CRM
 * ====================================================================
 * Fonte única de verdade (Single Source of Truth) para RBAC no frontend.
 *
 * LISTA DEFINITIVA DE 8 PERFIS (em ordem hierárquica descendente):
 * 1. admin          — Administrador do Sistema
 * 2. ceo            — CEO
 * 3. diretor        — Diretor(a)
 * 4. administrativo — Apoio Administrativo
 * 5. consultor      — Consultor(a)
 * 6. intermediario  — Intermediário(a) de Crédito
 * 7. indexacao      — Indexação de Dados
 * 8. parceiro       — Parceiro (utilizador fantasma)
 *
 * NOTA: Os perfis 'mediador' e 'consultor_intermediario' foram removidos.
 * O perfil 'cliente' é mantido apenas para referência (não é perfil de sistema).
 * ====================================================================
 */

// ====================================================================
// CONSTANTES DE PERFIS
// ====================================================================

/** Lista definitiva de perfis do sistema (exclui 'cliente') */
export const VALID_ROLES = [
  "admin",
  "ceo",
  "diretor",
  "administrativo",
  "consultor",
  "intermediario",
  "indexacao",
  "parceiro",
];

/** Perfis de staff (têm acesso à plataforma, exclui cliente e parceiro) */
export const STAFF_ROLES = [
  "admin",
  "ceo",
  "diretor",
  "administrativo",
  "consultor",
  "intermediario",
  "indexacao",
];

/** Perfis que podem aceder ao Painel de Administração */
export const ADMIN_PANEL_ROLES = ["admin", "ceo"];

/** Perfis que podem gerir utilizadores (CRUD) */
export const USER_MANAGEMENT_ROLES = ["admin", "ceo"];

/** Perfis de gestão (diretoria + admin) */
export const MANAGEMENT_ROLES = ["admin", "ceo", "diretor"];

/** Perfis disponíveis como "Cargo Adicional" (exclui admin, parceiro, cliente) */
export const ADDITIONAL_ROLE_OPTIONS = [
  "consultor",
  "intermediario",
  "diretor",
  "administrativo",
  "indexacao",
  "ceo",
];

/** Perfis disponíveis no dropdown de "Cargo Principal" (exclui cliente) */
export const PRIMARY_ROLE_OPTIONS = [
  "consultor",
  "intermediario",
  "diretor",
  "administrativo",
  "indexacao",
  "parceiro",
  "ceo",
  "admin",
];

// ====================================================================
// MAPEAMENTO DE RÓTULOS AMIGÁVEIS
// ====================================================================

/** Rótulo amigável completo (para tabelas e formulários) */
export const ROLE_LABELS = {
  admin: "Administrador do Sistema",
  ceo: "CEO",
  diretor: "Diretor(a)",
  administrativo: "Apoio Administrativo",
  consultor: "Consultor(a)",
  intermediario: "Intermediário(a) de Crédito",
  indexacao: "Indexação de Dados",
  parceiro: "Parceiro",
  cliente: "Cliente",
};

/** Rótulo curto (para badges e espaços reduzidos) */
export const ROLE_SHORT_LABELS = {
  admin: "Admin",
  ceo: "CEO",
  diretor: "Diretor",
  administrativo: "Adminvo",
  consultor: "Consultor",
  intermediario: "Intermédio",
  indexacao: "Indexação",
  parceiro: "Parceiro",
  cliente: "Cliente",
};

// ====================================================================
// CORES DOS BADGES (Tailwind CSS)
// ====================================================================

/**
 * Cores para badges de perfil — schema visual coerente.
 * CEO = dourado/preto (executivo), Admin = vermelho (poder total),
 * Consultor = azul (operacional), Indexação = cinza (restrição), etc.
 */
export const ROLE_COLORS = {
  admin: "bg-red-100 text-red-800 border-red-200",
  ceo: "bg-yellow-100 text-yellow-950 border-yellow-400",
  diretor: "bg-purple-100 text-purple-800 border-purple-200",
  administrativo: "bg-orange-100 text-orange-800 border-orange-200",
  consultor: "bg-blue-100 text-blue-800 border-blue-200",
  intermediario: "bg-cyan-100 text-cyan-800 border-cyan-200",
  indexacao: "bg-slate-100 text-slate-800 border-slate-200",
  parceiro: "bg-violet-100 text-violet-800 border-violet-200",
  cliente: "bg-gray-100 text-gray-800 border-gray-200",
};

/** Cores para sidebar escura (fundo slate-900) */
export const ROLE_SIDEBAR_COLORS = {
  admin: "bg-red-500/20 text-red-300",
  ceo: "bg-yellow-500/20 text-yellow-200",
  diretor: "bg-purple-500/20 text-purple-300",
  administrativo: "bg-orange-500/20 text-orange-300",
  consultor: "bg-blue-500/20 text-blue-300",
  intermediario: "bg-cyan-500/20 text-cyan-300",
  indexacao: "bg-slate-500/20 text-slate-300",
  parceiro: "bg-violet-500/20 text-violet-300",
  cliente: "bg-gray-500/20 text-gray-300",
};

/** Cores para pills/badges adicionais (mais subtis) */
export const ROLE_ADDITIONAL_COLORS = {
  admin: "bg-red-50 text-red-700 border-red-100",
  ceo: "bg-yellow-50 text-yellow-800 border-yellow-200",
  diretor: "bg-purple-50 text-purple-700 border-purple-100",
  administrativo: "bg-orange-50 text-orange-700 border-orange-100",
  consultor: "bg-blue-50 text-blue-700 border-blue-100",
  intermediario: "bg-cyan-50 text-cyan-700 border-cyan-100",
  indexacao: "bg-slate-50 text-slate-700 border-slate-100",
  parceiro: "bg-violet-50 text-violet-700 border-violet-100",
  cliente: "bg-gray-50 text-gray-700 border-gray-100",
};

// ====================================================================
// ÍCONES DOS PERFIS
// ====================================================================

/** Emojis para o Context Switcher e indicações rápidas */
export const ROLE_ICONS = {
  admin: "🛡️",
  ceo: "⭐",
  diretor: "👔",
  administrativo: "📁",
  consultor: "💼",
  intermediario: "🤝",
  indexacao: "📋",
  parceiro: "🏢",
  cliente: "👤",
};

// ====================================================================
// HIERARQUIA DE PERFIS
// ====================================================================

/**
 * Nível hierárquico — quanto maior, mais permissões.
 * Usado para comparações e ordenação.
 */
export const ROLE_HIERARCHY = {
  admin: 100,
  ceo: 90,
  diretor: 70,
  administrativo: 50,
  consultor: 30,
  intermediario: 30,
  indexacao: 10,
  parceiro: 0,
  cliente: 0,
};

// ====================================================================
// FUNÇÕES DE VERIFICAÇÃO DE PERMISSÕES
// ====================================================================

/**
 * Verifica se um utilizador possui um determinado role (principal ou adicional).
 * @param {Object} user - Objecto do utilizador
 * @param {string} role - Role a verificar (ex: "consultor", "intermediario")
 * @returns {boolean}
 */
export const hasRole = (user, role) => {
  if (!user) return false;
  return user.role === role || (user.additional_roles && user.additional_roles.includes(role));
};

/**
 * Verifica se um utilizador possui qualquer um dos roles especificados.
 * @param {Object} user - Objecto do utilizador
 * @param {string[]} roles - Lista de roles a verificar
 * @returns {boolean}
 */
export const hasAnyRole = (user, roles) => {
  if (!user || !roles || roles.length === 0) return false;
  return roles.some(role => hasRole(user, role));
};

/**
 * Verifica se o utilizador pode aceder ao Painel de Administração.
 * Apenas admin e CEO.
 */
export const canAccessAdminPanel = (user) => {
  return hasAnyRole(user, ADMIN_PANEL_ROLES);
};

/**
 * Verifica se o utilizador pode gerir outros utilizadores (CRUD).
 * Apenas admin e CEO.
 */
export const canManageUsers = (user) => {
  return hasAnyRole(user, USER_MANAGEMENT_ROLES);
};

/**
 * Verifica se o utilizador pode ver a secção "Gestão e Operações".
 * Admin, CEO e Diretor.
 */
export const canSeeGestao = (user) => {
  return hasAnyRole(user, MANAGEMENT_ROLES);
};

/**
 * Verifica se o utilizador é gestor (admin, CEO ou diretor).
 * Gestores têm permissões alargadas mas não acesso total ao Painel de Administração.
 */
export const isManager = (user) => {
  return hasAnyRole(user, MANAGEMENT_ROLES);
};

/**
 * Verifica se o utilizador tem nível hierárquico suficiente para uma ação.
 * @param {Object} user - Objecto do utilizador
 * @param {string} requiredRole - Role mínimo necessário
 * @returns {boolean}
 */
export const hasAccess = (user, requiredRole) => {
  if (!user) return false;
  const userLevel = Math.max(
    getRoleLevel(user.role),
    ...(user.additional_roles || []).map(r => getRoleLevel(r))
  );
  return userLevel >= getRoleLevel(requiredRole);
};

/**
 * Verifica se um role é válido no sistema.
 * @param {string} role - Role a validar
 * @returns {boolean}
 */
export const isValidRole = (role) => {
  return VALID_ROLES.includes(role);
};

/**
 * Verifica se o utilizador é staff (tem acesso à plataforma).
 * @param {Object} user - Objecto do utilizador
 * @returns {boolean}
 */
export const isStaff = (user) => {
  if (!user) return false;
  return STAFF_ROLES.includes(user.role);
};

/**
 * Retorna o nível hierárquico de um role.
 * @param {string} role - Role a consultar
 * @returns {number} Nível (0-100)
 */
export const getRoleLevel = (role) => {
  return ROLE_HIERARCHY[role] || 0;
};

/**
 * Retorna o rótulo amigável completo de um role.
 * @param {string} role - Role a consultar
 * @returns {string} Rótulo amigável
 */
export const getRoleLabel = (role) => {
  return ROLE_LABELS[role] || role;
};

/**
 * Retorna o rótulo curto de um role.
 * @param {string} role - Role a consultar
 * @returns {string} Rótulo curto
 */
export const getRoleShortLabel = (role) => {
  return ROLE_SHORT_LABELS[role] || role;
};

/**
 * Retorna as classes CSS do badge para um role.
 * @param {string} role - Role a consultar
 * @returns {string} Classes Tailwind
 */
export const getRoleColor = (role) => {
  return ROLE_COLORS[role] || "bg-gray-100 text-gray-800 border-gray-200";
};

/**
 * Retorna as classes CSS do badge para sidebar escura.
 * @param {string} role - Role a consultar
 * @returns {string} Classes Tailwind
 */
export const getRoleSidebarColor = (role) => {
  return ROLE_SIDEBAR_COLORS[role] || "bg-gray-500/20 text-gray-300";
};

/**
 * Retorna o ícone (emoji) de um role.
 * @param {string} role - Role a consultar
 * @returns {string} Emoji
 */
export const getRoleIcon = (role) => {
  return ROLE_ICONS[role] || "👤";
};

// ====================================================================
// FUNÇÕES DE FILTRAGEM E CONTAGEM
// ====================================================================

/**
 * Filtra uma lista de utilizadores que possuem um determinado role.
 * @param {Array} users - Lista de utilizadores
 * @param {string} role - Role a filtrar
 * @returns {Array}
 */
export const filterByRole = (users, role) => {
  if (!users || !role) return users || [];
  return users.filter(u => u.role === role || (u.additional_roles && u.additional_roles.includes(role)));
};

/**
 * Filtra uma lista de utilizadores que possuem qualquer um dos roles especificados.
 * @param {Array} users - Lista de utilizadores
 * @param {string[]} roles - Lista de roles
 * @returns {Array}
 */
export const filterByAnyRole = (users, roles) => {
  if (!users || !roles || roles.length === 0) return users || [];
  // Support single-user usage: filterByAnyRole(user, roles) inside .filter()
  if (!Array.isArray(users)) {
    return roles.includes(users.role) ||
      (users.additional_roles && users.additional_roles.some(r => roles.includes(r)));
  }
  return users.filter(u =>
    roles.includes(u.role) ||
    (u.additional_roles && u.additional_roles.some(r => roles.includes(r)))
  );
};

/**
 * Exclui utilizadores que possuem qualquer um dos roles especificados.
 * @param {Array} users - Lista de utilizadores
 * @param {string[]} excludeRoles - Lista de roles a excluir
 * @returns {Array}
 */
export const excludeRoles = (users, excludeRoles) => {
  if (!users || !excludeRoles || excludeRoles.length === 0) return users || [];
  return users.filter(u =>
    !excludeRoles.includes(u.role) &&
    !(u.additional_roles && u.additional_roles.some(r => excludeRoles.includes(r)))
  );
};

/**
 * Conta utilizadores com um determinado role.
 * @param {Array} users - Lista de utilizadores
 * @param {string} role - Role a contar
 * @returns {number}
 */
export const countByRole = (users, role) => {
  if (!users || !role) return 0;
  return users.filter(u => u.role === role || (u.additional_roles && u.additional_roles.includes(role))).length;
};
