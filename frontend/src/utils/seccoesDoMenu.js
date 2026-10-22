/**
 * Que grupos do menu lateral estão abertos (QA Index, Out 2026).
 *
 * O `DashboardLayout` é montado POR PÁGINA: cada navegação desmonta o menu e monta outro.
 * O estado «grupo aberto» vivia só num `useState` do layout, logo cada clique numa ligação
 * fazia o menu «fechar-se» — todos os grupos recolhiam a zero — e só reabria o grupo cuja
 * rota constava de uma lista escrita à mão (`/index` e `/validades`, do perfil Index, não
 * constavam em nenhuma). Duas correcções, as duas aqui:
 *
 *  1. **A rota activa decide o grupo a partir do PRÓPRIO menu** (`seccoesComRotaActiva`): o
 *     grupo que contém a ligação em que se está abre-se. Uma lista de rotas à parte diverge do
 *     menu sem dar erro — é o «menu e rotas têm de concordar» — e foi assim que o Index ficou de fora.
 *  2. **O que a pessoa abriu ou fechou à mão sobrevive à navegação** (`sessionStorage`, por
 *     separador): se abriu «Visão Global» e clica numa ligação, o grupo continua aberto.
 *
 * O armazenamento pode falhar (janela privada, site data bloqueado): nunca é obrigatório.
 */

export const CHAVE_DE_ARMAZENAMENTO = "menu-seccoes-abertas";

function eRotaDoItem(pathname, href) {
  if (!href || typeof pathname !== "string") return false;
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Uma ligação pode declarar outras rotas que lhe pertencem (`tambem`): a bancada do Index (`/index/:id`) pertence a «Os Meus Processos». */
function itemTemARota(item, pathname) {
  return eRotaDoItem(pathname, item?.href) || (Array.isArray(item?.tambem) && item.tambem.some((h) => eRotaDoItem(pathname, h)));
}

/** Ids dos grupos que têm uma ligação para a rota actual (ou para um pai dela). */
export function seccoesComRotaActiva(grupos, pathname) {
  if (!Array.isArray(grupos)) return [];
  return grupos
    .filter((g) => g && g.id && Array.isArray(g.items) && g.items.some((i) => itemTemARota(i, pathname)))
    .map((g) => g.id);
}

/** Lê o que ficou guardado; qualquer coisa que não seja `{id: true}` vale como «nada». */
export function lerSeccoesAbertas(storage) {
  try {
    const bruto = (storage ?? globalThis.sessionStorage)?.getItem(CHAVE_DE_ARMAZENAMENTO);
    const valor = bruto ? JSON.parse(bruto) : null;
    if (!valor || typeof valor !== "object" || Array.isArray(valor)) return {};
    return Object.fromEntries(Object.entries(valor).filter(([, v]) => typeof v === "boolean"));
  } catch {
    return {};
  }
}

export function gravarSeccoesAbertas(seccoes, storage) {
  try {
    (storage ?? globalThis.sessionStorage)?.setItem(CHAVE_DE_ARMAZENAMENTO, JSON.stringify(seccoes || {}));
  } catch {
    /* sem armazenamento o menu funciona na mesma — só não se lembra */
  }
}

/** Junta ao estado actual os grupos a abrir. Devolve o MESMO objecto se nada mudou (sem re-render). */
export function abrirSeccoes(anterior, ids) {
  let mudou = false;
  const seguinte = { ...anterior };
  for (const id of ids) {
    if (!seguinte[id]) {
      seguinte[id] = true;
      mudou = true;
    }
  }
  return mudou ? seguinte : anterior;
}
