/**
 * Pesquisa avançada do Index — regras PURAS (Out 2026).
 *
 * O servidor é a autoridade (`GET /api/index/advanced-search`): aqui só se decide o que o ecrã pergunta,
 * como o URL guarda a pergunta e como se lê a resposta.
 *
 * REGRAS QUE NÃO SE PODEM PERDER
 *  * **Um filtro que não existe no tipo nem vai no pedido.** O servidor responde 422 a um `bank` num
 *    recibo; o ecrã nem o mostra, e ao mudar de tipo descarta o que deixou de se aplicar — senão um
 *    banco escrito num extrato seguia, escondido, para a pesquisa de recibos.
 *  * **A forma da resposta lê-se UMA vez.** `Array.isArray`, nunca `|| []` (um objecto é «truthy»).
 *  * **Nada pessoal no ecrã**: o servidor não manda o nome do cliente nem do ficheiro, e os rótulos
 *    daqui só usam o que veio (tipo, entidade, banco, período).
 *  * **O atalho «Ver documento» só existe com uma referência exacta** (`document_id`): sem ela não se
 *    desenha o botão — um botão que não leva a lado nenhum é pior do que não o ter.
 */
import { formatarDinheiro } from "./indexRevisao";

export const TIPO_POR_EMPREGO = "";

export const TIPOS_DE_DOCUMENTO = Object.freeze([
  { valor: TIPO_POR_EMPREGO, rotulo: "Por emprego (agregado)" },
  { valor: "recibo", rotulo: "Recibos de vencimento" },
  { valor: "declaracao_efetividade", rotulo: "Declarações de efetividade" },
  { valor: "extrato", rotulo: "Extratos bancários" },
]);

export const CONTRATOS = Object.freeze([
  { valor: "efetivo", rotulo: "Efetivo" },
  { valor: "termo_certo", rotulo: "Termo certo" },
  { valor: "termo_incerto", rotulo: "Termo incerto" },
  { valor: "outro", rotulo: "Outro" },
]);

/** Quais campos de filtro existem em cada tipo (a mesma tabela do servidor, `_FILTROS_POR_TIPO`). */
const CAMPOS_COMUNS_DA_ENTIDADE = ["employer_name", "employer_nif", "employer_location", "contract_type"];
const CAMPOS_POR_TIPO = Object.freeze({
  [TIPO_POR_EMPREGO]: [...CAMPOS_COMUNS_DA_ENTIDADE, "job_title", "min_salary", "max_salary", "period_from", "period_to"],
  recibo: [...CAMPOS_COMUNS_DA_ENTIDADE, "job_title", "min_salary", "max_salary", "period_from", "period_to"],
  declaracao_efetividade: [...CAMPOS_COMUNS_DA_ENTIDADE, "job_title", "period_from", "period_to"],
  extrato: ["bank", "period_from", "period_to"],
});

export const FILTROS_VAZIOS = Object.freeze({
  document_type: TIPO_POR_EMPREGO,
  employer_name: "",
  employer_nif: "",
  employer_location: "",
  job_title: "",
  bank: "",
  min_salary: "",
  max_salary: "",
  period_from: "",
  period_to: "",
  contract_type: [],
});

export function camposDoTipo(tipo) {
  return CAMPOS_POR_TIPO[tipo] || CAMPOS_POR_TIPO[TIPO_POR_EMPREGO];
}

export function tipoValido(tipo) {
  return TIPOS_DE_DOCUMENTO.some((t) => t.valor === tipo) ? tipo : TIPO_POR_EMPREGO;
}

/** Os filtros do formulário, completos e com a forma certa (um valor desconhecido cai na omissão). */
export function normalizarFiltros(filtros) {
  const f = filtros && typeof filtros === "object" ? filtros : {};
  const saida = { ...FILTROS_VAZIOS, document_type: tipoValido(f.document_type) };
  for (const chave of Object.keys(FILTROS_VAZIOS)) {
    if (chave === "document_type" || chave === "contract_type") continue;
    saida[chave] = typeof f[chave] === "string" ? f[chave] : typeof f[chave] === "number" ? String(f[chave]) : "";
  }
  const validos = new Set(CONTRATOS.map((c) => c.valor));
  saida.contract_type = Array.isArray(f.contract_type) ? f.contract_type.filter((c) => validos.has(c)) : [];
  return saida;
}

