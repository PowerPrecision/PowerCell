/**
 * Um botão que sabe que não pode (Lote 6, ponto 3).
 *
 * Dois modos, e a escolha é por SÍTIO, não por gosto:
 *
 * * `cadeado` (por omissão) — o botão fica visível, desactivado, com um
 *   cadeado e um tooltip que DIZ o motivo. É o modo certo quando o utilizador
 *   pode razoavelmente esperar a acção: ensina a regra em vez de a esconder, e
 *   um ecrã que muda de forma a cada perfil é impossível de apoiar ao telefone.
 *
 * * `ocultar` — o botão não é renderizado. Reserva-se para acções cuja mera
 *   existência revela algo (gestão, eliminação em massa) e para barras onde um
 *   botão morto é só ruído.
 *
 * TRÊS DETALHES QUE NÃO SE PODEM PERDER
 * =====================================
 * 1. **O tooltip traz o seu próprio `TooltipProvider`.** Este projecto não tem
 *    um provider global, e um componente que dependa de o chamador o ter
 *    funciona numa página e falha noutra — sem erro, só sem tooltip.
 * 2. **O `disabled` vai no botão, não um `pointer-events: none` no contentor.**
 *    Um contentor sem eventos tira o tooltip e o foco do teclado: ficava um
 *    botão que parece activo, não responde e não explica nada.
 * 3. **Nunca se renderiza um `<button disabled>` dentro de um `<Tooltip>` sem
 *    um invólucro**: um elemento desactivado não emite eventos de rato, e o
 *    tooltip nunca abriria. O `<span>` é o que recebe o hover.
 * 4. **O nome acessível do botão bloqueado DIZ qual é a acção** (Lote 7). A
 *    primeira versão fazia `typeof children === "string" ? children : "Acção"`
 *    — e `children` quase nunca é uma string: o padrão da casa é ícone +
 *    rótulo, logo um array. O resultado era que TODOS os botões bloqueados do
 *    sistema se anunciavam como «Acção — sem permissão»: um leitor de ecrã não
 *    distinguia «Novo Processo» de «Exportar Excel», e por `getByRole("button",
 *    {name: /exportar/i})` o botão deixava de existir. Um botão sem nome
 *    acessível é um bug de acessibilidade E um teste impossível — foi o teste
 *    de página do Kanban a dar com ele. `textoDosFilhos` percorre a árvore.
 */
import React from "react";
import { Lock } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { motivoDoBloqueio, podeFazer } from "@/utils/capacidades";

export const MODO_CADEADO = "cadeado";
export const MODO_OCULTAR = "ocultar";

/**
 * O texto legível de uma árvore de `children`.
 *
 * Percorre arrays e elementos; ignora o que não tem texto (ícones, `null`,
 * booleanos) e junta o resto com um espaço. É o que dá nome acessível ao
 * botão bloqueado — sem isto, ícone + rótulo resolvia para nada.
 */
export function textoDosFilhos(children) {
  if (children === null || children === undefined || typeof children === "boolean") {
    return "";
  }
  if (typeof children === "string" || typeof children === "number") {
    return String(children).trim();
  }
  if (Array.isArray(children)) {
    return children.map(textoDosFilhos).filter(Boolean).join(" ").trim();
  }
  if (React.isValidElement(children)) {
    return textoDosFilhos(children.props?.children);
  }
  return "";
}

const BotaoComPermissao = ({
  user,
  capacidade,
  papel,
  modo = MODO_CADEADO,
  children,
  motivo,
  testId,
  ...props
}) => {
  const autorizado = podeFazer(user, capacidade, papel);

  if (autorizado) {
    return (
      <Button data-testid={testId} {...props}>
        {children}
      </Button>
    );
  }

  if (modo === MODO_OCULTAR) return null;

  const texto = motivo || motivoDoBloqueio(capacidade);
  // O rótulo sai do TEXTO dos filhos, não de `typeof children === "string"`:
  // o padrão da casa é ícone + rótulo (um array), e a versão antiga dava
  // «Acção» a todos os botões bloqueados do sistema.
  const nomeDaAccao = textoDosFilhos(children) || "Acção";

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          {/* O `span` recebe o hover: um botão desactivado não emite eventos
              de rato e o tooltip nunca abriria. */}
          <span className="inline-flex" data-testid={testId ? `${testId}-bloqueado` : undefined}>
            <Button
              {...props}
              disabled
              aria-disabled="true"
              aria-label={`${nomeDaAccao} — sem permissão`}
            >
              <Lock className="h-4 w-4 mr-2" aria-hidden="true" />
              {children}
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>{texto}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default BotaoComPermissao;
