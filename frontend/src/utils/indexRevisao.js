/**
 * indexRevisao — regras PURAS do ecrã do Index (Lote 12, Fase 4).
 *
 * O ecrã não decide nada de negócio: o servidor diz o estado, os campos a rever e os alertas.
 * Aqui vivem só as regras de apresentação e de montagem de pedidos, para serem testáveis sem
 * montar uma página.
 *
 * REGRAS QUE NÃO SE PODEM PERDER
 *  * «Marcar como Indexado» NUNCA é bloqueado pela IA, por campos em falta nem por alertas
 *    (decisão da direcção): `podeMarcarComoIndexado` só olha para o estado do PRÓPRIO pedido
 *    e para o estado do processo — nunca para o conteúdo da análise.
 *  * Uma lista do servidor normaliza-se UMA vez com `Array.isArray`, nunca com `|| []`.
 *  * O pedido de edição só leva o que MUDOU: reenviar o que a pessoa não tocou repunha, por
 *    cima de uma reanálise, o valor antigo (a lição do `construirPayload` do perfil do Portal).
 */

export const SEPARADORES = Object.freeze([
  { valor: "pending", rotulo: "Fila de Espera" },
  { valor: "reviews", rotulo: "Revisões Pendentes" },
]);

export const SEPARADOR_OMISSAO = "pending";

/** Um separador desconhecido (URL escrito à mão) cai no por omissão — nunca num ecrã vazio. */
export function separadorValido(valor) {
  return SEPARADORES.some((s) => s.valor === valor) ? valor : SEPARADOR_OMISSAO;
}

export const ROTULO_DO_ESTADO = Object.freeze({
  pending: "Por indexar",
  in_review: "Em tratamento",
  indexed: "Indexado",
});

export function rotuloDoEstado(estado, dispensado = false) {
  if (estado === "indexed" && dispensado) return "Indexado (dispensado)";
  return ROTULO_DO_ESTADO[estado] || "Por indexar";
}

export const CAMPOS_DO_TRABALHO = Object.freeze([
  { chave: "employer_name", rotulo: "Entidade patronal", tipo: "texto" },
  { chave: "employer_nif", rotulo: "NIF da entidade", tipo: "nif" },
  { chave: "job_title", rotulo: "Cargo", tipo: "texto" },
  { chave: "net_salary", rotulo: "Vencimento líquido", tipo: "dinheiro" },
  { chave: "contract_type", rotulo: "Tipo de contrato", tipo: "contrato" },
]);

export const TIPOS_DE_CONTRATO = Object.freeze([
  { valor: "efetivo", rotulo: "Efetivo" },
  { valor: "termo_certo", rotulo: "Termo certo" },
  { valor: "termo_incerto", rotulo: "Termo incerto" },
  { valor: "outro", rotulo: "Outro" },
]);

export function listaDoServidor(valor) {
  return Array.isArray(valor) ? valor : [];
}

/** O valor de um campo revisável, ou `null`. */
export function valorDoCampo(campo) {
  const v = campo && typeof campo === "object" ? campo.value : null;
  return v === undefined || v === "" ? null : v;
}

export function campoPrecisaDeRevisao(campo) {
  return Boolean(campo && typeof campo === "object" && campo.needs_review === true);
}

/** Os nomes dos campos do trabalho que ainda pedem revisão. */
export function camposARever(trabalho) {
  if (!trabalho || typeof trabalho !== "object") return [];
  return CAMPOS_DO_TRABALHO.filter((c) => campoPrecisaDeRevisao(trabalho[c.chave])).map((c) => c.chave);
}

export function totalDeCamposARever(trabalhos) {
  return listaDoServidor(trabalhos).reduce((n, t) => n + camposARever(t).length, 0);
}

/** `1234.5` → «1 234,50 €». Valor ausente → «—». Zero é um valor. */
export function formatarDinheiro(valor) {
  if (valor === null || valor === undefined || valor === "") return "—";
  const n = Number(valor);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("pt-PT", { style: "currency", currency: "EUR" }).format(n);
}

/** Só dígitos (o servidor valida o dígito de controlo; aqui só se tira a pontuação). */
export function normalizarNif(texto) {
  return String(texto ?? "").replace(/\D/g, "");
}

/** Um NIF «com cara de NIF» (9 dígitos). Dica de apresentação — a decisão é do servidor. */
export function nifTemForma(texto) {
  return /^\d{9}$/.test(normalizarNif(texto));
}

/** O texto que o `<input>` mostra para um campo (estado em TEXTO: um número no input faz reaparecer o `0`). */
export function textoInicialDoCampo(campo) {
  const v = valorDoCampo(campo);
  return v === null ? "" : String(v);
}

