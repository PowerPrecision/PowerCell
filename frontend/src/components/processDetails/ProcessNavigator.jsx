/**
 * ProcessNavigator — setas Anterior/Seguinte nos Detalhes (Ponto 17).
 *
 * Componente de APRESENTAÇÃO: recebe os vizinhos já resolvidos e diz o
 * que aconteceu (`onNavegar(id)`). Não sabe de cache, de sessão nem do
 * endpoint de fronteira — isso é do contentor.
 *
 * REGRA: um lado sem vizinho é um botão DESACTIVADO, não um botão
 * ausente. O controlo não pode saltar de sítio quando o utilizador
 * chega ao primeiro ou ao último processo — perder o alvo do rato a
 * meio de uma revisão de 40 processos é exactamente o atrito que esta
 * funcionalidade veio remover.
 */
import { Button } from "../ui/button";
import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";

/**
 * @param {object} props
 * @param {?string} props.anteriorId
 * @param {?string} props.seguinteId
 * @param {?number} props.posicao — 1-based, no conjunto filtrado inteiro
 * @param {number} props.total
 * @param {boolean} [props.aCarregar] — a camada 3 está a perguntar ao servidor
 * @param {(id: string) => void} props.onNavegar
 */
export default function ProcessNavigator({
  anteriorId,
  seguinteId,
  posicao,
  total,
  aCarregar = false,
  onNavegar,
}) {
  return (
    <div
      className="flex items-center gap-0.5 shrink-0"
      data-testid="navegacao-contigua"
    >
      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        aria-label="Processo anterior"
        disabled={!anteriorId || aCarregar}
        onClick={() => anteriorId && onNavegar?.(anteriorId)}
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>

      <span
        className="text-xs text-muted-foreground tabular-nums whitespace-nowrap px-1"
        data-testid="posicao-na-lista"
      >
        {aCarregar ? (
          <Loader2 className="h-3 w-3 animate-spin" aria-label="A procurar" />
        ) : posicao && total ? (
          `${posicao} / ${total}`
        ) : (
          ""
        )}
      </span>

      <Button
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        aria-label="Processo seguinte"
        disabled={!seguinteId || aCarregar}
        onClick={() => seguinteId && onNavegar?.(seguinteId)}
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );
}
