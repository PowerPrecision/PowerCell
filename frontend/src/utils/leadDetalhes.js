/**
 * «Ver Detalhes da Lead» — regras PURAS do painel.
 *
 * O servidor devolve uma lista positiva (`GET /financial-validation/lead/{id}/details`); aqui decide-se
 * o que se desenha: que secções existem, com que título, e que linhas (campo → valor legível). Uma
 * secção sem linhas NÃO se desenha (um título com nada por baixo lê-se como «não preencheu» quando pode
 * ser «não chegou»), e o que o parceiro escreveu à mão (as notas) nunca é interpretado.
 */
import { rotuloDaSugestao, textoDoValor } from "./rotulosDasSugestoes";

/** As secções de dados, pela ordem em que a equipa as lê. */
export const SECCOES_DA_LEAD = [
  { chave: "dados_pessoais", titulo: "Dados pessoais" },
  { chave: "titular2_data", titulo: "2.º titular" },
  { chave: "dados_financeiros", titulo: "Situação financeira" },
  { chave: "dados_imobiliarios", titulo: "Imóvel" },
];

/** Campos que já aparecem noutro bloco do painel (contactos, nome): não se repetem nas secções. */
const REPETIDOS = new Set(["nome", "email", "telefone"]);

const ROTULOS_PROPRIOS = {
  profissao: "Profissão",
  rendimento_mensal: "Rendimento mensal",
  tipo_de_pedido: "Tipo de pedido",
};

export function rotuloDoCampo(campo) {
  return ROTULOS_PROPRIOS[campo] || rotuloDaSugestao(campo);
}

/** Linhas `{campo, rotulo, valor}` de uma secção do servidor; vazio se não houver nada que mostrar. */
export function linhasDaSeccao(seccao, { semRepetidos = false } = {}) {
  if (!seccao || typeof seccao !== "object" || Array.isArray(seccao)) return [];
  return Object.entries(seccao)
    .filter(([campo]) => !(semRepetidos && REPETIDOS.has(campo)))
    .map(([campo, valor]) => ({ campo, rotulo: rotuloDoCampo(campo), valor: textoDoValor(valor) }));
}

/** As secções a desenhar, já com as suas linhas (as vazias ficam de fora). */
export function seccoesDaLead(detalhes) {
  return SECCOES_DA_LEAD
    .map(({ chave, titulo }) => ({
      chave,
      titulo,
      linhas: linhasDaSeccao(detalhes?.[chave], { semRepetidos: chave === "dados_pessoais" }),
    }))
    .filter((s) => s.linhas.length > 0);
}

/** Os ficheiros pela ordem recebida, sempre com o comprovativo primeiro. */
export function ficheirosDaLead(detalhes) {
  const lista = Array.isArray(detalhes?.ficheiros) ? detalhes.ficheiros : [];
  return [...lista].sort((a, b) => Number(Boolean(b.comprovativo)) - Number(Boolean(a.comprovativo)));
}

/** A forma mínima para a gaveta abrir: um id. */
export function podeAbrirDetalhes(cliente) {
  return Boolean(cliente && typeof cliente.id === "string" && cliente.id);
}
