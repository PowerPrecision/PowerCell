/**
 * VoiceNoteRecorder — nota de voz do consultor (Épico 7, Eixo 1).
 *
 * COMPONENTE DE APRESENTAÇÃO: não sabe o que é um processo, não chama a
 * API e não decide o que acontece depois do envio. Grava (ou aceita um
 * ficheiro), deixa ouvir, e entrega o resultado ao contentor por
 * `onEnviar(File)`. Regra do § 20 do FRONTEND_GUIDELINES: nada de `set*`
 * de estado do contentor aqui dentro.
 *
 * O ESTADO QUE DETÉM É SÓ SEU: o ficheiro à espera de confirmação e a URL
 * de pré-escuta. Quem grava é o `useAudioRecorder`; o que é decisão pura
 * (formatos, limites, mensagens) vem de `utils/voiceNote`.
 *
 * PROGRESSIVE DISCLOSURE: o ecrã normal tem um botão. O formulário só
 * existe dentro do `Dialog`, e a pré-escuta só aparece depois de haver
 * gravação.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2, Mic, Square, Trash2, Upload } from "lucide-react";

import useAudioRecorder from "../../hooks/useAudioRecorder";
import {
  ACEITA_FICHEIROS,
  DURACAO_DE_AVISO_SEGUNDOS,
  DURACAO_MAXIMA_SEGUNDOS,
  formatarDuracao,
  formatarTamanho,
  validarFicheiroDeAudio,
} from "../../utils/voiceNote";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";

/**
 * @param {Object} props
 * @param {boolean} props.open - O diálogo está aberto.
 * @param {(aberto: boolean) => void} props.onOpenChange
 * @param {(ficheiro: File) => void} props.onEnviar - Entrega a gravação.
 * @param {boolean} [props.aEnviar] - Upload em curso (bloqueia os botões).
 * @param {boolean} [props.aProcessar] - A IA está a trabalhar na última nota.
 */
