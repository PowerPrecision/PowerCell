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
 * Excepção cirúrgica (pagamentos): as comissões pagam-se no FIM, com o processo
 * já «Concluído». O servidor aceita `pago` sem reabrir (e SÓ `pago`, a partir de
 * pendente/faturado) — por isso, fechado, o único botão que se oferece é
 * «Marcar como Pago».
 *
 * @param {boolean} props.processoFechado
 * @param {string} [props.estado] - o estado actual (pending|invoiced|paid|cancelled)
 * @param {string} props.tituloDoBotao - ex.: "Clique para alterar para Faturado"
 * @param {() => void} props.onAlterar
 * @param {() => void} [props.onMarcarComoPago] - só quando o servidor a aceitar fechado
 * @param {import("react").ReactNode} props.children - o crachá do estado
 * @param {string} [props.id] - para o data-testid
 */
import { Banknote, Lock, Pencil } from "lucide-react";

/** Estados de que o servidor deixa passar a «pago» com o processo fechado. */
const ESTADOS_QUE_PASSAM_A_PAGO = ["pending", "invoiced"];

export default function EstadoEditavelDoRegisto({
  processoFechado = false,
  estado,
  tituloDoBotao,
  onAlterar,
  onMarcarComoPago,
  children,
  id = "",
}) {
  if (processoFechado) {
    const podePagar = typeof onMarcarComoPago === "function"
      && ESTADOS_QUE_PASSAM_A_PAGO.includes(estado);
    return (
      <span className="inline-flex items-center gap-2">
        <span
          className="inline-flex items-center gap-1 opacity-80"
          title="Processo fechado — reabra-o para alterar este registo"
          data-testid={`financa-fechada-${id}`}
        >
          {children}
          <Lock className="h-3 w-3 text-muted-foreground" aria-hidden="true" />
        </span>
        {podePagar && (
          <button
            type="button"
            onClick={onMarcarComoPago}
            title="Marcar como pago — sem reabrir o processo"
            className="inline-flex items-center gap-1 rounded border border-emerald-300 px-1.5 py-0.5 text-xs text-emerald-700 hover:bg-emerald-50 dark:text-emerald-300"
            data-testid={`financa-marcar-pago-${id}`}
          >
            <Banknote className="h-3 w-3" aria-hidden="true" />
            Marcar como Pago
          </button>
        )}
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