export function formularioDoTrabalho(trabalho) {
  const forma = {};
  for (const { chave } of CAMPOS_DO_TRABALHO) forma[chave] = textoInicialDoCampo(trabalho?.[chave]);
  return forma;
}

/**
 * O que enviar ao guardar: só os campos cujo texto MUDOU face ao que o servidor devolveu.
 * Texto vazio → `null` (a pessoa apagou de propósito, o servidor conta-o como revisto).
 */
export function edicoesDoTrabalho(trabalho, formulario) {
  const base = formularioDoTrabalho(trabalho);
  const saida = {};
  for (const { chave } of CAMPOS_DO_TRABALHO) {
    const atual = String(formulario?.[chave] ?? "").trim();
    if (atual === base[chave].trim()) continue;
    saida[chave] = atual === "" ? null : atual;
  }
  return saida;
}

/**
 * «Confirmar» um campo que a IA propôs e a pessoa aceita como está: o servidor só marca como
 * revisto um campo que lhe chega numa edição, por isso confirmar reenvia o valor actual.
 */
export function edicoesDeConfirmacao(trabalho, chaves) {
  const saida = {};
  for (const chave of listaDoServidor(chaves)) {
    const v = valorDoCampo(trabalho?.[chave]);
    saida[chave] = v === null ? null : String(v);
  }
  return saida;
}

/** Os trabalhos cujo NIF falta ou está em dúvida: é o que o diálogo de «Marcar como Indexado» pergunta. */
export function trabalhosSemNifConfirmado(trabalhos) {
  return listaDoServidor(trabalhos).filter((t) => {
    const nif = t?.employer_nif;
    return valorDoCampo(nif) === null || (campoPrecisaDeRevisao(nif) && nif.edited_by_human !== true);
  });
}

/** Do formulário do diálogo para o corpo do pedido: só NIFs com forma de NIF, com o `job_id`. */
export function empregadoresParaMarcar(respostas) {
  return Object.entries(respostas || {})
    .filter(([, nif]) => nifTemForma(nif))
    .map(([job_id, nif]) => ({ job_id, nif: normalizarNif(nif) }));
}

/**
 * Pode carregar em «Marcar como Indexado»?
 * Só o PRÓPRIO pedido a decorrer e o processo já indexado o impedem — NUNCA a análise, os
 * campos em dúvida ou os alertas (nada do módulo Index bloqueia a indexação).
 */
export function podeMarcarComoIndexado({ processo, aMarcar }) {
  if (aMarcar) return false;
  if (!processo) return false;
  return processo.index_status !== "indexed";
}

export const SEVERIDADES = Object.freeze({
  alerta: { rotulo: "Alerta", ordem: 0 },
  aviso: { rotulo: "Aviso", ordem: 1 },
  info: { rotulo: "Informação", ordem: 2 },
});

export function rotuloDaSeveridade(severidade) {
  return (SEVERIDADES[severidade] || SEVERIDADES.info).rotulo;
}

/** Alertas abertos primeiro, do mais grave para o menos; os dispensados no fim. */
export function ordenarAlertas(alertas) {
  return [...listaDoServidor(alertas)].sort((a, b) => {
    if (Boolean(a.dismissed) !== Boolean(b.dismissed)) return a.dismissed ? 1 : -1;
    const oa = (SEVERIDADES[a.severity] || SEVERIDADES.info).ordem;
    const ob = (SEVERIDADES[b.severity] || SEVERIDADES.info).ordem;
    return oa - ob;
  });
}

export function alertasAbertos(alertas) {
  return listaDoServidor(alertas).filter((a) => !a.dismissed);
}

/** A mensagem de uma recusa do servidor, sem nunca mostrar o texto cru de uma excepção. */
export function mensagemDeErro(erro, omissao = "Não foi possível concluir o pedido.") {
  const detalhe = erro?.response?.data?.detail;
  if (typeof detalhe === "string" && detalhe.trim()) return detalhe;
  return omissao;
}

/** O resumo de um job concluído, só números (o servidor nunca manda nomes nem valores). */
export function resumoDaAnalise(resultado) {
  if (!resultado || typeof resultado !== "object") return "";
  const partes = [];
  if (resultado.analisados) partes.push(`${resultado.analisados} analisado(s)`);
  if (resultado.saltados) partes.push(`${resultado.saltados} já analisado(s)`);
  if (resultado.falhas) partes.push(`${resultado.falhas} com falha`);
  if (resultado.alertas) partes.push(`${resultado.alertas} alerta(s)`);
  if (resultado.campos_a_rever) partes.push(`${resultado.campos_a_rever} campo(s) a rever`);
  return partes.join("; ");
}

