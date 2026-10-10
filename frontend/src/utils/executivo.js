/**
 * Dashboard Executivo e Relatório Semanal — regras puras (Bloco 4, pontos 13 e 16).
 *
 * O servidor é a autoridade dos números e do âmbito (rede); isto só traduz
 * filtros em parâmetros, valida o intervalo antes de o enviar e formata.
 * Todas as datas são `AAAA-MM-DD` em UTC, como no servidor: um `toISOString()`
 * numa máquina em UTC+1 devolveria o dia anterior depois da meia-noite.
 */

export const ROTULOS_DOS_PAPEIS = {
  consultor: "Consultor",
  intermediario: "Intermediário",
  administrativo: "Administrativo",
  diretor: "Diretor",
  ceo: "CEO",
};

/**
 * Perfis filtráveis. `master`, `admin` e `indexacao` NÃO existem aqui: o
 * relatório não os inclui (contas de gestão e perfil sem registo) — o servidor
 * é a autoridade, isto só evita oferecer um filtro que devolve sempre vazio.
 */
export const PAPEIS_FILTRAVEIS = Object.keys(ROTULOS_DOS_PAPEIS);

export const MAX_DIAS = 366;

export const PREDEFINICOES = [
  { chave: "this_week", rotulo: "Esta semana" },
  { chave: "last_week", rotulo: "Semana passada" },
  { chave: "this_month", rotulo: "Este mês" },
  { chave: "last_month", rotulo: "Mês passado" },
  { chave: "7d", rotulo: "Últimos 7 dias" },
  { chave: "14d", rotulo: "Últimos 14 dias" },
  { chave: "30d", rotulo: "Últimos 30 dias" },
  { chave: "90d", rotulo: "Últimos 90 dias" },
  { chave: "custom", rotulo: "Intervalo personalizado" },
];

const MS_POR_DIA = 86_400_000;

function paraTexto(data) {
  return data.toISOString().slice(0, 10);
}

/** Lê `AAAA-MM-DD` como data UTC; `null` se não for uma data real. */
export function lerData(texto) {
  if (typeof texto !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(texto)) return null;
  const data = new Date(`${texto}T00:00:00Z`);
  return Number.isNaN(data.getTime()) || paraTexto(data) !== texto ? null : data;
}

function somarDias(data, dias) {
  return new Date(data.getTime() + dias * MS_POR_DIA);
}

/** Segunda-feira da semana (ISO) que contém a data. */
export function segundaDaSemana(data) {
  const dia = (data.getUTCDay() + 6) % 7; // segunda = 0
  return somarDias(data, -dia);
}

/**
 * Intervalo de uma predefinição, relativo a `hoje` (injectável nos testes).
 * @returns {{inicio: string, fim: string}|null} `null` para `custom`/desconhecida.
 */
export function intervaloDaPredefinicao(chave, hoje = new Date()) {
  const h = new Date(`${paraTexto(hoje)}T00:00:00Z`);
  switch (chave) {
    case "this_week":
      return { inicio: paraTexto(segundaDaSemana(h)), fim: paraTexto(h) };
    case "last_week": {
      const segunda = segundaDaSemana(somarDias(h, -7));
      return { inicio: paraTexto(segunda), fim: paraTexto(somarDias(segunda, 6)) };
    }
    case "this_month":
      return { inicio: paraTexto(new Date(Date.UTC(h.getUTCFullYear(), h.getUTCMonth(), 1))), fim: paraTexto(h) };
    case "last_month": {
      const inicio = new Date(Date.UTC(h.getUTCFullYear(), h.getUTCMonth() - 1, 1));
      const fim = new Date(Date.UTC(h.getUTCFullYear(), h.getUTCMonth(), 0));
      return { inicio: paraTexto(inicio), fim: paraTexto(fim) };
    }
    case "7d": return { inicio: paraTexto(somarDias(h, -6)), fim: paraTexto(h) };
    case "14d": return { inicio: paraTexto(somarDias(h, -13)), fim: paraTexto(h) };
    case "30d": return { inicio: paraTexto(somarDias(h, -29)), fim: paraTexto(h) };
    case "90d": return { inicio: paraTexto(somarDias(h, -89)), fim: paraTexto(h) };
    default: return null;
  }
}