export default function VoiceNoteRecorder({
  open,
  onOpenChange,
  onEnviar,
  aEnviar = false,
  aProcessar = false,
}) {
  const [ficheiro, setFicheiro] = useState(null);
  const [urlDePreEscuta, setUrlDePreEscuta] = useState(null);
  const [erroLocal, setErroLocal] = useState(null);
  const inputRef = useRef(null);

  const aceitarFicheiro = useCallback((candidato) => {
    const { valido, erro } = validarFicheiroDeAudio(candidato);
    if (!valido) {
      setErroLocal(erro);
      setFicheiro(null);
      return;
    }
    setErroLocal(null);
    setFicheiro(candidato);
  }, []);

  const { suportado, aGravar, duracao, erro, iniciar, parar, cancelar } =
    useAudioRecorder({ onGravacao: aceitarFicheiro });

  // A URL do blob é um recurso do browser: sem `revokeObjectURL` cada
  // gravação descartada deixa o áudio inteiro em memória até ao refresh.
  useEffect(() => {
    if (!ficheiro) {
      setUrlDePreEscuta(null);
      return undefined;
    }
    const url = URL.createObjectURL(ficheiro);
    setUrlDePreEscuta(url);
    return () => URL.revokeObjectURL(url);
  }, [ficheiro]);

  // Fechar o diálogo limpa o que estava por confirmar — reabrir traz uma
  // folha em branco, não a gravação que o consultor já tinha descartado.
  useEffect(() => {
    if (!open) {
      setFicheiro(null);
      setErroLocal(null);
    }
  }, [open]);

  const descartar = () => {
    setFicheiro(null);
    setErroLocal(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const enviar = () => {
    if (ficheiro) onEnviar(ficheiro);
  };

  const mensagemDeErro = erroLocal || erro;
  const pertoDoLimite = duracao >= DURACAO_DE_AVISO_SEGUNDOS;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title="Nota de voz"
        description="Grave uma nota. A transcrição, o resumo e as tarefas são criados automaticamente."
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <Mic className="h-4 w-4 text-primary" />
            Nota de voz
          </DialogTitle>
          <DialogDescription>
            Grave o que ficou combinado. O resumo entra no histórico e as
            tarefas mencionadas são agendadas automaticamente.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* ── A gravar ────────────────────────────────────────────── */}
          {aGravar && (
            <div
              className="flex flex-col items-center gap-3 rounded-md border border-border bg-muted/40 py-6"
              data-testid="estado-a-gravar"
            >
              <span className="relative flex h-3 w-3">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-destructive opacity-75" />
                <span className="relative inline-flex h-3 w-3 rounded-full bg-destructive" />
              </span>
              <p className="text-sm font-medium text-foreground">A gravar...</p>
              <p
                className={`font-mono text-2xl tabular-nums ${
                  pertoDoLimite ? "text-destructive" : "text-foreground"
                }`}
                aria-live="polite"
                aria-label={`Tempo de gravação: ${formatarDuracao(duracao)}`}
              >
                {formatarDuracao(duracao)}
              </p>
              <p className="text-xs text-muted-foreground">
                Limite de {formatarDuracao(DURACAO_MAXIMA_SEGUNDOS)}
              </p>
              <div className="flex gap-2">
                <Button size="sm" onClick={parar} className="gap-1.5">
                  <Square className="h-3.5 w-3.5" />
                  Terminar
                </Button>
                <Button size="sm" variant="ghost" onClick={cancelar}>
                  Cancelar
                </Button>
              </div>
            </div>
          )}

          {/* ── Pré-escuta ──────────────────────────────────────────── */}
          {!aGravar && ficheiro && (
            <div className="space-y-2 rounded-md border border-border p-3" data-testid="pre-escuta">
              <div className="flex items-center justify-between gap-2">
                <p className="truncate text-sm font-medium text-foreground">
                  {ficheiro.name}
                </p>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {formatarTamanho(ficheiro.size)}
                </span>
              </div>
              {urlDePreEscuta && (
                // eslint-disable-next-line jsx-a11y/media-has-caption -- áudio ditado pelo próprio utilizador, sem legendas a fornecer
                <audio
                  controls
                  src={urlDePreEscuta}
                  className="w-full"
                  data-testid="audio-pre-escuta"
                />
              )}
              <Button
                size="sm"
                variant="ghost"
                onClick={descartar}
                disabled={aEnviar}
                className="gap-1.5 text-muted-foreground"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Descartar
              </Button>
            </div>
          )}

          {/* ── Repouso ─────────────────────────────────────────────── */}
          {!aGravar && !ficheiro && (
            <div className="flex flex-col items-center gap-3 py-4">
              {suportado ? (
                <Button onClick={iniciar} className="gap-2" data-testid="iniciar-gravacao">
                  <Mic className="h-4 w-4" />
                  Começar a gravar
                </Button>
              ) : (
                <p className="text-center text-sm text-muted-foreground">
                  Este browser não permite gravar. Carregue um ficheiro de áudio.
                </p>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={() => inputRef.current?.click()}
                className="gap-1.5"
              >
                <Upload className="h-3.5 w-3.5" />
                Carregar ficheiro
              </Button>
              <input
                ref={inputRef}
                type="file"
                accept={ACEITA_FICHEIROS}
                className="hidden"
                aria-label="Carregar ficheiro de áudio"
                onChange={(evento) => aceitarFicheiro(evento.target.files?.[0] || null)}
              />
            </div>
          )}

          {mensagemDeErro && (
            <p className="text-sm text-destructive" role="alert">
              {mensagemDeErro}
            </p>
          )}

          {aProcessar && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              A processar Inteligência Artificial...
            </p>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={aEnviar}
          >
            Fechar
          </Button>
          <Button onClick={enviar} disabled={!ficheiro || aEnviar || aGravar} className="gap-2">
            {aEnviar ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                A enviar...
              </>
            ) : (
              <>
                <Mic className="h-4 w-4" />
                Enviar nota
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
