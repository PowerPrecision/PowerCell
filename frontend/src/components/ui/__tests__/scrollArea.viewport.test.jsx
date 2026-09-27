/**
 * O limite de altura do ScrollArea vai no VIEWPORT (Lote 6, ponto 4).
 *
 * O DEFEITO (produção, Set 2026): o cartão "As minhas tarefas" do
 * Dashboard passava `maxHeight` ao `ScrollArea`, que o punha na `Root`. A
 * Root tem `overflow-hidden` e o `Viewport` tem `h-full`: com a Root em
 * altura AUTO, o `h-full` resolve para a altura do CONTEÚDO, o viewport
 * nunca transborda, o Radix não desenha barra nenhuma — e a Root corta o
 * excedente. Não era uma lista sem elevador: era uma lista TRUNCADA, com
 * tarefas inalcançáveis.
 *
 * O jsdom não faz layout, pelo que não se pode medir o scroll. O que se
 * afirma é o CONTRATO: o limite chega ao viewport e não à root. É o que
 * distingue a correcção de a ter escrito outra vez no sítio errado.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ScrollArea } from "../scroll-area";

describe("ScrollArea — viewportStyle", () => {
  it("aplica o limite ao viewport", () => {
    render(
      <ScrollArea viewportStyle={{ maxHeight: "280px" }}>
        <div>conteúdo</div>
      </ScrollArea>,
    );
    expect(screen.getByTestId("scroll-area-viewport")).toHaveStyle({ maxHeight: "280px" });
  });

  it("não põe o limite na root (era aí que ele não funcionava)", () => {
    const { container } = render(
      <ScrollArea viewportStyle={{ maxHeight: "280px" }}>
        <div>conteúdo</div>
      </ScrollArea>,
    );
    const root = container.firstChild;
    expect(root.style.maxHeight).toBe("");
    // Contraprova de que se está a olhar para a root certa: é ela que
    // esconde o excedente, e é por isso que um limite aqui truncava.
    expect(root.className).toContain("overflow-hidden");
  });

  it("sem viewportStyle o viewport continua sem limite", () => {
    render(
      <ScrollArea>
        <div>conteúdo</div>
      </ScrollArea>,
    );
    expect(screen.getByTestId("scroll-area-viewport").style.maxHeight).toBe("");
  });
});
