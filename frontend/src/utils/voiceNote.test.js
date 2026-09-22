/**
 * Testes da lógica pura das notas de voz (Épico 7, Eixo 4).
 *
 * Tudo o que aqui está corre sem browser: são as decisões que o hook e o
 * componente delegam para poderem ficar finos.
 */
import { describe, expect, it } from "vitest";

import {
  DURACAO_MAXIMA_SEGUNDOS,
  EXTENSOES_POR_MIME,
  MIMES_PREFERIDOS,
  TAMANHO_MAXIMO_BYTES,
  eNotaDeVozDoProcesso,
  escolherMimeDeGravacao,
  extensaoParaMime,
  formatarDuracao,
  formatarTamanho,
  mensagemDeConclusao,
  mimeBase,
  nomeParaGravacao,
  validarFicheiroDeAudio,
} from "./voiceNote";

const ficheiro = (overrides = {}) => ({
  name: "nota.webm",
  size: 1024,
  type: "audio/webm",
  ...overrides,
});

describe("mimeBase / extensaoParaMime", () => {
  it("retira os codecs que o MediaRecorder anexa", () => {
    expect(mimeBase("audio/webm;codecs=opus")).toBe("audio/webm");
  });

  it("normaliza maiúsculas e espaços", () => {
    expect(mimeBase("  AUDIO/WEBM ")).toBe("audio/webm");
  });

  it("dá a extensão do formato", () => {
    expect(extensaoParaMime("audio/webm;codecs=opus")).toBe(".webm");
    expect(extensaoParaMime("audio/mpeg")).toBe(".mp3");
  });

  it("devolve null para o que o backend não aceita", () => {
    expect(extensaoParaMime("video/mp4")).toBeNull();
    expect(extensaoParaMime("")).toBeNull();
  });
});

describe("escolherMimeDeGravacao", () => {
  it("escolhe o primeiro formato que o browser suporta", () => {
    const suporta = (mime) => mime === "audio/webm";

    expect(escolherMimeDeGravacao(suporta)).toBe("audio/webm");
  });

  it("prefere webm/opus quando tudo é suportado", () => {
    expect(escolherMimeDeGravacao(() => true)).toBe("audio/webm;codecs=opus");
  });

  it("devolve null quando nenhum serve", () => {
    // O chamador cai no upload de ficheiro em vez de gravar num formato
    // que o backend recusaria.
    expect(escolherMimeDeGravacao(() => false)).toBeNull();
  });

  it("não rebenta quando o browser não tem isTypeSupported", () => {
    expect(escolherMimeDeGravacao(undefined)).toBeNull();
  });

  it("todos os formatos preferidos têm extensão conhecida do backend", () => {
    // Guarda: acrescentar um mime à lista de preferência sem o mapear
    // produziria ficheiros que o endpoint recusa com 400.
    MIMES_PREFERIDOS.forEach((mime) => {
      expect(EXTENSOES_POR_MIME[mimeBase(mime)]).toBeTruthy();
    });
  });
});

describe("formatarDuracao", () => {
  it("mostra minutos e segundos", () => {
    expect(formatarDuracao(83)).toBe("01:23");
  });

  it("zero é 00:00", () => {
    expect(formatarDuracao(0)).toBe("00:00");
  });

  it("passa a horas quando é preciso", () => {
    expect(formatarDuracao(3725)).toBe("1:02:05");
  });

  it("valores inválidos não mostram NaN", () => {
    expect(formatarDuracao(undefined)).toBe("00:00");
    expect(formatarDuracao(-5)).toBe("00:00");
  });
});