/**
 * Valida o intervalo ANTES de pedir ao servidor (que também o valida).
 * @returns {string|null} A mensagem do problema, ou `null` se estiver bem.
 */
export function validarIntervalo(inicio, fim) {
  const a = lerData(inicio);
  const b = lerData(fim);
  if (!a || !b) return "Indique as duas datas.";
  if (a > b) return "A data de início tem de ser anterior ou igual à de fim.";
  if ((b - a) / MS_POR_DIA + 1 > MAX_DIAS) return `O período não pode exceder ${MAX_DIAS} dias.`;
  return null;
}

/**
 * Parâmetros do pedido. Filtros vazios NÃO viajam (o servidor trata a ausência
 * como «toda a equipa»), e os ids repetidos/em branco são limpos.
 */
export function parametrosDoRelatorio({ inicio, fim, utilizadores = [], papeis = [] } = {}) {
  const limpar = (lista) => [...new Set((Array.isArray(lista) ? lista : []).map((v) => String(v ?? "").trim()).filter(Boolean))].sort();
  const params = { start_date: inicio, end_date: fim };
  const ids = limpar(utilizadores);
  const roles = limpar(papeis);
  if (ids.length) params.user_ids = ids.join(",");
  if (roles.length) params.roles = roles.join(",");
  return params;
}

/** `null` (histórico desligado) é «—»; nunca 0. */
export function valorOuTraco(valor) {
  return valor === null || valor === undefined ? "—" : String(valor);
}

/** Acções = fases + tarefas concluídas. `null` conta como 0 só para ordenar. */
export function pontuacao(utilizador) {
  return (utilizador?.processes_moved || 0) + (utilizador?.tasks_completed || 0);
}

/** Taxa de conclusão do período; `null` sem tarefas (não é 0 %). */
export function taxaDeConclusao(utilizador) {
  const total = (utilizador?.tasks_completed || 0) + (utilizador?.tasks_pending || 0);
  if (total === 0) return null;
  return Math.round(((utilizador.tasks_completed || 0) / total) * 100);
}

/** `Array.isArray` e nunca `|| []` (§ 27.38). */
export function listaOuVazia(valor) {
  return Array.isArray(valor) ? valor : [];
}

/** Dados do gráfico de barras por colaborador. */
export function dadosDoGraficoDePessoas(utilizadores) {
  return listaOuVazia(utilizadores).map((u) => ({
    nome: String(u?.name || "N/A").split(" ")[0],
    nomeCompleto: u?.name || "N/A",
    "Fases alteradas": u?.phase_changes ?? 0,
    "Tarefas concluídas": u?.tasks_completed ?? 0,
    "Em atraso": u?.tasks_overdue ?? 0,
  }));
}

/** Nome do ficheiro do `Content-Disposition`, ou um recuo. */
export function nomeDoFicheiro(cabecalhos, recuo) {
  const valor = cabecalhos?.["content-disposition"] || cabecalhos?.["Content-Disposition"] || "";
  const m = /filename="?([^";]+)"?/i.exec(valor);
  return m ? m[1] : recuo;
}

/** A segunda-feira que a lista de semanas devolve, em formato curto. */
export function rotuloDaSemana(semana) {
  if (!semana?.week_start) return "";
  const fmt = (t) => `${t.slice(8, 10)}/${t.slice(5, 7)}`;
  return `${fmt(semana.week_start)} – ${fmt(semana.week_end)}`;
}

export function descarregarBlob(blob, nome) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nome;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revogar já cancelaria o descarregamento em alguns navegadores.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
