/**
 * O estado (pendente → faturado → pago) de um registo financeiro, clicável.
 *
 * D-34 — o registo financeiro de um processo FECHADO não se altera (o servidor
 * recusa com 403, a todos os perfis): reabre-se o processo primeiro. O ecrã
 * não oferece o que o servidor vai recusar — em vez do botão, mostra o estado
 * com um cadeado e a razão. A flag `processoFechado` vem calculada do servidor
 * (`processo_fechado` na listagem), nunca de uma lista escrita aqui.
 *
 * @param {Object} props
 * @param {boolean} props.processoFechado
 * @param {string} props.tituloDoBotao - ex.: "Clique para alterar para Faturado"
 * @param {() => void} props.onAlterar
 * @param {import("react").ReactNode} props.children - o crachá do estado
 * @param {string} [props.id] - para o data-testid
 */
import { Lock, Pencil } from "lucide-react";

export default function EstadoEditavelDoRegisto({
  processoFechado = false,
  tituloDoBotao,
  onAlterar,
  children,
  id = "",
}) {
  if (processoFechado) {
    return (
      <span
        className="inline-flex items-center gap-1 opacity-80"
        title="Processo fechado — reabra-o para alterar este registo"
        data-testid={`financa-fechada-${id}`}
      >
        {children}
        <Lock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
      </span>
    );
  }
  return (
    <button
      type="button"
      onClick={onAlterar}
      title={tituloDoBotao}
      className="inline-flex items-center gap-1 cursor-pointer hover:scale-105 transition-transform"
    >
      {children}
      <Pencil className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100" aria-hidden="true" />
    </button>
  );
}
