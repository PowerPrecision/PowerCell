/**
 * Linhagem de um processo: Parceiro → Empresa Y → Empresa Z → … (Out 2026).
 *
 * O servidor devolve `linhagem` (`process_lineage.construir_linhagem`), DERIVADA do
 * registo de partilhas e nunca gravada:
 *   { origem, dona, caminhos: [[nó, …], …], empresa_actual: [nomes], partilhas, tem_cadeia }
 * Esta camada decide o que se MOSTRA; o componente só desenha. Nada aqui reconstrói a
 * cadeia — uma segunda cópia da regra divergia da do servidor na primeira revogação.
 */

/** Um nó só é desenhado se tiver nome: um crachá vazio seria pior do que nenhum. */
const temNome = (no) => no && typeof no.nome === "string" && no.nome.trim() !== "";

/**
 * Os caminhos a desenhar, um por folha, cada um da origem à folha.
 * `Array.isArray` e nunca `|| []`: um objecto é truthy e o `.map` rebentaria noutro
 * sítio (FRONTEND_GUIDELINES § 27.38).
 */
export function caminhosDaLinhagem(linhagem) {
  const caminhos = linhagem?.caminhos;
  if (!Array.isArray(caminhos)) return [];
  return caminhos
    .map((caminho) => (Array.isArray(caminho) ? caminho.filter(temNome) : []))
    .filter((caminho) => caminho.length > 0);
}

/**
 * Vale a pena desenhar a linhagem? Só quando há mais do que a casa dona: um parceiro
 * angariador ou pelo menos uma partilha. Um processo da casa, sem partilhas nem
 * parceiro, já tem a etiqueta da empresa dona — repeti-la seria ruído.
 *
 * Só o `true` ESTRITO de `tem_cadeia` conta: um campo em falta nunca inventa uma cadeia.
 */
export function deveMostrarLinhagem(linhagem) {
  if (!linhagem || typeof linhagem !== "object") return false;
  const haParceiro = linhagem.origem?.tipo === "parceiro" && temNome(linhagem.origem);
  return (haParceiro || linhagem.tem_cadeia === true) && caminhosDaLinhagem(linhagem).length > 0;
}

/** «Parceiro João → Empresa Y → Empresa Z», para o título/leitor de ecrã. */
export function textoDoCaminho(caminho) {
  return (Array.isArray(caminho) ? caminho : [])
    .filter(temNome)
    .map((no) => no.nome.trim())
    .join(" → ");
}

/** As empresas que têm o processo AGORA (as folhas), por nome. */
export function empresasActuais(linhagem) {
  const nomes = linhagem?.empresa_actual;
  if (!Array.isArray(nomes)) return [];
  return nomes.filter((n) => typeof n === "string" && n.trim() !== "");
}

/** O nó é o fim do caminho (onde o processo está agora)? */
export function eOFimDoCaminho(caminho, indice) {
  return Array.isArray(caminho) && indice === caminho.length - 1;
}
