/**
 * Atribuição directa só dentro da própria rede (Out 2026 — Via Rápida extinta).
 *
 * O servidor recusa com 403 quando alguém tenta atribuir diretamente uma
 * pessoa de OUTRA rede (`assignment_network_guard.MENSAGEM_DE_RECUSA`), e a
 * lista de «quem posso escolher» já vem filtrada do servidor. Mas um 403 é,
 * para o interceptor do Axios, «Acesso Negado — não tem permissão», e esta
 * recusa NÃO é falta de permissão: vale para todos os perfis e diz para onde
 * ir («Partilhar com Empresa…»). Mostrar o genérico mandava pedir permissões
 * que não resolvem nada.
 *
 * O prefixo é o MESMO que o Python escreve — há um teste que LÊ o Python e
 * falha se as duas divergirem.
 */
export const PREFIXO_DA_RECUSA_DE_ATRIBUICAO_ENTRE_REDES =
  "Só pode atribuir diretamente pessoas da sua própria rede";

/**
 * O `detail` de um 403 é a recusa de atribuição entre redes?
 *
 * @param {unknown} detalhe
 * @returns {boolean}
 */
export function eRecusaDeAtribuicaoEntreRedes(detalhe) {
  return typeof detalhe === "string"
    && detalhe.startsWith(PREFIXO_DA_RECUSA_DE_ATRIBUICAO_ENTRE_REDES);
}
