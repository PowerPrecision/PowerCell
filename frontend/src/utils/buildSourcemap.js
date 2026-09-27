/**
 * Decide se um build gera sourcemaps — e a regra é fail-closed.
 *
 * `sourcemap: 'hidden'` só remove o comentário `//# sourceMappingURL=` do
 * ficheiro JS. Os `.map` continuam a ser EMITIDOS, vão no artefacto de deploy
 * e são servidos: um `GET /assets/<chunk>.js.map` devolvia 200 com o código
 * completo do frontend, comentários de regras de negócio incluídos.
 *
 * O plugin do Sentry já pedia `filesToDeleteAfterUpload: ['**\/*.map']`, mas
 * só corre quando há `SENTRY_AUTH_TOKEN`. Sem token não envia E não apaga —
 * degradava em silêncio para "os mapas ficam públicos", que é exactamente o
 * contrário do que a configuração aparentava garantir.
 *
 * Daí esta regra ser uma só: em produção, os mapas só se GERAM se houver como
 * os enviar e apagar. Sem token não se geram — perde-se a legibilidade dos
 * erros, o que é mau, mas é uma perda visível; publicar o código-fonte é uma
 * perda invisível.
 *
 * Fora de produção gera-se sempre (`true`, inline): é o modo de desenvolvimento
 * e não há artefacto a publicar.
 */

/**
 * @param {{ isProduction: boolean, temTokenDoSentry: boolean }} contexto
 * @returns {'hidden' | boolean} valor para `build.sourcemap` do Vite
 */
export function resolverSourcemapDoBuild({ isProduction, temTokenDoSentry }) {
  if (!isProduction) return true;
  return temTokenDoSentry ? "hidden" : false;
}

/**
 * Aviso a imprimir quando um build de produção sai sem mapas, ou `null`.
 *
 * Existe porque a decisão acima é silenciosa por natureza — ninguém repara num
 * `.map` que não foi gerado, e daqui a seis meses alguém pergunta porque é que
 * o Sentry mostra código minificado.
 */
export function avisoDoSourcemap({ isProduction, temTokenDoSentry }) {
  if (!isProduction || temTokenDoSentry) return null;
  return (
    "⚠️  Build de produção SEM sourcemaps: SENTRY_AUTH_TOKEN não está definido. " +
    "Os mapas não são gerados de propósito — sem token não há como enviá-los ao " +
    "Sentry nem apagá-los do artefacto, e publicá-los expõe o código-fonte. " +
    "Defina SENTRY_AUTH_TOKEN no serviço de deploy para voltar a ter stacks legíveis."
  );
}
