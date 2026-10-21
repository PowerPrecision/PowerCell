/**
 * Regras PURAS do «Log da IA» do processo (separador na página de detalhes).
 *
 * O servidor devolve cada acção já com `motivo_mensagem` (texto em português, a partir de um
 * código fechado) — o ecrã nunca mostra o texto cru de uma excepção, e este módulo também não o
 * inventa: se a mensagem faltar, usa uma frase genérica em vez de mostrar o código.
 */

export const ESTADOS = ["sucesso", "falha", "saltado"];

const ROTULOS_DO_ESTADO = {
  sucesso: "Sucesso",
  falha: "Falhou",
  saltado: "Não executada",
};

/** Filtros do separador (o primeiro é «sem filtro»). */
export const FILTROS = [
  { valor: "", rotulo: "Todas" },
  { valor: "sucesso", rotulo: "Sucesso" },
  { valor: "falha", rotulo: "Falhas" },
  { valor: "saltado", rotulo: "Não executadas" },
];

/** As acções cujo documento se pode voltar a analisar pelo botão «Reanalisar». */
const ACCOES_REANALISAVEIS = ["categorizar", "rever"];

export function rotuloDoEstado(estado) {
  return ROTULOS_DO_ESTADO[estado] || "—";
}

/**
 * Frase da linha da timeline: «<Acção> — <ficheiro>». O que a IA concluiu vem a seguir
 * (categoria e confiança), só quando a acção correu.
 */
export function tituloDaLinha(linha) {
  const accao = linha?.accao_rotulo || "Acção da IA";
  return linha?.ficheiro ? `${accao} — ${linha.ficheiro}` : accao;
}

/** «Identificação · 93 %» ou «Identificação». Vazio quando não há categoria. */
export function conclusaoDaLinha(linha) {
  if (linha?.estado !== "sucesso" || !linha?.categoria) return "";
  const confianca = linha.confianca;
  if (typeof confianca === "number" && Number.isFinite(confianca)) {
    // O servidor guarda 0–1; um valor já em 0–100 (legado) não se multiplica outra vez.
    const pct = Math.round(confianca <= 1 ? confianca * 100 : confianca);
    return `${linha.categoria} · ${pct} %`;
  }
  return linha.categoria;
}

/**
 * O que explica o estado: a mensagem do servidor. Uma falha sem mensagem nunca fica muda.
 * Um sucesso só tem nota quando o servidor a mandou (ex.: «só foi possível usar o nome»).
 */
export function notaDaLinha(linha) {
  if (linha?.motivo_mensagem) return linha.motivo_mensagem;
  if (linha?.estado === "falha") return "A IA não conseguiu analisar este documento.";
  return "";
}

/** Quem despoletou: «Automático (Portal)» ou «Manual — Diana». */
export function gatilhoDaLinha(linha) {
  if (linha?.gatilho === "manual") {
    return linha.utilizador_nome ? `Manual — ${linha.utilizador_nome}` : "Manual";
  }
  const origens = { portal: "Portal do cliente", parceiro: "Parceiro", staff: "Upload da equipa" };
  const origem = origens[linha?.origem];
  return origem ? `Automático (${origem})` : "Automático";
}

/** A linha tem um documento a que se pode voltar a aplicar a IA? */
export function linhaPodeSerReanalisada(linha) {
  return Boolean(linha?.documento_id) && ACCOES_REANALISAVEIS.includes(linha?.accao);
}

/**
 * Data legível em pt-PT (hora de Lisboa). Texto inválido devolve «—» em vez de «Invalid Date».
 */
export function formatarQuando(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("pt-PT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Lisbon",
  });
}

/**
 * A página do log tem forma de OBJECTO `{items, total, page, size, pode_reanalisar}`.
 * `Array.isArray`, nunca `|| []` (um objecto é truthy).
 */
export function normalizarPagina(dados) {
  const items = Array.isArray(dados?.items) ? dados.items : [];
  const total = Number.isFinite(dados?.total) ? dados.total : items.length;
  const size = Number.isFinite(dados?.size) && dados.size > 0 ? dados.size : 30;
  const page = Number.isFinite(dados?.page) && dados.page > 0 ? dados.page : 1;
  return {
    items,
    total,
    page,
    size,
    paginas: Math.max(1, Math.ceil(total / size)),
    podeReanalisar: dados?.pode_reanalisar === true,
  };
}

/**
 * Mensagem do resultado de uma reanálise (a resposta de `ai-analyze-review`).
 * @returns {{tipo: "sucesso"|"info"|"erro", texto: string}}
 */
export function mensagemDaReanalise(resposta) {
  if (!resposta || resposta.success !== true) {
    return { tipo: "erro", texto: "A reanálise falhou. O motivo ficou registado no Log da IA." };
  }
  const pct = Number.isFinite(resposta.confidence_score) ? ` (confiança ${resposta.confidence_score} %)` : "";
  if (resposta.auto_approved) {
    return { tipo: "sucesso", texto: `Documento reanalisado e atualizado automaticamente${pct}.` };
  }
  return {
    tipo: "info",
    texto: `Documento reanalisado${pct}. As sugestões aguardam a sua revisão no separador Documentos.`,
  };
}
