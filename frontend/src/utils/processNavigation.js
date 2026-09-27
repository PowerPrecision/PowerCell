/**
 * Ponto 17 — Navegação Contígua entre processos (estado e cache).
 *
 * O PROBLEMA: a listagem de processos (`ProcessesPage`) NÃO usa o
 * TanStack Query — guarda os resultados em `useState` e vai buscá-los à
 * mão. Não existe, portanto, cache de listagem para ler. As setas
 * Anterior/Seguinte dos Detalhes têm de saber a ordem de algum lado, e
 * esse lado não pode ser um pedido novo à base de dados por cada clique.
 *
 * A ESTRATÉGIA, três camadas, da mais barata para a mais cara:
 *
 *   1. `location.state` — a listagem leva consigo os ids JÁ ORDENADOS da
 *      página aberta. Cobre a esmagadora maioria dos cliques e custa
 *      ZERO pedidos. São ~40 ids, ~1,5 KB.
 *
 *   2. `sessionStorage` — o `state` do router morre num F5. O mesmo
 *      contexto fica guardado na sessão do separador, que sobrevive ao
 *      refresh e NÃO sobrevive a um separador novo — o que é correcto:
 *      quem abre o link directo não veio de listagem nenhuma.
 *
 *   3. `GET /processes/{id}/neighbours` — só na FRONTEIRA da página (o
 *      item 40 de 40, cujo seguinte vive na página a seguir). Um pedido
 *      minúsculo, que devolve dois ids.
 *
 * Quando nenhuma se aplica, as setas NÃO aparecem. Nunca se mostra uma
 * seta que possa levar ao sítio errado — é o mesmo princípio do 404 nas
 * automações: mais vale não dizer nada do que dizer mal.
 */

export const CHAVE_CONTEXTO = "powercell:navegacao-processos";

/** Versão do formato: um contexto antigo em sessão é descartado, não interpretado. */
export const VERSAO_CONTEXTO = 1;

function resolverStorage(storage) {
  if (storage) return storage;
  try {
    return typeof window !== "undefined" ? window.sessionStorage : null;
  } catch {
    // Janela privada, cookies bloqueados, jsdom sem storage: o contexto
    // é uma conveniência, nunca um requisito.
    return null;
  }
}

/**
 * Empacota a listagem aberta para viajar com a navegação.
 *
 * @param {object} args
 * @param {string[]} args.ids — ids pela ORDEM EM QUE APARECEM no ecrã
 * @param {number} args.page — página actual (1-based)
 * @param {number} args.size — itens por página
 * @param {number} args.total — total de processos no filtro
 * @param {string} args.origem — rota da listagem (para o botão Voltar)
 * @param {object} [args.params] — filtros a repetir no endpoint de vizinhos
 * @returns {object|null} — `null` quando não há nada que valha a pena guardar
 */
export function construirContextoDeNavegacao({
  ids,
  page,
  size,
  total,
  origem,
  params,
} = {}) {
  const lista = (Array.isArray(ids) ? ids : []).filter(Boolean);
  if (!lista.length) return null;

  const pagina = Number(page) > 0 ? Number(page) : 1;
  const tamanho = Number(size) > 0 ? Number(size) : lista.length;
  const totalSeguro = Number(total) > 0 ? Number(total) : lista.length;

  return {
    versao: VERSAO_CONTEXTO,
    ids: lista,
    page: pagina,
    size: tamanho,
    total: totalSeguro,
    origem: origem || "",
    params: params && typeof params === "object" ? { ...params } : {},
  };
}

/**
 * Vizinhos de `processId` dentro do contexto — sem tocar na rede.
 *
 * `precisaDeAnterior` / `precisaDeSeguinte` marcam a fronteira da
 * página: é o único caso em que vale a pena perguntar ao servidor.
 *
 * @returns {{
 *   disponivel: boolean, anteriorId: ?string, seguinteId: ?string,
 *   posicao: ?number, total: number,
 *   precisaDeAnterior: boolean, precisaDeSeguinte: boolean,
 *   origem: string, params: object
 * }}
 */
