/**
 * «Rever Sugestões IA» — painel lateral com a comparação campo a campo
 * (Lote 4, ponto 4).
 *
 * A barra e os campos em linha continuam a existir: o painel é a VISTA DE
 * REVISÃO — todas as sugestões numa tabela `Campo | Valor Atual | Sugestão IA
 * | Ação`, para quem prefere decidir com o antes e o depois lado a lado em vez
 * de ir de separador em separador.
 *
 * APRESENTAÇÃO E NADA MAIS. Não tem estado de sugestões nem grava: diz o que
 * aconteceu (`onAprovar`/`onRejeitar`/`onAprovarTodas`) e o contentor aplica a
 * máquina de estados de `utils/sugestoesEmLinha` — a mesma das sugestões em
 * linha, logo a regra de ouro (mostrar não é gravar; só o aprovado entra no
 * payload) vale aqui sem uma segunda implementação.
 *
 * Acessibilidade: cada botão leva o NOME DO CAMPO no nome acessível. Com doze
 * linhas, doze «Aceitar» são indistinguíveis para um leitor de ecrã (e
 * impossíveis de consultar num teste).
 */
import { Check, Sparkles, X } from "lucide-react";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "../ui/sheet";
import {
  APROVADA,
  PENDENTE,
  contarPorEstado,
} from "../../utils/sugestoesEmLinha";
import { rotuloDaSugestao, textoDoValor } from "../../utils/rotulosDasSugestoes";

function EstadoDaLinha({ estado }) {
  if (estado === APROVADA) {
    return (
      <Badge variant="outline" className="gap-1 bg-emerald-50 text-emerald-800 border-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-200 dark:border-emerald-800">
        <Check className="h-3 w-3" aria-hidden="true" />
        Aceite
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className="gap-1 bg-muted text-muted-foreground">
      <X className="h-3 w-3" aria-hidden="true" />
      Rejeitada
    </Badge>
  );
}

/**
 * @param {Object} props
 * @param {boolean} props.aberto
 * @param {Function} props.onAbertoChange   — (aberto: boolean) => void
 * @param {Object|null} props.sugestoes     — estado de `sugestoesEmLinha` (ou null)
 * @param {Function} props.onAprovar        — (campo) => void
 * @param {Function} props.onRejeitar       — (campo) => void
 * @param {Function} props.onAprovarTodas   — () => void
 */
export default function SugestoesIADrawer({
  aberto,
  onAbertoChange,
  sugestoes,
  onAprovar,
  onRejeitar,
  onAprovarTodas,
}) {
  const campos = Object.entries(sugestoes?.campos || {});
  const contagem = contarPorEstado(sugestoes);
  const pendentes = contagem[PENDENTE];

  return (
    <Sheet open={Boolean(aberto)} onOpenChange={onAbertoChange}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-2xl overflow-y-auto"
        data-testid="sugestoes-ia-drawer"
      >
        <SheetHeader className="pr-6">
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-amber-600" aria-hidden="true" />
            Rever Sugestões IA
          </SheetTitle>
          <SheetDescription>
            {sugestoes?.sourceDocument
              ? `Extraído de ${sugestoes.sourceDocument}. `
              : ""}
            Nada é gravado até aceitar: só os campos aceites entram na ficha.
          </SheetDescription>
        </SheetHeader>

        {campos.length === 0 ? (
          <p className="mt-6 text-sm text-muted-foreground" data-testid="sugestoes-ia-vazio">
            Não há sugestões da IA por rever.
          </p>
        ) : (
          <div className="mt-4 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-muted-foreground" data-testid="sugestoes-ia-contagem">
                {pendentes > 0
                  ? `${pendentes} por decidir de ${campos.length}`
                  : `Todas decididas (${campos.length})`}
              </p>
              {pendentes > 0 && (
                <Button type="button" size="sm" onClick={onAprovarTodas}>
                  <Check className="h-4 w-4 mr-1" aria-hidden="true" />
                  Aceitar Todas
                </Button>
              )}
            </div>

            <div className="overflow-x-auto rounded-md border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-left text-xs uppercase text-muted-foreground">
                  <tr>
                    <th scope="col" className="px-3 py-2 font-medium">Campo</th>
                    <th scope="col" className="px-3 py-2 font-medium">Valor Atual</th>
                    <th scope="col" className="px-3 py-2 font-medium">Sugestão IA</th>
                    <th scope="col" className="px-3 py-2 font-medium">Ação</th>
                  </tr>
                </thead>
                <tbody>
                  {campos.map(([campo, dados]) => {
                    const rotulo = rotuloDaSugestao(campo);
                    return (
                      <tr
                        key={campo}
                        className="border-t align-top"
                        data-testid={`sugestao-linha-${campo}`}
                      >
                        <th scope="row" className="px-3 py-2 text-left font-medium">
                          {rotulo}
                          {dados.eConflito && (
                            <span className="block text-[11px] font-normal text-amber-700 dark:text-amber-300">
                              Substitui um valor existente
                            </span>
                          )}
                        </th>
                        <td className="px-3 py-2 text-muted-foreground" data-testid={`sugestao-atual-${campo}`}>
                          {textoDoValor(dados.valorAnterior)}
                        </td>
                        <td className="px-3 py-2 font-medium" data-testid={`sugestao-nova-${campo}`}>
                          {textoDoValor(dados.valorSugerido)}
                        </td>
                        <td className="px-3 py-2">
                          {dados.estado === PENDENTE ? (
                            <div className="flex gap-1">
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="h-7 px-2"
                                onClick={() => onAprovar?.(campo)}
                                aria-label={`Aceitar sugestão para ${rotulo}`}
                              >
                                <Check className="h-3 w-3" aria-hidden="true" />
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                className="h-7 px-2 text-destructive"
                                onClick={() => onRejeitar?.(campo)}
                                aria-label={`Rejeitar sugestão para ${rotulo}`}
                              >
                                <X className="h-3 w-3" aria-hidden="true" />
                              </Button>
                            </div>
                          ) : (
                            <EstadoDaLinha estado={dados.estado} />
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
