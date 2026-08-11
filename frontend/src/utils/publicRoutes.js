/**
 * PACOTE DI — Rotas públicas que não devem disparar fetchUser() nem redirect to /login.
 *
 * Estas rotas usam tokens próprios (URL token, magic link) e não o token de staff global
 * guardado em localStorage. Quando um consultor com sessão staff ativa clica num destes
 * links (ex: /rgpd/:token recebido por email), o AuthContext NÃO deve chamar
 * /auth/me com o token de staff (que pode estar expirado e disparar o redirect 401),
 * e o interceptor 401 do api.js NÃO deve redirecionar para /login.
 *
 * Lista de prefixos cobertos:
 *  - /portal   → Portal do Cliente (portal_token próprio)
 *  - /rgpd     → Link público RGPD (/rgpd/:token — raw fetch no RGPDPage)
 *  - /upload   → Magic link de upload (/upload/:token)
 *  - /download → Magic link de download (/download/:token)
 */
export const PUBLIC_ROUTE_PREFIXES = ['/portal', '/rgpd', '/upload', '/download'];

/**
 * Verifica se o pathname atual corresponde a uma rota pública.
 *
 * @param {string} [pathname=window.location.pathname] - Pathname a verificar.
 *   Por defeito usa o pathname atual do browser, para que possa ser chamado sem args.
 * @returns {boolean} true se o pathname começar com algum dos prefixos públicos.
 */
export const isPublicRoute = (pathname = window.location.pathname) =>
  PUBLIC_ROUTE_PREFIXES.some(p => pathname.startsWith(p));
