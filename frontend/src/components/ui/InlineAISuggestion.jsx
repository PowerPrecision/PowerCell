/**
 * Aprovar/rejeitar uma sugestão da IA, ao lado do campo (Lote 3, ponto 1).
 *
 * Substitui a janela sobreposta de resultados: o valor aparece no campo, com
 * destaque, e a decisão toma-se ali — sem fechar nada para comparar com o
 * resto da ficha, e campo a campo em vez de um bloco inteiro.
 *
 * APRESENTAÇÃO E NADA MAIS. Diz o que aconteceu (`onAprovar`/`onRejeitar`) e
 * quem decide o que isso implica é o contentor. A máquina de estados vive em
 * `utils/sugestoesEmLinha.js`, que é onde a regra de ouro — mostrar não é
 * gravar — se consegue afirmar em teste.
 *
 * Dois detalhes de acessibilidade que não são decoração:
 *   · cada botão tem nome acessível com o NOME DO CAMPO. Com dez sugestões
 *     no ecrã, dez botões «Aprovar» são indistinguíveis para quem usa leitor
 *     de ecrã — e impossíveis de consultar num teste;
 *   · o valor anterior de um conflito vai à vista. Aprovar sem ver o que se
 *     perde não é uma decisão informada.
 */
import { Check, Sparkles, Undo2, X } from "lucide-react";

import { Badge } from "./badge";
import { Button } from "./button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./tooltip";
import { APROVADA, PENDENTE, REJEITADA } from "../../utils/sugestoesEmLinha";

function formatar(valor) {
  if (valor === null || valor === undefined || valor === "") return "vazio";
  return String(valor);
}

/**
 * @param {Object} props
 * @param {string} props.campo        — nome técnico (para o nome acessível)
 * @param {string} props.rotulo       — nome legível do campo
 * @param {Object} props.sugestao     — {valorSugerido, valorAnterior, estado, eConflito}
 * @param {Function} props.onAprovar  — (campo) => void
 * @param {Function} props.onRejeitar — (campo) => void
 * @param {Function} [props.onReabrir] — (campo) => void, para desfazer
 */
export function InlineAISuggestion({
  campo,
  rotulo,
  sugestao,
  onAprovar,
  onRejeitar,
  onReabrir,
}) {
  if (!sugestao) return null;
  const nome = rotulo || campo;

  if (sugestao.estado === PENDENTE) {
    return (
      <TooltipProvider delayDuration={200}>
        <span
          className="inline-flex items-center gap-1"
          data-testid={`sugestao-${campo}`}
        >
          <Tooltip>
            <TooltipTrigger asChild>
              <Badge
                variant="outline"
                className="gap-1 px-1.5 py-0 text-[10px] cursor-help bg-amber-50 text-amber-800 border-amber-300 dark:bg-amber-950/40 dark:text-amber-200 dark:border-amber-800"
              >
                <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />
                Sugestão IA
              </Badge>
            </TooltipTrigger>
            <TooltipContent side="bottom" className="max-w-xs">
              <p className="font-semibold">Sugerido pela IA</p>
              <p className="text-xs mt-1">{formatar(sugestao.valorSugerido)}</p>
              {sugestao.eConflito && (
                // Aprovar sem ver o que se perde não é uma decisão informada.
                <p className="text-xs text-muted-foreground mt-1">
                  Substitui: {formatar(sugestao.valorAnterior)}
                </p>
              )}
            </TooltipContent>
          </Tooltip>

          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-5 w-5 text-emerald-700 hover:bg-emerald-100 dark:text-emerald-400 dark:hover:bg-emerald-950"
            onClick={() => onAprovar?.(campo)}
            aria-label={`Aprovar sugestão da IA para ${nome}`}
            data-testid={`aprovar-${campo}`}
          >
            <Check className="h-3 w-3" aria-hidden="true" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-5 w-5 text-destructive hover:bg-destructive/10"
            onClick={() => onRejeitar?.(campo)}
            aria-label={`Rejeitar sugestão da IA para ${nome}`}
            data-testid={`rejeitar-${campo}`}
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </Button>
        </span>
      </TooltipProvider>
    );
  }

  // Decidida: fica o registo do que foi feito, com saída para desfazer —
  // um clique errado num ícone de 20px tem de ter volta.
  const decidida = sugestao.estado === APROVADA ? "Aprovada" : "Rejeitada";
  return (
    <span className="inline-flex items-center gap-1" data-testid={`sugestao-${campo}`}>
      <Badge
        variant="outline"
        className={`gap-1 px-1.5 py-0 text-[10px] ${
          sugestao.estado === APROVADA
            ? "bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-800"
            : "bg-muted text-muted-foreground"
        }`}
      >
        {sugestao.estado === APROVADA ? (
          <Check className="h-2.5 w-2.5" aria-hidden="true" />
        ) : (
          <X className="h-2.5 w-2.5" aria-hidden="true" />
        )}
        {decidida}
      </Badge>
      {onReabrir && (
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-5 w-5 text-muted-foreground"
          onClick={() => onReabrir(campo)}
          aria-label={`Reabrir sugestão da IA para ${nome}`}
          data-testid={`reabrir-${campo}`}
        >
          <Undo2 className="h-3 w-3" aria-hidden="true" />
        </Button>
      )}
    </span>
  );
}

/**
 * A barra de resumo: quantas faltam decidir e as acções em bloco.
 *
 * Com uma extracção de doze campos, decidir um a um é trabalho; mas o
 * "aprovar tudo" nunca reabre o que já foi rejeitado (ver
 * `utils/sugestoesEmLinha`), senão desfazia decisões em silêncio.
 */
export function BarraDeSugestoes({
  contagem,
  sourceDocument,
  onAprovarTodas,
  onRejeitarTodas,
  onFechar,
}) {
  const pendentes = contagem?.[PENDENTE] || 0;
  const aprovadas = contagem?.[APROVADA] || 0;
  const rejeitadas = contagem?.[REJEITADA] || 0;
  if (pendentes + aprovadas + rejeitadas === 0) return null;

  return (
    <div
      data-testid="barra-sugestoes-ia"
      className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs dark:border-amber-800 dark:bg-amber-950/30"
    >
      <Sparkles className="h-4 w-4 shrink-0 text-amber-700 dark:text-amber-300" aria-hidden="true" />
      <span className="flex-1 min-w-0 text-amber-900 dark:text-amber-100">
        {pendentes > 0 ? (
          <>
            <strong>{pendentes}</strong>{" "}
            {pendentes === 1 ? "sugestão da IA por decidir" : "sugestões da IA por decidir"}
          </>
        ) : (
          <>Sugestões decididas: {aprovadas} aprovada(s), {rejeitadas} rejeitada(s).</>
        )}
        {sourceDocument ? (
          <span className="text-amber-700 dark:text-amber-300"> — {sourceDocument}</span>
        ) : null}
      </span>
      {pendentes > 0 && (
        <>
          <Button type="button" variant="outline" size="sm" className="h-7" onClick={onAprovarTodas}>
            <Check className="h-3 w-3 mr-1" aria-hidden="true" />
            Aprovar todas
          </Button>
          <Button type="button" variant="ghost" size="sm" className="h-7" onClick={onRejeitarTodas}>
            Rejeitar todas
          </Button>
        </>
      )}
      {pendentes === 0 && onFechar && (
        <Button type="button" variant="ghost" size="sm" className="h-7" onClick={onFechar}>
          Fechar
        </Button>
      )}
    </div>
  );
}

export default InlineAISuggestion;
