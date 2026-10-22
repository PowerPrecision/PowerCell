import { describe, expect, it } from "vitest";

import { abreABancada, destinoDoProcesso } from "./destinoDoProcesso";

describe("destinoDoProcesso — o clique em «Os Meus Processos» conforme o perfil ACTIVO", () => {
  it("o Index vai direto para a bancada", () => {
    expect(destinoDoProcesso("indexacao", "abc-123")).toBe("/index/abc-123");
    expect(abreABancada("indexacao")).toBe(true);
  });

  it.each(["consultor", "intermediario", "diretor", "admin", "ceo", "master", "administrativo", "parceiro", "", undefined, null])(
    "%s continua no detalhe do processo",
    (papel) => {
      expect(destinoDoProcesso(papel, "abc-123")).toBe("/process/abc-123");
      expect(abreABancada(papel)).toBe(false);
    },
  );

  it("não distingue maiúsculas (o perfil vem de vários sítios)", () => {
    expect(destinoDoProcesso("Indexacao", "x")).toBe("/index/x");
  });

  it("o id é codificado: um id estranho não parte o caminho", () => {
    expect(destinoDoProcesso("indexacao", "a/b?c")).toBe("/index/a%2Fb%3Fc");
  });

  it("sem id não rebenta", () => {
    expect(destinoDoProcesso("indexacao", undefined)).toBe("/index/");
  });
});
