import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NotaDoPedido from "../NotaDoPedido";

describe("NotaDoPedido", () => {
  it("mostra a nota inteira, sem a cortar", () => {
    const longa = "Tem de estar legalizada e ter menos de 3 meses. ".repeat(6).trim();
    render(<NotaDoPedido nota={longa} />);
    const nota = screen.getByTestId("nota-do-pedido");
    expect(nota).toHaveTextContent(longa);
    expect(nota.className).not.toMatch(/truncate/);
  });

  it("preserva as quebras de linha que a equipa escreveu", () => {
    render(<NotaDoPedido nota={"Linha 1\nLinha 2"} />);
    expect(screen.getByTestId("nota-do-pedido").className).toMatch(/whitespace-pre-line/);
  });

  it.each([undefined, null, "", "   ", 42, {}, { label: "x" }, []])(
    "sem texto (%j) não desenha nada",
    (nota) => {
      const { container } = render(<NotaDoPedido nota={nota} />);
      expect(container).toBeEmptyDOMElement();
    },
  );

  it("apara o texto", () => {
    render(<NotaDoPedido nota="  olá  " />);
    expect(screen.getByTestId("nota-do-pedido").textContent).toBe("olá");
  });
});
