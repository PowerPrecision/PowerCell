/**
 * KanbanHeader Component
 * 
 * Header do Kanban com título, indicador de WebSocket, pesquisa e controlos de navegação.
 * 
 * RESPONSABILIDADE ÚNICA:
 * - Renderizar header do Kanban
 * - Gerir estado de pesquisa e filtros
 * - Fornecer controlos de navegação horizontal
 */
import React, { memo, useCallback } from 'react';
import { Input } from '../ui/input';
import { Button } from '../ui/button';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '../ui/select';
import { 
  Search, 
  ChevronLeft, 
  ChevronRight, 
  Calendar, 
  AlertCircle, 
  List, 
  LayoutGrid,
  Wifi,
  WifiOff,
  Archive
} from 'lucide-react';

const KanbanHeader = memo(({
  totalProcesses,
  totalInactive,
  visibleCount,
  isConnected,
  searchTerm,
  onSearchChange,
  viewMode,
  onViewModeChange,
  showViewToggle,
  dateFilter,
  onDateFilterChange,
  urgencyFilter,
  onUrgencyFilterChange,
  completedDays,
  onCompletedDaysChange,
  onScrollLeft,
  onScrollRight,
}) => {
  const handleSearchChange = useCallback((e) => {
    onSearchChange?.(e.target.value);
  }, [onSearchChange]);

  const handleClearFilters = useCallback(() => {
    onDateFilterChange?.('all');
    onUrgencyFilterChange?.('all');
    onCompletedDaysChange?.(30);
  }, [onDateFilterChange, onUrgencyFilterChange, onCompletedDaysChange]);

  return (
    <>
      {/* Main Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div>
            <h2 className="text-xl font-bold">Quadro Geral de Processos</h2>
            <p className="text-sm text-muted-foreground">
              {totalProcesses} processos{totalInactive > 0 ? ` • ${totalInactive} concluídos/desistências` : ''} • Arraste para mover entre fases ou clique para ver detalhes
            </p>
          </div>
          {/* WebSocket Connection Status Indicator */}
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs ${
            isConnected 
              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' 
              : 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
          }`}>
            {isConnected ? (
              <>
                <Wifi className="h-3 w-3" />
                <span className="hidden sm:inline">Tempo real</span>
              </>
            ) : (
              <>
                <WifiOff className="h-3 w-3" />
                <span className="hidden sm:inline">A reconectar...</span>
              </>
            )}
          </div>
        </div>
        
        <div className="flex items-center gap-2 w-full sm:w-auto">
          {/* Search Input */}
          <div className="relative flex-1 sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Pesquisar cliente..."
              className="pl-10"
              value={searchTerm}
              onChange={handleSearchChange}
            />
          </div>
          
          {/* View Mode Toggle */}
          {showViewToggle && (
            <div className="flex gap-1 border rounded-md p-1">
              <Button 
                variant={viewMode === 'kanban' ? 'default' : 'ghost'} 
                size="icon"
                className="h-8 w-8"
                onClick={() => onViewModeChange?.('kanban')}
              >
                <LayoutGrid className="h-4 w-4" />
              </Button>
              <Button 
                variant={viewMode === 'list' ? 'default' : 'ghost'} 
                size="icon"
                className="h-8 w-8"
                onClick={() => onViewModeChange?.('list')}
              >
                <List className="h-4 w-4" />
              </Button>
            </div>
          )}
          
          {/* Scroll Controls */}
          <div className="flex gap-1">
            <Button 
              variant="outline" 
              size="icon" 
              onClick={onScrollLeft} 
              aria-label="Deslocar para a esquerda"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button 
              variant="outline" 
              size="icon" 
              onClick={onScrollRight} 
              aria-label="Deslocar para a direita"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* Filters Row */}
      <div className="flex flex-wrap items-center gap-2" data-testid="kanban-filters">
        <Select value={dateFilter} onValueChange={onDateFilterChange}>
          <SelectTrigger className="h-8 w-full sm:w-[130px] text-xs" data-testid="kanban-date-filter">
            <Calendar className="h-3 w-3 mr-1" />
            <SelectValue placeholder="Data" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas as datas</SelectItem>
            <SelectItem value="today">Hoje</SelectItem>
            <SelectItem value="week">Última semana</SelectItem>
            <SelectItem value="month">Último mês</SelectItem>
          </SelectContent>
        </Select>
        
        <Select value={urgencyFilter} onValueChange={onUrgencyFilterChange}>
          <SelectTrigger className="h-8 w-full sm:w-[130px] text-xs" data-testid="kanban-urgency-filter">
            <AlertCircle className="h-3 w-3 mr-1" />
            <SelectValue placeholder="Urgência" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas</SelectItem>
            <SelectItem value="overdue">Atrasados (&gt;14d)</SelectItem>
            <SelectItem value="urgent">Urgentes (7-14d)</SelectItem>
            <SelectItem value="normal">Recentes (&lt;7d)</SelectItem>
          </SelectContent>
        </Select>
        
        {/* Filtro de Concluídos — período de datas */}
        <Select value={String(completedDays)} onValueChange={(v) => onCompletedDaysChange?.(Number(v))}>
          <SelectTrigger className="h-8 w-full sm:w-[160px] text-xs" data-testid="kanban-completed-filter">
            <Archive className="h-3 w-3 mr-1" />
            <SelectValue placeholder="Concluídos" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Últimos 7 dias</SelectItem>
            <SelectItem value="15">Últimos 15 dias</SelectItem>
            <SelectItem value="30">Últimos 30 dias</SelectItem>
            <SelectItem value="90">Últimos 90 dias</SelectItem>
            <SelectItem value="0">Todos (sem limite)</SelectItem>
          </SelectContent>
        </Select>
        
        {(dateFilter !== 'all' || urgencyFilter !== 'all' || completedDays !== 30) && (
          <Button 
            variant="ghost" 
            size="sm" 
            className="h-8 text-xs"
            onClick={handleClearFilters}
            data-testid="kanban-clear-filters"
          >
            Limpar filtros
          </Button>
        )}
        
        <span className="text-xs text-muted-foreground ml-auto">
          {visibleCount} processos visíveis
        </span>
      </div>
    </>
  );
});

KanbanHeader.displayName = 'KanbanHeader';

export default KanbanHeader;
