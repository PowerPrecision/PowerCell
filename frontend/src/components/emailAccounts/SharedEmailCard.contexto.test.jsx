/**
 * Caixas partilhadas por (cargo, REDE) — o cartão tem de dizer em que rede fala (D-8).
 *
 * A rede em que o servidor gere uma caixa partilhada é a da empresa activa
 * (`X-Company-Id`). O cartão fala com `fetch` cru, que só leva o que lhe
 * escreverem à mão; sem o cabeçalho o servidor cai na rede de omissão e o
 * administrador de uma ilha editava (às cegas) a caixa errada. A regra do
 * projecto é Axios; enquanto o cartão não migrar, a fonte dos cabeçalhos é UMA
 * (`cabecalhosDeContexto`, a mesma do interceptor) e cada `fetch` tem de a usar.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cabecalhosDeContexto, syncAuthContextHeaders } from "../../services/api";

const AQUI = dirname(fileURLToPath(import.meta.url));

function semComentarios(texto) {
  return texto.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

describe("cabecalhosDeContexto", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    syncAuthContextHeaders({});
  });
  afterEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    syncAuthContextHeaders({});
  });

  it("sem contexto não inventa cabeçalhos", () => {
    expect(cabecalhosDeContexto()).toEqual({});
  });

  it("o snapshot do AuthContext vence o storage (a mesma regra do interceptor)", () => {
    sessionStorage.setItem("activeRole", "consultor");
    localStorage.setItem("active_company_id", "cmp-antiga");
    syncAuthContextHeaders({ role: "admin", companyId: "cmp-domus" });
    expect(cabecalhosDeContexto()).toEqual({
      "X-Active-Role": "admin",
      "X-Company-Id": "cmp-domus",
    });
  });

  it("recorre ao storage quando o snapshot ainda não foi escrito", () => {
    localStorage.setItem("active_company_id", "cmp-power");
    sessionStorage.setItem("activeRole", "ceo");
    expect(cabecalhosDeContexto()).toEqual({
      "X-Active-Role": "ceo",
      "X-Company-Id": "cmp-power",
    });
  });
});

describe("SharedEmailCard — cada fetch leva o contexto", () => {
  const fonte = semComentarios(readFileSync(join(AQUI, "SharedEmailCard.jsx"), "utf8"));

  it("a contraprova: o leitor encontrou as chamadas ao servidor", () => {
    expect([...fonte.matchAll(/fetch\(`\$\{API_URL\}\/api\/admin\/shared-email/g)].length).toBeGreaterThanOrEqual(5);
  });

  it("nenhum fetch às caixas partilhadas parte só com o Authorization", () => {
    const chamadas = fonte.split("fetch(`${API_URL}/api/admin/shared-email").slice(1);
    for (const chamada of chamadas) {
      const ate = chamada.slice(0, chamada.indexOf("});") + 3);
      expect(ate, ate).toContain("cabecalhosDeContexto()");
    }
  });

  it("a empresa activa entra na chave de cache: trocar de empresa não mostra a caixa da outra", () => {
    expect(fonte).toMatch(/queryKey:\s*\["shared-email",\s*effectiveCompanyId/);
  });
});
