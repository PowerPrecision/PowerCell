/**
 * Refresca os alertas de um processo DEPOIS de uma acção cujo efeito chega tarde.
 *
 * «Enviar por Email» o link do Portal responde logo (`queued: true`) e entrega em segundo
 * plano: o alerta «Email de acesso não entregue» só deixa de valer quando o email SAI. Um
 * único refresco imediato apanha o estado antigo; por isso há duas passagens espaçadas.
 * Os alertas são derivados (não se «resolvem»): basta voltar a pedi-los.
 */
import { queryKeys } from "../lib/queryClient";

export const ESPERAS_DO_REFRESCO_MS = [4000, 12000];

/** Devolve uma função que cancela as passagens ainda por fazer (desmontagem do ecrã). */
export function agendarRefrescoDosAlertas(queryClient, processId, esperas = ESPERAS_DO_REFRESCO_MS) {
  if (!queryClient || !processId) return () => {};
  const temporizadores = esperas.map((ms) =>
    setTimeout(() => {
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.alerts(processId) });
    }, ms),
  );
  return () => temporizadores.forEach(clearTimeout);
}
