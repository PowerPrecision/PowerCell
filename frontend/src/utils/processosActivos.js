/**
 * Aviso «este cliente já tem um processo activo» — regras puras (Bloco 1, ponto 5).
 *
 * O servidor decide o que é «activo» (o motor de fases) e o que o utilizador
 * pode ver (a rede). Isto só traduz a resposta para o que se mostra, e fixa
 * a política do aviso:
 *
 * 1. **Consultivo, não bloqueante**: um cliente pode legitimamente ter dois
 *    processos (dois créditos, 1.º titular num e 2.º noutro). O aviso
 *    pergunta, e a resposta é do utilizador;
 * 2. **Falha aberta e DITA**: se a verificação falhar, o fluxo continua — mas
 *    o utilizador é informado de que não foi verificado. Um aviso que falha
 *    em silêncio ensina a confiar na ausência de aviso.
 */

const ROTULOS_DO_TITULAR = {
  titular1: "1.º titular",
  titular2: "2.º titular",
  co_titular: "co-titular",
};

/** Normaliza `GET /clients/{id}/active-processes`. */
export function normalizarProcessosActivos(data) {
  const lista = Array.isArray(data?.processos) ? data.processos : [];
  const processos = lista
    .filter((p) => p && typeof p.id === "string" && p.id)
    .map((p) => ({
      id: p.id,
      process_number: p.process_number ?? null,
      status_label: p.status_label || p.status || "",
      titular: ROTULOS_DO_TITULAR[p.titular] ? p.titular : "co_titular",
      consultor_names: Array.isArray(p.consultor_names) ? p.consultor_names.filter(Boolean) : [],
    }));
  const total = Number.isFinite(data?.total) ? data.total : processos.length;
  return {
    client_name: typeof data?.client_name === "string" ? data.client_name : "",
    // O total real pode exceder a lista (o servidor limita-a).
    total: Math.max(total, processos.length),
    processos,
  };
}

/** Só se avisa quando há MESMO algo a dizer. */
export function deveAvisar(resposta) {
  return Boolean(resposta) && resposta.total > 0;
}

export function rotuloDoTitular(titular) {
  return ROTULOS_DO_TITULAR[titular] || ROTULOS_DO_TITULAR.co_titular;
}

/** «tem 1 processo activo» / «tem 3 processos activos». */
export function frase(resposta) {
  const n = resposta?.total ?? 0;
  return n === 1 ? "1 processo activo" : `${n} processos activos`;
}

/** Quantos processos existem para além dos listados. */
export function processosOcultos(resposta) {
  return Math.max((resposta?.total ?? 0) - (resposta?.processos?.length ?? 0), 0);
}

export const AVISO_NAO_VERIFICADO =
  "Não foi possível verificar se o cliente já tem processos activos.";
