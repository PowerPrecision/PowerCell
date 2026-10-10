/**
 * Indicadores do período — um cartão por número (Bloco 4, pontos 13 e 16).
 * Apresentação pura: recebe o resumo do servidor; com `utilizador`, mostra o
 * dele em vez do da equipa.
 */
import { AlertTriangle, CheckCircle, Clock, GitBranch, TrendingUp } from "lucide-react";

import { Card, CardContent } from "../ui/card";
import { valorOuTraco } from "../../utils/executivo";

const INDICADORES = [
  { id: "fases", rotulo: "Fases alteradas", Icone: GitBranch, equipa: "total_phase_changes", pessoa: "phase_changes", tom: "text-primary" },
  { id: "processos", rotulo: "Processos avançados", Icone: TrendingUp, equipa: "total_processes_moved", pessoa: "processes_moved", tom: "text-primary" },
  { id: "concluidas", rotulo: "Tarefas concluídas", Icone: CheckCircle, equipa: "total_tasks_completed", pessoa: "tasks_completed", tom: "text-foreground" },
  { id: "pendentes", rotulo: "Tarefas pendentes", Icone: Clock, equipa: "total_tasks_pending", pessoa: "tasks_pending", tom: "text-foreground" },
  { id: "atraso", rotulo: "Tarefas em atraso", Icone: AlertTriangle, equipa: "total_tasks_overdue", pessoa: "tasks_overdue", tom: "text-destructive" },
];

/**
 * @param {Object} props
 * @param {object} [props.summary]
 * @param {object|null} [props.utilizador] - Se existir, mostra os números dele.
 */
export default function ExecutiveKpis({ summary, utilizador = null }) {
  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4" data-testid="indicadores-executivos">
      {INDICADORES.map(({ id, rotulo, Icone, equipa, pessoa, tom }) => {
        const valor = utilizador ? utilizador[pessoa] : summary?.[equipa];
        return (
          <Card key={id}>
            <CardContent className="p-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center shrink-0">
                <Icone className={`h-5 w-5 ${tom}`} aria-hidden="true" />
              </div>
              <div className="min-w-0">
                <p className={`text-2xl font-bold ${tom}`} data-testid={`indicador-${id}`}>
                  {valor === undefined ? "—" : valorOuTraco(valor)}
                </p>
                <p className="text-xs text-muted-foreground">{rotulo}</p>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
