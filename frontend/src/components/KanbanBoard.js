/**
 * KanbanBoard — Quadro Kanban principal (orquestrador) com drag-drop e tempo real.
 *
 * PORQUÊ: O PowerCell gere processos de crédito habitação que fluem por múltiplas
 * fases (documentação, análise, aprovação bancária, CPCV, escritura). Este quadro
 * visual permite à equipa acompanhar e mover processos entre fases de forma intuitiva,
 * substituindo planilhas e emails internos. A arquitectura orquestrador delega a
 * lógica de apresentação para subcomponentes (KanbanColumn → KanbanCard), mantendo
 * apenas estado de UI local e delegando server state ao TanStack Query.
 *
 * DECISÕES ARQUITECTURAIS:
 * - TanStack Query para caching com staleTime e refetch on window focus.
 * - Integração WebSocket via useKanbanRealtime para actualizações em tempo real
 *   sem polling (setQueryData para optimistic updates).
 * - Drag-and-drop nativo (HTML5) em vez de biblioteca externa, simplificando
 *   a cadeia de dependências.
 * - Filtros por consultor, mediador, indexação e parceiro para visão personalizada.
 * - Locking de processos via WebSocket para evitar conflitos de edição simultânea.
 *
 * @param {Object} props
 * @param {string} props.token — Token JWT de autenticação
 * @param {Object} props.user — Utilizador autenticado ({ id, role, name, … })
 * @param {string} [props.consultorFilter='all'] — Filtrar por ID do consultor
 * @param {string} [props.mediadorFilter='all'] — Filtrar por ID do mediador
 * @param {string} [props.indexacaoFilter='all'] — Filtrar por ID de indexação
 * @param {string} [props.parceiroFilter='all'] — Filtrar por ID do parceiro
 *
 * @hook {useKanbanQuery} — Busca dados do quadro com caching TanStack Query
 * @hook {useKanbanRealtime} — Integração WebSocket + React Query para tempo real
 * @hook {useMoveProcessMutation} — Mutação de movimentação com optimistic update
 *
 * @example
 * <KanbanBoard
 *   token={jwtToken}
 *   user={currentUser}
 *   consultorFilter="consultor-123"
 *   mediadorFilter="all"
 * />
 */
import { useState, useCallback, useRef, useMemo, useEffect } from 'react';
import { ScrollArea, ScrollBar } from './ui/scroll-area';
import { toast } from 'sonner';
import { hasAnyRole } from '../utils/roleUtils';

// React Query hooks
import { useKanbanQuery } from '../hooks/queries/useKanbanQuery';
import { useKanbanRealtime } from '../hooks/queries/useKanbanRealtime';
import { useMoveProcessMutation } from '../hooks/mutations/useProcessMutations';

// Importar componentes refatorados
import KanbanColumn from './kanban/KanbanColumn';
import KanbanHeader from './kanban/KanbanHeader';
import KanbanSkeleton from './kanban/KanbanSkeleton';
import SearchResultsList from './kanban/SearchResultsList';
import ProcessDetailsModal from './kanban/ProcessDetailsModal';
import CreateClientModal from './kanban/CreateClientModal';
import AssignUsersModal from './kanban/AssignUsersModal';

// ====================================================================
// ORDENAÇÃO POR PRIORIDADE + TAGS URGENTES
// Peso: Alta=3, Urgente tag=3, Média=2, Baixa=1, undefined=0
// Ordenação primária por peso (desc), secundária por updated_at (desc)
// ====================================================================
const PRIORITY_WEIGHT = { alta: 3, media: 2, baixa: 1, high: 3, medium: 2, low: 1 };

const hasUrgentTag = (process) => {
  const tags = process.tags || process.labels || [];
  if (!Array.isArray(tags) || tags.length === 0) return false;
  return tags.some(t => {
    const label = (typeof t === 'string' ? t : (t?.label || t?.name || '')).toLowerCase();
    return label.includes('urgente') || label.includes('urgent');
  });
};

