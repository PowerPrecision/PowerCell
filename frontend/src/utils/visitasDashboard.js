/**
 * O quadro de Visitas: normalizar, filtrar e montar as linhas da tabela.
 *
 * PORQUE É QUE ISTO É UM MÓDULO PURO (Lote 9, Fase B)
 * ===================================================
 * A `VisitsPage` tinha o estado inicial `useState([])` — um ARRAY — e o
 * endpoint `/visits/kanban` devolve um OBJECTO
 * (`{solicitadas, agendadas, concluidas, canceladas, total}`). No primeiro
 * render `visits.solicitadas` é `undefined` e só um `|| []` por coluna
 * impedia o `.filter` de rebentar; o `total` vinha do servidor e
 * contradizia o ecrã depois de uma pesquisa em memória.
 *
 * É a forma do `KanbanBoard` da D-20, com as mesmas três regras:
 *
 * 1. **a forma normaliza-se UMA vez**, num ponto único — cinco cópias da
 *    mesma guarda divergem, e foi assim que quatro colunas do Kanban
 *    ficaram sem ela;
 * 2. **`Array.isArray`, nunca `|| []`** — um objecto é *truthy*, logo
 *    `coluna || []` devolve o objecto e o erro muda de sítio em vez de
 *    desaparecer;
 * 3. **as contagens DERIVAM das listas** — depois do filtro em memória, o
 *    `total` do servidor diz outro número do que o ecrã mostra.
 */

export const COLUNAS = ["solicitadas", "agendadas", "concluidas", "canceladas"];

/** O quadro vazio, já com a forma certa. É este o estado INICIAL. */
export const QUADRO_VAZIO = Object.freeze({
  solicitadas: [],
  agendadas: [],
  concluidas: [],
  canceladas: [],
});

const lista = (valor) => (Array.isArray(valor) ? valor : []);
const texto = (valor) => String(valor ?? "").trim();

/**
 * O quadro com a forma garantida.
 *
 * Aceita também um ARRAY (a forma que `/visits` devolve), para a página
 * não ter de saber de que endpoint vieram os dados: um array entra todo
 * pela coluna do seu `status`.
 */
export function normalizarQuadro(dados) {
  if (Array.isArray(dados)) {
    const porEstado = { ...QUADRO_VAZIO };
    COLUNAS.forEach((c) => {
      porEstado[c] = [];
    });
    dados.forEach((v) => {
      porEstado[colunaDoEstado(v?.status)].push(v);
    });
    return porEstado;
  }
  const quadro = {};
  COLUNAS.forEach((coluna) => {
    quadro[coluna] = lista(dados?.[coluna]);
  });
  return quadro;
}

/** A coluna a que um estado pertence. `recusada` vive com as canceladas. */
export function colunaDoEstado(status) {
  const estado = texto(status).toLowerCase();
  if (estado === "solicitada") return "solicitadas";
  if (estado === "agendada") return "agendadas";
  if (estado === "concluida" || estado === "concluída") return "concluidas";
  return "canceladas";
}

/** Os campos sobre os quais a pesquisa corre. */
const CAMPOS_DE_PESQUISA = [
  (v) => v?.property_title,
  (v) => v?.client_name,
  (v) => v?.consultor_name,
  (v) => v?.notes,
  (v) => v?.scraped_url,
  (v) => v?.scraped_typology,
  (v) => v?.scraped_estado,
  (v) => v?.scraped_data?.title,
  (v) => v?.scraped_data?.location,
  (v) => v?.scraped_data?.typology,
  // LOTE 10 — procurar pela agência e pelo comercial. Sem isto, a
  // coluna nova era visível e não pesquisável: o consultor lê «Predial
  // Atlântico» no ecrã, escreve-o na caixa e não encontra nada.
  (v) => v?.agency_name,
  (v) => v?.agent_name,
  (v) => v?.agent_phone,
  (v) => v?.scraped_data?.consultant?.agency_name,
  (v) => v?.scraped_data?.consultant?.name,
];

export function visitaCasaComPesquisa(visita, termo) {
  const alvo = texto(termo).toLowerCase();
  if (!alvo) return true;
  return CAMPOS_DE_PESQUISA.some((ler) =>
    texto(ler(visita)).toLowerCase().includes(alvo)
  );
}

