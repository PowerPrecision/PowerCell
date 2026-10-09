/**
 * A etiqueta de PARTILHA (D-25).
 *
 * PORQUE É QUE ESTA ETIQUETA TEM TESTE PRÓPRIO
 * A partilha é Via Rápida: abre-se uma fronteira de rede sem aprovação
 * manual, e esta etiqueta é a ÚNICA coisa que a torna visível a quem
 * trabalha o processo. Uma etiqueta que não aparece — ou que aparece com
 * o nome errado — não é um defeito cosmético: é a abertura a ficar
 * silenciosa, que é o oposto de tolerância zero.
 *
 * A `Sub35Badge` ensinou a forma de defeito: a etiqueta existia em três
 * cópias e **nunca apareceu**, porque o campo que liam não era escrito
 * por ninguém no servidor. Daqui para a frente, o campo que o servidor
 * calcula e o campo que o componente lê afirmam-se no mesmo teste.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import PartilhaBadge, {
  empresasDaPartilha,
  estaPartilhado,
  ROTULO_PARTILHA,
} from "../PartilhaBadge";

describe("PartilhaBadge", () => {
  it("nomeia a EMPRESA e não só «partilhado»", () => {
    // Saber que «está partilhado» sem saber com quem não responde à
    // pergunta que uma pessoa faz ao ver a linha.
    render(<PartilhaBadge processo={{ partilha_com: ["Precision"] }} />);

    const etiqueta = screen.getByTestId("etiqueta-partilha");
    expect(etiqueta).toHaveTextContent(`${ROTULO_PARTILHA}: Precision`);
  });

  it("lista as duas empresas quando o processo está partilhado com duas", () => {
    render(
      <PartilhaBadge processo={{ partilha_com: ["Precision", "Domus"] }} />,
    );

    expect(screen.getByTestId("etiqueta-partilha")).toHaveTextContent(
      "Precision, Domus",
    );
  });

  it("não se renderiza quando o processo NÃO está partilhado", () => {
    // A presença do elemento É a afirmação: um elemento vazio resolve
    // num `findBy*` e a asserção seguinte corre contra o vazio (§ 27.17).
    render(<PartilhaBadge processo={{ id: "p1" }} />);

    expect(screen.queryByTestId("etiqueta-partilha")).not.toBeInTheDocument();
  });

  it("nem com uma lista vazia, nem com um processo em falta", () => {
    const { rerender } = render(
      <PartilhaBadge processo={{ partilha_com: [] }} />,
    );
    expect(screen.queryByTestId("etiqueta-partilha")).not.toBeInTheDocument();

    rerender(<PartilhaBadge processo={undefined} />);
    expect(screen.queryByTestId("etiqueta-partilha")).not.toBeInTheDocument();
  });

  it("aceita as empresas já resolvidas, sem processo", () => {
    render(<PartilhaBadge empresas={["Domus"]} />);

    expect(screen.getByTestId("etiqueta-partilha")).toHaveTextContent("Domus");
  });

  it("explica no `title` o que a partilha NÃO abre", () => {
    // Quem passa o rato tem de saber que a fronteira continua fechada
    // nos restantes processos — é a diferença entre isto e dar acesso à
    // outra rede inteira.
    render(<PartilhaBadge processo={{ partilha_com: ["Domus"] }} />);

    expect(screen.getByTestId("etiqueta-partilha")).toHaveAttribute(
      "title",
      expect.stringContaining("fronteira continua fechada"),
    );
  });
});

describe("empresasDaPartilha", () => {
  it("prefere o campo CALCULADO pelo servidor", () => {
    expect(
      empresasDaPartilha({
        partilha_com: ["Domus"],
        partner_companies: [{ company_name: "Outra" }],
      }),
    ).toEqual(["Domus"]);
  });

  it("recorre ao registo cru quando o calculado não vem", () => {
    // O detalhe do processo não passa pela serialização das listagens.
    expect(
      empresasDaPartilha({
        partner_companies: [
          { company_name: "Domus", network_id: "grupo_domus" },
        ],
      }),
    ).toEqual(["Domus"]);
  });

  it("cai para o ID quando não há nome, em vez de desaparecer", () => {
    // Mostrar um uuid é pior do que o nome; ESCONDER a partilha é muito
    // pior, porque é a etiqueta que a torna visível.
    expect(
      empresasDaPartilha({ partner_companies: [{ company_id: "cmp-x" }] }),
    ).toEqual(["cmp-x"]);
  });

  it("não repete a mesma empresa", () => {
    expect(
      empresasDaPartilha({
        partner_companies: [
          { company_name: "Domus" },
          { company_name: "Domus" },
        ],
      }),
    ).toEqual(["Domus"]);
  });

  it("NUNCA mostra a lista de REDES", () => {
    // `partner_network_ids` é a fronteira de segurança e não tem nome
    // legível: `rede:8a0b6657…` não responde a pergunta nenhuma.
    expect(
      empresasDaPartilha({ partner_network_ids: ["rede:8a0b6657"] }),
    ).toEqual([]);
  });

  it("um valor do TIPO errado degrada para lista vazia", () => {
    // `Array.isArray` e nunca `|| []`: um objecto é truthy, logo
    // `valor || []` devolvia o objecto e o `.map` rebentava noutro sítio
    // em vez de aqui (§ 27.38).
    expect(empresasDaPartilha({ partilha_com: "Domus" })).toEqual([]);
    expect(empresasDaPartilha({ partner_companies: { a: 1 } })).toEqual([]);
    expect(empresasDaPartilha("Domus")).toEqual([]);
  });
});

describe("estaPartilhado", () => {
  it("lê a flag que o servidor calcula", () => {
    expect(estaPartilhado({ is_partilhado: true })).toBe(true);
    expect(estaPartilhado({ is_partilhado: false })).toBe(false);
  });

  it("e deriva dos nomes quando a flag não vem", () => {
    expect(estaPartilhado({ partilha_com: ["Domus"] })).toBe(true);
    expect(estaPartilhado({})).toBe(false);
  });
});
