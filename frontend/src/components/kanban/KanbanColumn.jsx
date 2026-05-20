/**
 * KanbanColumn Component
 * 
 * Coluna do Kanban - contentor que recebe eventos de drop.
 * 
 * RESPONSABILIDADES:
 * - Renderizar header da coluna com contagem
 * - Receber eventos de drag & drop
 * - Renderizar lista de KanbanCard
 * - Suportar estado colapsado/expandido
 * - Na coluna 'concluidos': seletor de datas e botão "Ver mais antigos"
 * 
 * @param {Object} column - Dados da coluna (id, name, label, color, order, count, processes)
 * @param {boolean} isCollapsed - Se a coluna está colapsada
 * @param {string} dragOverColumn - Nome da coluna sobre a qual está a ser feito drag
 * @param {Function} onDragOver - Handler de drag over
 * @param {Function} onDragLeave - Handler de drag leave
 * @param {Function} onDrop - Handler de drop
 * @param {Function} onToggleCollapse - Handler para toggle de collapse
 * @param {Function} onDragStart - Handler de início de drag (passado aos cards)
 * @param {Function} onCardClick - Handler de clique no card (passado aos cards)
 * @param {Object} draggingCard - Card atualmente a ser arrastado
 * @param {number} completedDays - Filtro de dias para concluídos (default 30, 0 = sem limite)
 * @param {Function} onCompletedDaysChange - Callback para alterar o filtro de dias
 */
import React, { memo, useCallback } from 'react';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { ScrollArea } from '../ui/scroll-area';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '../ui/select';
import { ChevronLeft, ChevronRight, Users, Calendar, History, Loader2 } from 'lucide-react';
import KanbanCard from './KanbanCard';
import { statusColors, statusHeaderColors } from './constants';
import { safeLabel } from '../dashboard/DashboardShared';

