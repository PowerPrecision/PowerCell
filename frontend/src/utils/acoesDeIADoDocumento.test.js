import { describe, it, expect } from "vitest";
import { ACAO_CLASSIFICAR, ACAO_EXTRAIR } from "./acoesDeIADoDocumento";

describe("as duas acções de IA por documento distinguem-se", () => {
  it("têm texto, nome acessível e estilo diferentes", () => {
    expect(ACAO_CLASSIFICAR.titulo).not.toBe(ACAO_EXTRAIR.titulo);
    expect(ACAO_CLASSIFICAR.aria("cc.pdf")).not.toBe(ACAO_EXTRAIR.aria("cc.pdf"));
    expect(ACAO_CLASSIFICAR.classe).not.toBe(ACAO_EXTRAIR.classe);
  });

  it("dizem o que fazem: uma mexe nos metadados do ficheiro, a outra na ficha", () => {
    expect(ACAO_CLASSIFICAR.titulo).toMatch(/categoria/i);
    expect(ACAO_EXTRAIR.titulo).toMatch(/ficha/i);
  });

  it("o nome acessível leva o nome do ficheiro", () => {
    expect(ACAO_CLASSIFICAR.aria("cc.pdf")).toContain("cc.pdf");
    expect(ACAO_EXTRAIR.aria("cc.pdf")).toContain("cc.pdf");
  });

  it("só usam tokens semânticos (nada de cores cruas do Tailwind)", () => {
    expect(`${ACAO_CLASSIFICAR.classe} ${ACAO_EXTRAIR.classe}`).not.toMatch(/(gray|red|blue|green|purple|amber)-\d/);
  });
});
