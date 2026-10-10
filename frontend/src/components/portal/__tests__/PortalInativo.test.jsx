import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PortalInativo from "../PortalInativo";

describe("PortalInativo", () => {
  it("anuncia o bloqueio como alerta e mostra a mensagem recebida", () => {
    render(<PortalInativo mensagem="Mensagem de teste distinta." />);
    const alerta = screen.getByRole("alert");
    expect(alerta).toHaveTextContent("Acesso suspenso");
    expect(alerta).toHaveTextContent("Mensagem de teste distinta.");
  });

  it("não oferece uma acção que não resolve nada (sem botão de tentar de novo)", () => {
    render(<PortalInativo mensagem="x" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