/** Um número escrito à portuguesa («1.234,56» ou «1234,56») ou à inglesa; `null` se não for um número. */
export function numeroDoTexto(texto) {
  const t = String(texto ?? "").trim().replace(/\s/g, "");
  if (!t) return null;
  const normal = /,/.test(t) ? t.replace(/\./g, "").replace(",", ".") : t;
  if (!/^\d+(\.\d+)?$/.test(normal)) return NaN;
  return Number(normal);
}

const PERIODO = /^\d{4}-(0[1-9]|1[0-2])$/;

/** Os erros que o servidor também daria (422), para os dizer antes do pedido. `{campo: mensagem}`. */
export function validarFiltros(filtros) {
  const f = normalizarFiltros(filtros);
  const visiveis = new Set(camposDoTipo(f.document_type));
  const erros = {};
  const min = numeroDoTexto(f.min_salary);
  const max = numeroDoTexto(f.max_salary);
  if (visiveis.has("min_salary") && Number.isNaN(min)) erros.min_salary = "Valor inválido";
  if (visiveis.has("max_salary") && Number.isNaN(max)) erros.max_salary = "Valor inválido";
  if (!erros.min_salary && !erros.max_salary && min !== null && max !== null && min > max) {
    erros.max_salary = "O máximo não pode ser inferior ao mínimo";
  }
  for (const campo of ["period_from", "period_to"]) {
    if (visiveis.has(campo) && f[campo] && !PERIODO.test(f[campo])) erros[campo] = "Use AAAA-MM";
  }
  if (!erros.period_to && f.period_from && f.period_to && PERIODO.test(f.period_from) && PERIODO.test(f.period_to) && f.period_from > f.period_to) {
    erros.period_to = "O fim não pode ser anterior ao início";
  }
  for (const campo of ["employer_name", "employer_location", "job_title", "bank"]) {
    const t = f[campo].trim();
    if (visiveis.has(campo) && t && t.length < 2) erros[campo] = "Pelo menos 2 caracteres";
  }
  if (visiveis.has("employer_nif") && f.employer_nif.trim()) {
    if (f.employer_nif.replace(/\D/g, "").length < 3) erros.employer_nif = "Pelo menos 3 dígitos";
  }
  return erros;
}

/** Os parâmetros do pedido: só os campos do tipo, aparados, e o valor numérico como número. */
export function filtrosParaPedido(filtros, { pagina = 1, tamanho = 25 } = {}) {
  const f = normalizarFiltros(filtros);
  const pedido = {};
  if (f.document_type) pedido.document_type = f.document_type;
  for (const campo of camposDoTipo(f.document_type)) {
    const valor = f[campo];
    if (campo === "contract_type") {
      if (valor.length) pedido.contract_type = [...valor];
    } else if (campo === "min_salary" || campo === "max_salary") {
      const n = numeroDoTexto(valor);
      if (n !== null && !Number.isNaN(n)) pedido[campo] = n; // o zero é um valor
    } else if (valor.trim()) {
      pedido[campo] = valor.trim();
    }
  }
  if (pagina > 1) pedido.page = pagina;
  pedido.size = tamanho;
  return pedido;
}

// ---------------------------------------------------------------------------
// O URL (a pergunta sobrevive a «abrir um processo e voltar»)
// ---------------------------------------------------------------------------
const PREFIXO = "ps_";
/** «Já se pesquisou» — uma pesquisa SEM filtros (listar tudo) também é uma pesquisa e tem de sobreviver ao URL. */
export const MARCA_DE_PESQUISA = `${PREFIXO}go`;
const CHAVES_DO_URL = Object.freeze({
  document_type: "tipo",
  employer_name: "ent",
  employer_nif: "nif",
  employer_location: "loc",
  job_title: "cargo",
  bank: "banco",
  min_salary: "min",
  max_salary: "max",
  period_from: "de",
  period_to: "ate",
  contract_type: "contrato",
});

/** `URLSearchParams` → filtros (um parâmetro escrito à mão e ilegível cai na omissão). */
export function filtrosDoUrl(parametros) {
  const bruto = {};
  for (const [campo, chave] of Object.entries(CHAVES_DO_URL)) {
    const v = parametros.get(PREFIXO + chave);
    if (v === null) continue;
    bruto[campo] = campo === "contract_type" ? v.split(",").filter(Boolean) : v;
  }
  return normalizarFiltros(bruto);
}

