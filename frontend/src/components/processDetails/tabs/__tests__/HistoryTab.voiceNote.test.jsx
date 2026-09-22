/**
 * Integração do separador Histórico com a nota de voz (Épico 7, Eixo 4).
 *
 * PORQUÊ ESTE TESTE EXISTE:
 *   A lição do Épico 6 — "um componente extraído só está coberto quando o
 *   ecrã que o usa também é montado". Os testes do `VoiceNoteRecorder`
 *   provam o componente isolado; este prova a LIGAÇÃO: o botão abre o
 *   diálogo certo, e o ficheiro gravado chega ao callback que o contentor
 *   fornece. Sem ele, um `onEnviar` mal ligado passava despercebido.
 *
 * O que é falso: só a timeline de fases e a tabela de auditoria (arrastam
 * queries e gráficos que nada têm a ver com o que aqui se testa). O
 * `VoiceNoteRecorder` e o `useAudioRecorder` são os reais.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../ProcessTimeline", () => ({
  default: () => <div data-testid="timeline-de-fases" />,
}));

vi.mock("../../../UnifiedAuditTrail", () => ({
  default: () => <div data-testid="tabela-de-auditoria" />,
}));

import HistoryTab from "../HistoryTab";

class MediaRecorderFalso {
  static isTypeSupported() {
    return true;
  }

  constructor(stream, opcoes) {
    this.mimeType = opcoes?.mimeType;
    this.ondataavailable = null;
    this.onstop = null;
  }

  start() {}

  stop() {
    this.ondataavailable?.({ data: new Blob(["audio"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

const props = (overrides = {}) => ({
  processId: "p-1",
  process: { status: "Em Análise" },
  history: [],
  workflowStatuses: [],
  activities: [],
  newComment: "",
  setNewComment: vi.fn(),
  sendingComment: false,
  handleSendComment: vi.fn(),
  handleDeleteComment: vi.fn(),
  user: { id: "u-1", name: "Carla", role: "consultor" },
  isProcessLocked: false,
  voiceNoteOpen: false,
  onVoiceNoteOpenChange: vi.fn(),
  onEnviarNotaDeVoz: vi.fn(),
  aEnviarNotaDeVoz: false,
  aProcessarNotaDeVoz: false,
  ...overrides,
});

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:nota");
  URL.revokeObjectURL = vi.fn();
  window.MediaRecorder = MediaRecorderFalso;
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn(() =>
        Promise.resolve({ getTracks: () => [{ stop: vi.fn() }] }),
      ),
    },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("HistoryTab — ligação à nota de voz", () => {
  it("o botão 'Nota de voz' vive ao lado de 'Registar Atividade'", () => {
    render(<HistoryTab {...props()} />);

    expect(screen.getByTestId("voice-note-open")).toBeInTheDocument();
    expect(screen.getByTestId("quick-note-open")).toBeInTheDocument();
  });

  it("clicar no botão pede a abertura ao contentor", async () => {
    // O separador NÃO detém o estado do diálogo: diz o que aconteceu e o
    // contentor decide (regra do § 20).
    const utilizador = userEvent.setup();
    const onVoiceNoteOpenChange = vi.fn();
    render(<HistoryTab {...props({ onVoiceNoteOpenChange })} />);

    await utilizador.click(screen.getByTestId("voice-note-open"));

    expect(onVoiceNoteOpenChange).toHaveBeenCalledWith(true);
  });

  it("com o diálogo aberto, o gravador real aparece", () => {
    render(<HistoryTab {...props({ voiceNoteOpen: true })} />);

    expect(screen.getByTestId("iniciar-gravacao")).toBeInTheDocument();
  });

  it("a gravação atravessa o separador até ao callback do contentor", async () => {
    const utilizador = userEvent.setup();
    const onEnviarNotaDeVoz = vi.fn();
    render(
      <HistoryTab {...props({ voiceNoteOpen: true, onEnviarNotaDeVoz })} />,
    );

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));
    await utilizador.click(await screen.findByRole("button", { name: /Terminar/ }));
    await utilizador.click(await screen.findByRole("button", { name: /Enviar nota/ }));

    await waitFor(() => expect(onEnviarNotaDeVoz).toHaveBeenCalledTimes(1));
    expect(onEnviarNotaDeVoz.mock.calls[0][0]).toBeInstanceOf(File);
  });

  it("o estado de processamento chega ao gravador", () => {
    render(<HistoryTab {...props({ voiceNoteOpen: true, aProcessarNotaDeVoz: true })} />);

    expect(
      screen.getByText("A processar Inteligência Artificial..."),
    ).toBeInTheDocument();
  });

  it("um processo bloqueado não oferece a gravação", () => {
    // Mesma regra do comentário manual: processo fechado não recebe notas.
    render(<HistoryTab {...props({ isProcessLocked: true })} />);

    expect(screen.queryByTestId("voice-note-open")).not.toBeInTheDocument();
  });

  it("sem callback do contentor, o botão não aparece", () => {
    // Defesa contra meia-ligação: um botão que não faz nada é pior do que
    // botão nenhum.
    render(<HistoryTab {...props({ onEnviarNotaDeVoz: undefined })} />);

    expect(screen.queryByTestId("voice-note-open")).not.toBeInTheDocument();
  });
});
