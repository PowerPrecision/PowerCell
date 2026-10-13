/**
 * Empresa dona de um processo, para o cabeçalho do detalhe (Multi-Tenant).
 *
 * O servidor devolve `empresa_dona`:
 *   { company_id, company_name, network_id, e_de_outra_rede } | null
 * Esta regra decide o que se MOSTRA; o componente só desenha.
 *
 * Duas decisões com motivo:
 *  - sem nome não há etiqueta (um crachá vazio seria pior do que nenhum);
 *  - «partilhado» só se afirma quando o servidor o diz com `=== true` — um
 *    campo em falta (sessão/servidor antigos) nunca vira «processo de outra casa».
 */
export function etiquetaDaEmpresaDona(empresaDona) {
  if (!empresaDona || typeof empresaDona !== "object") return null;
  const nome = typeof empresaDona.company_name === "string" ? empresaDona.company_name.trim() : "";
  if (!nome) return null;
  const partilhado = empresaDona.e_de_outra_rede === true;
  return {
    nome,
    partilhado,
    titulo: partilhado
      ? `Processo da empresa ${nome} — partilhado com a sua rede`
      : `Empresa dona do processo: ${nome}`,
  };
}
