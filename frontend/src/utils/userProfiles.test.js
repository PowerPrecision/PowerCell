/**
 * Pacote DP — mapeamento de perfis / UCRs para Área Pessoal e Header.
 * Run: node --test src/utils/userProfiles.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildProfileRoleTabs,
  buildUserProfileItems,
  collectUserRoles,
  getDistinctCompanies,
  getUserCompanyRecords,
  resolveActiveCompanyName,
  resolveCompanyIdFromUser,
} from "./userProfiles.js";

describe("getUserCompanyRecords", () => {
  it("lê companies, company_roles ou user_company_roles", () => {
    assert.deepEqual(getUserCompanyRecords({ companies: [{ role: "consultor" }] }).length, 1);
    assert.deepEqual(getUserCompanyRecords({ company_roles: [{ role: "diretor" }] }).length, 1);
    assert.deepEqual(getUserCompanyRecords({ user_company_roles: [{ role: "ceo" }] }).length, 1);
    assert.deepEqual(getUserCompanyRecords({}), []);
  });
});

describe("buildUserProfileItems", () => {
  it("mapeia UCRs com company_id camelCase e não descarta default", () => {
    const items = buildUserProfileItems({
      role: "consultor",
      companies: [
        { role: "Consultor", companyId: "default", companyName: "Power" },
        { role: "intermediario", company_id: "c2", company_name: "Precision" },
      ],
    });
    assert.equal(items.length, 2);
    assert.equal(items[0].role, "consultor");
    assert.equal(items[0].company_id, "default");
    assert.equal(items[1].role, "intermediario");
  });

  it("cai para additional_roles quando companies está vazio (bug Área Pessoal)", () => {
    const items = buildUserProfileItems({
      role: "consultor",
      additional_roles: ["intermediario", "diretor"],
      company: "Power Real Estate",
    });
    assert.equal(items.length, 3);
    assert.deepEqual(
      items.map((i) => i.role),
      ["consultor", "intermediario", "diretor"]
    );
    assert.ok(items.every((i) => i.company_id === "Power Real Estate"));
  });

  it("PACOTE 8 — perfis fantasma: com UCRs reais NÃO mescla additional_roles/role primário", () => {
    // Cenário do bug: utilizadora com 2 perfis activos via 3 opções no menu.
    // O role global de login (ceo) e o additional_role sem UCR (intermediario)
    // são perfis sintéticos — o menu só pode mostrar os 2 UCRs reais.
    const items = buildUserProfileItems({
      role: "ceo",
      additional_roles: ["intermediario"],
      companies: [
        { role: "diretor", company_id: "c1", company_name: "Power" },
        { role: "consultor", company_id: "c2", company_name: "Precision" },
      ],
    });
    assert.equal(items.length, 2);
    assert.deepEqual(items.map((i) => i.role), ["diretor", "consultor"]);
    // company_id vem sempre do UCR real — nunca do fallback sintético
    assert.deepEqual(items.map((i) => i.company_id), ["c1", "c2"]);
  });
});

describe("buildProfileRoleTabs", () => {
  it("gera uma tab ProfileRoleTab por perfil válido", () => {
    const tabs = buildProfileRoleTabs({
      role: "consultor",
      additional_roles: ["intermediario"],
      company: "Power",
    });
    assert.equal(tabs.length, 2);
    assert.equal(tabs[0].role, "consultor");
    assert.equal(tabs[0].companyId, "Power");
    assert.match(tabs[0].label, /Consultor/);
    assert.equal(tabs[1].role, "intermediario");
    assert.ok(tabs[0].id);
    assert.ok(tabs[1].id);
    assert.notEqual(tabs[0].id, tabs[1].id);
    assert.deepEqual(tabs[0].roleData, {
      display_name: "",
      professional_phone: "",
      job_title: "",
      signature: "",
    });
  });

  it("passa role_data do UCR para a tab", () => {
    const tabs = buildProfileRoleTabs({
      role: "consultor",
      companies: [{
        role: "consultor",
        company_id: "c1",
        company_name: "Power",
        display_name: "Ana Power",
        professional_phone: "910000000",
        job_title: "Consultora",
        signature: "<p>Ana</p>",
      }],
    });
    assert.equal(tabs[0].roleData.display_name, "Ana Power");
    assert.equal(tabs[0].roleData.professional_phone, "910000000");
    assert.equal(tabs[0].roleData.job_title, "Consultora");
    assert.equal(tabs[0].roleData.signature, "<p>Ana</p>");
  });
});

describe("getDistinctCompanies", () => {
  it("devolve uma entrada por company_id, mesmo com vários cargos na mesma empresa", () => {
    const companies = getDistinctCompanies({
      role: "diretor",
      companies: [
        { role: "diretor", company_id: "c1", company_name: "Power Real Estate" },
        { role: "consultor", company_id: "c1", company_name: "Power Real Estate" },
        { role: "intermediario", company_id: "c2", company_name: "Precision Crédito" },
      ],
    });
    assert.equal(companies.length, 2);
    assert.deepEqual(companies.map((c) => c.company_id), ["c1", "c2"]);
    // Nomes intactos — nunca concatenados entre entradas
    assert.equal(companies[0].company_name, "Power Real Estate");
    assert.equal(companies[1].company_name, "Precision Crédito");
  });

  it("ignora UCRs sem company_id real (não itera por 'default')", () => {
    const companies = getDistinctCompanies({
      role: "consultor",
      companies: [
        { role: "consultor" }, // sem company_id / company_name — inválido
        { role: "intermediario", company_id: "c2", company_name: "Precision Crédito" },
      ],
    });
    assert.equal(companies.length, 1);
    assert.equal(companies[0].company_id, "c2");
  });

  it("usa company_id como fallback de nome em vez de deixar vazio", () => {
    const companies = getDistinctCompanies({
      role: "consultor",
      companies: [{ role: "consultor", company_id: "c3" }],
    });
    assert.equal(companies.length, 1);
    assert.equal(companies[0].company_name, "c3");
  });

  it("devolve lista vazia sem empresas associadas", () => {
    assert.deepEqual(getDistinctCompanies({ role: "consultor" }), []);
    assert.deepEqual(getDistinctCompanies(null), []);
  });
});

describe("collectUserRoles", () => {
  it("inclui roles só presentes em UCRs", () => {
    const roles = collectUserRoles({
      role: "consultor",
      additional_roles: [],
      companies: [{ role: "intermediario", company_id: "c1" }],
    });
    assert.ok(roles.includes("consultor"));
    assert.ok(roles.includes("intermediario"));
  });
});

describe("resolveCompanyIdFromUser", () => {
  const user = {
    role: "consultor",
    company: "Precision Crédito",
    companies: [
      { role: "consultor", company_id: "co-uuid", company_name: "Precision Crédito" },
    ],
  };

  it("resolve o id canónico quando o hint é o nome da empresa", () => {
    assert.equal(resolveCompanyIdFromUser(user, "Precision Crédito", "consultor"), "co-uuid");
  });

  it("mantém um company_id já canónico", () => {
    assert.equal(resolveCompanyIdFromUser(user, "co-uuid", "consultor"), "co-uuid");
  });

  it("não devolve o nome da empresa quando não há UCR", () => {
    assert.equal(
      resolveCompanyIdFromUser({ role: "consultor", company: "Precision Crédito" }, "Precision Crédito", "consultor"),
      null,
    );
  });
});


/**
 * ────────────────────────────────────────────────────────────────────
 * Ponto 12 — o nome da empresa activa, junto ao nome e ao perfil.
 * ────────────────────────────────────────────────────────────────────
 *
 * O PEDIDO: mostrar a empresa actual no canto inferior esquerdo, ao pé
 * do Nome/Perfil.
 *
 * PORQUE É QUE NÃO BASTAVA LER O `ContextSwitcher`
 *   Ele já resolvia o nome — mas devolve `null` quando o utilizador tem
 *   um só perfil E uma só empresa (`if (!hasMultipleRoles &&
 *   !showCompanySwitcher) return null;`). Ou seja: quem tem uma empresa
 *   só, que é a maioria, nunca via o nome dela em lado nenhum. O menu
 *   tem de o mostrar SEMPRE, e por isso a resolução saiu do componente
 *   para aqui — duplicar a cadeia de fallback daria dois sítios a
 *   divergir, que é a raiz do incidente de 2026-09-21.
 *
 * `user.company` É O NOME, `company_id` É O ID
 *   A confusão entre os dois é o incidente de 2026-09-21. Aqui
 *   queremos mesmo o NOME, e `user.company` é o último recurso
 *   legítimo — mas só isso: um `company_id` nunca pode acabar no ecrã
 *   como se fosse nome.
 */
