/**
 * Pesquisa global — a etiqueta da empresa e o destino de cada resultado (Lote 7.1).
 *
 * A pesquisa do cabeçalho (Ctrl+K) é a ÚNICA excepção ao contexto estrito de
 * empresa: procura em todas as redes a que o utilizador tem acesso e cada
 * resultado traz `empresa` ({company_id, company_name, network_id,
 * e_de_outra_rede}). Abrir por id continua estrito — um resultado de OUTRA
 * empresa responde «não existe» se se abrir com a empresa activa errada —, por
 * isso o ecrã tem de trocar de empresa ANTES de navegar.
 *
 * Puro e sem React: a regra («o que se mostra» e «para onde se vai») vive aqui
 * e o componente só a desenha, como `calendarioIdentidade` e `empresaDona`.
 */

/** O nome da empresa dona, ou ``null`` (nunca inventa um nome). */
export function etiquetaDaEmpresa(dados) {
  const nome = dados?.empresa?.company_name;
  return typeof nome === "string" && nome.trim() ? nome.trim() : null;
}

/**
 * Abrir este resultado exige trocar de empresa?
 *
 * Só quando o servidor o afirma (`=== true`) e diz para que empresa: um campo
 * em falta nunca vira «trocar», senão uma resposta antiga mandava recarregar a
 * página a cada clique.
 */
export function exigeTrocaDeEmpresa(dados) {
  const empresa = dados?.empresa;
  return empresa?.e_de_outra_rede === true && typeof empresa?.company_id === "string" && empresa.company_id !== "";
}

/** A rota do resultado (a mesma de sempre; sem destino, ``null``). */
export function destinoDoResultado(tipo, dados) {
  switch (tipo) {
    case "process":
      return dados?.id ? `/processo/${dados.id}` : null;
    case "client":
      // Um cliente navega SEMPRE para a ficha do cliente, nunca para o processo.
      return dados?.id ? `/cliente/${dados.id}` : null;
    case "task":
      return "/pendentes";
    default:
      return null;
  }
}
