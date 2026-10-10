/**
 * Tabela por colaborador (Bloco 4, pontos 13 e 16). É a alternativa em texto
 * dos gráficos: a identidade nunca depende só da cor.
 *
 * O histórico desligado aparece como «—» com explicação — um 0 diria «não
 * fez nada» quando o que é verdade é «não se regista».
 */
import { AlertTriangle } from "lucide-react";

import { Badge } from "../ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import {
  ROTULOS_DOS_PAPEIS,
  listaOuVazia,
  pontuacao,
  taxaDeConclusao,
  valorOuTraco,
} from "../../utils/executivo";

const SEM_HISTORICO = "O histórico deste utilizador está desligado: as mudanças de fase não são registadas.";

/**
 * @param {Object} props
 * @param {Array} props.utilizadores
 * @param {string} [props.selecionado] - `user_id` realçado.
 * @param {(userId: string) => void} [props.onSelecionar]
 */
export default function ExecutiveUsersTable({ utilizadores, selecionado = "", onSelecionar }) {
  const linhas = listaOuVazia(utilizadores);
  if (linhas.length === 0) {
    return (
      <p className="text-center py-10 text-sm text-muted-foreground">
        Sem colaboradores para os filtros seleccionados
      </p>
    );
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-10">#</TableHead>
            <TableHead>Colaborador</TableHead>
            <TableHead>Perfil</TableHead>
            <TableHead className="text-center">Fases alteradas</TableHead>
            <TableHead className="text-center">Processos</TableHead>
            <TableHead className="text-center">Concluídas</TableHead>
            <TableHead className="text-center">Pendentes</TableHead>
            <TableHead className="text-center">Em atraso</TableHead>
            <TableHead className="text-center">Conclusão</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {linhas.map((u, indice) => {
            const taxa = taxaDeConclusao(u);
            const clicavel = typeof onSelecionar === "function";
            return (
              <TableRow
                key={u.user_id}
                data-testid={`linha-${u.user_id}`}
                className={`${clicavel ? "cursor-pointer" : ""} hover:bg-muted/50 ${selecionado === u.user_id ? "bg-muted" : ""}`}
                onClick={clicavel ? () => onSelecionar(u.user_id) : undefined}
              >
                <TableCell className="text-muted-foreground">{indice + 1}</TableCell>
                <TableCell className="font-medium">
                  <span className="flex items-center gap-2">
                    {u.name}
                    {pontuacao(u) >= 10 && <Badge variant="secondary" className="text-[10px] px-1.5">Top</Badge>}
                  </span>
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">{ROTULOS_DOS_PAPEIS[u.role] || u.role}</TableCell>
                <TableCell className="text-center font-semibold" title={u.historico_silenciado ? SEM_HISTORICO : undefined}>
                  {valorOuTraco(u.phase_changes)}
                </TableCell>
                <TableCell className="text-center" title={u.historico_silenciado ? SEM_HISTORICO : undefined}>
                  {valorOuTraco(u.processes_moved)}
                </TableCell>
                <TableCell className="text-center font-semibold">{u.tasks_completed}</TableCell>
                <TableCell className="text-center">{u.tasks_pending}</TableCell>
                <TableCell className={`text-center font-semibold ${u.tasks_overdue > 0 ? "text-destructive" : "text-muted-foreground"}`}>
                  {u.tasks_overdue > 0 ? (
                    <span className="inline-flex items-center justify-center gap-1">
                      <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
                      {u.tasks_overdue}
                    </span>
                  ) : "0"}
                </TableCell>
                <TableCell className="text-center">
                  <Badge variant="outline">{taxa === null ? "—" : `${taxa}%`}</Badge>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
