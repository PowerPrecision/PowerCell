/**
 * ResultadosDaPesquisa — a tabela da pesquisa avançada do Index (apresentação pura).
 *
 * Diz o que aconteceu (`onVerDocumento(documentos, titulo)`); quem decide o que isso implica é a página.
 * As colunas dependem do que se procurou (emprego, recibo, declaração, extrato) e só mostram o que o
 * servidor devolveu — nunca o nome do cliente nem do ficheiro. O botão «Ver documento» só se desenha
 * com uma referência exacta ao documento (`document_id`/`document_ids`).
 */
import { AlertTriangle, Eye, SearchX } from "lucide-react";
import { Link } from "react-router-dom";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/EmptyState";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import {
  dataDeAdmissao,
  documentosDoResultado,
  rotuloDoContrato,
  rotuloDoDocumento,
  valorEmEuros,
} from "../../utils/pesquisaIndex";

const SEM = <span className="text-muted-foreground">—</span>;

function Processo({ item }) {
  const numero = item.process_number ? `#${item.process_number}` : String(item.process_id || "").slice(0, 8);
  return (
    <div>
      <Link
        to={`/index/${item.process_id}`}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-primary hover:underline"
        data-testid="resultado-processo"
      >
        {numero}
      </Link>
      {item.company_name && <div className="text-xs text-muted-foreground">{item.company_name}</div>}
    </div>
  );
}

function Entidade({ item }) {
  const e = item.employer || {};
  if (!e.name && !e.nif) return SEM;
  return (
    <div>
      <div className="text-sm">{e.name || SEM}</div>
      {e.nif && <div className="text-xs text-muted-foreground">NIF {e.nif}</div>}
    </div>
  );
}

function Contrato({ item }) {
  if (!item.contract_type) return SEM;
  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className="text-sm">{rotuloDoContrato(item.contract_type)}</span>
      {item.certified_by_declaration && (
        <Badge variant="secondary" className="text-[10px]" title="Tipo de contrato certificado por uma Declaração de Efetividade">
          Certificado
        </Badge>
      )}
    </div>
  );
}

const COLUNAS = {
  emprego: [
    ["Entidade", (i) => <Entidade item={i} />],
    ["Localidade", (i) => i.employer?.location || SEM],
    ["Cargo", (i) => i.job_title || SEM],
    ["Líquido", (i) => valorEmEuros(i.net_salary)],
    ["Contrato", (i) => <Contrato item={i} />],
    ["Admissão", (i) => dataDeAdmissao(i.admission_date)],
    ["Período", (i) => i.period || SEM],
  ],
  recibo: [
    ["Entidade", (i) => <Entidade item={i} />],
    ["Localidade", (i) => i.employer?.location || SEM],
    ["Cargo", (i) => i.job_title || SEM],
    ["Líquido", (i) => valorEmEuros(i.net_salary)],
    ["Contrato", (i) => <Contrato item={i} />],
    ["Período", (i) => i.period || SEM],
  ],
  declaracao_efetividade: [
    ["Entidade", (i) => <Entidade item={i} />],
    ["Localidade", (i) => i.employer?.location || SEM],
    ["Cargo", (i) => i.job_title || SEM],
    ["Contrato", (i) => <Contrato item={i} />],
    ["Admissão", (i) => dataDeAdmissao(i.admission_date)],
    ["Emissão", (i) => i.period || SEM],
  ],
  extrato: [
    ["Banco", (i) => i.bank || <span className="text-muted-foreground" title="A IA não leu o banco deste extrato">não identificado</span>],
    ["Período", (i) => i.period || SEM],
  ],
};

/** Que conjunto de colunas: por emprego, ou pelo tipo de documento que se procurou. */
export function formaDasColunas(vista, tipo) {
  if (vista !== "documents") return "emprego";
  return COLUNAS[tipo] ? tipo : "recibo";
}

/**
 * @param {Object} props
 * @param {"jobs"|"documents"} props.vista
 * @param {string} props.tipo — o `document_type` pedido ("" = por emprego)
 * @param {Array<Object>} props.itens
 * @param {(documentos: Array<{id: string, rotulo: string}>, titulo: string) => void} props.onVerDocumento
 */
export function ResultadosDaPesquisa({ vista, tipo, itens, onVerDocumento }) {
  if (!itens.length) {
    return (
      <EmptyState
        icon={SearchX}
        title="Sem resultados"
        message="Nenhum documento dos processos a que tem acesso corresponde a estes filtros."
      />
    );
  }

  const forma = formaDasColunas(vista, tipo);
  const colunas = COLUNAS[forma];

  return (
    <Table data-testid="pesquisa-resultados">
      <TableHeader>
        <TableRow>
          <TableHead>Processo</TableHead>
          {colunas.map(([titulo]) => (
            <TableHead key={titulo}>{titulo}</TableHead>
          ))}
          <TableHead className="text-right">Documento</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {itens.map((item, n) => {
          const documentos = documentosDoResultado(item, vista);
          const titulo = vista === "documents" ? rotuloDoDocumento(item) : `Documentos do emprego${item.employer?.name ? ` · ${item.employer.name}` : ""}`;
          return (
            <TableRow key={item.document_id || item.job_id || `${item.process_id}-${n}`} data-testid="pesquisa-linha">
              <TableCell>
                <Processo item={item} />
              </TableCell>
              {colunas.map(([titulo_, celula]) => (
                <TableCell key={titulo_}>
                  {celula(item)}
                  {titulo_ === colunas[0][0] && item.needs_review && (
                    <span className="mt-1 flex items-center gap-1 text-xs text-[hsl(var(--warning))]" title="Há campos por rever neste registo">
                      <AlertTriangle className="h-3 w-3" aria-hidden="true" />A rever
                    </span>
                  )}
                </TableCell>
              ))}
              <TableCell className="text-right">
                {documentos.length ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 gap-1"
                    onClick={() => onVerDocumento(documentos, titulo)}
                    aria-label={documentos.length > 1 ? `Ver documentos (${documentos.length}) — ${titulo}` : `Ver documento — ${titulo}`}
                    data-testid="ver-documento"
                  >
                    <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                    {documentos.length > 1 ? `Ver documentos (${documentos.length})` : "Ver documento"}
                  </Button>
                ) : (
                  <span className="text-xs text-muted-foreground">Sem documento</span>
                )}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

export default ResultadosDaPesquisa;
