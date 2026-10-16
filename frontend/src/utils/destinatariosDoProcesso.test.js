import { describe, expect, it } from "vitest";
import {
  destinatariosDoProcesso,
  emailsDosClientes,
  idsDosIntermediarios,
  normalizarEmail,
} from "./destinatariosDoProcesso";

const PROCESSO = {
  client_email: "Joana@Exemplo.pt",
  titular2_data: { email: "tiago@exemplo.pt" },
  assigned_mediador_ids: ["m1", "m2"],
};
const EQUIPA = [
  { id: "m1", email: "ines@precision.pt" },
  { id: "m2", email: "rui@precision.pt" },
  { id: "c1", email: "outra@precision.pt" },
];

describe("destinatariosDoProcesso", () => {
  it("cliente, 2.º titular e intermediários atribuídos, por esta ordem", () => {
    expect(destinatariosDoProcesso(PROCESSO, EQUIPA).para).toEqual([
      "joana@exemplo.pt", "tiago@exemplo.pt", "ines@precision.pt", "rui@precision.pt",
    ]);
  });

  it("só os atribuídos: quem está na equipa mas não no processo fica de fora", () => {
    expect(destinatariosDoProcesso(PROCESSO, EQUIPA).para).not.toContain("outra@precision.pt");
  });

  it("sem equipa (a leitura falhou) ficam os clientes — nunca nada", () => {
    expect(destinatariosDoProcesso(PROCESSO, undefined).para).toEqual(["joana@exemplo.pt", "tiago@exemplo.pt"]);
    expect(destinatariosDoProcesso(PROCESSO, null).intermediarios).toEqual([]);
  });

  it("sem repetidos nem endereços inválidos", () => {
    const p = { client_email: "a@x.pt", titular2_data: { email: "A@X.pt" }, second_client_email: "isto não é email" };
    expect(emailsDosClientes(p)).toEqual(["a@x.pt"]);
  });

  it("um intermediário com o mesmo email do cliente não aparece duas vezes", () => {
    const r = destinatariosDoProcesso({ client_email: "a@x.pt", assigned_mediador_id: "m" }, [{ id: "m", email: "a@x.pt" }]);
    expect(r.para).toEqual(["a@x.pt"]);
  });

  it("formas de dados reais: nulos, objectos em vez de texto, listas em vez de objectos", () => {
    expect(destinatariosDoProcesso(null, null).para).toEqual([]);
    expect(destinatariosDoProcesso({ client_email: { x: 1 }, titular2_data: "x" }, [null, 1]).para).toEqual([]);
    expect(idsDosIntermediarios({ assigned_mediador_ids: "m1" })).toEqual([]);
  });

  it("o id do singular legado também conta, sem repetir o da lista", () => {
    expect(idsDosIntermediarios({ assigned_mediador_ids: ["m1"], assigned_mediador_id: "m1", mediador_id: "m3" })).toEqual(["m1", "m3"]);
  });

  it("normalizarEmail recusa o que não é endereço", () => {
    expect(normalizarEmail(" X@Y.PT ")).toBe("x@y.pt");
    expect(normalizarEmail("a@b")).toBe("");
    expect(normalizarEmail("a@b.pt, c@d.pt")).toBe("");
  });
});
