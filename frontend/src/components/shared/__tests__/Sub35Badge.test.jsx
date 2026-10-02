/**
 * A etiqueta Sub35 (Lote 4, ponto 1).
 *
 * A etiqueta anterior existia em três cópias e nunca apareceu: liam
 * `process.under_35`, que nenhum ficheiro do backend escreve. Daí o
 * primeiro teste ser sobre o CAMPO — é o campo, e não o desenho, que a
 * fazia estar sempre invisível.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import Sub35Badge, { ROTULO_SUB35, eSub35 } from "../Sub35Badge";

describe("eSub35", () => {
  it("aceita o campo novo", () => {
    expect(eSub35({ is_sub35: true })).toBe(true);
  });

  it("aceita o nome LEGADO, que é o que três ecrãs já liam", () => {
    expect(eSub35({ under_35: true })).toBe(true);
  });

  it("é estrito: nada de valores aproximados", () => {
    // `"false"`, `1` e `{}` são todos truthy em JS e nenhum deles é uma
    // afirmação do servidor.
    expect(eSub35({ is_sub35: "true" })).toBe(false);
    expect(eSub35({ is_sub35: 1 })).toBe(false);
    expect(eSub35({ is_sub35: false })).toBe(false);
    expect(eSub35({})).toBe(false);
    expect(eSub35(null)).toBe(false);
    expect(eSub35("processo")).toBe(false);
  });

  it("NÃO calcula a idade no cliente", () => {
    // A listagem não recebe (nem deve receber) a ficha pessoal inteira,
    // e duas contas da mesma regra divergem no dia de um aniversário.
    // Quem decide é o servidor.
    expect(eSub35({ personal_data: { birth_date: "2005-01-01" } })).toBe(false);
  });
});

describe("Sub35Badge", () => {
  it("não desenha nada quando o processo não é elegível", () => {
    const { container } = render(<Sub35Badge processo={{ id: "p1" }} />);
    expect(container.firstChild).toBeNull();
  });

  it("mostra «Sub35» quando é", () => {
    render(<Sub35Badge processo={{ is_sub35: true }} />);
    expect(screen.getByTestId("etiqueta-sub35").textContent).toContain(ROTULO_SUB35);
  });

  it("explica o critério ao passar o rato", () => {
    // "<35 anos" — o rótulo antigo — estava à letra ERRADO: o critério
    // é até aos 35, inclusive. E desde o Lote 5 é sobre TODOS os
    // titulares: a etiqueta não pode prometer menos do que a regra exige.
    render(<Sub35Badge processo={{ is_sub35: true }} />);
    const titulo = screen.getByTestId("etiqueta-sub35").getAttribute("title");
    expect(titulo).toContain("Todos os titulares");
    expect(titulo).toContain("35 anos ou menos");
  });

  it("aceita `activo` já resolvido (para quem não tem o processo à mão)", () => {
    render(<Sub35Badge activo />);
    expect(screen.getByTestId("etiqueta-sub35")).toBeTruthy();
  });

  it("`activo={false}` vence um processo etiquetado", () => {
    // Prop explícita é uma decisão do chamador; cair para o processo
    // nesse caso faria `activo` ser ignorado quando é `false` — o
    // mesmo defeito do `.get(k, default)` com valor vazio.
    const { container } = render(<Sub35Badge activo={false} processo={{ is_sub35: true }} />);
    expect(container.firstChild).toBeNull();
  });

  it("tem dois tamanhos e nenhum deles usa cores cruas", () => {
    const { container: pequeno } = render(
      <Sub35Badge processo={{ is_sub35: true }} tamanho="sm" />,
    );
    const { container: normal } = render(<Sub35Badge processo={{ is_sub35: true }} />);
    const classes = `${pequeno.firstChild.className} ${normal.firstChild.className}`;
    // As três cópias antigas tinham `bg-green-50 text-green-700`, que no
    // modo escuro é verde-claro sobre verde-claro.
    expect(classes).not.toMatch(/bg-green|text-green|border-green/);
    expect(pequeno.firstChild.className).not.toBe(normal.firstChild.className);
  });
});
