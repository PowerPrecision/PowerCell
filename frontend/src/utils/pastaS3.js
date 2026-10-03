/**
 * O que se MOSTRA de uma pasta S3, e o que se USA para operar nela.
 *
 * Desde que a identidade documental deriva do ID (Lote 6, ponto 1), a pasta de
 * um cliente novo chama-se `11111111-1111-4111-8111-111111111111`. O nome real
 * é resolúvel — está no mapeamento — e o backend devolve-o em `display_name`
 * (`s3_explorer_scope.nome_legivel`).
 *
 * A REGRA QUE NÃO SE PODE PERDER
 * ==============================
 * `path` e `name` continuam a ser a autoridade de TODAS as operações (entrar,
 * renomear, apagar, descarregar). O `display_name` é só para o ecrã. Mostrar
 * uma coisa e operar noutra é a forma discreta de uma parede não valer nada —
 * é a mesma razão por que as primitivas novas do `s3_storage` são de chave
 * EXACTA.
 *
 * E a pesquisa casa contra os DOIS: quem procura "Carolina" tem de encontrar a
 * pasta, e quem cola um uuid de um log também. Filtrar só pelo visível fazia o
 * uuid deixar de ser pesquisável no dia em que o nome passou a aparecer.
 */

/** O nome a desenhar. Nunca vazio: sem resolução fica o nome da pasta. */
export const nomeVisivel = (pasta) =>
  (pasta?.display_name || "").trim() || (pasta?.name || "").trim() || "—";

/**
 * A pasta é reclamada por mais do que uma ficha?
 *
 * É a colisão de identidade do D-19. O backend manda os nomes todos de
 * propósito — escolher um faria a colisão parecer resolvida.
 */
export const temColisao = (pasta) =>
  Array.isArray(pasta?.nomes_dos_clientes) && pasta.nomes_dos_clientes.length > 1;

/** Nenhuma ficha reclama esta pasta (invisível ao staff normal). */
export const eOrfa = (pasta) => pasta?.orfa === true;

/** O nome visível foi resolvido a partir do mapeamento (não é o do bucket). */
export const nomeFoiResolvido = (pasta) => {
  const visivel = nomeVisivel(pasta);
  const cru = (pasta?.name || "").trim();
  return Boolean(cru) && visivel !== cru;
};

/** Casa contra o nome visível E o nome cru. */
export const casaPesquisa = (pasta, termo) => {
  const alvo = (termo || "").trim().toLowerCase();
  if (!alvo) return true;
  const candidatos = [
    nomeVisivel(pasta),
    pasta?.name,
    ...(Array.isArray(pasta?.nomes_dos_clientes) ? pasta.nomes_dos_clientes : []),
  ];
  return candidatos.some((c) => String(c || "").toLowerCase().includes(alvo));
};

/** Ordena pelo nome VISÍVEL — é a ordem que o utilizador lê. */
export const ordenarPastas = (pastas) =>
  [...(pastas || [])].sort((a, b) =>
    nomeVisivel(a).localeCompare(nomeVisivel(b), "pt")
  );
