import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import PortalHub from "../PortalHub";

const P1 = { id: "p-1", numero: 11, tipo_rotulo: "Crédito Habitação", empresa: "Power Real Estate", estado_rotulo: "Fase Bancária" };
const P2 = { id: "p-2", numero: 22, tipo_rotulo: "Crédito Pessoal", empresa: "Domus", estado_rotulo: "Clientes em Espera" };

describe("PortalHub", () => {
  it("lista cada processo por «Tipo · Empresa», com o número e a fase por baixo", () => {
    render(<PortalHub nome="Joana" processos={[P1, P2]} onEscolher={() => {}} />);
    expect(screen.getByRole("heading")).toHaveTextContent("Olá, Joana");
    const a = screen.getByRole("button", { name: "Crédito Habitação · Power Real Estate" });
    const b = screen.getByRole("button", { name: "Crédito Pessoal · Domus" });
    expect(a).toHaveTextContent("Processo n.º 11 · Fase Bancária");
    expect(b).toHaveTextContent("Processo n.º 22 · Clientes em Espera");
  });

  it("clicar escolhe esse processo e só esse", async () => {
    const onEscolher = vi.fn();
    render(<PortalHub processos={[P1, P2]} onEscolher={onEscolher} />);
    await userEvent.click(screen.getByRole("button", { name: /Domus/ }));
    expect(onEscolher).toHaveBeenCalledTimes(1);
    expect(onEscolher).toHaveBeenCalledWith("p-2");
  });

  it("enquanto um pedido decorre, nenhum botão aceita outro clique", async () => {
    const onEscolher = vi.fn();
    render(<PortalHub processos={[P1, P2]} aEscolher="p-1" onEscolher={onEscolher} />);
    for (const botao of screen.getAllByRole("button")) {
      if (botao.getAttribute("data-testid")?.startsWith("portal-hub-processo")) expect(botao).toBeDisabled();
    }
    await userEvent.click(screen.getByRole("button", { name: /Domus/ }));
    expect(onEscolher).not.toHaveBeenCalled();
  });

  it("mostra o erro num alerta", () => {
    render(<PortalHub processos={[P1, P2]} erro="Este processo já não está disponível." onEscolher={() => {}} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Este processo já não está disponível.");
  });

  it("sem erro não há alerta", () => {
    render(<PortalHub processos={[P1, P2]} onEscolher={() => {}} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("«Sair» só existe se quem o monta souber sair", async () => {
    const onSair = vi.fn();
    const { rerender } = render(<PortalHub processos={[P1, P2]} onEscolher={() => {}} />);
    expect(screen.queryByRole("button", { name: /sair/i })).not.toBeInTheDocument();
    rerender(<PortalHub processos={[P1, P2]} onEscolher={() => {}} onSair={onSair} />);
    await userEvent.click(screen.getByRole("button", { name: /sair/i }));
    expect(onSair).toHaveBeenCalledTimes(1);
  });

  it.each([[undefined], [null], [{}], ["x"]])("uma lista que não é um array (%j) não rebenta", (lista) => {
    render(<PortalHub processos={lista} onEscolher={() => {}} />);
    expect(screen.getByTestId("portal-hub")).toBeInTheDocument();
    expect(screen.queryByTestId(/portal-hub-processo-/)).not.toBeInTheDocument();
  });
});
