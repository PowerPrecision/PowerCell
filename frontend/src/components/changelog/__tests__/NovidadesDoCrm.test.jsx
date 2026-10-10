import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import NovidadesDoCrm from "../NovidadesDoCrm";
import PremiumBadge from "../PremiumBadge";

const md = (texto) => `<p>${texto}</p>`;

const NORMAL = { id: "1", version: "2026-09-01", published_at: "2026-09-01", content_markdown: "nota normal", is_premium: false };
const PREMIUM = { id: "2", version: "2026-10-01", published_at: "2026-10-01", content_markdown: "módulo novo", is_premium: true };

function montar(entradas) {
  return render(<NovidadesDoCrm entradas={entradas} markdownParaHtml={md} />);
}

describe("PremiumBadge", () => {
  it("diz «Módulo Premium»", () => {
    render(<PremiumBadge />);
    expect(screen.getByTestId("badge-premium")).toHaveTextContent("Módulo Premium");
  });
});

describe("NovidadesDoCrm", () => {
  it("uma novidade Premium é destacada com a marca e o convite a pedir o módulo", () => {
    montar([PREMIUM]);
    const cartao = screen.getByTestId("novidade");
    expect(cartao).toHaveAttribute("data-premium", "true");
    expect(within(cartao).getByTestId("badge-premium")).toBeInTheDocument();
    expect(within(cartao).getByTestId("convite-premium")).toHaveTextContent(/peça ao seu administrador/i);
  });

  it("uma novidade normal não tem marca nem convite (contraprova)", () => {
    montar([NORMAL]);
    const cartao = screen.getByTestId("novidade");
    expect(cartao).toHaveAttribute("data-premium", "false");
    expect(screen.queryByTestId("badge-premium")).toBeNull();
    expect(screen.queryByTestId("convite-premium")).toBeNull();
  });

  it("uma Premium atrás de uma mais recente que não o é continua visível", () => {
    montar([NORMAL, PREMIUM]);
    const cartoes = screen.getAllByTestId("novidade");
    expect(cartoes).toHaveLength(2);
    expect(cartoes[0]).toHaveAttribute("data-premium", "false");
    expect(cartoes[1]).toHaveAttribute("data-premium", "true");
    expect(screen.getAllByTestId("badge-premium")).toHaveLength(1);
  });

  it("só o booleano true conta (uma string 'true' ou o 1 não destacam)", () => {
    montar([{ ...NORMAL, id: "a", is_premium: "true" }, { ...NORMAL, id: "b", is_premium: 1 }, { ...NORMAL, id: "c" }]);
    expect(screen.queryByTestId("badge-premium")).toBeNull();
  });

  it("o primeiro cartão é «Novidades do CRM» e os outros «Novidade anterior»", () => {
    montar([NORMAL, PREMIUM]);
    expect(screen.getByText("Novidades do CRM")).toBeInTheDocument();
    expect(screen.getByText("Novidade anterior")).toBeInTheDocument();
  });

  it("o conteúdo passa pelo sanitizador (um <script> não chega ao DOM)", () => {
    const { container } = render(
      <NovidadesDoCrm
        entradas={[{ ...NORMAL, content_markdown: "x" }]}
        markdownParaHtml={() => '<p>ok</p><script>window.__xss = 1</script><img src=x onerror="window.__xss=1">'}
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.innerHTML).not.toMatch(/onerror/);
    expect(window.__xss).toBeUndefined();
  });

  it.each([undefined, null, {}, "x", []])("entradas inválidas (%s) não rebentam e não desenham nada", (invalido) => {
    const { container } = montar(invalido);
    expect(container).toBeEmptyDOMElement();
  });

  it("entradas sem conteúdo são ignoradas", () => {
    montar([{ id: "9", version: "v", content_markdown: "" }, NORMAL]);
    expect(screen.getAllByTestId("novidade")).toHaveLength(1);
  });
});
