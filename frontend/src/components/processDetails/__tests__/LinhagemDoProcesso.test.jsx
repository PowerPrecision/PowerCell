/**
 * A linhagem no cabeçalho do detalhe: Parceiro → Empresa Y → Empresa Z (Out 2026).
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LinhagemDoProcesso from "../LinhagemDoProcesso";

const PARCEIRO = { tipo: "parceiro", nome: "João Angariador", nivel: 0 };
const Y = { tipo: "empresa", papel: "dona", nome: "Empresa Y", nivel: 1 };
const Z = { tipo: "empresa", papel: "convidada", nome: "Empresa Z", nivel: 2, partilhado_por: "Empresa Y" };
const W = { tipo: "empresa", papel: "convidada", nome: "Empresa W", nivel: 3, partilhado_por: "Empresa Z" };

const montar = (linhagem) => render(<LinhagemDoProcesso linhagem={linhagem} />);

describe("LinhagemDoProcesso", () => {
  it("desenha Parceiro → Y → Z, pela ordem da cadeia", () => {
    montar({ origem: PARCEIRO, caminhos: [[PARCEIRO, Y, Z]], tem_cadeia: true });
    const caminho = screen.getByRole("list", { name: /Linhagem: João Angariador → Empresa Y → Empresa Z/ });
    const nomes = within(caminho).getAllByRole("listitem").map((li) => li.textContent);
    expect(nomes[0]).toContain("Parceiro João Angariador");
    expect(nomes[1]).toContain("Empresa Y");
    expect(nomes[2]).toContain("Empresa Z");
  });

  it("marca onde o processo está agora (o fim do caminho)", () => {
    montar({ origem: PARCEIRO, caminhos: [[PARCEIRO, Y, Z]], tem_cadeia: true });
    const agora = screen.getAllByTestId("linhagem-empresa").filter((el) => el.getAttribute("aria-current") === "true");
    expect(agora).toHaveLength(1);
    expect(agora[0]).toHaveTextContent("Empresa Z");
    expect(agora[0]).toHaveTextContent("aqui");
  });

  it("a cadeia é contínua: Y → Z → W", () => {
    montar({ origem: PARCEIRO, caminhos: [[PARCEIRO, Y, Z, W]], tem_cadeia: true });
    expect(screen.getAllByTestId("linhagem-empresa")).toHaveLength(3);
    expect(screen.getByRole("list", { name: /Empresa Z → Empresa W/ })).toBeInTheDocument();
  });

  it("uma ramificação são duas linhas", () => {
    montar({
      origem: PARCEIRO,
      caminhos: [[PARCEIRO, Y, Z], [PARCEIRO, Y, { ...Z, nome: "Empresa K" }]],
      tem_cadeia: true,
    });
    expect(screen.getAllByTestId("linhagem-caminho")).toHaveLength(2);
  });

  it("diz de quem veio cada empresa convidada (título)", () => {
    montar({ origem: PARCEIRO, caminhos: [[PARCEIRO, Y, Z]], tem_cadeia: true });
    const z = screen.getAllByTestId("linhagem-empresa").find((el) => el.textContent.includes("Empresa Z"));
    expect(z).toHaveAttribute("title", "Partilhado por Empresa Y");
    const y = screen.getAllByTestId("linhagem-empresa").find((el) => el.textContent.includes("Empresa Y"));
    expect(y).toHaveAttribute("title", "Empresa dona do processo");
  });

  it("sem parceiro, só a cadeia de empresas", () => {
    montar({ origem: null, caminhos: [[Y, Z]], tem_cadeia: true });
    expect(screen.queryByTestId("linhagem-parceiro")).not.toBeInTheDocument();
    expect(screen.getAllByTestId("linhagem-empresa")).toHaveLength(2);
  });

  it("um processo da casa, sem parceiro nem partilhas, não desenha nada", () => {
    const { container } = montar({ origem: null, caminhos: [[Y]], tem_cadeia: false });
    expect(container).toBeEmptyDOMElement();
  });

  it.each([undefined, null, {}, "x"])("linhagem %j não desenha nem rebenta", (linhagem) => {
    const { container } = montar(linhagem);
    expect(container).toBeEmptyDOMElement();
  });
});