export function filtrarQuadro(quadro, termo) {
  const normalizado = normalizarQuadro(quadro);
  if (!texto(termo)) return normalizado;
  const filtrado = {};
  COLUNAS.forEach((coluna) => {
    filtrado[coluna] = normalizado[coluna].filter((v) =>
      visitaCasaComPesquisa(v, termo)
    );
  });
  return filtrado;
}

/**
 * As contagens, DERIVADAS das listas.
 *
 * O `total` do servidor contradizia o ecrã depois de uma pesquisa em
 * memória — é a regra do `count` do `KanbanBoard`.
 */
export function resumoDoQuadro(quadro) {
  const normalizado = normalizarQuadro(quadro);
  const resumo = { total: 0 };
  COLUNAS.forEach((coluna) => {
    resumo[coluna] = normalizado[coluna].length;
    resumo.total += resumo[coluna];
  });
  return resumo;
}

/**
 * O estado da EXTRACÇÃO, que é diferente do estado da visita.
 *
 * Cinco valores, e não dois: o `sem_dados` é o terceiro veredicto que o
 * backend ganhou neste lote (um anúncio que responde 200 com tudo vazio
 * contava como sucesso) e o `sem_url` separa «não há nada a extrair» de
 * «ainda não extraí» — um ícone de relógio numa visita criada à mão
 * dizia que o sistema estava a trabalhar quando não estava.
 */
export function estadoDaExtraccao(visita) {
  if (!texto(visita?.scraped_url)) return "sem_url";
  const estado = texto(visita?.scraper_status).toLowerCase();
  if (estado === "completed") return "ok";
  if (estado === "sem_dados") return "sem_dados";
  if (estado === "error") return "erro";
  return "pendente";
}

export function extraccaoEmCurso(quadro) {
  const normalizado = normalizarQuadro(quadro);
  return COLUNAS.some((coluna) =>
    normalizado[coluna].some((v) => estadoDaExtraccao(v) === "pendente")
  );
}

/**
 * Os dados do imóvel que a IA leu, prontos para a célula.
 *
 * Lê primeiro os campos de topo (`scraped_*`, que este lote criou) e cai
 * no `scraped_data` para os registos ANTERIORES — nada se migra, e uma
 * visita antiga não pode deixar de mostrar o que já tinha.
 */
export function dadosDaIA(visita) {
  const bruto = visita?.scraped_data || {};
  return {
    preco: visita?.scraped_price ?? bruto.price ?? null,
    tipologia: texto(visita?.scraped_typology || bruto.typology),
    area: visita?.scraped_area ?? bruto.area ?? null,
    estado: texto(visita?.scraped_estado || bruto.raw_data?.estado),
    localizacao: texto(
      visita?.property_address?.municipality || bruto.location
    ),
    fonte: texto(bruto.source),
  };
}

/**
 * Quem anuncia o imóvel: a agência e o comercial (LOTE 10).
 *
 * É a pergunta que o consultor faz primeiro — «a quem ligo para marcar a
 * partilha?» — e a resposta já existia no sistema e não chegava ao ecrã:
 * o prompt da IA pede estes campos pelo nome desde sempre, o
 * `property_scraper` já construía o `ConsultantInfo`, e um `grep` por
 * `consultant|agency|agente` neste ficheiro e na `VisitasTable` dava
 * **zero**. Terceira ocorrência da forma «a UI lê (ou não lê) um
 * contrato que o servidor já cumpre», depois do `under_35` e das notas
 * do consultor.
 *
 * Lê primeiro os campos de TOPO (criados neste lote) e cai no
 * `scraped_data.consultant` para os registos ANTERIORES: nada se migra, e
 * uma visita já extraída não pode deixar de mostrar o que tinha.
 *
 * **O directo e a central são campos SEPARADOS.** Juntá-los num só fazia
 * o consultor ligar à recepção da agência convencido de que falava com
 * quem vende o imóvel — e no ecrã os dois seriam indistinguíveis.
 */
export function contactoDoAnunciante(visita) {
  const consultor = visita?.scraped_data?.consultant || {};
  return {
    agencia: texto(visita?.agency_name || consultor.agency_name),
    nome: texto(visita?.agent_name || consultor.name),
    telefone: texto(visita?.agent_phone || consultor.phone),
    email: texto(visita?.agent_email || consultor.email),
    telefoneDaAgencia: texto(visita?.agency_phone),
    origem: texto(consultor.source_url),
  };
}

