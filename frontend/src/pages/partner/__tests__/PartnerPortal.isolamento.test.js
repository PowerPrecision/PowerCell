/**
 * O Portal do Parceiro é outro plano de identidade — as guardas que o provam.
 *
 *  1. `/parceiro` é uma rota PÚBLICA para o CRM (sem isto, um consultor com a
 *     sessão do staff expirada via o interceptor mandá-lo para /login, e o
 *     `AuthContext` pedia /auth/me com o token errado);
 *  2. nenhum ficheiro do portal importa o contexto nem o cliente HTTP do staff
 *     (levariam `X-Company-Id`/`X-Active-Role` e o token do CRM);
 *  3. o Sentry não grava a sessão (o replay regista nomes e NIFs de leads);
 *  4. as rotas estão montadas fora do `ProtectedRoute` do staff.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { PUBLIC_ROUTE_PREFIXES, isPublicRoute } from "@/utils/publicRoutes";

const SRC = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const ler = (...p) => readFileSync(join(SRC, ...p), "utf8");

/** Sem comentários (a explicação do defeito não pode fazer a guarda ficar vermelha). */
const semComentarios = (codigo) => codigo.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

const ficheiros = (dir) =>
  readdirSync(dir).flatMap((nome) => {
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) return nome === "__tests__" ? [] : ficheiros(caminho);
    return /\.(jsx?|js)$/.test(nome) && !/\.test\./.test(nome) ? [caminho] : [];
  });

const DO_PORTAL = [
  ...ficheiros(join(SRC, "pages", "partner")),
  ...ficheiros(join(SRC, "components", "partner")),
  join(SRC, "services", "partnerApi.js"),
  join(SRC, "contexts", "PartnerAuthContext.jsx"),
  join(SRC, "utils", "partnerSession.js"),
  join(SRC, "utils", "partnerPortal.js"),
];

describe("rota pública para o CRM", () => {
  it("/parceiro está na lista e reconhece sub-rotas", () => {
    expect(PUBLIC_ROUTE_PREFIXES).toContain("/parceiro");
    for (const p of ["/parceiro", "/parceiro/casos/x", "/parceiro/convite/tok"]) expect(isPublicRoute(p)).toBe(true);
    expect(isPublicRoute("/processos")).toBe(false);
  });

  it("o Sentry (main.jsx) também trata TODAS as rotas públicas como tal — o replay grava PII de leads", () => {
    const m = ler("main.jsx").match(/const isPublicRoute = (\/[^\n]+\/)\.test/);
    expect(m, "regex do main.jsx não encontrada").not.toBeNull();
    const re = new RegExp(m[1].slice(1, -1));
    for (const prefixo of PUBLIC_ROUTE_PREFIXES) expect(re.test(prefixo), prefixo).toBe(true);
    expect(re.test("/processos")).toBe(false);
  });
});

describe("o portal não toca no plano do staff", () => {
  it("o inventário leu ficheiros a sério (contraprova)", () => {
    expect(DO_PORTAL.length).toBeGreaterThan(12);
    expect(DO_PORTAL.some((f) => f.endsWith("PartnerCasePage.jsx"))).toBe(true);
  });

  it("nenhum ficheiro importa o AuthContext, o cliente Axios nem o token do staff", () => {
    const proibido = [
      /from\s+["'](?:@|\.\.?)\/?(?:[./]*)contexts\/AuthContext["']/,
      /from\s+["'](?:@\/|[./]+\/)services\/api["']/,
      /from\s+["'](?:@\/|[./]+\/)services\/sessionExpiry["']/,
      /localStorage/,
      /X-Company-Id|X-Active-Role/,
    ];
    for (const ficheiro of DO_PORTAL) {
      const codigo = semComentarios(readFileSync(ficheiro, "utf8"));
      for (const re of proibido) expect(codigo, `${ficheiro} ~ ${re}`).not.toMatch(re);
    }
  });

  it("o cliente HTTP do parceiro é separado e não traz os cabeçalhos do CRM", () => {
    const codigo = semComentarios(ler("services", "partnerApi.js"));
    expect(codigo).toMatch(/axios\.create\(/);
    expect(codigo).toMatch(/\/partner/);
    expect(codigo).not.toMatch(/X-Company-Id|X-Active-Role|authContextHeaders/);
  });

  it("as rotas do parceiro vivem fora de qualquer ProtectedRoute", () => {
    // sem `semComentarios`: o literal "/parceiro/*" contém «/*» e o removedor de comentários engoliria o ficheiro
    const app = ler("App.js");
    const bloco = app.match(/<Route\s+path="\/parceiro\/\*"[\s\S]*?\/>\s*\n/);
    expect(bloco, "rota /parceiro/* não encontrada").not.toBeNull();
    expect(bloco[0]).toMatch(/PartnerPortalRoutes/);
    expect(bloco[0]).not.toMatch(/ProtectedRoute/);
  });
});
