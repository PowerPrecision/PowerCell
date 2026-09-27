import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import WebmailCompanyTabs from "../WebmailCompanyTabs";

const DUAS = [
  { company_id: "power", company_name: "Power Real Estate" },
  { company_id: "domus", company_name: "Domus" },
];

function montar(props = {}) {
  const onSelectCompany = vi.fn();
  const onSync = vi.fn();
  render(
    <WebmailCompanyTabs
      empresas={DUAS}
      empresaActivaId="power"
      onSelectCompany={onSelectCompany}
      onSync={onSync}
      {...props}
    />,
  );
  return { onSelectCompany, onSync };
}

describe("WebmailCompanyTabs", () => {
  it("desenha um separador por empresa", () => {
    montar();
    expect(screen.getByRole("tab", { name: /Power Real Estate/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Domus/ })).toBeInTheDocument();
  });

  it("marca o separador activo", () => {
    montar({ empresaActivaId: "domus" });
    expect(screen.getByRole("tab", { name: /Domus/ }))
      .toHaveAttribute("data-state", "active");
  });

  it("avisa quando se troca de empresa", async () => {
    const user = userEvent.setup();
    const { onSelectCompany } = montar();
    await user.click(screen.getByRole("tab", { name: /Domus/ }));
    expect(onSelectCompany).toHaveBeenCalledWith("domus");
  });

  it("com UMA empresa não desenha separador nenhum", () => {
    // Zero ruído: um separador solitário é uma escolha que não existe.
    montar({ empresas: [DUAS[0]], empresaActivaId: "power" });
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
    // Mas o nome continua visível — saber onde se está não é ruído.
    expect(screen.getByTestId("webmail-empresa-unica"))
      .toHaveTextContent("Power Real Estate");
  });

  it("mostra o estado da sincronização em vez de um painel", () => {
    montar({ ultimaSinc: new Date(Date.now() - 5 * 60000) });
    expect(screen.getByTestId("webmail-estado-sinc"))
      .toHaveTextContent("Actualizado há 5 min");
  });

  it("sincroniza a pedido", async () => {
    const user = userEvent.setup();
    const { onSync } = montar();
    await user.click(screen.getByRole("button", { name: /sincronizar/i }));
    expect(onSync).toHaveBeenCalled();
  });

  it("trava o botão enquanto sincroniza", async () => {
    const user = userEvent.setup();
    const { onSync } = montar({ syncing: true });
    const botao = screen.getByRole("button", { name: /sincronizar/i });
    expect(botao).toBeDisabled();
    expect(screen.getByTestId("webmail-estado-sinc"))
      .toHaveTextContent("A sincronizar…");
    await user.click(botao);
    expect(onSync).not.toHaveBeenCalled();
  });

  it("um nome em falta não deixa o separador em branco", () => {
    montar({
      empresas: [{ company_id: "sem-nome" }, DUAS[1]],
      empresaActivaId: "sem-nome",
    });
    expect(screen.getByRole("tab", { name: /sem-nome/ })).toBeInTheDocument();
  });
});
