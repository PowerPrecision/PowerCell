import { describe, expect, it } from "vitest";
import {
  avisoDoDestino,
  devePerguntarAPasta,
  erroDoArquivo,
  mensagemDoArquivo,
  podeArquivarAnexos,
  processoEscolhido,
  processoPreSeleccionado,
  processosOndeFoiArquivado,
  rotuloDoProcesso,
  sugestoesDe,
} from "./emailArchive";

const S1 = { process_id: "p-1", process_number: 42, client_name: "Joana", ja_indexado: false };
const S2 = { process_id: "p-2", process_number: 43, client_name: "Joana M.", ja_indexado: true };

describe("podeArquivarAnexos", () => {
  it.each(["admin", "ceo", "diretor", "administrativo", "consultor", "intermediario", "indexacao", "CONSULTOR"])(
    "%s arquiva",
    (papel) => expect(podeArquivarAnexos(papel)).toBe(true),
  );
  it.each(["parceiro", "cliente", "", null, undefined])(
    "%s não arquiva",
    (papel) => expect(podeArquivarAnexos(papel)).toBe(false),
  );
});

describe("sugestoesDe / processoPreSeleccionado", () => {
  it("um objecto, um texto ou nada nunca rebentam e dão lista vazia", () => {
    for (const r of [undefined, null, {}, { sugestoes: {} }, { sugestoes: "x" }]) {
      expect(sugestoesDe(r)).toEqual([]);
    }
  });

  it("descarta linhas sem process_id", () => {
    expect(sugestoesDe({ sugestoes: [S1, null, {}, { client_name: "x" }] })).toEqual([S1]);
  });

  it("pré-selecciona SÓ o que o servidor sugeriu", () => {
    expect(processoPreSeleccionado({ sugestoes: [S1], sugerido: "p-1" })).toBe("p-1");
  });

  it("com ambiguidade (sugerido null) não escolhe o primeiro", () => {
    expect(processoPreSeleccionado({ sugestoes: [S1, S2], sugerido: null, ambiguo: true })).toBeNull();
  });

  it("um sugerido que não está na lista é ignorado", () => {
    expect(processoPreSeleccionado({ sugestoes: [S1], sugerido: "p-fantasma" })).toBeNull();
  });
});

describe("o destino do ficheiro", () => {
  it("processo por indexar: avisa da Index e não pergunta a pasta", () => {
    expect(devePerguntarAPasta(S1)).toBe(false);
    expect(avisoDoDestino(S1)).toMatch(/pasta Index/);
  });

  it("processo indexado: pergunta a pasta e avisa que não há IA", () => {
    expect(devePerguntarAPasta(S2)).toBe(true);
    expect(avisoDoDestino(S2)).toMatch(/sem passar pela IA/);
  });

  it("sem processo escolhido não há aviso", () => {
    expect(avisoDoDestino(null)).toBeNull();
    expect(devePerguntarAPasta(null)).toBe(false);
  });

  it("um servidor antigo (sem ja_indexado) trata-se como por indexar", () => {
    expect(devePerguntarAPasta({ process_id: "p" })).toBe(false);
  });

  it("encontra o processo escolhido na lista", () => {
    expect(processoEscolhido({ sugestoes: [S1, S2] }, "p-2")).toBe(S2);
    expect(processoEscolhido({ sugestoes: [S1] }, "p-2")).toBeNull();
  });
});

describe("textos", () => {
  it("rótulo com número", () => {
    expect(rotuloDoProcesso(S1)).toBe("#42 · Joana");
    expect(rotuloDoProcesso({ process_id: "x" })).toBe("Processo");
  });

  it("mensagem depois de arquivar", () => {
    expect(mensagemDoArquivo({ already_archived: true })).toMatch(/já estava arquivado/);
    expect(mensagemDoArquivo({ intake: { fila_ia: true } })).toMatch(/pasta Index/);
    expect(mensagemDoArquivo({ intake: { fila_ia: false } })).toBe("Anexo arquivado no processo.");
    expect(mensagemDoArquivo(undefined)).toBe("Anexo arquivado no processo.");
  });

  it("o erro do servidor vence o texto por omissão", () => {
    expect(erroDoArquivo({ response: { data: { detail: "Sem permissão X" } } })).toBe("Sem permissão X");
    expect(erroDoArquivo({ response: { status: 413 } })).toMatch(/demasiado grande/);
    expect(erroDoArquivo({ response: { status: 403, data: { detail: { x: 1 } } } })).toMatch(/permissão/);
    expect(erroDoArquivo(new Error("rede"))).toBe("Não foi possível arquivar o anexo.");
  });

  it("onde o anexo foi arquivado, sempre como lista", () => {
    expect(processosOndeFoiArquivado({ archived_to: [{ process_id: "p-1" }, null] })).toEqual([{ process_id: "p-1" }]);
    expect(processosOndeFoiArquivado({ archived_to: "x" })).toEqual([]);
    expect(processosOndeFoiArquivado(null)).toEqual([]);
  });
});