export function vizinhosNoContexto(contexto, processId) {
  const vazio = {
    disponivel: false,
    anteriorId: null,
    seguinteId: null,
    posicao: null,
    total: 0,
    precisaDeAnterior: false,
    precisaDeSeguinte: false,
    origem: "",
    params: {},
  };

  if (!contexto || contexto.versao !== VERSAO_CONTEXTO) return vazio;
  const ids = Array.isArray(contexto.ids) ? contexto.ids : [];
  const indice = ids.indexOf(processId);
  // O processo não pertence a esta listagem: o utilizador chegou por
  // outro caminho (pesquisa global, link, notificação). Inventar-lhe uma
  // posição seria prometer uma vizinhança que não existe.
  if (indice < 0) return vazio;

  const size = contexto.size || ids.length;
  const total = contexto.total || ids.length;
  const posicao = (contexto.page - 1) * size + indice + 1;

  return {
    disponivel: true,
    anteriorId: indice > 0 ? ids[indice - 1] : null,
    seguinteId: indice < ids.length - 1 ? ids[indice + 1] : null,
    posicao,
    total,
    precisaDeAnterior: indice === 0 && contexto.page > 1,
    precisaDeSeguinte: indice === ids.length - 1 && posicao < total,
    origem: contexto.origem || "",
    params: contexto.params || {},
  };
}

/**
 * Substitui os ids que vieram do servidor no contexto em memória.
 *
 * A Camada 3 devolve o vizinho de FORA da página. Guardá-lo evita
 * repetir o pedido se o utilizador hesitar e voltar atrás.
 */
export function comVizinhosDoServidor(vizinhos, resposta) {
  if (!resposta) return vizinhos;
  return {
    ...vizinhos,
    anteriorId: vizinhos.anteriorId ?? resposta.previous_id ?? null,
    seguinteId: vizinhos.seguinteId ?? resposta.next_id ?? null,
    posicao: vizinhos.posicao ?? resposta.position ?? null,
    total: vizinhos.total || resposta.total || 0,
    precisaDeAnterior: false,
    precisaDeSeguinte: false,
  };
}

/** Guarda o contexto na sessão. Nunca levanta: é uma conveniência. */
export function guardarContexto(contexto, storage) {
  const store = resolverStorage(storage);
  if (!store || !contexto) return false;
  try {
    store.setItem(CHAVE_CONTEXTO, JSON.stringify(contexto));
    return true;
  } catch {
    return false;
  }
}

/** Lê o contexto da sessão. Devolve `null` em tudo o que não reconheça. */
export function lerContexto(storage) {
  const store = resolverStorage(storage);
  if (!store) return null;
  try {
    const cru = store.getItem(CHAVE_CONTEXTO);
    if (!cru) return null;
    const contexto = JSON.parse(cru);
    if (!contexto || contexto.versao !== VERSAO_CONTEXTO) return null;
    if (!Array.isArray(contexto.ids) || !contexto.ids.length) return null;
    return contexto;
  } catch {
    // JSON corrompido por uma versão anterior: descartar em silêncio é
    // melhor do que rebentar a página de Detalhes por causa das setas.
    return null;
  }
}

/**
 * Converte os filtros guardados no contexto em `URLSearchParams`.
 *
 * Tem de ser `URLSearchParams` e não um objecto simples: `labels` é um
 * filtro de VÁRIOS valores e o backend lê-o como `List[str]`. Um objecto
 * `{labels: [...]}` seria serializado como `labels=a,b` e o servidor
 * passaria a procurar uma etiqueta chamada "a,b" — a vizinhança sairia
 * calculada sobre outro filtro, sem erro nenhum. É o mesmo defeito que o
 * `Object.fromEntries` ia introduzindo no Kanban.
 */
export function paramsDeVizinhos(params) {
  const sp = new URLSearchParams();
  for (const [chave, valor] of Object.entries(params || {})) {
    if (valor === undefined || valor === null || valor === "") continue;
    if (Array.isArray(valor)) {
      for (const item of valor) {
        if (item !== undefined && item !== null && item !== "") {
          sp.append(chave, String(item));
        }
      }
      continue;
    }
    sp.append(chave, String(valor));
  }
  return sp;
}
