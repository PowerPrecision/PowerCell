/**
 * Ligação do cartão de Observações à nota de voz (Ponto 9).
 *
 * PORQUÊ ESTE TESTE VIVE AQUI E NÃO NO HISTÓRICO
 *   Era um teste do `HistoryTab` — o botão vivia lá, ao lado do
 *   "Registar Atividade". O Ponto 9 tornou o Histórico numa trilha de
 *   auditoria só de leitura, e a nota de voz **mudou-se** para o sítio
 *   onde as notas passaram a escrever-se: o cartão de Observações do
 *   Resumo. O teste mudou-se com ela, em vez de ser apagado — o que se
 *   prova é o mesmo: que o ficheiro gravado chega ao callback do
 *   contentor.
 *
 *   Mantém-se a lição do Épico 6: os testes do `VoiceNoteRecorder`
 *   provam o componente isolado; este prova a LIGAÇÃO. Sem ele, um
 *   `onEnviar` mal ligado passava despercebido.
 *
 * O `VoiceNoteRecorder` e o `useAudioRecorder` são os REAIS. O gravador
 * é renderizado aqui ao lado do cartão porque na aplicação vive ao nível
 * da PÁGINA, junto dos outros diálogos: um diálogo não é conteúdo de
 * separador, e estava dentro do `HistoryTab` só por ser lá que o botão
 * tinha nascido. O cartão limita-se a pedir a abertura.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ProcessObservationsCard from "../ProcessObservationsCard";
import VoiceNoteRecorder from "../VoiceNoteRecorder";

/**
 * Reproduz o que a página faz: o gatilho no cartão, o gravador ao lado.
 */
function Ecra({
  onAbrirNotaDeVoz,
  voiceNoteOpen = false,
  onVoiceNoteOpenChange = () => {},
  onEnviarNotaDeVoz,
  aEnviarNotaDeVoz = false,
  aProcessarNotaDeVoz = false,
  disabled = false,
}) {
  return (
    <>
      <ProcessObservationsCard
        process={{ observation_notes: [] }}
        onAdd={vi.fn()}
        disabled={disabled}
        onAbrirNotaDeVoz={onAbrirNotaDeVoz}
      />
      {onEnviarNotaDeVoz && (
        <VoiceNoteRecorder
          open={voiceNoteOpen}
          onOpenChange={onVoiceNoteOpenChange}
          onEnviar={onEnviarNotaDeVoz}
          aEnviar={aEnviarNotaDeVoz}
          aProcessar={aProcessarNotaDeVoz}
        />
      )}
    </>
  );
}

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
  onAbrirNotaDeVoz: vi.fn(),
  voiceNoteOpen: false,
  onVoiceNoteOpenChange: vi.fn(),
  onEnviarNotaDeVoz: vi.fn(),
  aEnviarNotaDeVoz: false,
  aProcessarNotaDeVoz: false,
  disabled: false,
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

describe("Observações — ligação à nota de voz (Ponto 9)", () => {
  it("o botão 'Nota de voz' vive no cartão de Observações", () => {
    render(<Ecra {...props()} />);

    expect(screen.getByTestId("voice-note-open")).toBeInTheDocument();
    // E o "Registar Atividade" já não existe em lado nenhum: saiu com o
    // Histórico só de leitura.
    expect(screen.queryByTestId("quick-note-open")).not.toBeInTheDocument();
  });

  it("clicar no botão pede a abertura ao contentor", async () => {
    // O cartão NÃO detém o estado do diálogo: diz o que aconteceu e o
    // contentor decide (regra do § 20).
    const utilizador = userEvent.setup();
    const onAbrirNotaDeVoz = vi.fn();
    render(<Ecra {...props({ onAbrirNotaDeVoz })} />);

    await utilizador.click(screen.getByTestId("voice-note-open"));

    expect(onAbrirNotaDeVoz).toHaveBeenCalledTimes(1);
  });

  it("com o diálogo aberto, o gravador real aparece", () => {
    render(<Ecra {...props({ voiceNoteOpen: true })} />);

    expect(screen.getByTestId("iniciar-gravacao")).toBeInTheDocument();
  });

  it("a gravação atravessa o separador até ao callback do contentor", async () => {
    const utilizador = userEvent.setup();
    const onEnviarNotaDeVoz = vi.fn();
    render(<Ecra {...props({ voiceNoteOpen: true, onEnviarNotaDeVoz })} />);

    await utilizador.click(screen.getByTestId("iniciar-gravacao"));
    await utilizador.click(await screen.findByRole("button", { name: /Terminar/ }));
    await utilizador.click(await screen.findByRole("button", { name: /Enviar nota/ }));

    await waitFor(() => expect(onEnviarNotaDeVoz).toHaveBeenCalledTimes(1));
    expect(onEnviarNotaDeVoz.mock.calls[0][0]).toBeInstanceOf(File);
  });

  it("o estado de processamento chega ao gravador", () => {
    render(<Ecra {...props({ voiceNoteOpen: true, aProcessarNotaDeVoz: true })} />);

    expect(
      screen.getByText("A processar Inteligência Artificial..."),
    ).toBeInTheDocument();
  });

  it("um processo bloqueado não oferece a gravação", () => {
    // Processo eliminado, desistido ou concluído não recebe notas — nem
    // escritas nem ditadas.
    render(<Ecra {...props({ disabled: true })} />);

    expect(screen.queryByTestId("voice-note-open")).not.toBeInTheDocument();
  });

  it("sem callback do contentor, o botão não aparece", () => {
    // Defesa contra meia-ligação: um botão que não faz nada é pior do que
    // botão nenhum.
    render(<Ecra {...props({ onAbrirNotaDeVoz: undefined })} />);

    expect(screen.queryByTestId("voice-note-open")).not.toBeInTheDocument();
  });
});