export function paginaDoUrl(parametros) {
  const n = Number(parametros.get(`${PREFIXO}p`));
  return Number.isInteger(n) && n >= 1 ? n : 1;
}

/** Escreve os filtros e a página num `URLSearchParams` novo (não pisa os parâmetros que não são nossos). */
export function filtrosParaUrl(anterior, filtros, pagina = 1) {
  const seguinte = new URLSearchParams(anterior);
  for (const chave of [...seguinte.keys()]) if (chave.startsWith(PREFIXO)) seguinte.delete(chave);
  const f = normalizarFiltros(filtros);
  for (const campo of ["document_type", ...camposDoTipo(f.document_type)]) {
    const valor = f[campo];
    const texto = Array.isArray(valor) ? valor.join(",") : String(valor).trim();
    if (texto) seguinte.set(PREFIXO + CHAVES_DO_URL[campo], texto);
  }
  seguinte.set(MARCA_DE_PESQUISA, "1");
  if (pagina > 1) seguinte.set(`${PREFIXO}p`, String(pagina));
  return seguinte;
}

/** Já há uma pergunta no URL? (sem ela a página espera que se pesquise) */
export function haPesquisaNoUrl(parametros) {
  return parametros.has(MARCA_DE_PESQUISA);
}

// ---------------------------------------------------------------------------
// A resposta
// ---------------------------------------------------------------------------
export function normalizarResultado(dados) {
  const d = dados && typeof dados === "object" ? dados : {};
  const itens = Array.isArray(d.items) ? d.items.filter((i) => i && typeof i === "object") : [];
  return {
    vista: d.view === "documents" ? "documents" : "jobs",
    itens,
    total: Number.isFinite(d.total) ? d.total : itens.length,
    pagina: Number.isInteger(d.page) && d.page >= 1 ? d.page : 1,
    tamanho: Number.isInteger(d.size) && d.size >= 1 ? d.size : itens.length || 25,
  };
}

const ROTULO_DO_TIPO = Object.freeze({
  recibo: "Recibo",
  declaracao_efetividade: "Declaração de efetividade",
  extrato: "Extrato",
});

export function rotuloDoTipo(tipo) {
  return ROTULO_DO_TIPO[tipo] || "Documento";
}

export function rotuloDoContrato(valor) {
  return CONTRATOS.find((c) => c.valor === valor)?.rotulo ?? (valor || "—");
}

/** Só o que veio: «Extrato · Caixa Geral de Depósitos · 2026-09». Nunca o nome do cliente nem do ficheiro. */
export function rotuloDoDocumento(item) {
  if (!item || typeof item !== "object") return "Documento";
  const partes = [rotuloDoTipo(item.document_type)];
  if (item.document_type === "extrato" && item.bank) partes.push(item.bank);
  else if (item.employer?.name) partes.push(item.employer.name);
  if (item.period) partes.push(item.period);
  return partes.join(" · ");
}

/**
 * Os documentos a que o atalho «Ver documento» leva para esta linha — `[{id, rotulo}]`, vazio se não há
 * referência. Na vista por documento é UM (o que fez match); por emprego são os que o sustentam.
 */
export function documentosDoResultado(item, vista) {
  if (!item || typeof item !== "object") return [];
  // o arquivo histórico guarda os DADOS, não o ficheiro: não há nada a abrir nem a descarregar
  if (item.historical === true) return [];
  if (vista === "documents") {
    return typeof item.document_id === "string" && item.document_id ? [{ id: item.document_id, rotulo: rotuloDoDocumento(item) }] : [];
  }
  const ids = Array.isArray(item.document_ids) ? item.document_ids.filter((d) => typeof d === "string" && d) : [];
  const entidade = item.employer?.name ? ` · ${item.employer.name}` : "";
  return ids.map((id, i) => ({ id, rotulo: `Documento ${i + 1} de ${ids.length}${entidade}` }));
}

export function valorEmEuros(valor) {
  return formatarDinheiro(valor);
}

/** Admissão em `DD/MM/AAAA` (a data vem `AAAA-MM-DD`); `—` quando não há. */
export function dataDeAdmissao(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(typeof iso === "string" ? iso : "");
  return m ? `${m[3]}/${m[2]}/${m[1]}` : "—";
}

/** Chave estável da consulta: dois objectos iguais não podem dar duas caches. */
export function chaveDaPesquisa(pedido) {
  return JSON.stringify(
    Object.keys(pedido)
      .sort()
      .map((k) => [k, pedido[k]]),
  );
}
