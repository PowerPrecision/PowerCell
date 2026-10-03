/**
 * A regra do cabeçalho fixo (Lote 4, ponto 4).
 *
 * O defeito que estes testes impedem de voltar: `sticky` sem `top`. É
 * invisível a olho — a classe que falta não dá erro, não dá aviso do
 * Tailwind e o ecrã parece normal; só não cola. E era indistinguível de
 * um `sticky` correcto em qualquer teste de render, porque o jsdom não
 * calcula posicionamento.
 */
import { describe, expect, it } from "vitest";

import {
  CAMADA_DA_GAVETA,
  CAMADA_DO_CABECALHO,
  CAMADA_DO_FUNDO_DA_GAVETA,
  TOPO_COM_IMPERSONACAO,
  TOPO_SEM_IMPERSONACAO,
  classesDoCabecalhoFixo,
} from "./stickyHeader";

describe("classesDoCabecalhoFixo", () => {
  it("é sticky nos dois casos", () => {
    expect(classesDoCabecalhoFixo({ isImpersonating: false })).toContain("sticky");
    expect(classesDoCabecalhoFixo({ isImpersonating: true })).toContain("sticky");
  });

  it("declara SEMPRE um top — é esta a linha que faltava", () => {
    // Não basta "tem top-0" no caso normal: o que o defeito fazia era
    // ter `top` só num dos ramos. A asserção é sobre AMBOS.
    for (const isImpersonating of [false, true]) {
      const classes = classesDoCabecalhoFixo({ isImpersonating });
      expect(classes.split(/\s+/).some((c) => /^top-/.test(c))).toBe(true);
    }
  });

  it("sem argumentos comporta-se como «não está a impersonar»", () => {
    // O chamador pode não passar nada; o ramo por omissão não pode ser o
    // que não tem topo.
    expect(classesDoCabecalhoFixo()).toContain(TOPO_SEM_IMPERSONACAO);
    expect(classesDoCabecalhoFixo()).not.toContain(TOPO_COM_IMPERSONACAO);
  });

  it("desce 48px quando há faixa de impersonação", () => {
    expect(classesDoCabecalhoFixo({ isImpersonating: true })).toContain(
      TOPO_COM_IMPERSONACAO,
    );
    // Contraprova: os dois topos são diferentes. Um `top-0` nos dois
    // ramos "passaria" o teste do topo acima e esconderia o cabeçalho
    // atrás da faixa.
    expect(TOPO_COM_IMPERSONACAO).not.toBe(TOPO_SEM_IMPERSONACAO);
  });

  it("fica numa camada ABAIXO da gaveta lateral e do seu fundo", () => {
    // Em ecrã estreito a gaveta ocupa a mesma faixa do cabeçalho. Com
    // camadas iguais ganha quem vem depois no DOM — o cabeçalho — e o
    // logótipo e o botão de fechar da gaveta ficavam tapados.
    expect(CAMADA_DO_CABECALHO).toBeLessThan(CAMADA_DO_FUNDO_DA_GAVETA);
    expect(CAMADA_DO_FUNDO_DA_GAVETA).toBeLessThan(CAMADA_DA_GAVETA);
  });

  it("as classes de camada e de topo são LITERAIS (o Tailwind lê o código)", () => {
    // Guarda contra a tentação de voltar a compor `z-${CAMADA}`: uma
    // classe que não existe como texto no ficheiro não é gerada, e o
    // resultado é o cabeçalho sem camada nenhuma.
    const fonte = classesDoCabecalhoFixo({ isImpersonating: false });
    expect(fonte).toContain("z-40");
    expect(fonte).not.toContain("${");
  });

  it("mantém a altura fixa nos dois ramos", () => {
    expect(classesDoCabecalhoFixo({ isImpersonating: false })).toContain("h-14");
    expect(classesDoCabecalhoFixo({ isImpersonating: true })).toContain("h-14");
  });
});
