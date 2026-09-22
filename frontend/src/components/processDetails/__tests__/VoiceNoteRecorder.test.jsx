/**
 * Testes do gravador de notas de voz (Épico 7, Eixo 4).
 *
 * O jsdom não tem `MediaRecorder`, `getUserMedia` nem `createObjectURL`.
 * Em vez de falsear o hook (o que deixaria a integração por testar), o
 * teste substitui essas TRÊS APIs do browser — o hook e o componente
 * exercitados são os reais.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import VoiceNoteRecorder from "../VoiceNoteRecorder";

// ── Falsificação das APIs de media ───────────────────────────────────

/** Instâncias criadas, para o teste poder disparar `ondataavailable`. */
let gravadores = [];
let faixasParadas = 0;

class MediaRecorderFalso {
  static suportados = new Set(["audio/webm;codecs=opus", "audio/webm"]);

  static isTypeSupported(mime) {
    return MediaRecorderFalso.suportados.has(mime);
  }

  constructor(stream, opcoes) {
    this.stream = stream;
    this.mimeType = opcoes?.mimeType;
    this.state = "inactive";
    this.ondataavailable = null;
    this.onstop = null;
    gravadores.push(this);
  }

  start() {
    this.state = "recording";
  }

  stop() {
    this.state = "inactive";
    // O browser real entrega os dados antes do `onstop`.
    this.ondataavailable?.({ data: new Blob(["audio"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

function ligarMediaFalsa({ recusarPermissao = false, semFormatoSuportado = false } = {}) {
  MediaRecorderFalso.suportados = semFormatoSuportado
    ? new Set()
    : new Set(["audio/webm;codecs=opus", "audio/webm"]);

  window.MediaRecorder = MediaRecorderFalso;

  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn(() => {
        if (recusarPermissao) {
          const erro = new Error("recusado");
          erro.name = "NotAllowedError";
          return Promise.reject(erro);
        }
        return Promise.resolve({
          getTracks: () => [{ stop: () => { faixasParadas += 1; } }],
        });
      }),
    },
  });
}

const props = (overrides = {}) => ({
  open: true,
  onOpenChange: vi.fn(),
  onEnviar: vi.fn(),
  aEnviar: false,
  aProcessar: false,
  ...overrides,
});

beforeEach(() => {
  gravadores = [];
  faixasParadas = 0;
  URL.createObjectURL = vi.fn(() => "blob:nota");
  URL.revokeObjectURL = vi.fn();
  ligarMediaFalsa();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ====================================================================

describe("VoiceNoteRecorder — abertura", () => {
  it("fechado não rende nada", () => {
    render(<VoiceNoteRecorder {...props({ open: false })} />);

    expect(screen.queryByText("Nota de voz")).not.toBeInTheDocument();
  });

  it("aberto convida a gravar", () => {
    render(<VoiceNoteRecorder {...props()} />);

    expect(screen.getByTestId("iniciar-gravacao")).toBeInTheDocument();
  });

  it("sem gravação, o envio está bloqueado", () => {
    render(<VoiceNoteRecorder {...props()} />);

    expect(screen.getByRole("button", { name: /Enviar nota/ })).toBeDisabled();
  });
});

describe("VoiceNoteRecorder — gravar", () => {
  it("começar a gravar mostra o cronómetro", async () => {
    const utilizador = userEvent.setup();
    render(<VoiceNoteRecorder {...props()} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));

    expect(await screen.findByTestId("estado-a-gravar")).toBeInTheDocument();
    expect(screen.getByText("A gravar...")).toBeInTheDocument();
    expect(screen.getByText("00:00")).toBeInTheDocument();
  });

  it("grava no formato preferido que o browser suporta", async () => {
    const utilizador = userEvent.setup();
    render(<VoiceNoteRecorder {...props()} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));
    await screen.findByTestId("estado-a-gravar");

    expect(gravadores[0].mimeType).toBe("audio/webm;codecs=opus");
  });

  it("terminar produz a pré-escuta", async () => {
    const utilizador = userEvent.setup();
    render(<VoiceNoteRecorder {...props()} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));
    await utilizador.click(await screen.findByRole("button", { name: /Terminar/ }));

    expect(await screen.findByTestId("pre-escuta")).toBeInTheDocument();
    expect(screen.getByTestId("audio-pre-escuta")).toBeInTheDocument();
  });

  it("cancelar deita a gravação fora", async () => {
    const utilizador = userEvent.setup();
    render(<VoiceNoteRecorder {...props()} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));
    await utilizador.click(await screen.findByRole("button", { name: "Cancelar" }));

    await waitFor(() =>
      expect(screen.queryByTestId("pre-escuta")).not.toBeInTheDocument(),
    );
    expect(screen.getByTestId("iniciar-gravacao")).toBeInTheDocument();
  });

  it("o microfone é libertado ao terminar", async () => {
    // Sem isto o indicador de gravação do browser fica aceso e o
    // utilizador julga — com razão — que continua a ser ouvido.
    const utilizador = userEvent.setup();
    render(<VoiceNoteRecorder {...props()} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));
    await utilizador.click(await screen.findByRole("button", { name: /Terminar/ }));

    await waitFor(() => expect(faixasParadas).toBeGreaterThan(0));
  });

  it("o microfone é libertado também ao cancelar", async () => {
    const utilizador = userEvent.setup();
    render(<VoiceNoteRecorder {...props()} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));
    await utilizador.click(await screen.findByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(faixasParadas).toBeGreaterThan(0));
  });
});

