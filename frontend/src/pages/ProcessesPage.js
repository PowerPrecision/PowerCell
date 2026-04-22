/**
 * ProcessesPage — Página de listagem paginada de todos os processos do CRM.
 *
 * PORQUÊ: Vista tabular alternativa ao Kanban. Mostra processos com filtros por estado,
 * pesquisa por nome ou email, e paginação. Suporta toggle entre ativos e arquivo via view_mode na URL.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect, useCallback } from "react";
import { useNavigate, useSearchParams, useLocation } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import { Label } from "../components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { 
  Search, Eye, FileText, Phone, Mail, MapPin, Euro, Filter,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Loader2,
  User, Users, Archive, ArrowUpDown, ArrowUp, ArrowDown
} from "lucide-react";
import { toast } from "sonner";
import { getProcesses } from "../services/api";
import { TableSkeleton } from "../components/ui/skeletons";

const ProcessesPage = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [processes, setProcesses] = useState([]);
  const [loading, setLoading] = useState(true);

  // Determinar título baseado na rota
  // /lista-processos → "Todos os Processos" (Visão Global)
  // /processos → "Os Meus Processos" (O Meu Negócio)
  const pageTitle = location.pathname === "/lista-processos" ? "Todos os Processos" : "Os Meus Processos";
  
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
  // Quando showCompleted=true, mostra todos incluindo arquivo (view_mode=all)
  // ================================================================
  const [showCompleted, setShowCompleted] = useState(
    searchParams.get("view_mode") === "all"  // Default: show only active (active_only)
  );
  
  // Sort state
  const [sortField, setSortField] = useState(searchParams.get("sort") || "created_at");
  const [sortOrder, setSortOrder] = useState(searchParams.get("order") || "desc");
  const [sortedProcesses, setSortedProcesses] = useState([]);

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

  // Sync filters with URL
  const searchTerm = searchParams.get("search") || "";
  const setSearchTerm = (value) => {
    setSearchParams(prev => {
      if (value) prev.set("search", value);
      else prev.delete("search");
      prev.set("page", "1"); // Reset para página 1 ao pesquisar
      return prev;
    }, { replace: true });
  };

  const fetchProcesses = async () => {
    try {
      setLoading(true);
      // Para "/processos" (Os Meus Processos): NÃO enviar show_all — o backend
      // filtra automaticamente por user_id. Para "/lista-processos": enviar show_all
      // para mostrar TODOS os processos da empresa (visão global).
      const isGlobalView = location.pathname === "/lista-processos";

      const response = await getProcesses({
        page: pagination.page,
        size: pagination.size,
        search: searchTerm || undefined,
        view_mode: showCompleted ? "all" : "active_only",
        sort_field: sortField,
        sort_order: sortOrder,
        ...(isGlobalView ? { show_all: true } : {}),
      });
      
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
      toast.error("Erro ao carregar processos");
    } finally {
      setLoading(false);
    }
  };
  
  // Handler para toggle de processos concluídos
  const handleToggleCompleted = (checked) => {
    setShowCompleted(checked);
    setSearchParams(prev => {
      if (checked) prev.set("view_mode", "all");
      else prev.set("view_mode", "active_only");
      prev.set("page", "1"); // Reset para página 1
      return prev;
    }, { replace: true });
  };

  // Debounced search — only updates URL param, main useEffect handles fetch
  const [searchInput, setSearchInput] = useState(searchTerm);
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== searchTerm) {
        setSearchTerm(searchInput);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Sorting is handled server-side — sortedProcesses mirrors processes directly
  useEffect(() => {
    setSortedProcesses(processes);
  }, [processes]);

  // Re-fetch when search, sort, or view mode changes (driven by URL param sync)
  useEffect(() => {
    fetchProcesses();
  }, [pagination.page, pagination.size, showCompleted, searchTerm, sortField, sortOrder]);

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

  const getPriorityBadge = (priority) => {
    const colors = {
      high: "bg-red-100 text-red-800",
      medium: "bg-yellow-100 text-yellow-800",
      low: "bg-green-100 text-green-800",
    };
    const labels = {
      high: "Alta",
      medium: "Média",
      low: "Baixa",
    };
    return { color: colors[priority] || colors.medium, label: labels[priority] || priority };
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

  if (loading) {
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
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col sm:flex-row gap-4 mb-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input 
                  placeholder="Pesquisar por nome ou email..." 
                  className="pl-10" 
                  value={searchInput} 
                  onChange={(e) => setSearchInput(e.target.value)} 
                />
              </div>
              
              {/* Toggle para mostrar concluídos/desistências */}
              <div className="flex items-center gap-2 px-3 py-2 bg-muted/50 rounded-lg">
                <Archive className="h-4 w-4 text-muted-foreground" />
                <div className="flex items-center gap-2">
                  <Switch
                    id="show-completed"
                    checked={showCompleted}
                    onCheckedChange={handleToggleCompleted}
                  />
                  <Label htmlFor="show-completed" className="text-sm cursor-pointer">
                    {showCompleted ? "Mostrando todos" : "Mostrar arquivo"}
                  </Label>
                </div>
              </div>
            </div>
            
            {!showCompleted && (
              <div className="mb-4 p-2 bg-blue-50 dark:bg-blue-900/20 rounded border border-blue-200 dark:border-blue-800">
                <p className="text-xs text-blue-700 dark:text-blue-300">
                  📋 Mostrando apenas processos ativos. Ative "Mostrar arquivo" para ver também concluídos e desistências.
                </p>
              </div>
            )}

            <div className="rounded-md border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="cursor-pointer hover:bg-muted select-none" onClick={() => toggleSort("client_name")}>
                      <span className="flex items-center">Cliente <SortIcon field="client_name" /></span>
                    </TableHead>
                    <TableHead className="cursor-pointer hover:bg-muted select-none" onClick={() => toggleSort("contacto")}>
                      <span className="flex items-center">Contacto <SortIcon field="contacto" /></span>
                    </TableHead>
                    <TableHead className="cursor-pointer hover:bg-muted select-none" onClick={() => toggleSort("property_location")}>
                      <span className="flex items-center">Localização <SortIcon field="property_location" /></span>
                    </TableHead>
                    <TableHead className="cursor-pointer hover:bg-muted select-none" onClick={() => toggleSort("property_value")}>
                      <span className="flex items-center">Valor <SortIcon field="property_value" /></span>
                    </TableHead>
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
                      <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                        {searchTerm ? `Nenhum processo encontrado com "${searchTerm}"` : "Nenhum processo encontrado"}
                      </TableCell>
                    </TableRow>
                  ) : (
                    sortedProcesses.map((process) => {
                      const priorityBadge = getPriorityBadge(process.priority);
                      
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
                          className="cursor-pointer hover:bg-muted/50"
                          onClick={() => navigate(`/process/${process.id}`)}
                        >
                          <TableCell className="font-medium">
                            <div>
                              <p>{process.client_name}</p>
                              {process.client_nif && (
                                <p className="text-xs text-muted-foreground">NIF: {process.client_nif}</p>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            <div className="text-sm space-y-1">
                              {process.client_email && (
                                <div className="flex items-center gap-1">
                                  <Mail className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-xs">{process.client_email}</span>
                                </div>
                              )}
                              {process.client_phone && (
                                <div className="flex items-center gap-1">
                                  <Phone className="h-3 w-3 text-muted-foreground" />
                                  <span className="text-xs">{process.client_phone}</span>
                                </div>
                              )}
                            </div>
                          </TableCell>
                          <TableCell>
                            {process.property_location ? (
                              <div className="flex items-center gap-1">
                                <MapPin className="h-3 w-3 text-muted-foreground" />
                                <span className="text-sm">{process.property_location}</span>
                              </div>
                            ) : (
                              "-"
                            )}
                          </TableCell>
                          <TableCell>
                            {process.property_value ? (
                              <div className="text-sm">
                                <div className="font-medium text-emerald-600 flex items-center gap-1">
                                  <Euro className="h-3 w-3" />
                                  {process.property_value.toLocaleString('pt-PT')}
                                </div>
                                {process.loan_amount && (
                                  <div className="text-xs text-muted-foreground">
                                    Financ: €{process.loan_amount.toLocaleString('pt-PT')}
                                  </div>
                                )}
                              </div>
                            ) : (
                              "-"
                            )}
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
                            {process.priority && (
                              <Badge className={priorityBadge.color}>
                                {priorityBadge.label}
                              </Badge>
                            )}
                          </TableCell>
                          <TableCell>
                            <Badge variant="outline" className="capitalize">
                              {process.status?.replace(/_/g, ' ')}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right">
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
    </DashboardLayout>
  );
};

export default ProcessesPage;

