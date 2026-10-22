/**
 * IndexQueueTable — a lista de processos do dashboard do Index (apresentação pura).
 *
 * Diz o que aconteceu (`onAbrir(processId)`); quem decide o que isso implica é a página.
 * Nunca mostra dados do cliente além do nome e do nº do processo, e a fila nem os recebe
 * (o servidor só devolve a lista positiva).
 *
 * A coluna «Empresa/Origem» diz de que empresa é o processo (`company`, calculada ao servir) e, quando
 * o processo foi PARTILHADO por outra rede, di-lo — quem trata a fila precisa de saber de onde vem.
 * Sem empresa determinável mostra «—»: nunca se inventa uma.
 *
 * ORDENAÇÃO (Out 2026): os cabeçalhos de Processo, Empresa/Origem, Estado, Alertas e da data são botões que
 * pedem a ordem (`onOrdenar(coluna)`); `ordem` diz a que está em vigor e cada `<th>` leva `aria-sort`. A
 * tabela não ordena nada: a ordem é do servidor (a página seguinte tem de continuar a mesma lista).
 */
import { AlertTriangle, ArrowDown, ArrowUp, ArrowUpDown, FileSearch } from "lucide-react";

import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/EmptyState";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { formatDateTime } from "../../lib/utils";
import { rotuloDoEstado, sentidoDaColuna } from "../../utils/indexRevisao";

const ICONE_DO_SENTIDO = { ascending: ArrowUp, descending: ArrowDown, none: ArrowUpDown };

/** Cabeçalho que ordena: botão com o nome da coluna, o sentido em vigor e `aria-sort` no `<th>`. */
function ColunaOrdenavel({ coluna, rotulo, separador, ordem, onOrdenar, className }) {
  const sentido = sentidoDaColuna(separador, ordem, coluna);
  const Icone = ICONE_DO_SENTIDO[sentido];
  if (!onOrdenar) return <TableHead className={className}>{rotulo}</TableHead>;
  return (
    <TableHead className={className} aria-sort={sentido}>
      <button
        type="button"
        onClick={() => onOrdenar(coluna)}
        className="inline-flex items-center gap-1 font-medium hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        data-testid={`ordenar-${coluna}`}
      >
        {rotulo}
        <Icone className={`h-3.5 w-3.5 ${sentido === "none" ? "opacity-40" : ""}`} aria-hidden="true" />
      </button>
    </TableHead>
  );
}

export function IndexQueueTable({ itens, separador, onAbrir, mensagemVazia, ordem, onOrdenar, comFiltros = false }) {
  if (!itens.length) {
    return (
      <EmptyState
        icon={FileSearch}
        title={mensagemVazia || (comFiltros ? "Nenhum processo com estes filtros" : "Nada por tratar")}
        message={
          comFiltros
            ? "Experimente tirar um filtro ou limpar a pesquisa."
            : separador === "reviews"
              ? "Quando um processo indexado ficar com campos por rever, aparece aqui."
              : "Os processos que esperam indexação aparecem aqui."
        }
      />
    );
  }

  return (
    <Table data-testid="index-queue-table">
      <TableHeader>
        <TableRow>
          <ColunaOrdenavel coluna="processo" rotulo="Processo" separador={separador} ordem={ordem} onOrdenar={onOrdenar} />
          <ColunaOrdenavel coluna="empresa" rotulo="Empresa/Origem" separador={separador} ordem={ordem} onOrdenar={onOrdenar} />
          <ColunaOrdenavel coluna="estado" rotulo="Estado" separador={separador} ordem={ordem} onOrdenar={onOrdenar} />
          <TableHead className="text-right">Documentos</TableHead>
          <ColunaOrdenavel coluna="alertas" rotulo="Alertas" separador={separador} ordem={ordem} onOrdenar={onOrdenar} className="text-right" />
          <ColunaOrdenavel
            coluna="data"
            rotulo={separador === "reviews" ? "Indexado em" : "Entrada"}
            separador={separador}
            ordem={ordem}
            onOrdenar={onOrdenar}
          />
          <TableHead className="sr-only">Acções</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {itens.map((p) => (
          <TableRow key={p.id} data-testid="index-queue-row">
            <TableCell>
              <div className="font-medium">{p.client_name || "—"}</div>
              <div className="text-xs text-muted-foreground">
                {p.process_number ? `#${p.process_number}` : String(p.id).slice(0, 8)}
              </div>
            </TableCell>
            <TableCell data-testid="index-queue-origem">
              {p.company?.name ? (
                <div className="text-sm">
                  {p.company.name}
                  {p.company.other_network === true && (
                    <Badge variant="secondary" className="ml-1">
                      Partilhado
                    </Badge>
                  )}
                </div>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </TableCell>
            <TableCell>
              <Badge variant={p.index_status === "in_review" ? "default" : "outline"}>
                {rotuloDoEstado(p.index_status, p.index_skipped)}
              </Badge>
              {p.has_pending_review && (
                <Badge variant="secondary" className="ml-1">
                  A rever
                </Badge>
              )}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {p.documents_total ?? 0}
              {p.documents_to_analyse > 0 && (
                <span className="ml-1 text-xs text-muted-foreground">({p.documents_to_analyse} por analisar)</span>
              )}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {p.index_alerts_open > 0 ? (
                <span className="inline-flex items-center gap-1 text-[hsl(var(--warning))]">
                  <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                  {p.index_alerts_open}
                </span>
              ) : (
                "0"
              )}
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {formatDateTime(separador === "reviews" ? p.indexed_at : p.created_at) || "—"}
            </TableCell>
            <TableCell className="text-right">
              <Button size="sm" variant="outline" onClick={() => onAbrir(p.id)}>
                {`Abrir ${p.client_name || "processo"}`}
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

export default IndexQueueTable;