/** Um evento `task_*` é de um job do Index deste processo? */
export function eventoDoIndex(payload, processId) {
  if (!payload || typeof payload !== "object") return false;
  if (!String(payload.task_type || "").startsWith("INDEX_")) return false;
  return !processId || payload.process_id === processId;
}

export const TIPO_DE_ANALISE_ROTULO = Object.freeze({
  recibo_vencimento: "Recibo de vencimento",
  extrato_bancario: "Extrato bancário",
  declaracao_efetividade: "Declaração de efetividade",
  identificacao: "Identificação",
});

export function rotuloDoTipoDeAnalise(tipo) {
  return TIPO_DE_ANALISE_ROTULO[tipo] || null;
}

// ====================================================================
// ORDENAÇÃO E FILTROS DA FILA (Out 2026) — iguais às listas fechadas do servidor (`index_queue_query`)
// ====================================================================
/** Ordem por omissão de cada aba: o que o ecrã mostrava antes de haver ordenação. */
export const ORDENACAO_POR_OMISSAO = Object.freeze({ pending: "created_asc", reviews: "indexed_desc" });

const ROTULOS_DA_ORDENACAO = Object.freeze({
  created: ["Entrada · mais antigos primeiro", "Entrada · mais recentes primeiro"],
  indexed: ["Indexado em · mais antigos primeiro", "Indexado em · mais recentes primeiro"],
  client: ["Cliente · A → Z", "Cliente · Z → A"],
  number: ["Nº do processo · crescente", "Nº do processo · decrescente"],
  company: ["Empresa · A → Z", "Empresa · Z → A"],
  status: ["Estado · A → Z", "Estado · Z → A"],
  alerts: ["Alertas · menos primeiro", "Alertas · mais primeiro"],
});

/** `indexed` só existe nas Revisões (os processos por indexar não têm data de indexação). */
function camposDaAba(aba) {
  const comuns = ["client", "number", "company", "status", "alerts"];
  return aba === "reviews" ? ["indexed", ...comuns] : ["created", ...comuns];
}

/** As opções do seletor «Ordenar por»: `[{valor: "client_asc", rotulo}]`. */
export function opcoesDeOrdenacao(aba) {
  return camposDaAba(aba).flatMap((campo) => [
    { valor: `${campo}_asc`, rotulo: ROTULOS_DA_ORDENACAO[campo][0] },
    { valor: `${campo}_desc`, rotulo: ROTULOS_DA_ORDENACAO[campo][1] },
  ]);
}

/** Uma ordem que a aba não aceita (URL escrito à mão, aba trocada) cai na por omissão — nunca num 422. */
export function ordenacaoValida(aba, valor) {
  const omissao = ORDENACAO_POR_OMISSAO[aba] || ORDENACAO_POR_OMISSAO.pending;
  return opcoesDeOrdenacao(aba).some((o) => o.valor === valor) ? valor : omissao;
}

/** A coluna → o campo de ordenação (a coluna da data muda de campo com a aba). */
export function campoDaColuna(aba, coluna) {
  if (coluna === "data") return aba === "reviews" ? "indexed" : "created";
  return { processo: "client", empresa: "company", estado: "status", alertas: "alerts" }[coluna] || null;
}

/** `aria-sort` de uma coluna, dada a ordem em vigor. */
export function sentidoDaColuna(aba, ordem, coluna) {
  const campo = campoDaColuna(aba, coluna);
  const [atual, sentido] = String(ordem || "").split("_");
  if (!campo || atual !== campo) return "none";
  return sentido === "desc" ? "descending" : "ascending";
}

/**
 * A ordem a pedir quando se carrega no cabeçalho de uma coluna: noutra coluna começa pelo sentido natural
 * (alertas: os mais primeiro; datas e texto: ascendente), na mesma coluna inverte.
 */
export function proximaOrdenacao(aba, ordem, coluna) {
  const campo = campoDaColuna(aba, coluna);
  if (!campo) return ordenacaoValida(aba, ordem);
  const [atual, sentido] = String(ordem || "").split("_");
  if (atual === campo) return `${campo}_${sentido === "asc" ? "desc" : "asc"}`;
  return `${campo}_${campo === "alerts" ? "desc" : "asc"}`;
}

/** Estados que cada aba pode ter (o servidor recusa os outros com 422). */
export const ESTADOS_DA_ABA = Object.freeze({ pending: ["pending", "in_review"], reviews: ["indexed"] });
export const ORIGENS_DA_FILA = Object.freeze([
  { valor: "own", rotulo: "Da minha rede" },
  { valor: "shared", rotulo: "Partilhados por outra" },
]);

