/**
 * Uma notificação só apita (som + toast) quando o servidor a marcou como importante:
 * `alerta` é o que também iria para o Telegram da pessoa; `apitar` é um aviso
 * importante que se juntou a um grupo que ainda não tinha apitado. O resto fica
 * calado no sino, como histórico (Flavio, Nov 2026).
 */
export function deveApitar(notificacao) {
  return Boolean(notificacao) && (notificacao.alerta === true || notificacao.apitar === true);
}
