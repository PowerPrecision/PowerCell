/**
 * «Modo de Operação» do Master: só o nome limpo de cada empresa.
 *
 * O Master tem um UCR por empresa, todos com o mesmo cargo. O menu repetia
 * «Master (Global)» em cada linha (e a empresa entre parênteses); agora cada
 * linha é a empresa, e «Sistema» a vista global. Os outros cargos mantêm o
 * cargo — é a única informação que os distingue.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const auth = vi.hoisted(() => ({ valor: {} }));
vi.mock("../../../contexts/AuthContext", () => ({ useAuth: () => auth.valor }));

import ContextSwitcher from "../ContextSwitcher";
import { rotuloDoPerfil } from "../../../utils/userProfiles";

const MASTER = {
  role: "master",
  companies: [
    { role: "master", company_id: "cmp-domus", company_name: "Domus" },
    { role: "master", company_id: "cmp-power", company_name: "Power Real Estate" },
    { role: "master", company_id: "cmp-precision", company_name: "Precision Crédito" },
    { role: "master", company_id: "default", company_name: "default" },
  ],
};

function montar(user, extra = {}) {
  auth.valor = {
    user,
    effectiveRole: "master",
    effectiveCompanyId: "cmp-domus",
    switchActiveRole: vi.fn(),
    switchActiveCompany: vi.fn(),
    ...extra,
  };
  return render(<ContextSwitcher />);
}

async function abrirModoDeOperacao() {
  await userEvent.click(screen.getByRole("button", { name: /modo atual/i }));
  return screen.findByRole("menu");
}

describe("rotuloDoPerfil", () => {
  it("Master: o nome da empresa, sem o cargo e sem parênteses", () => {
    expect(rotuloDoPerfil({ role: "master", company_id: "c1", company_name: "Domus" }, { varias_empresas: true }))
      .toEqual({ principal: "Domus", secundario: "" });
  });

  it("Master sem empresa real (ou 'default'): «Sistema»", () => {
    expect(rotuloDoPerfil({ role: "master", company_id: null, company_name: null }).principal).toBe("Sistema");
    expect(rotuloDoPerfil({ role: "master", company_id: "default", company_name: "default" }).principal).toBe("Sistema");
  });

  it("Master com id real mas sem nome não mostra o id: «Sistema»", () => {
    expect(rotuloDoPerfil({ role: "master", company_id: "cmp-x", company_name: "" }).principal).toBe("Sistema");
  });

  it("outros cargos mantêm o cargo e a empresa (só com várias empresas)", () => {
    const p = { role: "diretor", company_id: "c1", company_name: "Power" };
    expect(rotuloDoPerfil(p, { varias_empresas: true })).toEqual({ principal: "Diretor(a)", secundario: "Power" });
    expect(rotuloDoPerfil(p, { varias_empresas: false })).toEqual({ principal: "Diretor(a)", secundario: "" });
  });
});

describe("ContextSwitcher — vista Master", () => {
  it("cada linha é só o nome da empresa; «Master (Global)» não se repete no menu", async () => {
    montar(MASTER);
    const menu = await abrirModoDeOperacao();
    const itens = within(menu).getAllByRole("menuitem");

    expect(itens).toHaveLength(4);
    expect(itens.map((i) => i.textContent.replace(/ATIVO|Padrão/g, "").replace(/\p{Extended_Pictographic}/gu, "").trim()))
      .toEqual(["Domus", "Power Real Estate", "Precision Crédito", "Sistema"]);
    expect(within(menu).queryByText(/Master \(Global\)/)).not.toBeInTheDocument();
  });

  it("escolher uma linha muda para esse perfil e essa empresa", async () => {
    const switchActiveRole = vi.fn();
    montar(MASTER, { switchActiveRole });
    const menu = await abrirModoDeOperacao();
    await userEvent.click(within(menu).getByRole("menuitem", { name: /Power Real Estate/ }));
    expect(switchActiveRole).toHaveBeenCalledWith("master", "cmp-power");
  });

  it("quem tem cargos diferentes em empresas diferentes continua a ver o cargo", async () => {
    montar({
      role: "diretor",
      companies: [
        { role: "diretor", company_id: "cmp-power", company_name: "Power Real Estate" },
        { role: "consultor", company_id: "cmp-domus", company_name: "Domus" },
      ],
    }, { effectiveRole: "diretor", effectiveCompanyId: "cmp-power" });
    const menu = await abrirModoDeOperacao();
    expect(within(menu).getByText("Diretor(a)")).toBeInTheDocument();
    expect(within(menu).getByText("(Domus)")).toBeInTheDocument();
  });
});
