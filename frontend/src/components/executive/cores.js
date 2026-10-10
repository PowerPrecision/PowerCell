/**
 * Cores dos gráficos executivos — as MESMAS do PDF (`executive_report_pdf.py`).
 *
 * Validadas para daltonismo com o validador do dataviz (ΔE CVD ≥ 12 entre
 * vizinhas, no claro e no escuro; os mesmos hex servem os dois modos). O par
 * vermelho/verde que a página usava antes tinha ΔE 5 em deuteranopia: as
 * «tarefas concluídas» e as «atrasadas» confundiam-se para 1 em 12 homens.
 * A identidade nunca depende só da cor: há sempre legenda e tabela.
 */
export const COR_FASES = "#2563eb";
export const COR_CONCLUIDAS = "#0d9488";
export const COR_ATRASO = "#d97706";

export const SERIES_POR_PESSOA = [
  { chave: "Fases alteradas", cor: COR_FASES },
  { chave: "Tarefas concluídas", cor: COR_CONCLUIDAS },
  { chave: "Em atraso", cor: COR_ATRASO },
];
