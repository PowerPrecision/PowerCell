/**
 * O polling como RECURSO, não como motor (Épico 10, Fase 3).
 *
 * PORQUE É QUE ISTO SÓ AGORA É SEGURO
 * ===================================
 * Até às Fases 1 e 2, o polling das notificações não era redundância — era
 * suporte de vida. `send_realtime_notification` decidia a entrega por
 * `manager.is_user_connected(user_id)`, uma pergunta que MENTE com vários
 * workers (`UVICORN_WORKERS=2`): com o socket no worker B, o evento morria
 * em silêncio no worker A e quem entregava a notificação era este
 * `setInterval` de 30 s. Cortá-lo antes teria apagado metade das
 * notificações em produção, com ar de melhoria de performance.
 *
 * Hoje a entrega passa pelo Redis e chega a qualquer worker, pelo que o
 * intervalo pode dormir enquanto o socket estiver de pé.
 *
 * O QUE NÃO SE FAZ: apagar o intervalo. Um WebSocket cai — rede móvel,
 * portátil a adormecer, deploy do servidor. O padrão é o mesmo do Webmail e
 * do `TasksContext`: parar quando ligado, retomar quando cai.
 *
 * E A LACUNA QUE NINGUÉM VÊ: os eventos emitidos ENQUANTO o socket esteve
 * em baixo perderam-se para sempre — não há repetição. Por isso a volta da
 * ligação obriga a UMA leitura de recuperação (`precisaDeRecuperar`), senão
 * o ecrã fica calado e desactualizado ao mesmo tempo, que é a pior das
 * combinações: parece funcionar.
 */

/** Intervalo normal de sondagem quando não há WebSocket. */
export const INTERVALO_BASE_MS = 30000;

/** Tecto do recuo por rate limiting (5 min). */
export const INTERVALO_MAXIMO_MS = 300000;

const MULTIPLICADOR_DE_RECUO = 2;

function numeroValido(valor) {
  return typeof valor === "number" && Number.isFinite(valor) && valor > 0;
}

/**
 * Intervalo a usar agora, ou `null` para não sondar de todo.
 *
 * @param {{isConnected: boolean, intervaloActual?: number}} estado
 * @returns {number|null}
 */
export function intervaloEfectivo({ isConnected, intervaloActual } = {}) {
  if (isConnected) return null;
  // Um intervalo inválido cai no base: falhar para "sem rede de segurança"
  // seria o pior dos dois lados.
  return numeroValido(intervaloActual) ? intervaloActual : INTERVALO_BASE_MS;
}

/**
 * A ligação acabou de voltar depois de ter caído?
 *
 * `anterior === null` é a primeira ligação da montagem, e aí a leitura
 * inicial já foi feita — recuperar seria pedir duas vezes o mesmo.
 */
export function precisaDeRecuperar({ anterior, actual } = {}) {
  return anterior === false && actual === true;
}

/** Duplica o intervalo depois de um 429, com tecto. */
export function aplicarRecuoPorRateLimit(intervaloActual) {
  const base = numeroValido(intervaloActual) ? intervaloActual : INTERVALO_BASE_MS;
  return Math.min(base * MULTIPLICADOR_DE_RECUO, INTERVALO_MAXIMO_MS);
}
