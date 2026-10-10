/**
 * Qual é o perfil que o ecrã deve mostrar? — ponto único (Bloco 4, ponto 33).
 *
 * Em sessão normal é o perfil activo (`activeRole`), escolhido no
 * `ContextSwitcher`, ou o cargo base. Em IMPERSONATE o ambiente tem de
 * espelhar exactamente — e apenas — o que o utilizador-alvo vê, mesmo que
 * quem iniciou a sessão seja Admin. O `activeRole` é estado do NAVEGADOR e
 * pode ter ficado do administrador (sessionStorage de outro separador, um
 * arranque que ainda não leu o `/auth/me`); se for um perfil que o alvo não
 * tem, ignora-se e vale o cargo do alvo.
 *
 * Antes desta regra o menu lateral tinha o seu próprio atalho
 * (`isImpersonating ? user.role : effectiveRole`) e TODOS os outros
 * consumidores do `effectiveRole` (guardas de rota, redirecção do
 * dashboard, selector de perfil, gates dos botões) liam o `activeRole` cru:
 * duas fontes para a mesma pergunta, que divergem sem dar erro. Agora o
 * `AuthContext` publica um só valor e o menu limita-se a lê-lo.
 */
import { collectUserRoles } from "./userProfiles";

/**
 * @param {Object} sessao
 * @param {boolean} [sessao.isImpersonating]
 * @param {object|null} [sessao.user] - Utilizador da sessão (o ALVO, em impersonate).
 * @param {string|null} [sessao.activeRole] - Perfil activo guardado no navegador.
 * @returns {string|undefined}
 */
export function papelEfectivoDaSessao({ isImpersonating = false, user = null, activeRole = null } = {}) {
  if (!isImpersonating) return activeRole || user?.role;

  const perfisDoAlvo = collectUserRoles(user);
  if (activeRole && perfisDoAlvo.includes(activeRole)) return activeRole;
  return user?.role;
}