export function temContactoDoAnunciante(visita) {
  const contacto = contactoDoAnunciante(visita);
  return Boolean(
    contacto.agencia ||
      contacto.nome ||
      contacto.telefone ||
      contacto.email ||
      contacto.telefoneDaAgencia
  );
}

/**
 * O `href` para ligar, ou `null`.
 *
 * **Sem número não se desenha a ligação** — a regra do `rotaDaFicha` e do
 * `calendarioIdentidade`: um `tel:` vazio abre a aplicação do telefone
 * sem nada marcado, que é pior do que texto.
 *
 * O `+351` é acrescentado aqui e não guardado na base de dados: o campo
 * guarda o número nacional (é o que o backend normaliza) e o indicativo é
 * uma decisão de APRESENTAÇÃO — para o telemóvel do consultor marcar
 * mesmo quando está em roaming.
 */
export function ligacaoTelefonica(numero) {
  const limpo = texto(numero).replace(/[^\d+]/g, "");
  if (!limpo) return null;
  if (limpo.startsWith("+")) return `tel:${limpo}`;
  if (limpo.length !== 9) return null;
  return `tel:+351${limpo}`;
}

/** `912345678` → `912 345 678`. Só para LER; o valor guardado não muda. */
export function telefoneLegivel(numero) {
  const limpo = texto(numero).replace(/\D/g, "");
  if (limpo.length !== 9) return texto(numero);
  return `${limpo.slice(0, 3)} ${limpo.slice(3, 6)} ${limpo.slice(6)}`;
}

export function temDadosDaIA(visita) {
  const dados = dadosDaIA(visita);
  return Boolean(
    dados.preco !== null ||
      dados.tipologia ||
      dados.area !== null ||
      dados.estado ||
      dados.localizacao
  );
}

/**
 * A rota da ficha do cliente, ou `null`.
 *
 * Prefere o PROCESSO (documentação e timeline) e cai no cliente para quem
 * vive na Pool sem processo. **Quem recebe `null` não desenha a ligação:**
 * um link que não leva a lado nenhum é pior do que texto.
 *
 * É a mesma regra do `calendarioIdentidade`, e há um teste de
 * concordância entre as duas — duas cópias de uma regra de navegação
 * divergem, e a que divergir leva a um 404.
 */
export function rotaDaFicha(visita) {
  const processo = texto(visita?.process_id);
  if (processo) return `/processo/${encodeURIComponent(processo)}`;
  const cliente = texto(visita?.client_id);
  if (cliente) return `/cliente/${encodeURIComponent(cliente)}`;
  return null;
}

export function textoDaFicha(visita) {
  return texto(visita?.process_id) ? "Abrir processo" : "Abrir ficha do cliente";
}

/** O que a célula do imóvel mostra, por ordem de utilidade. */
export function tituloDoImovel(visita) {
  const titulo = texto(visita?.property_title) || texto(visita?.scraped_data?.title);
  if (titulo) return titulo;
  const url = texto(visita?.scraped_url);
  if (url) return url.replace(/^https?:\/\//, "").slice(0, 60);
  return "Imóvel sem título";
}

/**
 * As linhas da tabela, ordenadas por quem precisa de ACÇÃO primeiro.
 *
 * Um pedido do Portal sem agendamento é o que estorva o consultor; uma
 * visita concluída é histórico. Ordenar por data punha os pedidos (que não
 * têm data) no fim, onde ninguém os vê — e um pedido que ninguém vê é a
 * forma de defeito desta casa.
 */
const PESO_DA_COLUNA = {
  solicitadas: 0,
  agendadas: 1,
  concluidas: 2,
  canceladas: 3,
};

export function linhasDaTabela(quadro) {
  const normalizado = normalizarQuadro(quadro);
  const linhas = [];
  COLUNAS.forEach((coluna) => {
    normalizado[coluna].forEach((visita) => {
      linhas.push({ ...visita, _coluna: coluna });
    });
  });
  return linhas.sort((a, b) => {
    const peso = PESO_DA_COLUNA[a._coluna] - PESO_DA_COLUNA[b._coluna];
    if (peso !== 0) return peso;
    const da = texto(a.scheduled_date) || texto(a.created_at);
    const db = texto(b.scheduled_date) || texto(b.created_at);
    return da.localeCompare(db);
  });
}
