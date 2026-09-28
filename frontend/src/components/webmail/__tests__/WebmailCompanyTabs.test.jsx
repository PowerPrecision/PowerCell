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

describe("a lista ainda a carregar não inventa uma empresa", () => {
  it("com zero empresas NÃO desenha o rótulo do nome", () => {
    /**
     * O DEFEITO (CI, Set 2026): o ramo do nome único era o `else` de
     * `deveMostrarSeparadores` (`length > 1`), e o complemento disso
     * inclui o ZERO. Enquanto a lista carregava — ou quando o pedido
     * falha, ou o utilizador não tem UCR nenhum — desenhava-se o ícone
     * de empresa com o nome EM BRANCO ao lado: no ecrã, "a carregar" e
     * "uma empresa" ficavam indistinguíveis.
     *
     * E foi isso que fez o `WebmailPage.test.jsx` ser vermelho só no CI:
     * o `findByTestId` resolvia nesse estado intermédio (o elemento já
     * existia, vazio) e a asserção sobre o texto corria contra o vazio.
     * Numa máquina rápida a query chegava antes e passava.
     *
     * A correcção não é esperar melhor no teste — é o elemento só existir
     * quando tem o que dizer. A presença dele passa a SER a afirmação.
     */
    montar({ empresas: [] });

    expect(screen.queryByTestId("webmail-empresa-unica")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });

  it("com zero empresas a barra continua lá, com a sincronização", () => {
    // Contraprova: "não desenhar nada" não pode virar "esconder a barra".
    // O indicador de sincronização é independente das empresas e tem de
    // sobreviver ao estado de carregamento.
    montar({ empresas: [] });
    expect(screen.getByTestId("webmail-company-bar")).toBeInTheDocument();
  });

  it("com UMA empresa escreve o nome", () => {
    montar({ empresas: [{ company_id: "power", company_name: "Power Real Estate" }] });
    expect(screen.getByTestId("webmail-empresa-unica"))
      .toHaveTextContent("Power Real Estate");
  });
});
