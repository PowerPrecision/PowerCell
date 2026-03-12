/**
 * ProcessTimeline - Timeline visual do processo
 * Mostra a evolução do processo através das diferentes fases
 */
import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";
import { ScrollArea, ScrollBar } from "./ui/scroll-area";
import { Loader2, CheckCircle, Clock, Circle, ArrowRight } from "lucide-react";
import { format, parseISO, differenceInDays } from "date-fns";
import { pt } from "date-fns/locale";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Fases do processo de crédito habitação
const PROCESS_PHASES = [
  { id: "clientes_espera", label: "Clientes em Espera", color: "#FCD34D", order: 1 },
  { id: "fase_documental", label: "Fase Documental", color: "#60A5FA", order: 2 },
  { id: "entregue_aos_intermediarios", label: "Entregue aos Intermediários", color: "#A78BFA", order: 3 },
  { id: "enviado_ao_bruno", label: "Enviado ao Bruno", color: "#F97316", order: 4 },
  { id: "enviado_ao_luis", label: "Enviado ao Luís", color: "#FB923C", order: 5 },
  { id: "banco_em_analise", label: "Banco em Análise", color: "#38BDF8", order: 6 },
  { id: "aprovado_pelo_banco", label: "Aprovado pelo Banco", color: "#4ADE80", order: 7 },
  { id: "cpcv", label: "CPCV", color: "#22D3EE", order: 8 },
  { id: "a_escriturar", label: "A Escriturar", color: "#818CF8", order: 9 },
  { id: "escriturado", label: "Escriturado", color: "#10B981", order: 10 },
  { id: "recusado", label: "Recusado", color: "#EF4444", order: 99 },
  { id: "desistiu", label: "Desistiu", color: "#6B7280", order: 98 },
];

// Normalizar status (mapear variantes para o ID principal)
const normalizeStatus = (status) => {
  const statusMap = {
    "clientes_em_espera": "clientes_espera",
  };
  return statusMap[status] || status;
};

// Componente de nó da timeline (compacto)
const TimelineNode = ({ phase, isCompleted, isCurrent, date, daysInPhase }) => {
  const phaseInfo = PROCESS_PHASES.find(p => p.id === phase) || { 
    label: phase, 
    color: "#9CA3AF" 
  };

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
        style={isCurrent ? { borderColor: phaseInfo.color } : {}}
      >
        {isCompleted ? (
          <CheckCircle className="h-3 w-3" />
        ) : isCurrent ? (
          <Circle className="h-3 w-3" style={{ color: phaseInfo.color }} />
        ) : (
          <Circle className="h-3 w-3 text-gray-300" />
        )}
      </div>

      {/* Label */}
      <div className="mt-1 text-center max-w-[80px]">
        <p className={`text-[10px] font-medium leading-tight ${isCurrent ? "text-blue-600" : isCompleted ? "text-green-600" : "text-gray-500"}`}>
          {phaseInfo.label}
        </p>
        {date && (
          <p className="text-[9px] text-muted-foreground">
            {format(parseISO(date), "dd/MM", { locale: pt })}
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

const ProcessTimeline = ({ processId, currentStatus, history }) => {
  const { token } = useAuth();
  const [timelineData, setTimelineData] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Normalizar o status atual
  const normalizedCurrentStatus = normalizeStatus(currentStatus);

  // Processar histórico para construir timeline
  const buildTimeline = useCallback(() => {
    // Encontrar a fase atual
    const currentPhaseInfo = PROCESS_PHASES.find(p => p.id === normalizedCurrentStatus);
    const currentOrder = currentPhaseInfo?.order || 0;

    // Se não há histórico, mostrar todas as fases até a atual
    if (!history || history.length === 0) {
      const timeline = PROCESS_PHASES
        .filter(p => p.order <= currentOrder && p.order < 90) // Excluir recusado/desistiu
        .map(p => ({
          phase: p.id,
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
      new Date(a.timestamp || a.created_at) - new Date(b.timestamp || b.created_at)
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
          ? differenceInDays(parseISO(nextDate), parseISO(entryDate))
          : 0;

        timeline.push({
          phase: status,
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
        date: null,
        isCurrent: true,
        isCompleted: false,
      });
    }

    // Ordenar pela ordem das fases
    timeline.sort((a, b) => {
      const orderA = PROCESS_PHASES.find(p => p.id === a.phase)?.order || 50;
      const orderB = PROCESS_PHASES.find(p => p.id === b.phase)?.order || 50;
      return orderA - orderB;
    });

    setTimelineData(timeline);
    setLoading(false);
  }, [history, normalizedCurrentStatus]);

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
  const currentPhaseInfo = PROCESS_PHASES.find(p => p.id === normalizedCurrentStatus);

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
                style={{ backgroundColor: currentPhaseInfo.color, color: '#fff' }}
              >
                {currentPhaseInfo.label}
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
                  phase={item.phase}
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