const sortProcessesByPriority = (processes, columnId) => {
  // For completed/closed columns, sort only by date (most recent first)
  if (columnId === 'concluidos' || columnId === 'desistencias') {
    return [...processes].sort((a, b) => {
      const dateA = a.updated_at || a.created_at || '';
      const dateB = b.updated_at || b.created_at || '';
      return dateB.localeCompare(dateA);
    });
  }

  // For active columns, sort by priority then date
  return [...processes].sort((a, b) => {
    // Peso de prioridade (campo prioridade/priority)
    let weightA = PRIORITY_WEIGHT[(a.prioridade || a.priority || '').toLowerCase()] || 0;
    let weightB = PRIORITY_WEIGHT[(b.prioridade || b.priority || '').toLowerCase()] || 0;
    // Tags urgentes contam como prioridade Alta
    if (hasUrgentTag(a)) weightA = Math.max(weightA, 3);
    if (hasUrgentTag(b)) weightB = Math.max(weightB, 3);
    if (weightB !== weightA) return weightB - weightA;
    // Secondary sort: most recently updated first
    const dateA = a.updated_at || a.created_at || '';
    const dateB = b.updated_at || b.created_at || '';
    return dateB.localeCompare(dateA);
  });
};

const KanbanBoard = ({ 
  token, 
  user, 
  consultorFilter = 'all', 
  mediadorFilter = 'all', 
  indexacaoFilter = 'all',
  parceiroFilter = 'all' 
}) => {
  // === ESTADO LOCAL (apenas UI state, não server state) ===
  const [searchTerm, setSearchTerm] = useState('');
  const [dateFilter, setDateFilter] = useState('all');
  const [urgencyFilter, setUrgencyFilter] = useState('all');
  const [viewMode, setViewMode] = useState('kanban');
  const [scrollPosition, setScrollPosition] = useState(0);
  
  // === ESTADO DE DRAG & DROP ===
  const [draggingCard, setDraggingCard] = useState(null);
  const [dragOverColumn, setDragOverColumn] = useState(null);
  
  // === ESTADO DE COLUNAS COLAPSADAS ===
  const [collapsedColumns, setCollapsedColumns] = useState(new Set());
  
  // === REFS ===
  const scrollContainerRef = useRef(null);
  
  // === ESTADO DE MODALS ===
  const [selectedProcess, setSelectedProcess] = useState(null);
  const [showProcessDialog, setShowProcessDialog] = useState(false);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showAssignDialog, setShowAssignDialog] = useState(false);
  const [assigningProcess, setAssigningProcess] = useState(null);
  
  // Verificar se o utilizador pode criar processos (qualquer staff)
  const canCreateProcess = hasAnyRole(user, ['admin', 'ceo', 'consultor', 'intermediario', 'administrativo', 'diretor', 'indexacao']);

  // === REACT QUERY - DATA FETCHING ===
  // Memoize filters to prevent infinite re-renders in dependent hooks
  const filters = useMemo(() => ({ consultorFilter, mediadorFilter, indexacaoFilter, parceiroFilter }), [consultorFilter, mediadorFilter, indexacaoFilter, parceiroFilter]);
  
  const {
    kanbanData,
    columns,
    totalProcesses,
    isLoading,
    isFetching,
    isError,
    refetch,
  } = useKanbanQuery({
    token,
    ...filters,
  });

  // === REACT QUERY - WEBSOCKET REAL-TIME ===
  const {
    isConnected,
    lockedProcesses,
    sendMessage,
    addPendingMove,
    removePendingMove,
  } = useKanbanRealtime({
    filters,
    userId: user?.id,
    onNotification: ({ type, message }) => {
      if (type === 'info') {
        toast.info(message);
      }
    },
  });

  // === REACT QUERY - MUTATIONS ===
  const moveProcessMutation = useMoveProcessMutation(addPendingMove, removePendingMove, { filters });

  // === AUTO-COLLAPSE EMPTY COLUMNS ===
  // Este efeito é local, não precisa de React Query
  // Never auto-collapse completed/desistencia columns — users need to see them
  useEffect(() => {
    if (columns.length > 0 && collapsedColumns.size === 0) {
      const PRESERVED_COLUMNS = new Set(['concluidos', 'desistencias']);
      const emptyColumnIds = columns
        .filter(col => col.count === 0 && !PRESERVED_COLUMNS.has(col.id))
        .map(col => col.id);
      if (emptyColumnIds.length > 0) {
        setCollapsedColumns(new Set(emptyColumnIds));
      }
    }
  }, [columns]);

  // === DRAG & DROP HANDLERS ===
  const handleDragStart = useCallback((e, process, columnName) => {
    setDraggingCard({ process, sourceColumn: columnName });
    e.dataTransfer.effectAllowed = 'move';
  }, []);

  const handleDragOver = useCallback((e, columnName) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverColumn(columnName);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOverColumn(null);
  }, []);

  const handleDrop = useCallback(async (e, targetColumn) => {
    e.preventDefault();
    setDragOverColumn(null);

    if (!draggingCard || draggingCard.sourceColumn === targetColumn) {
      setDraggingCard(null);
      return;
    }

    const { process, sourceColumn } = draggingCard;
    setDraggingCard(null);

    // Usar mutation com optimistic update
    moveProcessMutation.mutate({
      processId: process.id,
      newStatus: targetColumn,
      oldStatus: sourceColumn,
    });
  }, [draggingCard, moveProcessMutation]);

  // === COLUMN COLLAPSE HANDLER ===
  const handleToggleCollapse = useCallback((columnId) => {
    setCollapsedColumns(prev => {
      const newSet = new Set(prev);
      if (newSet.has(columnId)) {
        newSet.delete(columnId);
      } else {
        newSet.add(columnId);
      }
      return newSet;
    });
  }, []);

  // === CARD CLICK HANDLER ===
  const handleCardClick = useCallback((process) => {
    setSelectedProcess(process);
    setShowProcessDialog(true);
    // Send lock event via WebSocket
    if (sendMessage) {
      sendMessage('process_locked', { process_id: process.id });
    }
  }, [sendMessage]);

  // === DIALOG CLOSE HANDLER ===
  const handleDialogClose = useCallback((open) => {
    if (!open && selectedProcess && sendMessage) {
      sendMessage('process_unlocked', { process_id: selectedProcess.id });
    }
    if (!open) {
      setSelectedProcess(null);
    }
    setShowProcessDialog(open);
  }, [selectedProcess, sendMessage]);

  // === FILTERED DATA ===
  const filteredColumns = columns.map(column => ({
    ...column,
    processes: sortProcessesByPriority(
      column.processes.filter(process => {
        // Text search filter
        const matchesSearch =
          process.client_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          process.client_email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          process.client_phone?.includes(searchTerm) ||
          process.consultor_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
          process.mediador_name?.toLowerCase().includes(searchTerm.toLowerCase());

        // Date filter
        let matchesDate = true;
        if (dateFilter !== 'all' && process.created_at) {
          const created = new Date(process.created_at);
          const now = new Date();
          if (dateFilter === 'today') {
            matchesDate = created.toDateString() === now.toDateString();
          } else if (dateFilter === 'week') {
            const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            matchesDate = created >= weekAgo;
          } else if (dateFilter === 'month') {
            const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
            matchesDate = created >= monthAgo;
          }
        }

        // Urgency filter
        let matchesUrgency = true;
        if (urgencyFilter !== 'all') {
          const lastUpdate = process.updated_at || process.created_at;
          if (lastUpdate) {
            const daysSinceUpdate = Math.floor((Date.now() - new Date(lastUpdate).getTime()) / (1000 * 60 * 60 * 24));
            if (urgencyFilter === 'overdue') {
              matchesUrgency = daysSinceUpdate > 14;
            } else if (urgencyFilter === 'urgent') {
              matchesUrgency = daysSinceUpdate > 7 && daysSinceUpdate <= 14;
            } else if (urgencyFilter === 'normal') {
              matchesUrgency = daysSinceUpdate <= 7;
            }
          }
        }

        return matchesSearch && matchesDate && matchesUrgency;
      }),
      column.id
    ),
  }));

  // Flattened processes for list view
  const allFilteredProcesses = searchTerm.length >= 2
    ? filteredColumns.flatMap(col => col.processes.map(p => ({ ...p, columnLabel: col.label, columnColor: col.color })))
    : [];

  // === SCROLL HANDLERS ===
  const scrollContainer = useCallback((direction) => {
    const container = scrollContainerRef.current;
    if (container) {
      const scrollAmount = 350;
      const newPosition = direction === 'left'
        ? scrollPosition - scrollAmount
        : scrollPosition + scrollAmount;
      container.scrollTo({ left: newPosition, behavior: 'smooth' });
      setScrollPosition(newPosition);
    }
  }, [scrollPosition]);

  // === MODAL CALLBACKS ===
  const handleCreateSuccess = useCallback(() => {
    refetch();
  }, [refetch]);

  const handleAssignSuccess = useCallback(() => {
    refetch();
  }, [refetch]);

  // === RENDER ===
  if (isLoading) {
    return <KanbanSkeleton />;
  }

  return (
    <div className="space-y-4" data-testid="kanban-board">
      {/* Header */}
      <KanbanHeader
        totalProcesses={totalProcesses}
        visibleCount={filteredColumns.reduce((acc, col) => acc + col.processes.length, 0)}
        isConnected={isConnected}
        searchTerm={searchTerm}
        onSearchChange={setSearchTerm}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        showViewToggle={searchTerm.length >= 2}
        dateFilter={dateFilter}
        onDateFilterChange={setDateFilter}
        urgencyFilter={urgencyFilter}
        onUrgencyFilterChange={setUrgencyFilter}
        onScrollLeft={() => scrollContainer('left')}
        onScrollRight={() => scrollContainer('right')}
        isFetching={isFetching}
      />

      {/* Search Results List View */}
      {searchTerm.length >= 2 && viewMode === 'list' && (
        <SearchResultsList
          processes={allFilteredProcesses}
          searchTerm={searchTerm}
        />
      )}

      {/* Kanban Board */}
      {(searchTerm.length < 2 || viewMode === 'kanban') && (
        <div className="relative">
          <ScrollArea className="w-full whitespace-nowrap rounded-md">
            <div
              ref={scrollContainerRef}
              className="flex gap-4 pb-4 min-h-[70vh]"
              onScroll={(e) => setScrollPosition(e.currentTarget.scrollLeft)}
            >
              {filteredColumns.map(column => (
                <KanbanColumn
                  key={column.id}
                  column={column}
                  isCollapsed={collapsedColumns.has(column.id)}
                  dragOverColumn={dragOverColumn}
                  onDragOver={handleDragOver}
                  onDragLeave={handleDragLeave}
                  onDrop={handleDrop}
                  onToggleCollapse={handleToggleCollapse}
                  onDragStart={handleDragStart}
                  onCardClick={handleCardClick}
                  draggingCard={draggingCard}
                  lockedProcesses={lockedProcesses}
                />
              ))}
            </div>
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </div>
      )}

      {/* Modals */}
      <ProcessDetailsModal
        open={showProcessDialog}
        onOpenChange={handleDialogClose}
        process={selectedProcess}
        isLockedByOther={selectedProcess ? !!lockedProcesses[selectedProcess.id] && lockedProcesses[selectedProcess.id]?.user_id !== user?.id : false}
        lockedBy={selectedProcess ? lockedProcesses[selectedProcess.id]?.user_name : undefined}
      />

      {canCreateProcess && (
        <CreateClientModal
          open={showCreateDialog}
          onOpenChange={setShowCreateDialog}
          onSuccess={handleCreateSuccess}
        />
      )}

      <AssignUsersModal
        open={showAssignDialog}
        onOpenChange={setShowAssignDialog}
        process={assigningProcess}
        token={token}
        onSuccess={handleAssignSuccess}
      />
    </div>
  );
};

export default KanbanBoard;
