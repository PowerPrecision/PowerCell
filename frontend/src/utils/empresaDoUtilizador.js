/**
 * A empresa de cada pessoa nas listas de atribuição.
 *
 * O servidor junta `empresa_etiqueta` («Power · Precision») e `empresas` (lista de nomes) a
 * cada utilizador de `/users` e `/users/staff`, calculadas ao servir e restritas às empresas do
 * âmbito de quem pede. O ecrã não infere a empresa de mais nada (`user.company` é o NOME legado
 * e o `company_id` nunca se deduz de um nome): mostra o que o servidor devolveu, ou nada.
 *
 * Puro: decide o texto, quem chama desenha o rótulo.
 */

/**
 * @param {Object} [utilizador]
 * @returns {string} «Power», «Power · Precision» ou "" quando o servidor não disse.
 */
export function etiquetaDaEmpresa(utilizador) {
  const etiqueta = utilizador?.empresa_etiqueta;
  if (typeof etiqueta === "string" && etiqueta.trim()) return etiqueta.trim();
  const empresas = utilizador?.empresas;
  if (Array.isArray(empresas)) {
    const nomes = empresas.filter((n) => typeof n === "string" && n.trim());
    if (nomes.length) return nomes.join(" · ");
  }
  return "";
}

/**
 * Texto de uma opção de `<Select>` (que só aceita texto): «Ana (consultor) — Precision».
 */
export function textoDaOpcaoDeUtilizador(utilizador, { comPapel = true } = {}) {
  const nome = utilizador?.name || "";
  const papel = comPapel && utilizador?.role ? ` (${utilizador.role})` : "";
  const empresa = etiquetaDaEmpresa(utilizador);
  return `${nome}${papel}${empresa ? ` — ${empresa}` : ""}`;
}