/** Os filtros do URL, saneados para a aba: o que a aba não aceita desaparece (nunca vai ao servidor). */
export function filtrosDaFila(aba, { estado = "", empresa = "", origem = "" } = {}) {
  return {
    estado: (ESTADOS_DA_ABA[aba] || []).includes(estado) ? estado : "",
    empresa: typeof empresa === "string" ? empresa.trim().slice(0, 64) : "",
    origem: ORIGENS_DA_FILA.some((o) => o.valor === origem) ? origem : "",
  };
}

/** Quantos filtros estão ligados (a ordem não conta: não esconde linhas). */
export function totalDeFiltrosLigados(filtros) {
  return ["estado", "empresa", "origem"].filter((k) => Boolean(filtros?.[k])).length;
}

/**
 * Os parâmetros do pedido da fila. Só leva o que se afasta da omissão (`sort_by` por omissão é o do servidor):
 * um URL limpo é o estado limpo.
 */
export function parametrosDaFila({ tab, page, q, ordem, filtros }) {
  const params = { tab, page, q: q || undefined };
  if (ordem && ordem !== ORDENACAO_POR_OMISSAO[tab]) params.sort_by = ordem;
  if (filtros?.estado) params.index_status = filtros.estado;
  if (filtros?.empresa) params.company_id = filtros.empresa;
  if (filtros?.origem) params.origin = filtros.origem;
  return params;
}

/** A fila do servidor, com a forma garantida. `total` e `itens` derivam do que chegou. */
export function normalizarFila(dados) {
  const itens = listaDoServidor(dados?.items);
  const total = Number.isFinite(Number(dados?.total)) ? Number(dados.total) : itens.length;
  const empresas = listaDoServidor(dados?.facets?.companies)
    .filter((e) => e && typeof e.id === "string" && e.id)
    .map((e) => ({ id: e.id, nome: e.name || e.id, total: Number(e.count) || 0 }));
  return {
    itens,
    total,
    pagina: Number(dados?.page) || 1,
    tamanho: Number(dados?.size) || itens.length,
    empresas,
  };
}

/** A bancada do servidor, com a forma garantida (listas `Array.isArray`, objectos com recuo). */
export function normalizarBancada(dados) {
  const meta = dados?.professional_metadata;
  const jobs = dados?.active_jobs && typeof dados.active_jobs === "object" ? dados.active_jobs : {};
  return {
    processo: dados?.process && typeof dados.process === "object" ? dados.process : null,
    ficheiros: listaDoServidor(dados?.files),
    trabalhos: listaDoServidor(meta?.jobs),
    temRevisaoPendente: meta?.has_pending_review === true,
    alertas: listaDoServidor(dados?.alerts),
    jobsActivos: {
      analysis: jobs.analysis || null,
      finalize: jobs.finalize || null,
      sanitize: jobs.sanitize || null,
    },
  };
}

/** Há algum job do Index a correr neste processo? */
export function haJobActivo(jobsActivos) {
  return Boolean(jobsActivos && (jobsActivos.analysis || jobsActivos.finalize || jobsActivos.sanitize));
}

/** O ficheiro foi carregado pelo Index e ainda não tem PDF limpo? (é o que «Apagar metadados» trata.) */
export function ficheiroPorLimpar(ficheiro) {
  if (!ficheiro || ficheiro.is_clean_pdf) return false;
  const estado = ficheiro.file_state || "original";
  return ficheiro.uploaded_by_index === true && estado === "original" && !ficheiro.has_clean_pdf;
}

export function quantosPorLimpar(ficheiros) {
  return listaDoServidor(ficheiros).filter(ficheiroPorLimpar).length;
}

/** «dd/mm/aaaa» de uma data ISO, ou `null` se não for uma data. */
export function dataCurta(iso) {
  const d = new Date(iso);
  if (!iso || Number.isNaN(d.getTime())) return null;
  return new Intl.DateTimeFormat("pt-PT", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(d);
}

/**
 * O estado do ficheiro em palavras para o ecrã (ou `null` quando não há nada a dizer).
 * Um original com PDF limpo diz QUANDO deixa de existir: a margem de segurança tem de ser visível.
 */
export function estadoDoFicheiroEmTexto(ficheiro) {
  if (!ficheiro) return null;
  if (ficheiro.is_clean_pdf) return "PDF limpo (sem metadados)";
  if (ficheiro.file_state === "sanitizado") {
    const quando = dataCurta(ficheiro.purge_after);
    return quando ? `Tem PDF limpo — o original é eliminado a partir de ${quando}` : "Tem PDF limpo";
  }
  return null;
}