describe("VoiceNoteRecorder — entrega ao contentor", () => {
  it("enviar entrega o ficheiro gravado", async () => {
    const utilizador = userEvent.setup();
    const onEnviar = vi.fn();
    render(<VoiceNoteRecorder {...props({ onEnviar })} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));
    await utilizador.click(await screen.findByRole("button", { name: /Terminar/ }));
    await utilizador.click(await screen.findByRole("button", { name: /Enviar nota/ }));

    expect(onEnviar).toHaveBeenCalledTimes(1);
    const ficheiro = onEnviar.mock.calls[0][0];
    // O nome tem de trazer extensão: sem ela o motor de transcrição recusa.
    expect(ficheiro.name).toMatch(/\.webm$/);
    expect(ficheiro.type).toBe("audio/webm;codecs=opus");
  });

  it("o componente não envia nada sozinho", () => {
    const onEnviar = vi.fn();
    render(<VoiceNoteRecorder {...props({ onEnviar })} />);

    expect(onEnviar).not.toHaveBeenCalled();
  });

  it("descartar limpa a gravação por confirmar", async () => {
    const utilizador = userEvent.setup();
    render(<VoiceNoteRecorder {...props()} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));
    await utilizador.click(await screen.findByRole("button", { name: /Terminar/ }));
    await utilizador.click(await screen.findByRole("button", { name: /Descartar/ }));

    await waitFor(() =>
      expect(screen.queryByTestId("pre-escuta")).not.toBeInTheDocument(),
    );
  });

  it("a enviar, os botões ficam bloqueados", async () => {
    const utilizador = userEvent.setup();
    const { rerender } = render(<VoiceNoteRecorder {...props()} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));
    await utilizador.click(await screen.findByRole("button", { name: /Terminar/ }));

    rerender(<VoiceNoteRecorder {...props({ aEnviar: true })} />);

    expect(screen.getByRole("button", { name: /A enviar/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Fechar" })).toBeDisabled();
  });
});

describe("VoiceNoteRecorder — carregar ficheiro", () => {
  it("um ficheiro válido vai para a pré-escuta", async () => {
    const utilizador = userEvent.setup();
    render(<VoiceNoteRecorder {...props()} />);

    const ficheiro = new File(["som"], "reuniao.mp3", { type: "audio/mpeg" });
    await utilizador.upload(
      screen.getByLabelText("Carregar ficheiro de áudio"),
      ficheiro,
    );

    expect(await screen.findByTestId("pre-escuta")).toBeInTheDocument();
    expect(screen.getByText("reuniao.mp3")).toBeInTheDocument();
  });

  it("um formato recusado explica porquê e não fica em pré-escuta", async () => {
    // `applyAccept: false` a propósito: o atributo `accept` é uma sugestão
    // ao seletor de ficheiros, não uma garantia — o utilizador pode escolher
    // "Todos os ficheiros" ou arrastar. É essa porta que a validação fecha,
    // e é ela que este teste tem de atravessar para provar alguma coisa.
    const utilizador = userEvent.setup({ applyAccept: false });
    render(<VoiceNoteRecorder {...props()} />);

    const ficheiro = new File(["x"], "contrato.pdf", { type: "application/pdf" });
    await utilizador.upload(
      screen.getByLabelText("Carregar ficheiro de áudio"),
      ficheiro,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(/Formato não suportado/);
    expect(screen.queryByTestId("pre-escuta")).not.toBeInTheDocument();
  });
});

describe("VoiceNoteRecorder — quando não se pode gravar", () => {
  it("sem MediaRecorder, oferece o upload em vez de um botão morto", () => {
    delete window.MediaRecorder;

    render(<VoiceNoteRecorder {...props()} />);

    expect(screen.queryByTestId("iniciar-gravacao")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Este browser não permite gravar/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Carregar ficheiro/ })).toBeInTheDocument();
  });

  it("permissão de microfone recusada dá uma instrução accionável", async () => {
    ligarMediaFalsa({ recusarPermissao: true });
    const utilizador = userEvent.setup();
    render(<VoiceNoteRecorder {...props()} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Autorize o microfone/);
  });

  it("browser sem formato compatível não grava num formato que o servidor recusa", async () => {
    ligarMediaFalsa({ semFormatoSuportado: true });
    const utilizador = userEvent.setup();
    render(<VoiceNoteRecorder {...props()} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/não grava num formato/);
    expect(gravadores).toHaveLength(0);
  });
});

describe("VoiceNoteRecorder — estado da IA", () => {
  it("anuncia o processamento em curso", () => {
    render(<VoiceNoteRecorder {...props({ aProcessar: true })} />);

    expect(
      screen.getByText("A processar Inteligência Artificial..."),
    ).toBeInTheDocument();
  });

  it("em repouso não anuncia nada", () => {
    render(<VoiceNoteRecorder {...props()} />);

    expect(
      screen.queryByText("A processar Inteligência Artificial..."),
    ).not.toBeInTheDocument();
  });
});
