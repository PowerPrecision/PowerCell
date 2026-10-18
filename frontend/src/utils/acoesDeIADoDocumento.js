/**
 * As duas acções de IA POR DOCUMENTO, com nomes que as distinguem (QA-6).
 *
 * Eram dois ícones lado a lado com o mesmo tom e quase o mesmo nome — «Analisar com IA» e
 * «Extrair Dados com IA» — e fazem coisas diferentes:
 *
 *  - CLASSIFICAR: a IA sugere os METADADOS do ficheiro (categoria, validade, nome). Abre o painel
 *    «Revisão de Sugestões IA» e só se aplica o que o utilizador aceitar.
 *  - EXTRAIR: a IA lê o conteúdo e propõe DADOS PARA A FICHA do cliente/processo (NIF, morada,
 *    rendimento…). Abre a revisão da ficha; nada se grava sem confirmação.
 *
 * Não se fundiram num só botão de propósito: são dois fluxos com dois endpoints e dois ecrãs de
 * revisão, e juntá-los escondia ao utilizador qual dos dois estava a gastar uma chamada paga.
 * Aqui fica a copy e o estilo num ponto único — os três sítios onde o ficheiro se desenha
 * (lista, grelha «Todos», grelha por categoria) divergiam em silêncio quando estavam à mão.
 */

export const ACAO_CLASSIFICAR = {
  titulo: "Classificar documento: sugere categoria, validade e nome (rever antes de aplicar)",
  aria: (nome) => `Classificar ${nome} com IA`,
  // Tokens semânticos: o «classificar» é o primário; o «extrair» ganha fundo para se ler como outra acção.
  classe: "text-primary hover:text-primary",
};

export const ACAO_EXTRAIR = {
  titulo: "Extrair dados do documento: preenche a ficha do cliente (rever antes de aplicar)",
  aria: (nome) => `Extrair dados de ${nome}`,
  classe: "text-accent-foreground bg-accent/60 hover:bg-accent hover:text-accent-foreground",
};
