/**
 * Hierarquia de perfis no ecrã: UM global (Master), o resto local
 * (adenda de RBAC, Out 2026).
 *
 * O servidor é a parede (403/404). Isto garante o lado do ecrã: que o Master
 * passa onde o Admin passa, que o Admin NÃO passa onde só o Master passa, que
 * as listas de papéis do frontend não esquecem o Master, e que as duas
 * listas de perfis (Python e JS) dizem o mesmo.
 */
import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import {
  VALID_ROLES,
  canAccessByEffectiveRole,
  canAccessOrgAdmin,
  grantableRoles,
  hasAnyRole,
  hasRole,
  isMaster,
  normalizeRole,
  PRIMARY_ROLE_OPTIONS,
  ROLE_LABELS,
  UCR_ASSIGNABLE_ROLES,
} from "./roleUtils";

const AQUI = dirname(fileURLToPath(import.meta.url));
const SRC = join(AQUI, "..");
const BACKEND = join(SRC, "..", "..", "backend");

const OS_NOVE = [
  "master", "admin", "ceo", "diretor", "administrativo",
  "consultor", "intermediario", "parceiro", "indexacao",
];

const MASTER = { role: "master" };
const ADMIN = { role: "admin" };

describe("os 9 perfis", () => {
  it("o frontend reconhece exactamente os 9", () => {
    expect([...VALID_ROLES].sort()).toEqual([...OS_NOVE].sort());
  });

  it("Python e JS dizem o mesmo (duas listas em linguagens diferentes divergem sem dar erro)", () => {
    const py = readFileSync(join(BACKEND, "models", "auth.py"), "utf8");
    const bloco = py.match(/PERFIS_DO_SISTEMA = \(([\s\S]*?)\)/)[1];
    const doPython = [...bloco.matchAll(/"(\w+)"/g)].map((m) => m[1]);
    expect(doPython.sort()).toEqual([...VALID_ROLES].sort());
  });

  it("«Index» é o nome do ecrã do perfil indexacao", () => {
    expect(normalizeRole("Index")).toBe("indexacao");
    expect(normalizeRole("indexador")).toBe("indexacao");
    expect(ROLE_LABELS.master).toBeTruthy();
  });
});

describe("o Master passa tudo o que o Admin passa — e o Admin não passa o que é do Master", () => {
  it("hasRole: master implica admin, admin NÃO implica master", () => {
    expect(hasRole(MASTER, "admin")).toBe(true);
    expect(hasRole(MASTER, "master")).toBe(true);
    expect(hasRole(ADMIN, "master")).toBe(false);
    expect(hasAnyRole(ADMIN, ["master"])).toBe(false);
    expect(hasAnyRole(MASTER, ["admin", "ceo"])).toBe(true);
  });

  it("um additional_role `master` não torna ninguém global (o servidor ignora-os)", () => {
    // A contraprova é o servidor; aqui só se afirma o que o ecrã faz hoje.
    expect(isMaster({ role: "admin", additional_roles: ["master"] })).toBe(false);
  });

  it("canAccessByEffectiveRole: o Master passa qualquer guarda de rota", () => {
    expect(canAccessByEffectiveRole("master", ["consultor"])).toBe(true);
    expect(canAccessByEffectiveRole("master", ["master"])).toBe(true);
    expect(canAccessByEffectiveRole("admin", ["master"])).toBe(false);
    expect(canAccessByEffectiveRole("ceo", ["master"])).toBe(false);
  });

  it("o painel de administração é de master, admin e ceo", () => {
    for (const r of ["master", "admin", "ceo"]) expect(canAccessOrgAdmin(r)).toBe(true);
    for (const r of ["diretor", "consultor", "indexacao"]) expect(canAccessOrgAdmin(r)).toBe(false);
  });

  it("só o Master concede o perfil master", () => {
    expect(grantableRoles("master", PRIMARY_ROLE_OPTIONS)).toContain("master");
    expect(grantableRoles("admin", PRIMARY_ROLE_OPTIONS)).not.toContain("master");
    expect(grantableRoles("", UCR_ASSIGNABLE_ROLES)).not.toContain("master");
    expect(grantableRoles("ceo", UCR_ASSIGNABLE_ROLES)).toContain("admin");
  });
});

// ── inventário de fonte ─────────────────────────────────────────────
function ficheiros(pasta) {
  const saida = [];
  for (const nome of readdirSync(pasta)) {
    const caminho = join(pasta, nome);
    if (statSync(caminho).isDirectory()) {
      if (nome === "node_modules" || nome === "__tests__") continue;
      saida.push(...ficheiros(caminho));
    } else if (/\.(js|jsx)$/.test(nome) && !/\.test\./.test(nome)) {
      saida.push(caminho);
    }
  }
  return saida;
}