describe("resolveActiveCompanyName — ponto 12", () => {
  const utilizador = {
    company: "Power Real Estate",
    user_company_roles: [
      { company_id: "c1", company_name: "Power Real Estate", role: "consultor" },
      { company_id: "c2", company_name: "Precision Crédito", role: "intermediario" },
    ],
  };

  it("devolve o nome da empresa activa", () => {
    assert.equal(resolveActiveCompanyName(utilizador, "c2"), "Precision Crédito");
  });

  it("com uma empresa só continua a devolver o nome", () => {
    // O caso que o ContextSwitcher não cobria: é ele que esconde tudo
    // quando não há nada para alternar.
    const umaSo = {
      company: "Power Real Estate",
      user_company_roles: [
        { company_id: "c1", company_name: "Power Real Estate", role: "consultor" },
      ],
    };
    assert.equal(resolveActiveCompanyName(umaSo, "c1"), "Power Real Estate");
  });

  it("sem empresa activa escolhida cai no nome do utilizador", () => {
    assert.equal(resolveActiveCompanyName(utilizador, null), "Power Real Estate");
  });

  it("uma empresa activa desconhecida não inventa nome", () => {
    // Melhor não dizer nada do que dizer a empresa errada no ecrã.
    const semFallback = { user_company_roles: [{ company_id: "c1", company_name: "A" }] };
    assert.equal(resolveActiveCompanyName(semFallback, "cX"), "");
  });

  it("NUNCA devolve um company_id como se fosse nome", () => {
    // A confusão id/nome é o incidente de 2026-09-21. Um id no ecrã é
    // um sintoma silencioso: parece um nome estranho, não um erro.
    const semNome = { user_company_roles: [{ company_id: "c1", role: "consultor" }] };
    const resultado = resolveActiveCompanyName(semNome, "c1");
    assert.notEqual(resultado, "c1");
  });

  it("sem dados nenhuns devolve string vazia e não rebenta", () => {
    assert.equal(resolveActiveCompanyName(null, null), "");
    assert.equal(resolveActiveCompanyName(undefined, "c1"), "");
    assert.equal(resolveActiveCompanyName({}, null), "");
  });
});
