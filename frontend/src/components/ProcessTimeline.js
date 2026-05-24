/**
 * ProcessTimeline - Timeline visual do processo
 * Mostra a evolução do processo através das diferentes fases
 * 
 * Usa as fases dinâmicas da BD (workflow_statuses) em vez de dados hardcoded.
 */
import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { ScrollArea, ScrollBar } from "./ui/scroll-area";
import { Loader2, CheckCircle, Clock, Circle, ArrowRight } from "lucide-react";
import { differenceInDays } from "date-fns";
import { pt } from "date-fns/locale";
import { safeLabel } from "./dashboard/DashboardShared";
import { safeDateStr, safeFormat } from "../lib/utils";

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

// Normalizar status (mapear variantes antigas para o nome atual na BD)
const normalizeStatus = (status) => {
  if (!status) return status;
  const statusMap = {
    "clientes_em_espera": "clientes_espera",
    "enviado_ao_bruno": "enviado_bruno",
    "enviado_ao_luis": "enviado_luis",
    "banco_em_analise": "fase_bancaria",
    "aprovado_pelo_banco": "ch_aprovado",
    "cpcv": "fase_escritura",
    "a_escriturar": "escritura_agendada",
    "escriturado": "concluidos",
    "recusado": "desistencias",
    "desistiu": "desistencias",
  };
  return statusMap[status] || status;
};

// Componente de nó da timeline (compacto)
const TimelineNode = ({ phaseInfo, isCompleted, isCurrent, date, daysInPhase }) => {
  const nodeColor = phaseInfo ? getColor(phaseInfo.color) : "#9CA3AF";
  const label = phaseInfo?.label || "Desconhecida";

  return (
    <div className="flex flex-col items-center min-w-[80px]">
      {/* Nó */}
      <div
        className={`w-6 h-6 rounded-full flex items-center justify-center border-2 transition-all ${
          isCompleted
            ? "bg-green-500 border-green-500 text-white"
            : isCurrent
            ? "border-blue-500 bg-blue-50"
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
        <p className={`text-[10px] font-medium leading-tight ${isCurrent ? "text-blue-600" : isCompleted ? "text-green-600" : "text-gray-500"}`}>
          {safeLabel(label)}
        </p>
        {date && (
          <p className="text-[9px] text-muted-foreground">
            {safeFormat(date, "dd/MM", { locale: pt })}
          </p>
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

const ProcessTimeline = ({ processId, currentStatus, history, workflowStatuses }) => {
  const { token } = useAuth();
  const [timelineData, setTimelineData] = useState([]);
  const [loading, setLoading] = useState(true);

  // Construir mapa de fases a partir dos workflowStatuses dinâmicos
  const phasesMap = useMemo(() => {
    if (!workflowStatuses || workflowStatuses.length === 0) return {};
    const map = {};
    workflowStatuses.forEach(s => {
      map[s.name] = {
        id: s.name,
        label: s.label || s.name,
        color: getColor(s.color),
        order: s.order || 0,
      };
    });
    return map;
  }, [workflowStatuses]);

  // Lista de fases ordenada
  const sortedPhases = useMemo(() => {
    return Object.values(phasesMap).sort((a, b) => a.order - b.order);
  }, [phasesMap]);

  // Normalizar o status atual
  const normalizedCurrentStatus = normalizeStatus(currentStatus);

  // Encontrar a fase atual (declarado ANTES do useCallback para evitar temporal dead zone)
  const currentPhaseInfo = phasesMap[normalizedCurrentStatus];
  const currentOrder = currentPhaseInfo?.order || 0;

  // Processar histórico para construir timeline
  const buildTimeline = useCallback(() => {

    // Se não há fases carregadas, não mostrar nada
    if (sortedPhases.length === 0) {
      setTimelineData([]);
      setLoading(false);
      return;
    }

    // Se não há histórico, mostrar todas as fases até a atual
    if (!history || history.length === 0) {
      const timeline = sortedPhases
        .filter(p => p.order <= currentOrder)
        .map(p => ({
          phase: p.id,
          phaseInfo: p,
          date: null,
          isCurrent: p.id === normalizedCurrentStatus,
          isCompleted: p.order < currentOrder,
        }));
      
      setTimelineData(timeline);
      setLoading(false);
      return;
    }

    // Ordenar histórico por data
    const sortedHistory = [...history].sort((a, b) => 
      new Date(safeDateStr(a.timestamp || a.created_at)) - new Date(safeDateStr(b.timestamp || b.created_at))
    );

    // Construir timeline a partir do histórico
    const timeline = [];
    const seenPhases = new Set();

    sortedHistory.forEach((entry, index) => {
      const status = normalizeStatus(entry.new_status || entry.status);
      if (status && !seenPhases.has(status)) {
        seenPhases.add(status);
        
        const nextEntry = sortedHistory[index + 1];
        const entryDate = entry.timestamp || entry.created_at;
        const nextDate = nextEntry ? (nextEntry.timestamp || nextEntry.created_at) : new Date().toISOString();
        
        const daysInPhase = entryDate && nextDate 
          ? differenceInDays(safeParseISO(nextDate), safeParseISO(entryDate))
          : 0;

        timeline.push({
          phase: status,
          phaseInfo: phasesMap[status] || { id: status, label: status, color: "#6B7280", order: 50 },
          date: entryDate,
          daysInPhase: status !== normalizedCurrentStatus ? daysInPhase : undefined,
          isCurrent: status === normalizedCurrentStatus,
          isCompleted: status !== normalizedCurrentStatus,
        });
      }
    });

    // Adicionar fase atual se não estiver no histórico
    if (!seenPhases.has(normalizedCurrentStatus)) {
      timeline.push({
        phase: normalizedCurrentStatus,
        phaseInfo: currentPhaseInfo || { id: normalizedCurrentStatus, label: normalizedCurrentStatus, color: "#6B7280", order: currentOrder },
        date: null,
        isCurrent: true,
        isCompleted: false,
      });
    }

    // Ordenar pela ordem das fases (usando order da BD)
    timeline.sort((a, b) => (a.phaseInfo?.order || 50) - (b.phaseInfo?.order || 50));

    setTimelineData(timeline);
    setLoading(false);
  }, [history, normalizedCurrentStatus, phasesMap, sortedPhases, currentPhaseInfo]);

  useEffect(() => {
    buildTimeline();
  }, [buildTimeline]);

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-4">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  // Calcular estatísticas
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
            {currentPhaseInfo && (
              <Badge 
                className="text-[10px] px-1.5 py-0"
                style={{ backgroundColor: getColor(currentPhaseInfo.color), color: '#fff' }}
              >
                {safeLabel(currentPhaseInfo.label)}
              </Badge>
            )}
          </div>
        </div>
        {totalDays > 0 && (
          <p className="text-[10px] text-muted-foreground">
            {completedPhases} fases • {totalDays} dias
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
        </div>
      </CardContent>
    </Card>
  );
};

export default ProcessTimeline;
