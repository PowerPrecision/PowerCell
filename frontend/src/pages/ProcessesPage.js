/**
 * ProcessesPage — Página de listagem paginada de todos os processos do CRM.
 *
 * PORQUÊ: Vista tabular alternativa ao Kanban. Mostra processos com filtros por estado,
 * pesquisa por nome ou email, e paginação. Suporta toggle entre ativos e arquivo via view_mode na URL.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useNavigate, useSearchParams, useLocation } from "react-router-dom";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import { Label } from "../components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { 
  Search, Eye, FileText, Phone, Mail, Filter,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Loader2, ArrowUpDown, ArrowUp, ArrowDown, Plus, Shield,
  Flame, X, ClipboardCheck, CheckCircle2, Download, RotateCcw, Trash2
} from "lucide-react";
import { toast } from "sonner";
import { getProcesses, markProcessIndexed, restoreProcess } from "../services/api";
import { TableSkeleton } from "../components/ui/skeletons";
import CreateProcessModal from "../components/CreateProcessModal";
// PACOTE CX — ClientDetailsModal para popup de detalhes ao clicar no nome
import ClientDetailsModal from "../components/ClientDetailsModal";
import { useAuth } from "../contexts/AuthContext";
import { safeString } from "../utils/safeString";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";

const roleLabels = {
  consultor: "Consultor",
  intermediario: "Intermediário",
  indexacao: "Indexação",
  administrativo: "Administrativo",
  diretor: "Diretor",
  ceo: "CEO",
  admin: "Administrador",
};

const ProcessesPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, token, effectiveRole } = useAuth();
  const [processes, setProcesses] = useState([]);
  const [loading, setLoading] = useState(true);
  
  // Context Isolation: toggle para filtrar por cargo ativo
  const [filterByRole, setFilterByRole] = useState(true);
  const hasMultipleRoles = (user?.additional_roles?.length || 0) > 0;

  // Sincronizar X-Active-Role com o toggle de filtragem por cargo
  // Quando toggle ON: usa o effectiveRole do ContextSwitcher
  // Quando toggle OFF: envia "all" para o backend devolver todos os processos
  useEffect(() => {
    if (!hasMultipleRoles) return;
    if (filterByRole) {
      // Restaurar o effectiveRole do ContextSwitcher
      sessionStorage.setItem("activeRole", effectiveRole);
    } else {
      // Enviar "all" para desativar filtro por cargo
      sessionStorage.setItem("activeRole", "all");
    }
  }, [filterByRole, effectiveRole, hasMultipleRoles]);

  // Determinar título baseado na rota
  // /lista-processos → "Todos os Processos" (Visão Global)
  // /processos → "Os Meus Processos" (O Meu Negócio)
  const pageTitle = location.pathname === "/lista-processos" ? "Todos os Processos" : "Os Meus Processos";
  const isGlobalView = location.pathname === "/lista-processos";
  
  // Estado de paginação
  const [pagination, setPagination] = useState({
    page: parseInt(searchParams.get("page") || "1"),
    size: parseInt(searchParams.get("size") || "20"),
    total: 0,
    pages: 0
  });
  
  // ================================================================
  // FILTRO DE ESTADO ATIVO
  // Por defeito, mostra apenas processos ativos (view_mode=active_only)
  // "all" mostra todos incluindo arquivo (view_mode=all)
  // "deleted" mostra apenas eliminados (view_mode=deleted) — com botão Restaurar
  // FIX (Pacote K): adicionado modo "deleted" para mostrar processos eliminados
  // ================================================================
  const [viewMode, setViewMode] = useState(
    searchParams.get("view_mode") || "active_only"
  );
  const showCompleted = viewMode === "all";  // backward compat para lógica existente
  
  // Sort state
  const [sortField, setSortField] = useState(searchParams.get("sort") || "created_at");
  const [sortOrder, setSortOrder] = useState(searchParams.get("order") || "desc");
  const [sortedProcesses, setSortedProcesses] = useState([]);
  const [showCreateProcess, setShowCreateProcess] = useState(false);
  // PACOTE CX — estado para ClientDetailsModal (popup ao clicar no nome do cliente)
  const [clientDetailsModal, setClientDetailsModal] = useState({ open: false, clientId: null });

  // PACOTE CA — indexStatusFilter persistido no URL para restauração na navegação Back/Forward.
  // Default: 'pending' para role indexacao, 'all' para os restantes.
  // Lido do URL se existir; caso contrário usa o default do role.
  const indexStatusFilter = searchParams.get("index_status") ||
    (user?.role?.toLowerCase() === 'indexacao' ? 'pending' : 'all');
  const setIndexStatusFilter = useCallback((value) => {
    setSearchParams(prev => {
      if (value && value !== 'all') {
        prev.set("index_status", value);
      } else {
        prev.delete("index_status");
      }
      return prev;
    }, { replace: true });
  }, [setSearchParams]);
  // Estado para tracking de mark-indexed em cada processo
  const [markingProcessIds, setMarkingProcessIds] = useState(new Set());
  const [exporting, setExporting] = useState(false);

  const canMarkIndexed = useMemo(() => {
    const role = user?.role?.toLowerCase();
    return role === 'indexacao' || role === 'admin' || role === 'ceo';
  }, [user?.role]);

  // Sync filters with URL — searchTerm precisa de ser declarado antes de handleExportExcel
  const searchTerm = searchParams.get("search") || "";

  const handleExportExcel = useCallback(async () => {
    setExporting(true);
    try {
      const XLSX = await import('xlsx');
      // Buscar TODOS os processos com paginação (backend limita size a 100)
      const baseParams = {
        search: searchTerm || undefined,
        view_mode: showCompleted ? 'all' : 'active_only',
        sort_field: sortField,
        sort_order: sortOrder,
        ...(isGlobalView ? { show_all: true } : {}),
      };

      let allProcs = [];
      let page = 1;
      let totalPages = 1;

      while (page <= totalPages) {
        const response = await getProcesses({ ...baseParams, page, size: 100 });
        const items = response.data.items || response.data;
        allProcs = allProcs.concat(items);
        if (response.data.pages) {
          totalPages = response.data.pages;
        } else {
          break; // formato antigo (array) — não paginar
        }
        page++;
      }

      let exportData = allProcs.map(p => ({
        'Processo': p.process_number || '',
        'Cliente': p.client_name || '',
        'NIF': p.client_nif || '',
        'Telefone': p.client_phone || '',
        'Email': p.client_email || '',
        'Tipo de Processo': p.process_type ? String(p.process_type).replace(/_/g, ' ') : '',
        'Consultores': p.consultor_name || '',
        'Intermediários': p.mediador_name || '',
        'Indexação': p.indexacao_name || '',
        'Parceiro': p.parceiro_name || '',
        'Fase': (p.status || '').replace(/_/g, ' '),
        'Valor Imóvel': p.real_estate_data?.valor_imovel || p.property_value || '',
        'Morada do Imóvel': p.real_estate_data?.morada_imovel || p.real_estate_data?.morada || p.property_address || '',
        'Link Imóvel': p.real_estate_data?.link_imovel || '',
        'Notas/Descrição': p.description || '',
        'Prioridade': p.prioridade || p.priority || '',
        'Data de Criação': p.created_at || '',
        'Indexado': p.is_indexed ? 'Sim' : 'Não',
      }));

      // Aplicar filtro de indexação no lado do cliente
      if (indexStatusFilter === 'completed') {
        exportData = exportData.filter(p => p['Indexado'] === 'Sim');
      } else if (indexStatusFilter === 'pending') {
        exportData = exportData.filter(p => p['Indexado'] === 'Não');
      }

      if (exportData.length === 0) {
        toast.error('Nenhum processo para exportar com os filtros selecionados');
        return;
      }

      const ws = XLSX.utils.json_to_sheet(exportData);
      ws['!cols'] = [
        { wch: 10 }, // Processo
        { wch: 25 }, // Cliente
        { wch: 12 }, // NIF
        { wch: 15 }, // Telefone
        { wch: 25 }, // Email
        { wch: 18 }, // Tipo de Processo
        { wch: 25 }, // Consultores
        { wch: 25 }, // Intermediários
        { wch: 20 }, // Indexação
        { wch: 20 }, // Parceiro
        { wch: 18 }, // Fase
        { wch: 14 }, // Valor Imóvel
        { wch: 30 }, // Morada do Imóvel
        { wch: 35 }, // Link Imóvel
        { wch: 40 }, // Notas/Descrição
        { wch: 12 }, // Prioridade
        { wch: 18 }, // Data de Criação
        { wch: 8 },  // Indexado
      ];
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Processos');
      const filename = `PowerCell_Processos_${new Date().toISOString().slice(0,10)}.xlsx`;
      XLSX.writeFile(wb, filename);
      toast.success(`${exportData.length} processos exportados com sucesso!`);
    } catch (err) {
      toast.error('Erro ao exportar Excel');
    } finally {
      setExporting(false);
    }
  }, [searchTerm, showCompleted, sortField, sortOrder, isGlobalView, indexStatusFilter]);

  const handleMarkIndexed = useCallback(async (e, processId) => {
    e.stopPropagation();
    if (!processId || markingProcessIds.has(processId)) return;
    setMarkingProcessIds(prev => new Set(prev).add(processId));
    try {
      await markProcessIndexed(processId);
      toast.success('Indexação concluída! A equipa foi notificada.');
      // Atualizar localmente o processo
      setProcesses(prev => prev.map(p => p.id === processId ? { ...p, is_indexed: true } : p));
    } catch (error) {
      const detail = extractErrorMessage(error.response?.data?.detail, error.message || 'Erro ao marcar indexação.');
      toast.error(detail);
    } finally {
      setMarkingProcessIds(prev => {
        const next = new Set(prev);
        next.delete(processId);
        return next;
      });
    }
  }, [markingProcessIds]);

  const toggleSort = (field) => {
    if (sortField === field) {
      const newOrder = sortOrder === "asc" ? "desc" : "asc";
      setSortOrder(newOrder);
      setSearchParams(prev => {
        prev.set("sort", field);
        prev.set("order", newOrder);
        return prev;
      }, { replace: true });
    } else {
      setSortField(field);
      setSortOrder("asc");
      setSearchParams(prev => {
        prev.set("sort", field);
        prev.set("order", "asc");
        return prev;
      }, { replace: true });
    }
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
    return sortOrder === "asc" 
      ? <ArrowUp className="h-3 w-3 ml-1" />
      : <ArrowDown className="h-3 w-3 ml-1" />;
  };

  // Sync filters with URL — searchTerm já declarado acima (antes de handleExportExcel)
  const setSearchTerm = (value) => {
    setSearchParams(prev => {
      if (value) prev.set("search", value);
      else prev.delete("search");
      prev.set("page", "1"); // Reset para página 1 ao pesquisar
      return prev;
    }, { replace: true });
  };

  // Ref para manter searchTerm actualizado sem causar re-render do fetchProcesses
  const searchTermRef = useRef(searchTerm);
  useEffect(() => {
    searchTermRef.current = searchTerm;
  }, [searchTerm]);

  // Ref para prevenir pedidos duplicados concorrentes
  const fetchControllerRef = useRef(null);

  const fetchProcesses = useCallback(async () => {
    // Cancelar pedido anterior se ainda estiver em curso
    if (fetchControllerRef.current) {
      fetchControllerRef.current.abort();
    }

    const controller = new AbortController();
    fetchControllerRef.current = controller;

    try {
      setLoading(true);
      // Para "/processos" (Os Meus Processos): NÃO enviar show_all — o backend
      // filtra automaticamente por user_id. Para "/lista-processos": enviar show_all
      // para mostrar TODOS os processos da empresa (visão global).
      const response = await getProcesses({
        page: pagination.page,
        size: pagination.size,
        search: searchTermRef.current || undefined,
        view_mode: viewMode,
        sort_field: sortField,
        sort_order: sortOrder,
        ...(isGlobalView ? { show_all: true } : {}),
        // PACOTE BZ: passar indexStatusFilter como query param is_indexed ao backend
        // (antes era filtrado localmente com .filter(), causando tamanhos de página irregulares)
        ...(indexStatusFilter === 'completed' ? { is_indexed: true } :
           indexStatusFilter === 'pending' ? { is_indexed: false } : {}),
      });
      
      // Ignorar resposta se o pedido foi cancelado (dependency mudou entretanto)
      if (controller.signal.aborted) return;

      // Suporta novo formato paginado
      if (response.data.items) {
        setProcesses(response.data.items);
        setPagination(prev => ({
          ...prev,
          total: response.data.total,
          pages: response.data.pages
        }));
      } else {
        // Compatibilidade com formato antigo (array)
        setProcesses(response.data);
        setPagination(prev => ({
          ...prev,
          total: response.data.length,
          pages: 1
        }));
      }
    } catch (error) {
      if (error?.name === 'CanceledError' || error?.code === 'ERR_CANCELED') return;
      toast.error("Erro ao carregar processos");
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [pagination.page, pagination.size, viewMode, sortField, sortOrder, location.pathname, indexStatusFilter]);
  
  // FIX (Pacote K): Handler para mudança de filtro de vista (Select)
  const handleViewModeChange = (newMode) => {
    setViewMode(newMode);
    setSearchParams(prev => {
      if (newMode === "active_only") prev.delete("view_mode");
      else prev.set("view_mode", newMode);
      prev.set("page", "1"); // Reset para página 1
      return prev;
    }, { replace: true });
  };

  // FIX (Pacote K): Handler para restaurar processo eliminado
  const [restoringProcessIds, setRestoringProcessIds] = useState(new Set());
  const handleRestoreProcess = async (e, processId) => {
    e.stopPropagation();
    setRestoringProcessIds(prev => new Set(prev).add(processId));
    try {
      await restoreProcess(processId);
      toast.success("Processo restaurado com sucesso");
      // Re-buscar a lista para remover o processo restaurado da vista "Eliminados"
      // (o backend agora devolve is_deleted=False, pelo que não aparece em view_mode=deleted)
      // Disparar re-fetch via mudança de state — usamos uma função que força o useEffect
      setProcesses(prev => prev.filter(p => p.id !== processId));
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao restaurar processo"));
    } finally {
      setRestoringProcessIds(prev => {
        const next = new Set(prev);
        next.delete(processId);
        return next;
      });
    }
  };

  // Debounced search — only updates URL param, main useEffect handles fetch
  const [searchInput, setSearchInput] = useState(searchTerm);
  const searchInputRef = useRef(null);
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== searchTerm) {
        setSearchTerm(searchInput);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Refocus search input after search results load
  useEffect(() => {
    if (!loading && searchInputRef.current) {
      searchInputRef.current.focus();
    }
  }, [loading]);

  // Peso de prioridade para ordenação (alta=3, urgente tag=3, media=2, baixa=1, sem=0)
  const hasUrgentTag = useCallback((process) => {
    const tags = process.tags || process.labels || [];
    if (!Array.isArray(tags) || tags.length === 0) return false;
    return tags.some(t => {
      const label = (typeof t === 'string' ? t : (t?.label || t?.name || '')).toLowerCase();
      return label.includes('urgente') || label.includes('urgent');
    });
  }, []);

  const getPriorityWeight = useCallback((process) => {
    const raw = (process.prioridade || process.priority || "").toLowerCase();
    if (raw === "alta" || raw === "high") return 3;
    if (raw === "media" || raw === "medium") return 2;
    if (raw === "baixa" || raw === "low") return 1;
    // Tags urgentes contam como prioridade Alta
    if (hasUrgentTag(process)) return 3;
    return 0;
  }, [hasUrgentTag]);

  // PACOTE BZ: Sorting apenas (filtragem de indexStatusFilter delegada ao backend via is_indexed query param)
  useEffect(() => {
    // Sorting: prioridade alta + tags urgentes SEMPRE no topo, depois pelo campo seleccionado
    // PACOTE BZ: Removido o .filter() local de indexStatusFilter — o backend
    // agora filtra via is_indexed query param, evitando tamanhos de página irregulares.
    const sorted = [...processes].sort((a, b) => {
      const pa = getPriorityWeight(a);
      const pb = getPriorityWeight(b);
      if (pa !== pb) return pb - pa;
      return 0;
    });
    setSortedProcesses(sorted);
  }, [processes, getPriorityWeight]);

  // Re-fetch when filters, sort, view mode, role filter, or search term changes
  useEffect(() => {
    fetchProcesses();
  }, [fetchProcesses, filterByRole, searchTerm]);

  // Funções de paginação
  const goToPage = useCallback((page) => {
    setPagination(prev => ({ ...prev, page }));
    setSearchParams(prev => {
      prev.set("page", page.toString());
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const changePageSize = useCallback((size) => {
    setPagination(prev => ({ ...prev, page: 1, size }));
    setSearchParams(prev => {
      prev.set("page", "1");
      prev.set("size", size.toString());
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  /**
   * Resolve a prioridade de um processo (suporta campo PT e EN).
   * Retorna objecto com nivel normalizado, label, classes CSS e se é Alta.
   */
  const resolvePriority = (process) => {
    const raw = (process.prioridade || process.priority || "").toLowerCase();
    const isAlta = raw === "alta" || raw === "high";
    const isMedia = raw === "media" || raw === "medium";
    const isBaixa = raw === "baixa" || raw === "low";

    let label, badgeColor;
    if (isAlta) {
      label = "Alta";
      badgeColor = "bg-red-500 text-white border-red-600";
    } else if (isMedia) {
      label = "Média";
      badgeColor = "bg-amber-100 text-amber-800 border-amber-300";
    } else if (isBaixa) {
      label = "Baixa";
      badgeColor = "bg-green-100 text-green-800 border-green-300";
    } else {
      return { isAlta: false, label: raw || null, badgeColor: "", raw };
    }

    return { isAlta, isMedia, isBaixa, label, badgeColor, raw };
  };

  // Componente de paginação
  const PaginationControls = () => {
    const { page, pages, total, size } = pagination;
    
    if (pages <= 1) return null;
    
    const startItem = (page - 1) * size + 1;
    const endItem = Math.min(page * size, total);
    
    return (
      <div className="flex items-center justify-between px-4 py-3 border-t">
        <div className="text-sm text-muted-foreground">
          Mostrando {startItem} a {endItem} de {total} processos
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => goToPage(1)}
            disabled={page === 1}
          >
            <ChevronsLeft className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => goToPage(page - 1)}
            disabled={page === 1}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          
          <span className="text-sm mx-2">
            Página {page} de {pages}
          </span>
          
          <Button
            variant="outline"
            size="sm"
            onClick={() => goToPage(page + 1)}
            disabled={page === pages}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => goToPage(pages)}
            disabled={page === pages}
          >
            <ChevronsRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    );
  };

  // Initial load (no data yet) — show full-page skeleton
  const isInitialLoad = loading && processes.length === 0;

  if (isInitialLoad) {
    return (
      <DashboardLayout title={pageTitle}>
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <FileText className="h-5 w-5" />
                    {pageTitle}
                  </CardTitle>
                  <CardDescription>
                    A carregar processos...
                  </CardDescription>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <TableSkeleton rows={8} columns={8} />
            </CardContent>
          </Card>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title={pageTitle}>
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  {pageTitle}
                </CardTitle>
                <CardDescription>
                  Total de {pagination.total} processos no sistema
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={handleExportExcel}
                  disabled={exporting}
                >
                  {exporting ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  Exportar Excel
                </Button>
                <Button
                  className="gap-2"
                  onClick={() => setShowCreateProcess(true)}
                >
                  <Plus className="h-4 w-4" />
                  Novo Processo
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row gap-4 mb-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input 
                  ref={searchInputRef}
                  placeholder="Pesquisar por nome, email ou NIF..." 
                  className="pl-10 pr-9" 
                  value={searchInput} 
                  onChange={(e) => setSearchInput(e.target.value)} 
                />
                {loading && !isInitialLoad ? (
                  <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground animate-spin" />
                ) : searchInput ? (
                  <button
                    onClick={() => setSearchInput("")}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-full hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              </div>
              
              {/* FIX (Pacote K): Filtro de vista — Select com 3 opções */}
              <div className="flex items-center gap-2 px-3 py-2 bg-muted/50 rounded-lg">
                <Filter className="h-4 w-4 text-muted-foreground" />
                <Select value={viewMode} onValueChange={handleViewModeChange}>
                  <SelectTrigger className="h-8 w-auto text-sm border-0 bg-transparent focus:ring-0">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="active_only">Processos Ativos</SelectItem>
                    <SelectItem value="all">Todos (incl. arquivo)</SelectItem>
                    <SelectItem value="deleted">
                      <div className="flex items-center gap-2">
                        <Trash2 className="h-4 w-4 text-red-400" />
                        Eliminados
                      </div>
                    </SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Filtro de Estado de Indexação */}
              {canMarkIndexed && (
                <div className="flex items-center gap-2 px-3 py-2 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg">
                  <ClipboardCheck className="h-4 w-4 text-emerald-600" />
                  <Select value={indexStatusFilter} onValueChange={setIndexStatusFilter}>
                    <SelectTrigger className="h-8 w-[180px] border-emerald-200 dark:border-emerald-800">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Todos</SelectItem>
                      <SelectItem value="pending">Pendentes (por indexar)</SelectItem>
                      <SelectItem value="completed">Concluídos (indexados)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              )}

              {/* Toggle de Context Isolation — filtrar por cargo ativo */}
              {hasMultipleRoles && !isGlobalView && (
                <div className="flex items-center gap-2 px-3 py-2 bg-primary/5 border border-primary/20 rounded-lg">
                  <Shield className="h-4 w-4 text-primary" />
                  <div className="flex items-center gap-2">
                    <Switch
                      id="filter-by-role"
                      checked={filterByRole}
                      onCheckedChange={setFilterByRole}
                    />
                    <Label htmlFor="filter-by-role" className="text-sm cursor-pointer whitespace-nowrap">
                      {filterByRole 
                        ? `Filtrar: ${roleLabels[effectiveRole] || effectiveRole}`
                        : "Todos os meus processos"}
                    </Label>
                  </div>
                </div>
              )}
            </div>
            
            {!showCompleted && (
              <div className="mb-4 p-2 bg-blue-50 dark:bg-blue-900/20 rounded border border-blue-200 dark:border-blue-800">
                <p className="text-xs text-blue-700 dark:text-blue-300">
                  📋 Mostrando apenas processos ativos. Ative "Mostrar arquivo" para ver também concluídos e desistências.
                </p>
              </div>
            )}

            <div className={`rounded-md border overflow-x-auto transition-opacity ${loading && !isInitialLoad ? 'opacity-60 pointer-events-none' : ''}`}>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="cursor-pointer hover:bg-muted select-none" onClick={() => toggleSort("client_name")}>
                      <span className="flex items-center">Cliente <SortIcon field="client_name" /></span>
                    </TableHead>
                    <TableHead className="cursor-pointer hover:bg-muted select-none" onClick={() => toggleSort("contacto")}>
                      <span className="flex items-center">Contacto <SortIcon field="contacto" /></span>
                    </TableHead>
                    {/* PACOTE AP: removidas colunas Localização e Valor, adicionada Notas do Consultor */}
                    <TableHead className="min-w-[180px] max-w-[280px]">Notas do Consultor</TableHead>
                    <TableHead>Equipa</TableHead>
                    <TableHead className="cursor-pointer hover:bg-muted select-none" onClick={() => toggleSort("priority")}>
                      <span className="flex items-center">Prioridade <SortIcon field="priority" /></span>
                    </TableHead>
                    <TableHead className="cursor-pointer hover:bg-muted select-none" onClick={() => toggleSort("status")}>
                      <span className="flex items-center">Status <SortIcon field="status" /></span>
                    </TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {sortedProcesses.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                        {searchTerm ? `Nenhum processo encontrado com "${searchTerm}"` : "Nenhum processo encontrado"}
                      </TableCell>
                    </TableRow>
                  ) : (
                    sortedProcesses.map((process) => {
                      const prio = resolvePriority(process);
                      
                      // Construir lista de equipa
                      const teamMembers = [];
                      if (process.consultor_name || process.assigned_consultor_ids?.length > 0) {
                        const name = process.consultor_name || "Consultor atribuído";
                        teamMembers.push({ role: "Consultor", name, color: "bg-blue-100 text-blue-800" });
                      }
                      if (process.mediador_name || process.assigned_mediador_ids?.length > 0) {
                        const name = process.mediador_name || "Intermediário atribuído";
                        teamMembers.push({ role: "Intermediário", name, color: "bg-teal-100 text-teal-800" });
                      }
                      if (process.indexacao_name || process.assigned_indexacao_id) {
                        const name = process.indexacao_name || "Atribuído";
                        teamMembers.push({ role: "Indexação", name, color: "bg-gray-100 text-gray-800" });
                      }
                      if (process.parceiro_name || process.assigned_parceiro_id) {
                        const name = process.parceiro_name || "Atribuído";
                        teamMembers.push({ role: "Parceiro", name, color: "bg-purple-100 text-purple-800" });
                      }
                      
                      return (
                        <TableRow 
                          key={process.id} 
                          className={`cursor-pointer hover:bg-muted/50 ${
                            prio.isAlta 
                              ? 'bg-red-50/50 dark:bg-red-950/10 border-l-[4px] border-l-red-500' 
                              : ''
                          }`}
                          onClick={() => navigate(`/process/${process.id}`)}
                        >
                          <TableCell>
                            <div>
                              <div className="flex items-center gap-2">
                                <p className={prio.isAlta ? 'font-bold' : 'font-medium'}>
                                  {prio.isAlta && <span className="mr-1" title="Prioridade Alta">🔥</span>}
                                  {/* PACOTE CX — nome clicável + bolinhas inline (igual a MyClientsPage/FilteredProcessList) */}
                                  <span
                                    className="cursor-pointer text-primary hover:underline"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      if (process.client_id) {
                                        setClientDetailsModal({ open: true, clientId: process.client_id });
                                      }
                                    }}
                                  >
                                    {safeString(process.client_name)}
                                    {process.has_unread_messages && <span className="w-2 h-2 rounded-full bg-blue-500 inline-block ml-2" title="Nova Mensagem"></span>}
                                    {process.has_new_documents && <span className="w-2 h-2 rounded-full bg-green-500 inline-block ml-2" title="Novo Ficheiro"></span>}
                                  </span>
                                </p>
                              </div>
                              <div className="flex items-center gap-2 mt-0.5">
                                {process.process_number && (
                                  <span className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                                    #{process.process_number}
                                  </span>
                                )}
                                {process.client_nif && (
                                  <span className="text-xs text-muted-foreground">NIF: {safeString(process.client_nif)}</span>
                                )}
                              </div>
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="text-sm space-y-1">
                              {process.client_email && (
                                <div className="flex items-center gap-1">
                                  <Mail className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-xs">{safeString(process.client_email)}</span>
                                </div>
                              )}
                              {process.client_phone && (
                                <div className="flex items-center gap-1">
                                  <Phone className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-xs">{safeString(process.client_phone)}</span>
                                </div>
                              )}
                            </div>
                          </TableCell>
                          {/* PACOTE CZ: Notas do Consultor — lê a atividade mais recente PRIMEIRO */}
                          <TableCell className="min-w-[180px] max-w-[280px]">
                            {(() => {
                              // PACOTE CZ: Priorizar latest_activity_preview (alias explícito do backend)
                              // e latest_note (batch aggregation PACOTE BT) sobre process.notes estático.
                              let noteText = '';
                              if (typeof process.latest_activity_preview === 'string' && process.latest_activity_preview.trim()) {
                                noteText = process.latest_activity_preview.trim();
                              } else if (typeof process.latest_note === 'string' && process.latest_note.trim()) {
                                noteText = process.latest_note.trim();
                              } else if (typeof process.latest_activity_note === 'string' && process.latest_activity_note.trim()) {
                                noteText = process.latest_activity_note.trim();
                              } else if (process.last_activity?.content) {
                                noteText = String(process.last_activity.content);
                              } else if (Array.isArray(process.activities) && process.activities.length > 0) {
                                const lastAct = process.activities[process.activities.length - 1];
                                noteText = lastAct?.content || lastAct?.description || '';
                              }
                              if (!noteText) return <span className="text-xs text-muted-foreground">—</span>;
                              return (
                                <p className="text-xs text-muted-foreground line-clamp-2" title={noteText}>
                                  {noteText.length > 100 ? noteText.substring(0, 100) + '…' : noteText}
                                </p>
                              );
                            })()}
                          </TableCell>
                          <TableCell>
                            {teamMembers.length > 0 ? (
                              <div className="flex flex-wrap gap-1">
                                {teamMembers.slice(0, 3).map((member, idx) => (
                                  <Badge key={idx} className={`${member.color} text-[10px] px-1.5 py-0.5`} title={`${member.role}: ${member.name}`}>
                                    {member.name.split(',')[0].trim().split(' ')[0]}
                                  </Badge>
                                ))}
                                {teamMembers.length > 3 && (
                                  <Badge variant="outline" className="text-[10px] px-1.5 py-0.5" title={teamMembers.slice(3).map(m => m.name).join(', ')}>
                                    +{teamMembers.length - 3}
                                  </Badge>
                                )}
                              </div>
                            ) : (
                              <span className="text-xs text-muted-foreground">-</span>
                            )}
                          </TableCell>
                          <TableCell>
                            {prio.label && (
                              <Badge className={`${prio.badgeColor} gap-0.5 ${prio.isAlta ? 'shadow-sm shadow-red-300/50 animate-pulse' : ''}`}>
                                {prio.isAlta && <Flame className="h-3 w-3" />}
                                {prio.label}
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            {process.is_deleted || process.status === "eliminado" ? (
                              <Badge variant="destructive" className="gap-0.5">
                                <Trash2 className="h-3 w-3" />
                                Eliminado
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="capitalize">
                                {process.status?.replace(/_/g, ' ')}
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell className="text-right">
                            <div className="flex items-center justify-end gap-1">
                              {/* FIX (Pacote K): botão Restaurar na vista de Eliminados */}
                              {viewMode === "deleted" && (
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8 text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                                  onClick={(e) => handleRestoreProcess(e, process.id)}
                                  disabled={restoringProcessIds.has(process.id)}
                                  title="Restaurar processo"
                                >
                                  {restoringProcessIds.has(process.id)
                                    ? <Loader2 className="h-4 w-4 animate-spin" />
                                    : <RotateCcw className="h-4 w-4" />
                                  }
                                </Button>
                              )}
                              {canMarkIndexed && !process.is_indexed && (
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="h-8 w-8 text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50"
                                  onClick={(e) => handleMarkIndexed(e, process.id)}
                                  disabled={markingProcessIds.has(process.id)}
                                  title="Marcar indexação como concluída"
                                >
                                  {markingProcessIds.has(process.id)
                                    ? <Loader2 className="h-4 w-4 animate-spin" />
                                    : <ClipboardCheck className="h-4 w-4" />
                                  }
                                </Button>
                              )}
                              {process.is_indexed && (
                                <span className="text-[9px] bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300 px-2 py-0.5 rounded-full font-medium whitespace-nowrap border border-emerald-200 dark:border-emerald-800 flex items-center gap-0.5" title="Indexação concluída">
                                  <CheckCircle2 className="h-3 w-3" /> Indexado
                                </span>
                              )}
                              <Button 
                                variant="ghost" 
                                size="icon"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  navigate(`/process/${process.id}`);
                                }}
                              >
                                <Eye className="h-4 w-4" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </div>
            
            {/* Controlos de Paginação */}
            <PaginationControls />
          </CardContent>
        </Card>
      </div>

      {/* Create Process Modal */}
      <CreateProcessModal
        open={showCreateProcess}
        onOpenChange={setShowCreateProcess}
        onSuccess={fetchProcesses}
      />
      {/* PACOTE CX — ClientDetailsModal (popup ao clicar no nome do cliente) */}
      <ClientDetailsModal
        open={clientDetailsModal.open}
        clientId={clientDetailsModal.clientId}
        onClose={() => setClientDetailsModal({ open: false, clientId: null })}
        onNavigateToProcess={(pid) => navigate(`/process/${pid}`)}
      />
    </DashboardLayout>
  );
};

export default ProcessesPage;

