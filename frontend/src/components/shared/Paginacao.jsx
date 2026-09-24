/**
 * Paginacao — controlo partilhado das listagens de administração.
 *
 * Ponto 11 (Lote 5, Secção B). Apresentação pura: diz que página se
 * quer (`onPageChange`) e quem decide o que isso implica — pedido,
 * cache, URL — é a página.
 *
 * Mostra SEMPRE o intervalo e o total ("1–25 de 132"). Sem o total, o
 * utilizador não sabe se a lista acabou ou se foi truncada — que era
 * exactamente o defeito do tecto de 200 que isto veio fechar.
 */
import { Button } from "../ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { calcularPaginacao } from "../../utils/paginacao";

export default function Paginacao({ total, page, size, onPageChange, etiqueta = "resultados" }) {
  const p = calcularPaginacao({ total, page, size });

  // Uma só página não precisa de controlos, mas o total continua a ver-se
  // quando há alguma coisa: é o que distingue "são estes" de "são os
  // primeiros".
  if (p.totalPaginas <= 1 && p.ultimo === 0) return null;

  return (
    <div
      className="flex items-center justify-between gap-3 flex-wrap pt-3"
      data-testid="paginacao"
    >
      <p className="text-xs text-muted-foreground" data-testid="paginacao-intervalo">
        {p.primeiro}–{p.ultimo} de {Math.max(0, Number(total) || 0)} {etiqueta}
      </p>

      {p.totalPaginas > 1 && (
        <div className="flex items-center gap-1.5">
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1"
            disabled={!p.temAnterior}
            onClick={() => onPageChange?.(p.paginaActual - 1)}
            data-testid="paginacao-anterior"
          >
            <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
            Anterior
          </Button>
          <span className="text-xs text-muted-foreground px-1" data-testid="paginacao-pagina">
            {p.paginaActual} / {p.totalPaginas}
          </span>
          <Button
            variant="outline"
            size="sm"
            className="h-8 gap-1"
            disabled={!p.temSeguinte}
            onClick={() => onPageChange?.(p.paginaActual + 1)}
            data-testid="paginacao-seguinte"
          >
            Seguinte
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Button>
        </div>
      )}
    </div>
  );
}
