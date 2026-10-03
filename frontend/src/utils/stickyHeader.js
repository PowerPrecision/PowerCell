/**
 * O cabeçalho fixo do CRM (Lote 4, ponto 4).
 *
 * O DEFEITO: `position: sticky` SEM `top` nunca cola.
 * O `DashboardLayout` declarava
 *
 *     <header className="border-b border-border bg-card sticky z-50 h-14"
 *             style={isImpersonating ? { top: '48px' } : {}}>
 *
 * A classe `sticky` estava lá, e com ela a intenção — há até um efeito de
 * scroll (`headerCollapsed`) escrito para quando o cabeçalho acompanha a
 * página. Mas `top` ficou por declarar, e o valor inicial de `top` é
 * `auto`: um elemento sticky com `top: auto` **não tem limiar onde colar**
 * e comporta-se exactamente como `static`. O cabeçalho subia com o scroll
 * em todo o sistema.
 *
 * PORQUE É QUE NINGUÉM VIU: o único caminho em que funcionava era a
 * IMPERSONAÇÃO — aí o `style` em linha punha `top: 48px` e o cabeçalho
 * colava. Quem testou "ver como cliente" viu-o a funcionar.
 *
 * E o padrão certo já existia no projecto, noutro ficheiro:
 * `PendingItemsList.js` escreve `sticky z-50 ${isImpersonating ? 'top-12' :
 * 'top-0'}` — com o `top` dos dois lados. Foi a única das três barras do
 * sistema (esta, aquela e a do Portal) a ficar sem ele.
 *
 * É puro porque o jsdom não calcula layout: não há teste de render que
 * distinga um `sticky` que cola de um que não cola. O que se pode afirmar
 * é a REGRA — e é isso que este módulo torna afirmável.
 */

/** Altura da faixa de impersonação ("Está a ver como…"), em px. */
export const ALTURA_DA_FAIXA_DE_IMPERSONACAO = 48;

/** A classe Tailwind equivalente (48px = 12 × 4px = `top-12`). */
export const TOPO_COM_IMPERSONACAO = "top-12";
export const TOPO_SEM_IMPERSONACAO = "top-0";

/**
 * Camadas de empilhamento da moldura.
 *
 * O cabeçalho fica ABAIXO da gaveta lateral e do seu fundo escuro. Não é
 * estética: em ecrã estreito a gaveta abre por cima de tudo e ocupa a
 * mesma faixa de 56px do cabeçalho. Com z iguais decide a ordem no DOM —
 * e o cabeçalho vem depois da gaveta, logo tapava-lhe o logótipo e o
 * botão de fechar. Ao tornar o cabeçalho REALMENTE fixo, isso passaria a
 * ser visível em cada abertura da gaveta.
 */
export const CAMADA_DA_GAVETA = 50;
export const CAMADA_DO_FUNDO_DA_GAVETA = 45;
export const CAMADA_DO_CABECALHO = 40;

/**
 * As classes do cabeçalho fixo.
 *
 * @param {object} [args]
 * @param {boolean} [args.isImpersonating] — há faixa de impersonação acima
 * @returns {string}
 */
export function classesDoCabecalhoFixo({ isImpersonating = false } = {}) {
  // Classes LITERAIS, nunca compostas por interpolação: o Tailwind gera o
  // CSS a partir do que LÊ no código-fonte. Um `z-${CAMADA}` não existe
  // como texto em sítio nenhum, logo a regra não é gerada e o cabeçalho
  // fica sem camada — o mesmo nada que o `top` em falta produzia.
  // `h-14` fixo: o cabeçalho minimiza o CONTEÚDO com o scroll
  // (`headerCollapsed`) e nunca a altura — mudar de altura a meio do
  // scroll empurra a página e faz o texto saltar debaixo do cursor.
  return isImpersonating
    ? "border-b border-border bg-card sticky top-12 z-40 h-14"
    : "border-b border-border bg-card sticky top-0 z-40 h-14";
}
