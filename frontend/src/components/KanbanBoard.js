/**
 * KanbanBoard Component (Orchestrator)
 * 
 * Componente principal do Quadro Kanban - agora um ORQUESTRADOR.
 * 
 * RESPONSABILIDADE ÚNICA (SRP):
 * - Fazer fetch dos dados na montagem
 * - Gerir estado global das colunas
 * - Fornecer contexto de Drag & Drop
 * - Renderizar lista de KanbanColumn
 * 
 * PERFORMANCE:
 * - Estado dos formulários ISOLADO nos modais
 * - React.memo nos cartões previne re-renders desnecessários
 * - Projeção de dados para minimizar dados transferidos
 * 
 * ARQUITETURA:
 * - KanbanBoard (orquestrador) → KanbanColumn → KanbanCard
 * - Modals com estado isolado: ProcessDetailsModal, CreateClientModal, AssignUsersModal
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { ScrollArea, ScrollBar } from './ui/scroll-area';
import { toast } from 'sonner';
import { useWebSocket, WSEventType } from '../hooks/useWebSocket';

// Importar componentes refatorados
import {
  KanbanColumn,
  KanbanHeader,
  KanbanSkeleton,
  SearchResultsList,
  ProcessDetailsModal,
  CreateClientModal,
  AssignUsersModal,
} from './kanban';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const KanbanBoard = ({ 
  token, 
  user, 
  consultorFilter = 'all', 
  mediadorFilter = 'all', 
  indexacaoFilter = 'all',
  parceiroFilter = 'all' 
}) => {
  // === ESTADO GLOBAL DO BOARD ===
  const [loading, setLoading] = useState(true);
  const [kanbanData, setKanbanData] = useState({ columns: [], total_processes: 0 });
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
  
  // === REFS (React way em vez de document.getElementById) ===
  const scrollContainerRef = useRef(null);
  
  // === ESTADO DE MODALS (apenas flags de abertura) ===
  const [selectedProcess, setSelectedProcess] = useState(null);
  const [showProcessDialog, setShowProcessDialog] = useState(false);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showAssignDialog, setShowAssignDialog] = useState(false);
  const [assigningProcess, setAssigningProcess] = useState(null);
  
  // Verificar se o utilizador pode criar clientes
  const canCreateClient = user && ['intermediario', 'mediador'].includes(user.role);

  // === DATA FETCHING ===
  const fetchKanbanData = useCallback(async () => {
    try {
      setLoading(true); // Mostrar loading quando filtros mudam
      const params = new URLSearchParams();
      
      // FILTRO DE ESTADO ATIVO: Por defeito, mostra apenas processos ativos
      // O backend usa 'active_only' como default, mas enviamos explicitamente
      params.append('view_mode', 'active_only');
      
      if (consultorFilter && consultorFilter !== 'all') {
        params.append('consultor_id', consultorFilter === 'none' ? 'none' : consultorFilter);
      }
      if (mediadorFilter && mediadorFilter !== 'all') {
        params.append('mediador_id', mediadorFilter === 'none' ? 'none' : mediadorFilter);
      }
      if (indexacaoFilter && indexacaoFilter !== 'all') {
        params.append('indexacao_id', indexacaoFilter === 'none' ? 'none' : indexacaoFilter);
      }
      if (parceiroFilter && parceiroFilter !== 'all') {
        params.append('parceiro_id', parceiroFilter === 'none' ? 'none' : parceiroFilter);
      }

      const url = `${API_URL}/api/processes/kanban?${params.toString()}`;

      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!response.ok) throw new Error('Failed to fetch kanban data');
      const data = await response.json();
      setKanbanData(data);
    } catch (error) {
      console.error('Error fetching kanban:', error);
      toast.error('Erro ao carregar dados do Kanban');
    } finally {
      setLoading(false);
    }
  }, [token, consultorFilter, mediadorFilter, indexacaoFilter, parceiroFilter]);

  useEffect(() => {
    fetchKanbanData();
  }, [fetchKanbanData]);

  // === WEBSOCKET REAL-TIME UPDATES ===
  const handleProcessUpdate = useCallback((eventType, payload) => {
    if (!payload || !payload.process_id) return;

    setKanbanData(prev => {
      const newColumns = prev.columns.map(col => ({ ...col, processes: [...col.processes] }));

      switch (eventType) {
        case WSEventType.PROCESS_CREATED: {
          const targetStatus = payload.status || 'clientes_espera';
          const targetColIndex = newColumns.findIndex(col => col.name === targetStatus);
          if (targetColIndex >= 0) {
            const newProcess = {
              id: payload.process_id,
              process_number: payload.process_number,
              client_name: payload.client_name || 'Novo Cliente',
              status: targetStatus,
              priority: payload.priority,
              process_type: payload.process_type,
              consultor_names: payload.consultor_names || [],
              mediador_names: payload.mediador_names || [],
              updated_at: payload.updated_at,
            };
            newColumns[targetColIndex].processes.unshift(newProcess);
            newColumns[targetColIndex].count += 1;
            toast.info(`Novo processo: ${payload.client_name || 'Novo Cliente'}`);
          }
          break;
        }

        case WSEventType.PROCESS_STATUS_CHANGED: {
          const sourceStatus = payload.old_status;
          const targetStatus = payload.status;
          let movedProcess = null;

          const sourceColIndex = newColumns.findIndex(col => col.name === sourceStatus);
          if (sourceColIndex >= 0) {
            const processIndex = newColumns[sourceColIndex].processes.findIndex(p => p.id === payload.process_id);
            if (processIndex >= 0) {
              movedProcess = { ...newColumns[sourceColIndex].processes[processIndex], status: targetStatus };
              newColumns[sourceColIndex].processes.splice(processIndex, 1);
              newColumns[sourceColIndex].count -= 1;
            }
          }

          const targetColIndex = newColumns.findIndex(col => col.name === targetStatus);
          if (targetColIndex >= 0) {
            if (movedProcess) {
              newColumns[targetColIndex].processes.unshift(movedProcess);
              newColumns[targetColIndex].count += 1;
            } else {
              newColumns[targetColIndex].processes.unshift({
                id: payload.process_id,
                process_number: payload.process_number,
                client_name: payload.client_name || 'Cliente',
                status: targetStatus,
                updated_at: payload.updated_at,
              });
              newColumns[targetColIndex].count += 1;
            }
          }
          break;
        }

        case WSEventType.PROCESS_UPDATED:
        case WSEventType.PROCESS_ASSIGNED: {
          for (const col of newColumns) {
            const processIndex = col.processes.findIndex(p => p.id === payload.process_id);
            if (processIndex >= 0) {
              col.processes[processIndex] = {
                ...col.processes[processIndex],
                ...(payload.client_name && { client_name: payload.client_name }),
                ...(payload.priority && { priority: payload.priority }),
                ...(payload.consultor_names && { consultor_names: payload.consultor_names }),
                ...(payload.mediador_names && { mediador_names: payload.mediador_names }),
                updated_at: payload.updated_at,
              };
              break;
            }
          }
          break;
        }

        default:
          break;
      }

      return { ...prev, columns: newColumns };
    });
  }, []);

  const { isConnected, on, off } = useWebSocket({
    onProcessUpdate: handleProcessUpdate,
    autoConnect: true,
  });

  useEffect(() => {
    const unsubscribers = [
      on(WSEventType.PROCESS_CREATED, (data) => handleProcessUpdate(WSEventType.PROCESS_CREATED, data)),
      on(WSEventType.PROCESS_STATUS_CHANGED, (data) => handleProcessUpdate(WSEventType.PROCESS_STATUS_CHANGED, data)),
      on(WSEventType.PROCESS_UPDATED, (data) => handleProcessUpdate(WSEventType.PROCESS_UPDATED, data)),
      on(WSEventType.PROCESS_ASSIGNED, (data) => handleProcessUpdate(WSEventType.PROCESS_ASSIGNED, data)),
    ];

    return () => {
      unsubscribers.forEach(unsub => unsub?.());
    };
  }, [on, handleProcessUpdate]);

  // === AUTO-COLLAPSE EMPTY COLUMNS ===
  useEffect(() => {
    if (kanbanData.columns.length > 0 && collapsedColumns.size === 0) {
      const emptyColumnIds = kanbanData.columns
        .filter(col => col.count === 0)
        .map(col => col.id);
      if (emptyColumnIds.length > 0) {
        setCollapsedColumns(new Set(emptyColumnIds));
      }
    }
  }, [kanbanData.columns, collapsedColumns.size]);

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

    // Optimistic update
    setKanbanData(prev => {
      const newColumns = prev.columns.map(col => {
        if (col.name === sourceColumn) {
          return {
            ...col,
            processes: col.processes.filter(p => p.id !== process.id),
            count: col.count - 1,
          };
        }
        if (col.name === targetColumn) {
          return {
            ...col,
            processes: [...col.processes, { ...process, status: targetColumn }],
            count: col.count + 1,
          };
        }
        return col;
      });
      return { ...prev, columns: newColumns };
    });

    // API call
    try {
      const response = await fetch(
        `${API_URL}/api/processes/kanban/${process.id}/move?new_status=${targetColumn}`,
        {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) throw new Error('Failed to move process');
      toast.success('Processo movido com sucesso');
    } catch (error) {
      console.error('Error moving process:', error);
      toast.error('Erro ao mover processo');
      fetchKanbanData(); // Revert on error
    }
  }, [draggingCard, token, fetchKanbanData]);

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
  }, []);

  // === FILTERED DATA ===
  const filteredColumns = kanbanData.columns.map(column => ({
    ...column,
    processes: column.processes.filter(process => {
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
  }));

  // Flattened processes for list view
  const allFilteredProcesses = searchTerm.length >= 2
    ? filteredColumns.flatMap(col => col.processes.map(p => ({ ...p, columnLabel: col.label, columnColor: col.color })))
    : [];

  // === SCROLL HANDLERS (usando useRef em vez de document.getElementById) ===
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
    fetchKanbanData();
  }, [fetchKanbanData]);

  const handleAssignSuccess = useCallback(() => {
    fetchKanbanData();
  }, [fetchKanbanData]);

  // === RENDER ===
  if (loading) {
    return <KanbanSkeleton />;
  }

  return (
    <div className="space-y-4" data-testid="kanban-board">
      {/* Header */}
      <KanbanHeader
        totalProcesses={kanbanData.total_processes}
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
                />
              ))}
            </div>
            <ScrollBar orientation="horizontal" />
          </ScrollArea>
        </div>
      )}

      {/* Modals - Estado isolado dentro de cada componente */}
      <ProcessDetailsModal
        open={showProcessDialog}
        onOpenChange={setShowProcessDialog}
        process={selectedProcess}
      />

      {canCreateClient && (
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
