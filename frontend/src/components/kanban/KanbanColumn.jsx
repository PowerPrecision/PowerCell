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
 */
import React, { memo, useCallback } from 'react';
import { Badge } from '../ui/badge';
import { Button } from '../ui/button';
import { ScrollArea } from '../ui/scroll-area';
import { ChevronLeft, ChevronRight, Users } from 'lucide-react';
import KanbanCard from './KanbanCard';
import { statusColors, statusHeaderColors } from './constants';

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
}) => {
  const isEmpty = column.count === 0;
  const isDragOver = dragOverColumn === column.name;

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
              {column.order || ''} - {column.label}
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
            {column.order || ''} - {column.label}
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
      </div>

      {/* Column Content */}
      <div className={`${statusColors[column.color] || "bg-gray-100"} min-h-[60vh] rounded-b-lg p-2`}>
        <ScrollArea className="h-[60vh]">
          <div className="space-y-2 pr-2">
            {column.processes.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground text-sm">
                <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>Nenhum processo</p>
              </div>
            ) : (
              column.processes.map((process) => (
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
              ))
            )}
          </div>
        </ScrollArea>
      </div>
    </div>
  );
});

KanbanColumn.displayName = 'KanbanColumn';

export default KanbanColumn;
