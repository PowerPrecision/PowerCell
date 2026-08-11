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
import { memo, useCallback, useState } from 'react';
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
  Archive,
  Download,
  Loader2,
  Bell,
  BellOff
} from 'lucide-react';
import { formatDate } from '../../lib/utils';

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
  isFetchingCompleted = false,
  columns = [],
  // ═══ Filtro "A Aguardar Ação" ═══
  showOnlyPendingActions = false,
  onTogglePendingActions,
  pendingActionsCount = 0,
}) => {
  const [exporting, setExporting] = useState(false);

  const handleExportExcel = useCallback(async () => {
    setExporting(true);
    try {
      const XLSX = await import('xlsx');
      // Achatar todos os processos de todas as colunas
      const allProcesses = columns.flatMap(col => 
        (col.processes || []).map(p => ({
          'Nome do Cliente': p.client_name || '—',
          'Nº Processo': p.process_number || '—',
          'Fase/Status': col.label || p.status || '—',
          'Valor Imóvel': p.real_estate_data?.valor_imovel 
            ? Number(p.real_estate_data.valor_imovel).toLocaleString('pt-PT') + '€' 
            : p.property_value 
              ? Number(p.property_value).toLocaleString('pt-PT') + '€' 
              : '—',
          'Consultor': p.consultor_name || p.assigned_consultor_name || '—',
          'Intermediário': p.mediador_name || p.assigned_intermediario_name || '—',
          'Prioridade': (p.prioridade || p.priority || '—').charAt(0).toUpperCase() + (p.prioridade || p.priority || '—').slice(1),
          'Indexado': p.is_indexed ? 'Sim' : 'Não',
          'Atualizado': formatDate(p.updated_at),
        }))
      );

      if (allProcesses.length === 0) {
        return;
      }

      const ws = XLSX.utils.json_to_sheet(allProcesses);
      // Ajustar larguras das colunas
      ws['!cols'] = [
        { wch: 30 }, // Nome do Cliente
        { wch: 12 }, // Nº Processo
        { wch: 25 }, // Fase/Status
        { wch: 16 }, // Valor Imóvel
        { wch: 22 }, // Consultor
        { wch: 22 }, // Intermediário
        { wch: 12 }, // Prioridade
        { wch: 10 }, // Indexado
        { wch: 14 }, // Atualizado
      ];
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Processos');
      const filename = `PowerCell_Processos_${new Date().toISOString().slice(0,10)}.xlsx`;
      XLSX.writeFile(wb, filename);
    } catch (error) {
      console.error('Erro ao exportar Excel:', error);
    } finally {
      setExporting(false);
    }
  }, [columns]);

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
                aria-label="Ver como quadro Kanban"
                aria-pressed={viewMode === 'kanban'}
              >
                <LayoutGrid className="h-4 w-4" />
              </Button>
              <Button 
                variant={viewMode === 'list' ? 'default' : 'ghost'} 
                size="icon"
                className="h-8 w-8"
                onClick={() => onViewModeChange?.('list')}
                aria-label="Ver como lista"
                aria-pressed={viewMode === 'list'}
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
          <SelectTrigger className="h-8 w-full sm:w-[130px] text-xs" data-testid="kanban-date-filter" aria-label="Filtrar por data">
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
          <SelectTrigger className="h-8 w-full sm:w-[130px] text-xs" data-testid="kanban-urgency-filter" aria-label="Filtrar por urgência">
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
        
        {/* Filtro de Concluídos — período de datas (com indicador de loading isolado) */}
        <div className="relative">
          <Select value={String(completedDays)} onValueChange={(v) => onCompletedDaysChange?.(Number(v))}>
            <SelectTrigger className="h-8 w-full sm:w-[160px] text-xs" data-testid="kanban-completed-filter" aria-label="Filtrar concluídos por período">
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
          {/* Spinner de loading — aparece APENAS quando a query isolada de Concluídos está a fetching */}
          {isFetchingCompleted && (
            <div className="absolute -top-1 -right-1 h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-blue-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500" />
            </div>
          )}
        </div>
        
        {/* ═══════════════════════════════════════════════════
            TOGGLE: "🔔 A Aguardar Ação"
            Filtra para mostrar APENAS processos com
            has_unread_messages ou has_new_documents
            ═══════════════════════════════════════════════════ */}
        <Button
          variant={showOnlyPendingActions ? 'default' : 'outline'}
          size="sm"
          className={`h-8 text-xs gap-1.5 shrink-0 ${
            showOnlyPendingActions 
              ? 'bg-amber-600 hover:bg-amber-700 text-white border-amber-700' 
              : 'hover:bg-amber-50 dark:hover:bg-amber-950/30 hover:text-amber-700 dark:hover:text-amber-400 hover:border-amber-300 dark:hover:border-amber-800'
          }`}
          onClick={onTogglePendingActions}
          data-testid="kanban-pending-actions-filter"
        >
          {showOnlyPendingActions ? (
            <Bell className="h-3.5 w-3.5" />
          ) : (
            <BellOff className="h-3.5 w-3.5" />
          )}
          A Aguardar Ação
          {pendingActionsCount > 0 && (
            <span className="ml-0.5 bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-300 text-[10px] px-1.5 py-0 rounded-full font-bold">
              {pendingActionsCount}
            </span>
          )}
        </Button>

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
        
        {/* Exportar Excel */}
        <Button
          variant="outline"
          size="sm"
          className="h-8 text-xs gap-1.5 shrink-0"
          onClick={handleExportExcel}
          disabled={exporting || columns.length === 0}
        >
          {exporting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Download className="h-3.5 w-3.5" />
          )}
          Exportar Excel
        </Button>
      </div>
    </>
  );
});

KanbanHeader.displayName = 'KanbanHeader';

export default KanbanHeader;
