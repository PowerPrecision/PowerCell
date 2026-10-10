/**
 * Calendário do Dashboard — regras puras (Bloco 4, ponto 29).
 *
 * O servidor classifica e filtra (`services/dashboard_calendar.py`); isto só
 * monta a grelha do mês e agrupa por dia. As cores foram validadas para
 * daltonismo (ΔE CVD ≥ 12 no claro e no escuro); no escuro o magenta fica
 * abaixo de 3:1 de contraste, o que obriga a rótulos visíveis — por isso cada
 * categoria tem também uma LETRA e a lista do dia diz o nome por extenso.
 * A identidade nunca depende só da cor.
 */
import { rotaDaFicha } from "./calendarioIdentidade";

export const CATEGORIAS = [
  { chave: "escritura", rotulo: "Escrituras", letra: "E", cor: "#2563eb" },
  { chave: "cpcv", rotulo: "CPCV", letra: "C", cor: "#d97706" },
  { chave: "marcacao", rotulo: "Marcações", letra: "M", cor: "#0d9488" },
  { chave: "ausencia", rotulo: "Ausências", letra: "A", cor: "#a21caf" },
  { chave: "prazo", rotulo: "Prazos", letra: "P", cor: "#64748b" },
];

const POR_CHAVE = Object.fromEntries(CATEGORIAS.map((c) => [c.chave, c]));

export function categoriaDe(chave) {
  return POR_CHAVE[chave] || POR_CHAVE.prazo;
}

/** `AAAA-MM` do mês de uma data (UTC, como o servidor). */
export function mesDe(data) {
  return `${data.getUTCFullYear()}-${String(data.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** Soma `n` meses a um `AAAA-MM`. */
export function somarMeses(mes, n) {
  const [a, m] = mes.split("-").map(Number);
  const indice = a * 12 + (m - 1) + n;
  return `${Math.floor(indice / 12)}-${String((indice % 12) + 1).padStart(2, "0")}`;
}

export function rotuloDoMes(mes) {
  const [a, m] = mes.split("-").map(Number);
  const nome = new Date(Date.UTC(a, m - 1, 1)).toLocaleDateString("pt-PT", { month: "long", timeZone: "UTC" });
  return `${nome.charAt(0).toUpperCase()}${nome.slice(1)} de ${a}`;
}

/**
 * A grelha do mês: semanas de segunda a domingo, com os dias dos meses
 * vizinhos a preencher (`doMes: false`).
 * @returns {Array<Array<{dia: string, numero: number, doMes: boolean}>>}
 */
export function construirGrelha(mes) {
  const [a, m] = mes.split("-").map(Number);
  const primeiro = new Date(Date.UTC(a, m - 1, 1));
  const recuo = (primeiro.getUTCDay() + 6) % 7; // segunda = 0
  const inicio = new Date(Date.UTC(a, m - 1, 1 - recuo));
  const ultimo = new Date(Date.UTC(a, m, 0));
  const dias = recuo + ultimo.getUTCDate();
  const semanas = Math.ceil(dias / 7);
  const grelha = [];
  for (let s = 0; s < semanas; s += 1) {
    const semana = [];
    for (let d = 0; d < 7; d += 1) {
      const data = new Date(inicio.getTime() + (s * 7 + d) * 86_400_000);
      semana.push({
        dia: data.toISOString().slice(0, 10),
        numero: data.getUTCDate(),
        doMes: data.getUTCMonth() === m - 1,
      });
    }
    grelha.push(semana);
  }
  return grelha;
}

/** `{ "2026-10-07": [itens] }`. `Array.isArray` e nunca `|| []` (§ 27.38). */
export function agruparPorDia(itens) {
  const mapa = {};
  for (const item of Array.isArray(itens) ? itens : []) {
    if (!item?.dia) continue;
    (mapa[item.dia] ||= []).push(item);
  }
  return mapa;
}

/** Quantas categorias distintas há num dia, pela ordem das categorias. */
export function categoriasDoDia(itensDoDia) {
  const presentes = new Set((Array.isArray(itensDoDia) ? itensDoDia : []).map((i) => i.categoria));
  return CATEGORIAS.filter((c) => presentes.has(c.chave));
}

/** Para onde leva o item, ou `null` (sem destino não se desenha ligação). */
export function rotaDoItem(item) {
  return rotaDaFicha({
    process_id: item?.process_id,
    client_id: item?.client_id,
    type: item?.categoria === "ausencia" ? "absence" : "event",
  });
}

export function contagemDe(contagens, chave) {
  const n = contagens?.[chave];
  return Number.isFinite(n) ? n : 0;
}
