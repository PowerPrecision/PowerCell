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
import { safeDateStr } from '../lib/utils';

// React Query hooks
import { useKanbanQuery } from '../hooks/queries/useKanbanQuery';
import { useKanbanCompletedQuery } from '../hooks/queries/useKanbanCompletedQuery';
import { useKanbanRealtime } from '../hooks/queries/useKanbanRealtime';
import { useCompletedDaysFilter } from '../hooks/queries/useCompletedDaysFilter';
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
  parceiroFilter = 'all',
  indexStatusFilter = 'all' 
}) => {
  // === ESTADO LOCAL (apenas UI state, não server state) ===
  const [searchTerm, setSearchTerm] = useState('');
  const [dateFilter, setDateFilter] = useState('all');
  const [urgencyFilter, setUrgencyFilter] = useState('all');
  const [viewMode, setViewMode] = useState('kanban');
  const [scrollPosition, setScrollPosition] = useState(0);

  // ═══════════════════════════════════════════════════════════
  // FILTRO MÁGICO "A Aguardar Ação"
  // Quando ativo, mostra APENAS processos com:
  //   has_unread_messages === true OU has_new_documents === true
  // ═══════════════════════════════════════════════════════════
  const [showOnlyPendingActions, setShowOnlyPendingActions] = useState(false);

  // === FILTRO ISOLADO DE CONCLUÍDOS ===
  // O estado do completedDays vive isolado NESTE hook, NÃO no estado global.
  // Isto impede que a mudança de período nos Concluídos provoque re-render
  // de todo o quadro. A query dos Concluídos tem cache key independente.
  const { completedDays, setCompletedDays, resetCompletedDays } = useCompletedDaysFilter();
  
  // === ESTADO DE DRAG & DROP ===
  const [draggingCard, setDraggingCard] = useState(null);
  const [dragOverColumn, setDragOverColumn] = useState(null);

  // === PACOTE DB — OPTIMISTIC MOVE LOCAL (reatividade imediata do Kanban) ===
  // Mapa processId → newStatus aplicado IMEDIATAMENTE no handleDrop, antes
  // de aguardar a resposta da API. Garante que o cartão se move visualmente
  // sem delay, independentemente do cache do TanStack Query. Limpo no
  // onSettled do mutation (quando a API responde e a query é invalidada).
  const [localMoves, setLocalMoves] = useState({});
  
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

  // === REACT QUERY - DATA FETCHING (QUERIES SEPARADAS) ===
  // Memoize filters to prevent infinite re-renders in dependent hooks
  const filters = useMemo(() => ({ consultorFilter, mediadorFilter, indexacaoFilter, parceiroFilter, indexStatusFilter }), [consultorFilter, mediadorFilter, indexacaoFilter, parceiroFilter, indexStatusFilter]);

  // QUERY 1: Colunas ACTIVAS (sem completedDays — não re-fetch quando o filtro muda)
  const {
    kanbanData,
    columns: activeColumns,
    totalProcesses,
    isLoading,
    isFetching,
    isError,
    refetch,
  } = useKanbanQuery({
    token,
    ...filters,
    completedDays: undefined, // NÃO enviar completedDays — a query activa não precisa deste filtro
  });

  // QUERY 2: Colunas CONCLUÍDOS (cache key INDEPENDENTE — re-fetch apenas quando completedDays muda)
  const {
    columns: completedColumns,
    isFetching: isFetchingCompleted,
    isLoading: isLoadingCompleted,
  } = useKanbanCompletedQuery({
    token,
    ...filters,
    completedDays,
  });

  // === MERGE: Colunas activas + concluídos ===
  // Substituir as colunas concluidos/desistencias da query activa pelos dados
  // da query isolada de Concluídos. Isto garante que quando o utilizador muda
  // o período, apenas as colunas inactivas são actualizadas.
  const columns = useMemo(() => {
    if (!activeColumns.length) return activeColumns;

    const completedMap = new Map(
      completedColumns.map(col => [col.name, col])
    );

    return activeColumns.map(col => {
      // Se é coluna concluidos/desistencias, usar dados da query isolada
      if (completedMap.has(col.name)) {
        return completedMap.get(col.name);
      }
      // Caso contrário, manter dados da query activa (não afectada pelo filtro)
      return col;
    });
  }, [activeColumns, completedColumns]);

  const totalInactive = completedColumns.reduce((acc, col) => acc + (col.count || 0), 0);

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
  // PACOTE DB — onSettled limpa o localMoves do processo quando a API responde
  const moveProcessMutation = useMoveProcessMutation(addPendingMove, removePendingMove, {
    filters,
    onSettled: (_data, _error, variables) => {
      // Limpar o move local — a query invalidada já tem o estado real
      setLocalMoves(prev => {
        if (!prev[variables.processId]) return prev;
        const next = { ...prev };
        delete next[variables.processId];
        return next;
      });
    },
  });

  // === AUTO-COLLAPSE EMPTY COLUMNS ===
  // Este efeito é local, não precisa de React Query
  // Never auto-collapse completed/desistencia columns — users need to see them
  useEffect(() => {
    if (columns.length > 0 && collapsedColumns.size === 0) {
      const PRESERVED_COLUMN_NAMES = new Set(['concluidos', 'desistencias']);
      const emptyColumnIds = columns
        .filter(col => col.count === 0 && !PRESERVED_COLUMN_NAMES.has(col.name))
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

    // PACOTE DB — Optimistic update LOCAL IMEDIATO: o cartão muda de coluna
    // VISUALMENTE no momento do drop, antes de aguardar a API. Esta camada
    // local é aplicada sobre as `columns` do TanStack Query (ver optimisticColumns).
    setLocalMoves(prev => ({ ...prev, [process.id]: targetColumn }));

    // Disparar a mutation (tem o seu próprio optimistic update no cache)
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

  // === PACOTE DB — OPTIMISTIC COLUMNS (reatividade imediata do Kanban) ===
  // Aplica `localMoves` sobre `columns` ANTES do filtro: move cada processo
  // da sua coluna original para a coluna-alvo definida em localMoves.
  // Isto garante que o drag-drop se reflete INSTANTANEAMENTE no render,
  // independentemente do cache do TanStack Query.
  const optimisticColumns = useMemo(() => {
    const moveEntries = Object.entries(localMoves);
    if (moveEntries.length === 0) return columns;

    const moveMap = new Map(moveEntries); // processId → newStatus

    // Recolher processos movidos (removê-los das colunas originais)
    const movedProcesses = new Map(); // processId → process object
    for (const col of columns) {
      for (const p of (col.processes || [])) {
        if (moveMap.has(p.id)) {
          movedProcesses.set(p.id, { ...p, status: moveMap.get(p.id) });
        }
      }
    }

    return columns.map(col => {
      let processes = (col.processes || []).filter(p => !moveMap.has(p.id));
      // Adicionar processos movidos PARA esta coluna
      for (const [, p] of movedProcesses) {
        if (p.status === col.name) {
          processes = [...processes, p];
        }
      }
      return { ...col, processes, count: processes.length };
    });
  }, [columns, localMoves]);

  // === FILTERED DATA ===
  const filteredColumns = optimisticColumns.map(column => ({
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
          const created = new Date(safeDateStr(process.created_at));
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
            const daysSinceUpdate = Math.floor((Date.now() - new Date(safeDateStr(lastUpdate)).getTime()) / (1000 * 60 * 60 * 24));
            if (urgencyFilter === 'overdue') {
              matchesUrgency = daysSinceUpdate > 14;
            } else if (urgencyFilter === 'urgent') {
              matchesUrgency = daysSinceUpdate > 7 && daysSinceUpdate <= 14;
            } else if (urgencyFilter === 'normal') {
              matchesUrgency = daysSinceUpdate <= 7;
            }
          }
        }

        // Index status filter
        let matchesIndexStatus = true;
        if (indexStatusFilter === 'completed' && !process.is_indexed) matchesIndexStatus = false;
        if (indexStatusFilter === 'pending' && process.is_indexed) matchesIndexStatus = false;

        // ═══════════════════════════════════════════════════
        // FILTRO "A Aguardar Ação"
        // Mostra APENAS processos com mensagens não lidas
        // ou novos documentos do portal do cliente
        // ═══════════════════════════════════════════════════
        const matchesPendingAction =
          !showOnlyPendingActions ||
          process.has_unread_messages === true ||
          process.has_new_documents === true;

        return matchesSearch && matchesDate && matchesUrgency && matchesIndexStatus && matchesPendingAction;
      }),
      column.name
    ),
  }));

  // Flattened processes for list view
  const allFilteredProcesses = searchTerm.length >= 2
    ? filteredColumns.flatMap(col => col.processes.map(p => ({ ...p, columnLabel: col.label, columnColor: col.color })))
    : [];

  // ═══════════════════════════════════════════════════════════
  // CONTAGEM DE PROCESSOS COM AÇÕES PENDENTES
  // Para o badge do botão "A Aguardar Ação"
  // ═══════════════════════════════════════════════════════════
  const pendingActionsCount = useMemo(() => {
    if (!columns || columns.length === 0) return 0;
    return columns.reduce((count, col) => {
      return count + (col.processes || []).filter(
        p => p.has_unread_messages || p.has_new_documents
      ).length;
    }, 0);
  }, [columns]);

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
        totalInactive={totalInactive}
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
        completedDays={completedDays}
        onCompletedDaysChange={setCompletedDays}
        onScrollLeft={() => scrollContainer('left')}
        onScrollRight={() => scrollContainer('right')}
        isFetching={isFetching}
        isFetchingCompleted={isFetchingCompleted}
        columns={filteredColumns}
        // ═══ Filtro "A Aguardar Ação" ═══
        showOnlyPendingActions={showOnlyPendingActions}
        onTogglePendingActions={() => setShowOnlyPendingActions(prev => !prev)}
        pendingActionsCount={pendingActionsCount}
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
                  completedDays={completedDays}
                  onCompletedDaysChange={setCompletedDays}
                  isFetchingCompleted={isFetchingCompleted && (column.name === 'concluidos' || column.name === 'desistencias')}
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
        onProcessUpdate={(processId, updates) => {
          // Atualizar o processo nas colunas locais e refetch para garantir consistência
          refetch();
        }}
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