function semComentarios(texto) {
  return texto
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .split("\n")
    .map((l) => l.replace(/^\s*\/\/.*$/, ""))
    .join("\n");
}

describe("inventário: nenhuma lista de papéis com `admin` esquece o `master`", () => {
  const ARRAYS = /\[[^[\]\n]*?(["'])admin\1[^[\]\n]*?\]/g;

  it("o leitor encontra mesmo listas (contraprova)", () => {
    let total = 0;
    for (const f of ficheiros(SRC)) {
      total += [...semComentarios(readFileSync(f, "utf8")).matchAll(ARRAYS)].length;
    }
    expect(total).toBeGreaterThan(30);
  });

  it("toda a lista com 'admin' tem 'master' (ou está declarada como excepção)", () => {
    // Excepções: objectos {role: "admin", label} das caixas partilhadas por
    // NOME DE CAIXA, que não são listas de perfis.
    const falhas = [];
    for (const f of ficheiros(SRC)) {
      const limpo = semComentarios(readFileSync(f, "utf8"));
      for (const m of limpo.matchAll(ARRAYS)) {
        if (!/["']master["']/.test(m[0])) {
          falhas.push(`${relative(SRC, f)}: ${m[0].slice(0, 90)}`);
        }
      }
    }
    expect(falhas, falhas.join("\n")).toEqual([]);
  });
});

describe("as rotas de infraestrutura são só do Master", () => {
  const APP = readFileSync(join(SRC, "App.js"), "utf8");
  const papeisDaRota = (caminho) => {
    const i = APP.indexOf(`path="${caminho}"`);
    const bloco = APP.slice(i, i + 700);
    return [...bloco.match(/allowedRoles=\{\[([\s\S]*?)\]\}/)[1].matchAll(/"([a-z_]+)"/g)].map((x) => x[1]);
  };

  it.each([
    "/configuracoes/ia", "/configuracoes/treino-ia", "/admin/processos-background",
    "/configuracoes/notificacoes", "/admin/logs", "/admin/backups",
    "/diagnosticos", "/contas-email", "/workflow-estados",
  ])("%s", (rota) => {
    expect(papeisDaRota(rota)).toEqual(["master"]);
  });

  it.each(["/admin", "/admin/organizacao", "/admin/desempenho", "/admin/relatorio-semanal"])(
    "%s é de master, admin e ceo",
    (rota) => {
      const p = papeisDaRota(rota);
      expect(p).toContain("master");
      expect(p).toContain("admin");
      expect(p).toContain("ceo");
    },
  );
});

describe("a ligação do isMaster aos ecrãs de gestão", () => {
  const ler = (...partes) => semComentarios(readFileSync(join(SRC, ...partes), "utf8"));

  it("as duas páginas que montam o separador Empresas e Utilizadores passam o isMaster", () => {
    for (const pagina of ["pages/SystemAdminPanel.jsx", "pages/OrganizationAdminPage.jsx"]) {
      const fonte = ler(pagina);
      expect(fonte, pagina).toMatch(/<CompaniesAdminTab isMaster=\{/);
      expect(fonte, pagina).toMatch(/<UsersAccessAdminTab isMaster=\{/);
    }
  });

  it("o separador de utilizadores passa o isMaster ao diálogo de criação", () => {
    expect(ler("components/admin/UsersAccessAdminTab.jsx")).toMatch(/<UserCreateDialog[\s\S]*?isMaster=\{isMaster\}/);
  });

  it("o diálogo de criação filtra os perfis pelo que o Master pode conceder", () => {
    const fonte = ler("components/admin/UserAccountDialogs.jsx");
    expect(fonte).toMatch(/grantableRoles\(viewerRole, PRIMARY_ROLE_OPTIONS\)/);
    expect(fonte).toMatch(/grantableRoles\(viewerRole, UCR_ASSIGNABLE_ROLES\)/);
    expect(fonte).not.toMatch(/PRIMARY_ROLE_OPTIONS\.map/);
  });

  it("o separador Técnico, o Histórico, as Comunicações e o Workflow usam o isMaster", () => {
    const fonte = ler("pages/SystemAdminPanel.jsx");
    expect(fonte).toMatch(/const isMaster = hasRole\(user, "master"\)/);
    expect(fonte).not.toMatch(/isAdmin/);
  });

  it("a configuração global de sistema decide pelo Master", () => {
    expect(ler("pages/SystemConfigPage.js")).toMatch(/const isMaster = hasRole\(user, "master"\)/);
    expect(ler("pages/systemConfig/MaintenanceSection.js")).toMatch(/hasRole\(user, "master"\) && <S3RelinkPanel/);
  });
});
