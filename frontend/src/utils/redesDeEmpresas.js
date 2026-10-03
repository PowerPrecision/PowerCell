/**
 * Etiquetas das redes (grupos) de empresas (Lote 4, ponto 5).
 *
 * O QUE ESTAVA MAL
 * A tabela de Empresas do painel de administração mostrava Nome, NIF,
 * Email e Estado — e **não mostrava a rede**. O campo existe, é editável
 * no diálogo (`CompanyNetworkField`) e é a FRONTEIRA DE SEGURANÇA do
 * sistema: `companies.network_id` é o que decide quem vê os dados de
 * quem, e uma empresa sem rede é uma ilha de uma só. Nada disso estava
 * visível na listagem: para saber a que grupo pertence uma empresa era
 * preciso abrir o diálogo de edição, uma a uma.
 *
 * PORQUE É QUE A ETIQUETA NÃO É SÓ COSMÉTICA
 * O valor é um slug (`grupo_power_precision`). Mostrá-lo bonito
 * ("Power Precision") tem um risco próprio, e é o MESMO contra o qual o
 * `CompanyNetworkField` foi construído: `grupo_power` em vez de
 * `grupo_power_precision` não dá erro nenhum — cria uma rede nova de uma
 * empresa só e o isolamento quebra ao contrário, escondendo dados de quem
 * os devia ver. Se duas redes diferentes forem desenhadas com o mesmo
 * rótulo bonito, a etiqueta passa a ESCONDER a gralha.
 *
 * Daí a regra deste módulo: embelezar sim, mas quando dois slugs
 * distintos no mesmo ecrã dão o mesmo rótulo, mostra-se o SLUG CRU dos
 * dois. A etiqueta nunca pode fazer duas redes parecerem uma.
 */

/** O valor que representa "sem rede" (ilha de uma só empresa). */
export const SEM_REDE = "";
export const ETIQUETA_SEM_REDE = "Sem grupo";

/** Normaliza o campo cru: `null`/espaços → `SEM_REDE`. */
export function normalizarRede(valor) {
  if (valor === null || valor === undefined) return SEM_REDE;
  return String(valor).trim();
}

/**
 * O rótulo legível de um slug de rede.
 *
 * `grupo_power_precision` → `Power Precision`. O prefixo "grupo" sai
 * porque a coluna já se chama Grupo — repeti-lo em cada linha é ruído.
 */
export function etiquetaDaRede(valor) {
  const slug = normalizarRede(valor);
  if (!slug) return ETIQUETA_SEM_REDE;

  const palavras = slug
    .replace(/[_-]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  // Só se descarta o "grupo" quando SOBRA alguma coisa: uma rede
  // chamada literalmente `grupo` tem de continuar a ver-se.
  const semPrefixo =
    palavras.length > 1 && palavras[0].toLowerCase() === "grupo"
      ? palavras.slice(1)
      : palavras;

  return semPrefixo
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())
    .join(" ");
}

/**
 * As etiquetas de uma lista de empresas, com desambiguação.
 *
 * @param {Array<{network_id?: string}>} empresas
 * @returns {Map<string, {etiqueta: string, ambigua: boolean, slug: string}>}
 *   indexado pelo slug NORMALIZADO (`SEM_REDE` incluído).
 */
export function etiquetasDeRede(empresas) {
  const slugs = new Set(
    (Array.isArray(empresas) ? empresas : []).map((e) => normalizarRede(e?.network_id)),
  );

  // Quantos slugs distintos caem em cada rótulo bonito.
  const porEtiqueta = new Map();
  for (const slug of slugs) {
    const etiqueta = etiquetaDaRede(slug);
    porEtiqueta.set(etiqueta, (porEtiqueta.get(etiqueta) || 0) + 1);
  }

  const resultado = new Map();
  for (const slug of slugs) {
    const bonita = etiquetaDaRede(slug);
    const ambigua = (porEtiqueta.get(bonita) || 0) > 1;
    resultado.set(slug, {
      slug,
      ambigua,
      // Ambígua → o slug cru, que é o único texto que distingue as duas.
      etiqueta: ambigua && slug ? slug : bonita,
    });
  }
  return resultado;
}

/*
 * LIMITE HONESTO, afirmado em teste: a desambiguação é do que está NO
 * ECRÃ. A tabela é paginada (25 por página), logo duas redes com o mesmo
 * rótulo em páginas diferentes não se vêem uma à outra. O erro é no
 * sentido seguro — deixa passar uma colisão, nunca inventa uma.
 *
 * E é por isso que NÃO há aqui uma contagem de empresas por rede: sobre
 * uma página, "esta rede tem uma empresa só" é falso em cada rede cujas
 * empresas estejam partidas entre páginas, e um aviso de "ilha" errado
 * sobre a fronteira de isolamento é pior do que aviso nenhum. A única
 * ilha que se pode afirmar linha a linha é a empresa SEM rede.
 */
