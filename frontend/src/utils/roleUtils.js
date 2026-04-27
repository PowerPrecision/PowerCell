/**
 * Deep Role Search Utilities
 *
 * Utilitários para verificação de roles que consideram tanto o role principal
 * quanto o array additional_roles de um utilizador.
 *
 * Quando um utilizador tem role="consultor" e additional_roles=["mediador"],
 * hasRole(user, "mediador") retorna TRUE.
 */

/**
 * Verifica se um utilizador possui um determinado role (principal ou adicional).
 * @param {Object} user - Objecto do utilizador
 * @param {string} role - Role a verificar (ex: "consultor", "mediador")
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