const KanbanColumn = memo(({
  column,
  isCollapsed,
  dragOverColumn,
  onDragOver,
  onDragLeave,
  onDrop,
  onToggleCollapse,
  onDragStart,
  onCardClick,
  draggingCard,
  lockedProcesses = {},
  completedDays = 30,
  onCompletedDaysChange,
  isFetchingCompleted = false,
}) => {
  const isEmpty = column.count === 0;
  const isDragOver = dragOverColumn === column.name;
  const isConcluidosColumn = column.name === 'concluidos';
  const isDesistenciasColumn = column.name === 'desistencias';
  const isInactiveColumn = isConcluidosColumn || isDesistenciasColumn;

  // Handlers memoizados
  const handleDragOver = useCallback((e) => {
    onDragOver?.(e, column.name);
  }, [onDragOver, column.name]);

  const handleDrop = useCallback((e) => {
    onDrop?.(e, column.name);
  }, [onDrop, column.name]);

  const handleToggleCollapse = useCallback(() => {
    onToggleCollapse?.(column.id);
  }, [onToggleCollapse, column.id]);

  // Render coluna colapsada
  if (isCollapsed) {
    return (
      <div
        className={`flex-shrink-0 w-[50px] rounded-lg border-2 transition-all ${
          isDragOver ? "border-primary border-dashed bg-primary/5" : "border-transparent"
        }`}
        onDragOver={handleDragOver}
        onDragLeave={onDragLeave}
        onDrop={handleDrop}
      >
        <div 
          className={`${statusHeaderColors[column.color] || "bg-gray-500"} min-h-[70vh] rounded-lg flex flex-col items-center justify-between py-4 cursor-pointer`}
          onClick={handleToggleCollapse}
          title="Clique para expandir"
        >
          <Badge variant="secondary" className="bg-white/20 text-white hover:bg-white/30">
            {column.count}
          </Badge>
          <div className="flex-1 flex items-center justify-center px-1">
            <span
              className="text-white text-xs font-medium text-center overflow-hidden"
              style={{ writingMode: 'vertical-rl', textOrientation: 'mixed' }}
            >
              {column.order || ''} - {safeLabel(column.label)}
            </span>
          </div>
          <ChevronRight className="h-4 w-4 text-white/70" />
        </div>
      </div>
    );
  }

  // Render coluna expandida
  return (
    <div
      className={`flex-shrink-0 w-[320px] rounded-lg border-2 transition-all ${
        isDragOver ? "border-primary border-dashed bg-primary/5" : "border-transparent"
      }`}
      onDragOver={handleDragOver}
      onDragLeave={onDragLeave}
      onDrop={handleDrop}
    >
      {/* Column Header */}
      <div 
        className={`${statusHeaderColors[column.color] || "bg-gray-500"} rounded-t-lg px-4 py-3 cursor-pointer`}
        onClick={isEmpty ? handleToggleCollapse : undefined}
        title={isEmpty ? "Clique para minimizar" : ""}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-white text-sm truncate">
            {column.order || ''} - {safeLabel(column.label)}
          </h3>
          <div className="flex items-center gap-1">
            <Badge variant="secondary" className="bg-white/20 text-white hover:bg-white/30">
              {column.count}
            </Badge>
            {isEmpty && (
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 text-white/70 hover:text-white hover:bg-white/20"
                onClick={(e) => { e.stopPropagation(); handleToggleCollapse(); }}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>
        
        {/* Seletor de período para coluna Concluídos */}
        {isConcluidosColumn && onCompletedDaysChange && (
          <div 
            className="mt-2 flex items-center gap-2"
            onClick={(e) => e.stopPropagation()}
          >
            <Calendar className="h-3.5 w-3.5 text-white/70 flex-shrink-0" />
            <Select 
              value={String(completedDays)} 
              onValueChange={(v) => onCompletedDaysChange(Number(v))}
            >
              <SelectTrigger className="h-7 text-xs bg-white/15 border-white/20 text-white hover:bg-white/25 focus:ring-white/30 w-full">
                <SelectValue placeholder="Período" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Últimos 7 dias</SelectItem>
                <SelectItem value="15">Últimos 15 dias</SelectItem>
                <SelectItem value="30">Últimos 30 dias</SelectItem>
                <SelectItem value="90">Últimos 90 dias</SelectItem>
                <SelectItem value="0">Todos (sem limite)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      {/* Column Content */}
      <div className={`${statusColors[column.color] || "bg-gray-100"} min-h-[60vh] rounded-b-lg p-2 flex flex-col`}>
        <ScrollArea className="h-[60vh]">
          <div className="space-y-2 pr-2">
            {/* Skeleton de loading LOCAL — aparece APENAS na coluna Concluídos enquanto a query segmentada está a fetching */}
            {isFetchingCompleted && column.processes.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">
                <Loader2 className="h-8 w-8 mx-auto mb-2 animate-spin opacity-50" />
                <p>A carregar processos...</p>
              </div>
            ) : column.processes.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">
                <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>Nenhum processo</p>
                {isInactiveColumn && completedDays > 0 && (
                  <p className="text-xs mt-1 opacity-70">
                    Mostrando apenas últimos {completedDays} dias
                  </p>
                )}
              </div>
            ) : (
              <>
                {/* Indicador de loading no topo da coluna — sem deslocar os cards existentes */}
                {isFetchingCompleted && (
                  <div className="flex items-center justify-center gap-1.5 py-1 mb-1 text-xs text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span>A actualizar...</span>
                  </div>
                )}
                {column.processes.map((process) => (
                  <KanbanCard
                    key={process.id}
                    process={process}
                    columnName={column.name}
                    draggingCard={draggingCard}
                    onDragStart={onDragStart}
                    onCardClick={onCardClick}
                    isLocked={!!lockedProcesses[process.id]}
                    lockedBy={lockedProcesses[process.id]?.user_name}
                  />
                ))}
              </>
            )}
          </div>
        </ScrollArea>
        
        {/* Botão "Ver processos mais antigos" no fundo da coluna Concluídos */}
        {isConcluidosColumn && completedDays > 0 && (
          <div className="pt-2 px-1 border-t border-border/30 mt-auto">
            <Button
              variant="ghost"
              size="sm"
              className="w-full text-xs gap-1.5 text-muted-foreground hover:text-foreground"
              onClick={() => onCompletedDaysChange?.(0)}
            >
              <History className="h-3.5 w-3.5" />
              Ver processos mais antigos
            </Button>
          </div>
        )}
      </div>
    </div>
  );
});

KanbanColumn.displayName = 'KanbanColumn';

export default KanbanColumn;
