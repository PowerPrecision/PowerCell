/** Recibos estrangeiros (Reino Unido, França, Países Baixos, Luxemburgo) na bancada do Index. */
import { describe, expect, it } from "vitest";

import { formatarDinheiro, NOME_DO_PAIS, trabalhosSemNifConfirmado } from "./indexRevisao";

const semNif = { value: null, needs_review: true };

describe("recibos estrangeiros", () => {
  it("o líquido em libras sai em libras", () => {
    expect(formatarDinheiro("2450", "GBP")).toContain("£");
    expect(formatarDinheiro("2450")).toContain("€");
    expect(formatarDinheiro("2450", null)).toContain("€");
    expect(formatarDinheiro("2450", "lixo")).toContain("€");
  });

  it("um emprego estrangeiro não pede NIF português", () => {
    const trabalhos = [
      { job_id: "a", country: "GB", employer_nif: semNif },
      { job_id: "b", country: "PT", employer_nif: semNif },
      { job_id: "c", employer_nif: semNif },
    ];
    expect(trabalhosSemNifConfirmado(trabalhos).map((t) => t.job_id)).toEqual(["b", "c"]);
  });

  it("Portugal não se assinala", () => {
    expect(NOME_DO_PAIS.PT).toBeUndefined();
    expect(NOME_DO_PAIS.NL).toBe("Países Baixos");
  });
});
