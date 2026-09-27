import * as React from "react"
import * as ScrollAreaPrimitive from "@radix-ui/react-scroll-area"

import { cn } from "@/lib/utils"

const ScrollBar = React.forwardRef(({ className, orientation = "vertical", ...props }, ref) => (
  <ScrollAreaPrimitive.ScrollAreaScrollbar
    ref={ref}
    orientation={orientation}
    className={cn(
      "flex touch-none select-none transition-colors",
      orientation === "vertical" &&
        "h-full w-2.5 border-l border-l-transparent p-[1px]",
      orientation === "horizontal" &&
        "h-2.5 flex-col border-t border-t-transparent p-[1px]",
      className
    )}
    {...props}>
    <ScrollAreaPrimitive.ScrollAreaThumb className="relative flex-1 rounded-full bg-border" />
  </ScrollAreaPrimitive.ScrollAreaScrollbar>
))
ScrollBar.displayName = ScrollAreaPrimitive.ScrollAreaScrollbar.displayName

/**
 * `viewportStyle` / `viewportClassName` — o limite de altura vai no VIEWPORT.
 *
 * PORQUÊ (Lote 6, ponto 4): a `Root` tem `overflow-hidden` e o `Viewport`
 * tem `h-full`. Um `maxHeight` posto na Root — que é o reflexo natural e o
 * que o `TasksPanel` fazia — deixa a Root com altura AUTO, pelo que o
 * `h-full` do viewport resolve para a altura do conteúdo: o viewport nunca
 * transborda, o Radix não mostra barra nenhuma, e a Root corta o excedente
 * com o seu `overflow-hidden`. O resultado não é uma lista com elevador: é
 * uma lista TRUNCADA, com tarefas que não se conseguem alcançar.
 *
 * Com o limite no viewport, a altura continua a crescer com o conteúdo até
 * ao limite (uma lista curta não deixa espaço morto) e a partir dali
 * aparece a barra.
 */
const ScrollArea = React.forwardRef(({ className, children, viewportClassName, viewportStyle, ...props }, ref) => (
  <ScrollAreaPrimitive.Root
    ref={ref}
    className={cn("relative overflow-hidden", className)}
    {...props}>
    <ScrollAreaPrimitive.Viewport
      className={cn("h-full w-full rounded-[inherit]", viewportClassName)}
      style={viewportStyle}
      data-testid="scroll-area-viewport">
      {children}
    </ScrollAreaPrimitive.Viewport>
    <ScrollBar />
    <ScrollAreaPrimitive.Corner />
  </ScrollAreaPrimitive.Root>
))
ScrollArea.displayName = ScrollAreaPrimitive.Root.displayName

export { ScrollArea, ScrollBar }
