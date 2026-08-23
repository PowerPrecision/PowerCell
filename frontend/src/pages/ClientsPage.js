/**
 * ClientsPage — Página de gestão de clientes do CRM PowerCell.
 *
 * PORQUÊ: Centraliza a listagem, pesquisa e gestão de todos os clientes. Permite ao admin e
 * consultores visualizar dados de contacto, NIF, e número de processos associados.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
// PACOTE DG — removido import `safeLabel` (dropdown de Fase removido; clientes não têm fase).
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import { toast } from "sonner";
import * as XLSX from 'xlsx';
import { safeDateStr } from "../lib/utils";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import {
  Users,
  Plus,
  Search,
  MoreHorizontal,
  FileText,
  Phone,
  Mail,
  Hash,
  Eye,
  Trash2,
  RefreshCw,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  // PACOTE DG — removidos ícones `CheckCircle` e `XCircle` (dropdown de Status removido).
  Flame,
  Download,
} from "lucide-react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { TableSkeleton } from "../components/ui/skeletons";
import { hasAnyRole, hasRole } from "../utils/roleUtils";
import CreateProcessModal from "../components/CreateProcessModal";
import CreateClientModal from "../components/kanban/CreateClientModal";
import { getExportPermission } from "../services/api";
import ClientFilters from "../components/filters/ClientFilters";

const API_URL = (process.env.REACT_APP_BACKEND_URL || "https://powercell.onrender.com") + "/api";

// PACOTE DG — removida função `getContrastColor` (só era usada para colorir badges de Fase,
// que foram removidos; clientes não têm lifecycle states).

export default function ClientsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [allowExcelExport, setAllowExcelExport] = useState(true);
  
  // Admin/CEO sempre podem exportar
  const canExportExcel = allowExcelExport || hasAnyRole(user, ['admin', 'ceo']);
  
  // Sync filters with URL search params
  const searchTerm = searchParams.get("search") || "";
  const sortField = searchParams.get("sort") || "created_at";
  const sortOrder = searchParams.get("order") || "desc";
  // PACOTE FK — filtros da entidade Cliente (origem, tipo, estado).
  // Independentes dos filtros de Processos (atribuição / indexação / fase).
  const fonteFilter = searchParams.get("fonte") || "all";
  const tipoFilter = searchParams.get("tipo") || "all";
  const statusFilter = searchParams.get("status") || "all";
  const showDeleted = statusFilter === "deleted" || searchParams.get("show_deleted") === "true";
  
  const updateParam = (key, value) => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      if (value && value !== "all") {
        next.set(key, value);
      } else {
        next.delete(key);
      }
      return next;
    }, { replace: true });
  };
  
  const setSearchTerm = (v) => updateParam("search", v);
  const setFonteFilter = (v) => updateParam("fonte", v);
  const setTipoFilter = (v) => updateParam("tipo", v);
  const setStatusFilter = (v) => updateParam("status", v);
  const resetClientFilters = () => {
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.delete("fonte");
      next.delete("tipo");
      next.delete("status");
      next.delete("assignment");
      next.delete("indexacao");
      next.delete("show_deleted");
      return next;
    }, { replace: true });
  };

  // Search local state — o input só dispara a pesquisa ao submeter o formulário
  // (Enter ou botão “Pesquisar”), evitando pesquisas automáticas a cada tecla
  // (onChange) que sobrecarregam o backend e pisca a lista.
  const [searchInput, setSearchInput] = useState(searchTerm);
  useEffect(() => {
    setSearchInput(searchTerm);
  }, [searchTerm]);
  
  // PACOTE DG — removido state `availablePhases` (era populado pelo backend para o dropdown de Fase).
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showProcessDialog, setShowProcessDialog] = useState(false);
  const [processModalClient, setProcessModalClient] = useState(null);

  
  // Verificar se pode eliminar clientes (apenas admin, ceo, diretor, administrativo)
  const canDeleteClients = hasAnyRole(user, ["admin", "ceo", "diretor", "administrativo"]);
  
  // Verificar se pode criar processos - baseado em permissões
  const userActions = user?.permissions?.actions || [];
  const isAdminOrCEO = hasAnyRole(user, ["admin", "ceo"]);
  const canCreateProcess = isAdminOrCEO || (userActions.length > 0
    ? userActions.includes("create_process")
    : !hasRole(user, "indexacao"));
  
  // Verificar se pode criar clientes - baseado em permissões
  // Admin e CEO SEMPRE podem criar clientes, independentemente das permissões
  const canCreateClients = isAdminOrCEO || (userActions.length > 0
    ? userActions.includes("create_client")
    : true); // Por defeito todos podem criar

  const fetchClients = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const params = new URLSearchParams();
      params.append("show_all", "true"); // Mostrar todos os clientes da empresa
      params.append("limit", "500"); // Aumentar limite para ver todos
      if (searchTerm) params.append("search", searchTerm);
      // PACOTE FK — filtros da entidade Cliente (não da fase/atribuição do processo).
      if (fonteFilter && fonteFilter !== "all") params.append("fonte", fonteFilter);
      if (tipoFilter && tipoFilter !== "all") params.append("tipo", tipoFilter);
      if (statusFilter && statusFilter !== "all") params.append("status", statusFilter);
      // Hide deleted clients by default unless the status filter is "eliminados"
      if (!showDeleted) params.append("exclude_deleted", "true");

      const response = await fetch(`${API_URL}/clients?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setClients(data.clients || []);
        // PACOTE DG — removido `setAvailablePhases(data.available_statuses || [])` (dropdown de Fase removido).
      } else {
        const errorData = await response.json().catch(() => ({}));
        toast.error(extractErrorMessage(errorData.detail, "Erro ao carregar clientes"));
      }
    } catch (error) {
      console.error("Erro ao carregar clientes:", error);
      toast.error("Erro ao carregar clientes");
    } finally {
      setLoading(false);
    }
  // PACOTE DG — deps array: removidos `statusFilter` e `phaseFilter` (filtros removidos).
  }, [searchTerm, fonteFilter, tipoFilter, statusFilter, showDeleted]);

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  // Verificar permissão de exportação para Excel
  useEffect(() => {
    const checkExportPermission = async () => {
      try {
        const res = await getExportPermission();
        setAllowExcelExport(res.data.allow_excel_export !== false);
      } catch {
        // Em caso de erro, manter default (true)
      }
    };
    checkExportPermission();
  }, []);

  // Aplicar filtros e ordenação (useMemo — reativo e sem render extra)
  const filteredClients = useMemo(() => {
    let result = [...clients];

    // Peso de prioridade (alta=3, urgente tag=3, media=2, baixa=1, sem=0)
    const getPriorityWeight = (c) => {
      const raw = (c.prioridade || c.priority || "").toLowerCase();
      if (raw === "alta" || raw === "high") return 3;
      if (raw === "media" || raw === "medium") return 2;
      if (raw === "baixa" || raw === "low") return 1;
      return 0;
    };

    // Determinar valores de ordenação para cada item
    const getSortValue = (c) => {
      if (sortField === "contacto") {
        return (c.contacto?.email || c.contacto?.telefone || "").toLowerCase();
      }
      if (sortField === "nif") {
        return (c.dados_pessoais?.nif || "").toLowerCase();
      }
      // PACOTE DG — removido case `fase` (clientes não têm fase). Sort por `process_count`
      // agora usa `process_ids.length` (total de processos), alinhado com a nova coluna "Processos".
      if (sortField === "process_count") {
        return c.process_ids?.length || 0;
      }
      if (sortField === "nome") {
        return (c.nome || "").toLowerCase();
      }
      // Campo genérico (ex: created_at, updated_at)
      const val = c[sortField];
      if (sortField === "created_at" || sortField === "updated_at") {
        // Use Infinity for null dates to sort them to the end, avoiding 01/01/1970 epoch
        if (!val) return sortOrder === "asc" ? Infinity : -Infinity;
        const parsed = new Date(safeDateStr(val));
        return isNaN(parsed.getTime()) ? (sortOrder === "asc" ? Infinity : -Infinity) : parsed.getTime();
      }
      return typeof val === "string" ? val.toLowerCase() : val;
    };

    result.sort((a, b) => {
      // 1ª chave: prioridade SEMPRE no topo (descendente — alta primeiro)
      const pa = getPriorityWeight(a);
      const pb = getPriorityWeight(b);
      if (pa !== pb) return pb - pa;

      // 2ª chave: campo de ordenação seleccionado pelo utilizador
      const aVal = getSortValue(a);
      const bVal = getSortValue(b);

      // Tipos mistos: converter para string como fallback
      if (typeof aVal !== typeof bVal) {
        const aStr = String(aVal || "");
        const bStr = String(bVal || "");
        return sortOrder === "asc"
          ? aStr.localeCompare(bStr)
          : bStr.localeCompare(aStr);
      }

      if (sortOrder === "asc") {
        return aVal > bVal ? 1 : aVal < bVal ? -1 : 0;
      }
      return aVal < bVal ? 1 : aVal > bVal ? -1 : 0;
    });

    return result;
  }, [clients, sortField, sortOrder]);

  const toggleSort = (field) => {
    const newOrder = sortField === field
      ? (sortOrder === "asc" ? "desc" : "asc")
      : "asc";
    setSearchParams(prev => {
      const next = new URLSearchParams(prev);
      next.set("sort", field);
      next.set("order", newOrder);
      return next;
    }, { replace: true });
  };

  const SortIcon = ({ field }) => {
    if (sortField !== field) return <ArrowUpDown className="h-3 w-3 ml-1 opacity-50" />;
    return sortOrder === "asc" 
      ? <ArrowUp className="h-3 w-3 ml-1" />
      : <ArrowDown className="h-3 w-3 ml-1" />;
  };

  const handleCreateModalSuccess = useCallback(() => {
    setShowCreateModal(false);
    fetchClients();
  }, [fetchClients]);

  const handleDeleteClient = async (clientId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar este cliente?")) {
      return;
    }

    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/clients/${clientId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        toast.success("Cliente eliminado");
        fetchClients();
      } else {
        const errorData = await response.json();
        toast.error(extractErrorMessage(errorData.detail, "Erro ao eliminar cliente"));
      }
    } catch (error) {
      console.error("Erro ao eliminar cliente:", error);
      toast.error("Erro ao eliminar cliente");
    }
  };

  const openCreateProcessDialog = (client) => {
    // Mapa do formato do cliente na listagem para o formato esperado pelo CreateProcessModal
    setProcessModalClient({
      id: client.id,
      name: client.nome,
      nif: client.dados_pessoais?.nif || "",
      email: client.contacto?.email || "",
      phone: client.contacto?.telefone || "",
    });
    setShowProcessDialog(true);
  };

  const handleExportExcel = () => {
    if (filteredClients.length === 0) {
      toast.error('Nenhum cliente para exportar');
      return;
    }
    try {
      const rows = filteredClients.map(c => ({
        'Nome': c.nome || '',
        'NIF': c.dados_pessoais?.nif || '',
        'Email': c.contacto?.email || '',
        'Telefone': c.contacto?.telefone || '',
        'Estado Civil': c.dados_pessoais?.estado_civil || '',
        'Profissão': c.dados_pessoais?.profissao || '',
        'Nacionalidade': c.dados_pessoais?.nacionalidade || '',
        'Morada Completa': c.dados_pessoais?.morada_fiscal || c.morada || '',
        'Código Postal': c.dados_pessoais?.codigo_postal || c.cod_postal || '',
        'Localidade': c.dados_pessoais?.localidade || c.localidade || '',
        'Nome Titular 2': c.titular2_data?.name || c.titular2_name || '',
        'NIF Titular 2': c.titular2_data?.nif || c.titular2_nif || '',
        'Email Titular 2': c.titular2_data?.email || c.titular2_email || '',
        'Telefone Titular 2': c.titular2_data?.phone || c.titular2_phone || '',
        'Fonte': c.fonte || '',
        'Data de Registo': c.created_at || '',
      }));
      const ws = XLSX.utils.json_to_sheet(rows);
      ws['!cols'] = [
        { wch: 30 }, // Nome
        { wch: 12 }, // NIF
        { wch: 30 }, // Email
        { wch: 15 }, // Telefone
        { wch: 14 }, // Estado Civil
        { wch: 20 }, // Profissão
        { wch: 16 }, // Nacionalidade
        { wch: 35 }, // Morada Completa
        { wch: 10 }, // Código Postal
        { wch: 18 }, // Localidade
        { wch: 30 }, // Nome Titular 2
        { wch: 12 }, // NIF Titular 2
        { wch: 30 }, // Email Titular 2
        { wch: 15 }, // Telefone Titular 2
        { wch: 14 }, // Fonte
        { wch: 18 }, // Data de Registo
      ];
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Clientes');
      XLSX.writeFile(wb, 'clientes_powercell_export.xlsx');
      toast.success(`${rows.length} clientes exportados com sucesso!`);
    } catch (err) {
      console.error('Erro ao exportar Excel:', err);
      toast.error('Erro ao exportar Excel');
    }
  };



  return (
    <DashboardLayout title="Clientes Registados">
      <div className="space-y-4 md:space-y-6" data-testid="clients-page">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Users className="h-6 w-6 text-primary" />
              {/* PACOTE DG — título renomeado de "Todos os Clientes" para "Clientes Registados". */}
              Clientes Registados
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Gerir todos os clientes da empresa
            </p>
          </div>
          <div className="flex items-center gap-2">
            {canExportExcel && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleExportExcel}
                className="gap-2"
                disabled={filteredClients.length === 0}
              >
                <Download className="h-4 w-4" />
                Exportar Excel
              </Button>
            )}
            {canCreateClients && (
              <Button
                onClick={() => setShowCreateModal(true)}
                className="gap-2"
                data-testid="btn-novo-cliente"
              >
                <Plus className="h-4 w-4" />
                Novo Cliente
              </Button>
            )}
          </div>
        </div>

        {/* Search, Filters & Stats */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="md:col-span-2">
            <CardContent className="pt-4">
              <div className="flex flex-wrap items-center gap-2">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    setSearchTerm(searchInput);
                  }}
                  className="flex items-center gap-2 w-full sm:flex-1 sm:min-w-[200px]"
                >
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
                    <Input
                      placeholder="Pesquisar por nome, email ou NIF..."
                      value={searchInput}
                      onChange={(e) => setSearchInput(e.target.value)}
                      className="pl-10"
                      data-testid="search-clients-input"
                    />
                  </div>
                  <Button
                    type="submit"
                    size="sm"
                    data-testid="search-clients-btn"
                    className="h-9"
                    title="Pesquisar"
                  >
                    <Search className="h-4 w-4 sm:mr-1" />
                    <span className="hidden sm:inline">Pesquisar</span>
                  </Button>
                </form>
                <div className="flex flex-wrap gap-2 w-full sm:w-auto">
                <ClientFilters
                  fonte={fonteFilter}
                  onFonteChange={setFonteFilter}
                  tipo={tipoFilter}
                  onTipoChange={setTipoFilter}
                  status={statusFilter}
                  onStatusChange={setStatusFilter}
                  onReset={resetClientFilters}
                />
                <Select value={`${sortField}_${sortOrder}`} onValueChange={(v) => {
                  const lastIdx = v.lastIndexOf('_');
                  const field = v.substring(0, lastIdx);
                  const order = v.substring(lastIdx + 1);
                  // Atualizar ambos os params numa única operação para evitar re-renders intermédios
                  setSearchParams(prev => {
                    const next = new URLSearchParams(prev);
                    next.set("sort", field);
                    next.set("order", order);
                    return next;
                  }, { replace: true });
                }}>
                  <SelectTrigger className="w-full sm:w-[150px]" data-testid="sort-field">
                    <ArrowUpDown className="h-4 w-4 mr-2" />
                    <SelectValue placeholder="Ordenar" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="created_at_desc">Mais Recentes</SelectItem>
                    <SelectItem value="created_at_asc">Mais Antigos</SelectItem>
                    <SelectItem value="nome_asc">Nome (A-Z)</SelectItem>
                    <SelectItem value="nome_desc">Nome (Z-A)</SelectItem>
                    <SelectItem value="process_count_desc">Mais Processos</SelectItem>
                    <SelectItem value="process_count_asc">Menos Processos</SelectItem>
                    <SelectItem value="contacto_asc">Contacto (A-Z)</SelectItem>
                    <SelectItem value="nif_asc">NIF (A-Z)</SelectItem>
                    {/* PACOTE DG — removido sort option `fase_asc` "Fase (A-Z)" (clientes não têm fase). */}
                    <SelectItem value="updated_at_desc">Última Atualização</SelectItem>
                  </SelectContent>
                </Select>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                  <Users className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{clients.length}</p>
                  <p className="text-xs text-muted-foreground">Total Clientes</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                  <FileText className="h-5 w-5 text-green-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">
                    {/* PACOTE DG — métrica agora usa `process_ids.length` (total de processos, não só ativos). */}
                    {clients.reduce((s, c) => s + (c.process_ids?.length || 0), 0)}
                  </p>
                  <p className="text-xs text-muted-foreground">Total de Processos</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Clients Table */}
        <Card>
          <CardHeader className="pb-3 sticky top-0 z-10 bg-card border-b">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">Lista de Clientes</CardTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={fetchClients}
                className="gap-2"
              >
                <RefreshCw className="h-4 w-4" />
                Actualizar
              </Button>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? (
              <div className="p-6">
                <TableSkeleton rows={8} columns={5} />
              </div>
            ) : filteredClients.length === 0 ? (
              <div className="text-center py-12">
                <Users className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                <p className="text-muted-foreground">
                  {clients.length === 0 ? "Nenhum cliente encontrado" : "Nenhum cliente corresponde aos filtros"}
                </p>
                {clients.length === 0 && canCreateClients && (
                  <Button
                    variant="outline"
                    className="mt-4"
                    onClick={() => setShowCreateModal(true)}
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Criar primeiro cliente
                  </Button>
                )}
              </div>
            ) : (
              <>
              {/* O9 - Mobile: Card view */}
              <div className="md:hidden space-y-3 p-3">
                {filteredClients.map((client, idx) => {
                  const clientPriority = (client.prioridade || '').toLowerCase();
                  const isAlta = clientPriority === 'alta' || clientPriority === 'high';
                  return (
                  <div key={`mobile-${client.id}-${idx}`} className={`border rounded-lg p-3 space-y-2 ${isAlta ? 'border-l-[4px] border-l-red-500 bg-red-50/60 dark:bg-red-950/20' : 'bg-card'}`} data-testid={`client-card-${client.id}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0 flex-1">
                        <div className={`h-8 w-8 rounded-full flex items-center justify-center shrink-0 ${isAlta ? 'bg-red-100 dark:bg-red-900/30' : 'bg-primary/10'}`}>
                          <span className={`text-xs font-medium ${isAlta ? 'text-red-600 dark:text-red-400' : 'text-primary'}`}>
                            {client.nome?.charAt(0)?.toUpperCase() || "?"}
                          </span>
                        </div>
                        <div className="min-w-0">
                          <button
                            className={`text-sm text-left hover:text-primary truncate block max-w-full ${isAlta ? 'font-bold' : 'font-medium'}`}
                            onClick={() => navigate(`/cliente/${client.id}`)}
                          >
                            {isAlta && <span className="mr-1">🔥</span>}
                            {client.nome}
                          </button>
                          {/* PACOTE DG — removido badge "Inativo" (clientes não têm estado activo/inactivo). */}
                          {client.contacto?.email && (
                            <p className="text-xs text-muted-foreground truncate">{client.contacto.email}</p>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        {isAlta && (
                          <Badge className="bg-red-500 text-white border-red-600 text-[9px] px-1.5 py-0 h-4 gap-0.5 animate-pulse shadow-sm shadow-red-300/50">
                            <Flame className="h-2.5 w-2.5" /> Alta
                          </Badge>
                        )}
                        {/* PACOTE DG — badge "Fase" substituído por badge "Processos" (total de processos do cliente). */}
                        <Badge variant="secondary" className="gap-1 text-[10px]">
                          <FileText className="h-3 w-3" />
                          {client.process_ids?.length || 0} Processo{(client.process_ids?.length || 0) !== 1 ? 's' : ''}
                        </Badge>
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <div className="flex items-center gap-3">
                        {client.contacto?.telefone && (
                          <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{client.contacto.telefone}</span>
                        )}
                        {client.dados_pessoais?.nif && (
                          <span className="flex items-center gap-1 font-mono"><Hash className="h-3 w-3" />{client.dados_pessoais.nif}</span>
                        )}
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-7 w-7">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => navigate(`/cliente/${client.id}`)}
                          >
                            <Eye className="h-4 w-4 mr-2" />
                            Ver Ficha
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() => openCreateProcessDialog(client)}
                          >
                            <Plus className="h-4 w-4 mr-2" />
                            Iniciar Novo Processo
                          </DropdownMenuItem>
                          {canDeleteClients && (
                            <DropdownMenuItem onClick={() => handleDeleteClient(client.id)} className="text-red-600">
                              <Trash2 className="h-4 w-4 mr-2" />
                              Eliminar
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                  );
                })}
              </div>

              {/* O9 - Desktop: Table */}
              <div className="hidden md:block max-h-[calc(100vh-350px)] overflow-auto">
                <Table>
                  <TableHeader className="sticky top-0 z-10 bg-card">
                    <TableRow className="bg-muted/50">
                      <TableHead 
                        className="cursor-pointer hover:bg-muted select-none" 
                        onClick={() => toggleSort("nome")}
                      >
                        <span className="flex items-center">
                          Cliente
                          <SortIcon field="nome" />
                        </span>
                      </TableHead>
                      <TableHead 
                        className="cursor-pointer hover:bg-muted select-none" 
                        onClick={() => toggleSort("contacto")}
                      >
                        <span className="flex items-center">
                          Contacto
                          <SortIcon field="contacto" />
                        </span>
                      </TableHead>
                      <TableHead 
                        className="cursor-pointer hover:bg-muted select-none" 
                        onClick={() => toggleSort("nif")}
                      >
                        <span className="flex items-center">
                          NIF
                          <SortIcon field="nif" />
                        </span>
                      </TableHead>
                      {/* PACOTE DG — coluna "Fase" substituída por "Processos" (clientes não têm fase). */}
                      <TableHead className="text-center">Processos</TableHead>
                      <TableHead className="text-right">Acções</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                  {filteredClients.map((client, idx) => {
                    const clientPriority = (client.prioridade || '').toLowerCase();
                    const isAlta = clientPriority === 'alta' || clientPriority === 'high';
                    return (
                    <TableRow 
                      key={`${client.id}-${idx}`} 
                      data-testid={`client-row-${client.id}`}
                      className={isAlta ? 'bg-red-50/60 dark:bg-red-950/10 border-l-[4px] border-l-red-500' : ''}
                    >
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <div className={`h-9 w-9 rounded-full flex items-center justify-center ${isAlta ? 'bg-red-100 dark:bg-red-900/30' : 'bg-primary/10'}`}>
                            <span className={`text-sm font-medium ${isAlta ? 'text-red-600 dark:text-red-400' : 'text-primary'}`}>
                              {client.nome?.charAt(0)?.toUpperCase() || "?"}
                            </span>
                          </div>
                          <div>
                            <div className="flex items-center gap-2">
                              <button
                                className={`text-left hover:text-primary hover:underline transition-colors cursor-pointer ${isAlta ? 'font-bold' : 'font-medium'}`}
                                onClick={() => navigate(`/cliente/${client.id}`)}
                                data-testid={`client-name-${client.id}`}
                              >
                                {isAlta && <span className="mr-1">🔥</span>}
                                {client.nome}
                              </button>
                              {isAlta && (
                                <Badge className="bg-red-500 text-white border-red-600 text-[10px] px-2 py-0 h-5 gap-0.5 shadow-sm shadow-red-300/50">
                                  <Flame className="h-3 w-3" /> Prioridade Alta
                                </Badge>
                              )}
                              {/* PACOTE DG — removido badge "Inativo" (clientes não têm estado activo/inactivo). */}
                            </div>
                            {client.fonte && (
                              <Badge variant="outline" className="text-xs mt-1">
                                {client.fonte}
                              </Badge>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          {client.contacto?.email && (
                            <div className="flex items-center gap-1 text-sm text-muted-foreground">
                              <Mail className="h-3 w-3" />
                              {client.contacto.email}
                            </div>
                          )}
                          {client.contacto?.telefone && (
                            <div className="flex items-center gap-1 text-sm text-muted-foreground">
                              <Phone className="h-3 w-3" />
                              {client.contacto.telefone}
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        {client.dados_pessoais?.nif ? (
                          <div className="flex items-center gap-1">
                            <Hash className="h-3 w-3 text-muted-foreground" />
                            <span className="font-mono text-sm">
                              {client.dados_pessoais.nif}
                            </span>
                          </div>
                        ) : (
                          <span className="text-muted-foreground text-sm">-</span>
                        )}
                      </TableCell>
                      {/* PACOTE DG — cell "Fase" substituída por cell "Processos" com Badge secundário (token semântico). */}
                      <TableCell className="text-center">
                        <Badge variant="secondary" className="gap-1">
                          <FileText className="h-3 w-3" />
                          {client.process_ids?.length || 0} Processo{(client.process_ids?.length || 0) !== 1 ? 's' : ''}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              data-testid={`client-actions-${client.id}`}
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => navigate(`/cliente/${client.id}`)}
                            >
                              <Eye className="h-4 w-4 mr-2" />
                              Ver Ficha
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={() => openCreateProcessDialog(client)}
                            >
                              <Plus className="h-4 w-4 mr-2" />
                              Iniciar Novo Processo
                            </DropdownMenuItem>
                            {canDeleteClients && (
                              <DropdownMenuItem
                                onClick={() => handleDeleteClient(client.id)}
                                className="text-red-600"
                              >
                                <Trash2 className="h-4 w-4 mr-2" />
                                Eliminar
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
              </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Create Client/Process Modal — mesmo fluxo que MyClientsPage */}
        <CreateClientModal
          open={showCreateModal}
          onOpenChange={setShowCreateModal}
          onSuccess={handleCreateModalSuccess}
        />

        {/* Create Process Modal — reutiliza CreateProcessModal com cliente pré-selecionado */}
        {canCreateProcess && (
          <CreateProcessModal
            open={showProcessDialog}
            onOpenChange={(open) => {
              setShowProcessDialog(open);
              if (!open) setProcessModalClient(null);
            }}
            preSelectedClient={processModalClient}
            onSuccess={() => fetchClients()}
          />
        )}
      </div>
    </DashboardLayout>
  );
}