describe("formatarTamanho", () => {
  it("bytes, KB e MB", () => {
    expect(formatarTamanho(512)).toBe("512 B");
    expect(formatarTamanho(2048)).toBe("2 KB");
    expect(formatarTamanho(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});

describe("validarFicheiroDeAudio", () => {
  it("aceita uma gravação normal", () => {
    expect(validarFicheiroDeAudio(ficheiro())).toEqual({ valido: true, erro: null });
  });

  it("recusa a ausência de ficheiro", () => {
    expect(validarFicheiroDeAudio(null).valido).toBe(false);
  });

  it("recusa um ficheiro vazio", () => {
    expect(validarFicheiroDeAudio(ficheiro({ size: 0 })).valido).toBe(false);
  });

  it("recusa acima do limite e diz o tamanho", () => {
    // Rejeitar aqui poupa ao consultor um upload de 30 MB para receber
    // um 413 no fim.
    const resultado = validarFicheiroDeAudio(
      ficheiro({ size: TAMANHO_MAXIMO_BYTES + 1 }),
    );

    expect(resultado.valido).toBe(false);
    expect(resultado.erro).toMatch(/25\.0 MB/);
  });

  it("recusa um formato que o backend não aceita", () => {
    expect(
      validarFicheiroDeAudio(ficheiro({ name: "contrato.pdf", type: "application/pdf" }))
        .valido,
    ).toBe(false);
  });

  it("aceita pela extensão quando o browser não preenche o type", () => {
    // Um ficheiro arrastado chega muitas vezes sem `type`; recusá-lo
    // bloquearia uploads perfeitamente válidos.
    expect(validarFicheiroDeAudio(ficheiro({ name: "reuniao.mp3", type: "" })).valido).toBe(
      true,
    );
  });
});

describe("nomeParaGravacao", () => {
  it("dá um nome com data e a extensão do formato", () => {
    const nome = nomeParaGravacao("audio/webm;codecs=opus", new Date(2026, 8, 22, 14, 5, 9));

    expect(nome).toBe("nota-de-voz-20260922-140509.webm");
  });

  it("formato desconhecido cai em .webm em vez de ficar sem extensão", () => {
    // Sem extensão, o motor de transcrição recusa o ficheiro.
    expect(nomeParaGravacao("audio/desconhecido")).toMatch(/\.webm$/);
  });
});

describe("mensagemDeConclusao", () => {
  it("conta as tarefas criadas", () => {
    expect(mensagemDeConclusao({ task_ids: ["a", "b", "c"] })).toMatch(/3 tarefas/);
  });

  it("uma tarefa vem no singular", () => {
    expect(mensagemDeConclusao({ task_ids: ["a"] })).toMatch(/1 tarefa criada/);
  });

  it("sem tarefas, diz que não encontrou nenhuma", () => {
    expect(mensagemDeConclusao({ task_ids: [] })).toMatch(/Não foram identificadas/);
  });

  it("o aviso de degradação tem precedência sobre a contagem", () => {
    // Quando a IA falha mas a transcrição ficou, o consultor tem de saber
    // que NÃO há tarefas — dizer "0 tarefas" esconderia a falha.
    const mensagem = mensagemDeConclusao({ task_ids: [], aviso: "LLM em baixo" });

    expect(mensagem).toMatch(/análise por IA falhou/);
  });

  it("resultado em falta não rebenta", () => {
    expect(mensagemDeConclusao(undefined)).toBeTruthy();
  });
});

describe("eNotaDeVozDoProcesso", () => {
  it("reconhece a nota deste processo", () => {
    expect(
      eNotaDeVozDoProcesso({ task_type: "VOICE_NOTE", process_id: "p1" }, "p1"),
    ).toBe(true);
  });

  it("ignora uma nota de voz de outro processo", () => {
    expect(
      eNotaDeVozDoProcesso({ task_type: "VOICE_NOTE", process_id: "p2" }, "p1"),
    ).toBe(false);
  });

  it("ignora outras tarefas de fundo do mesmo processo", () => {
    // Sem este filtro, cada importação ou análise em massa recarregaria a
    // página de detalhes do processo.
    expect(
      eNotaDeVozDoProcesso({ task_type: "BULK_IMPORT", process_id: "p1" }, "p1"),
    ).toBe(false);
  });

  it("payload ou processo em falta é sempre falso", () => {
    expect(eNotaDeVozDoProcesso(null, "p1")).toBe(false);
    expect(eNotaDeVozDoProcesso({ task_type: "VOICE_NOTE" }, "")).toBe(false);
  });
});

describe("limites alinhados com o backend", () => {
  it("o limite de tamanho é o mesmo do VOICE_NOTE_MAX_MB", () => {
    expect(TAMANHO_MAXIMO_BYTES).toBe(25 * 1024 * 1024);
  });

  it("a duração máxima é de cinco minutos", () => {
    expect(DURACAO_MAXIMA_SEGUNDOS).toBe(300);
  });
});
