/**
 * ProcessTimeline - Timeline visual do processo
 * Mostra a evolução do processo através das diferentes fases
 * 
 * Usa as fases dinâmicas da BD (workflow_statuses) em vez de dados hardcoded.
 */
import React, { useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { ScrollArea, ScrollBar } from "./ui/scroll-area";
import { Loader2, CheckCircle, Clock, Circle, ArrowRight } from "lucide-react";
import { pt } from "date-fns/locale";
import { safeLabel } from "./dashboard/DashboardShared";
import { safeFormat } from "../lib/utils";
import { construirTimeline } from "../utils/processTimeline";

// Cores de fallback mapeadas a partir do nome da cor da BD
const COLOR_MAP = {
  yellow: "#FCD34D", amber: "#F59E0B", orange: "#F97316", red: "#EF4444",
  green: "#22C55E", emerald: "#10B981", teal: "#14B8A6", cyan: "#06B6D4",
  blue: "#3B82F6", indigo: "#6366F1", violet: "#8B5CF6", purple: "#A855F7",
  pink: "#EC4899", rose: "#F43F5E", gray: "#6B7280", slate: "#64748B",
  lime: "#84CC16", sky: "#0EA5E9", fuchsia: "#D946EF",
};

const getColor = (colorName) => {
  if (!colorName) return "#6B7280";
  // Se já é um hex color
  if (colorName.startsWith("#")) return colorName;
  return COLOR_MAP[colorName.toLowerCase()] || "#6B7280";
};

// Componente de nó da timeline (compacto)
// PACOTE CY: adicionado isSkipped para fases saltadas (sem registo no histórico)
const TimelineNode = ({ phaseInfo, isCompleted, isCurrent, isSkipped, date, daysInPhase }) => {
  const nodeColor = phaseInfo ? getColor(phaseInfo.color) : "#9CA3AF";
  const label = phaseInfo?.label || phaseInfo?.name || "Desconhecida";

  return (
    <div className="flex flex-col items-center min-w-[80px]">
      {/* Nó */}
      <div
        className={`w-6 h-6 rounded-full flex items-center justify-center border-2 transition-all ${
          isCompleted
            ? "bg-green-500 border-green-500 text-white"
            : isCurrent
            ? "border-blue-500 bg-blue-50"
            : isSkipped
            ? "border-gray-300 bg-gray-50 border-dashed"
            : "border-gray-300 bg-white"
        }`}
        style={isCurrent ? { borderColor: nodeColor } : {}}
      >
        {isCompleted ? (
          <CheckCircle className="h-3 w-3" />
        ) : isCurrent ? (
          <Circle className="h-3 w-3" style={{ color: nodeColor }} />
        ) : (
          <Circle className="h-3 w-3 text-gray-300" />
        )}
      </div>

      {/* Label */}
      <div className="mt-1 text-center max-w-[80px]">
        <p className={`text-[10px] font-medium leading-tight ${
          isCurrent ? "text-blue-600" : isCompleted ? "text-green-600" : isSkipped ? "text-gray-400 italic" : "text-gray-500"
        }`}>
          {safeLabel(label)}
        </p>
        {date && (
          <p className="text-[9px] text-muted-foreground">
            {safeFormat(date, "dd/MM", { locale: pt })}
          </p>
        )}
        {isSkipped && (
          <p data-testid="fase-saltada" className="text-[8px] text-gray-400 italic">Saltada</p>
        )}
        {daysInPhase !== undefined && daysInPhase > 0 && (
          <Badge variant="outline" className="text-[9px] mt-0.5 px-1 py-0">
            {daysInPhase}d
          </Badge>
        )}
      </div>
    </div>
  );
};

// Componente de conector (compacto)
const TimelineConnector = ({ isCompleted }) => (
  <div className="flex items-center -mt-4">
    <div
      className={`h-0.5 w-4 ${
        isCompleted ? "bg-green-500" : "bg-gray-200"
      }`}
    />
    <ArrowRight
      className={`h-2 w-2 -ml-0.5 ${
        isCompleted ? "text-green-500" : "text-gray-300"
      }`}
    />
  </div>
);

const ProcessTimeline = ({ currentStatus, history, workflowStatuses }) => {
  // "UI de Fases Mentirosa" (Lote 5, P0): a decisão sobre o que está
  // concluído, saltado ou pendente — e quanto tempo cada fase durou —
  // mudou para `utils/processTimeline.js`, onde se consegue testar.
  // Aqui dentro não se testava, e era aqui que a UI passava por cima do
  // motor de workflow com um mapa de aliases cravado em código.
  const timelineData = useMemo(
    () =>
      construirTimeline({
        fases: workflowStatuses,
        estadoActual: currentStatus,
        historico: history,
      }),
    [workflowStatuses, currentStatus, history],
  );

  const loading = !Array.isArray(workflowStatuses);
  const faseActual = timelineData.find((f) => f.isCurrent)?.phaseInfo || null;

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-4">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  // Estatísticas do cabeçalho. O total de dias já não soma a mesma
  // janela de tempo várias vezes: cada fase mede da sua entrada até à
  // entrada na seguinte, por isso a soma é o tempo real decorrido.
  const completedPhases = timelineData.filter(t => t.isCompleted).length;
  const totalDays = timelineData.reduce((acc, t) => acc + (t.daysInPhase || 0), 0);

  return (
    <Card data-testid="process-timeline" className="overflow-hidden">
      <CardHeader className="py-2 px-4">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5" />
            Timeline
          </CardTitle>
          <div className="flex items-center gap-2">
            {faseActual && (
              <Badge
                data-testid="fase-actual"
                className="text-[10px] px-1.5 py-0"
                style={{ backgroundColor: getColor(faseActual.color), color: '#fff' }}
              >
                {safeLabel(faseActual.label || faseActual.name)}
              </Badge>
            )}
          </div>
        </div>
        {totalDays > 0 && (
          <p className="text-[10px] text-muted-foreground">
            {completedPhases} fases concluídas • {totalDays} dias no processo
          </p>
        )}
      </CardHeader>

      <CardContent className="pt-0 pb-2 px-3">
        <ScrollArea className="w-full">
          <div className="flex items-start py-2 px-1">
            {timelineData.map((item, index) => (
              <React.Fragment key={item.phase}>
                <TimelineNode
                  phaseInfo={item.phaseInfo}
                  isCompleted={item.isCompleted}
                  isCurrent={item.isCurrent}
                  isSkipped={item.isSkipped}
                  date={item.date}
                  daysInPhase={item.daysInPhase}
                />
                {index < timelineData.length - 1 && (
                  <TimelineConnector isCompleted={item.isCompleted} />
                )}
              </React.Fragment>
            ))}
          </div>
          <ScrollBar orientation="horizontal" />
        </ScrollArea>

        {/* Legenda compacta */}
        <div className="flex items-center gap-3 pt-2 border-t text-[10px] text-muted-foreground">
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-green-500" />
            <span>Concluído</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full border border-blue-500 bg-blue-50" />
            <span>Atual</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full border border-gray-300" />
            <span>Pendente</span>
          </div>
          {/* PACOTE CY — novo estado Saltada */}
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full border border-gray-300 border-dashed bg-gray-50" />
            <span>Saltada</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

export default ProcessTimeline;
