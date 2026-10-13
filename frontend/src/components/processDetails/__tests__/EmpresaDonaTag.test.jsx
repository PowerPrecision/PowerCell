import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import EmpresaDonaTag from "../EmpresaDonaTag";

describe("EmpresaDonaTag", () => {
  it("mostra o nome da empresa dona", () => {
    render(<EmpresaDonaTag empresaDona={{ company_name: "Power Real Estate", e_de_outra_rede: false }} />);
    const tag = screen.getByTestId("empresa-dona-tag");
    expect(tag).toHaveTextContent("Power Real Estate");
    expect(tag).not.toHaveTextContent("Partilhado");
  });

  it("destaca o processo partilhado por outra rede", () => {
    render(<EmpresaDonaTag empresaDona={{ company_name: "Power Real Estate", e_de_outra_rede: true }} />);
    const tag = screen.getByTestId("empresa-dona-tag");
    expect(tag).toHaveTextContent("Power Real Estate");
    expect(tag).toHaveTextContent("Partilhado");
    expect(tag).toHaveAttribute("title", expect.stringContaining("partilhado"));
  });

  it("não desenha nada sem empresa dona (contraprova)", () => {
    const { container, rerender } = render(<EmpresaDonaTag empresaDona={null} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<EmpresaDonaTag empresaDona={{ company_name: "" }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
