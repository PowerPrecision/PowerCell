/**
 * ClientRegistrationsPage - Página de Registo de Clientes (Triagem Manual)
 * Mostra leads pendentes de triagem (lead_status="new")
 * 
 * ACESSO: Todos os utilizadores
 * 
 * Funcionalidades:
 * - Listar leads pendentes (sem processo)
 * - Filtros: com/sem processo, pesquisa
 * - Ordenação por data de registo (defeito)
 * - "Criar Processo" abre CreateProcessModal (triagem manual)
 * 
 * FLUXO DE TRIAGEM:
 * 1. Formulário público cria cliente com lead_status="new"
 * 2. Consultor/Admin vê a lead aqui e clica "Criar Processo"
 * 3. CreateProcessModal abre com cliente pré-selecionado
 * 4. Após criação, lead_status muda para "converted" → desaparece da lista
 */
import React, { useState, useEffect, useCallback } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { toast } from "sonner";
import {
  Users,
  Loader2,
  Search,
  RefreshCw,
  Calendar,
  Mail,
  Phone,
  Hash,
  FileText,
  CheckCircle,
  XCircle,
  ArrowUpDown,
  Filter,
  Eye,
  MapPin,
  Briefcase,
  Heart,
  User,
  DollarSign,
  CreditCard,
  Building,
  Clock,
  FileInput,
  ClipboardList,
} from "lucide-react";
import { TableSkeleton } from "../components/ui/skeletons";
import { safeString } from "../utils/safeString";
import CreateProcessModal from "../components/CreateProcessModal";
import { formatDate, formatDateTime } from "../lib/utils";
import { formatCurrency } from "../utils/formatCurrency";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ClientRegistrationsPage = () => {
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [clients, setClients] = useState([]);
  const [total, setTotal] = useState(0);
  
  // Ler filtros da URL (persistidos na navegação)
  const [search, setSearch] = useState(() => searchParams.get("search") || "");
  const [hasProcessFilter, setHasProcessFilter] = useState(() => searchParams.get("has_process") || "false");
  const [sortField, setSortField] = useState(() => searchParams.get("sort_field") || "created_at");
  const [sortOrder, setSortOrder] = useState(() => searchParams.get("sort_order") || "desc");
  const [assignedToMe, setAssignedToMe] = useState(() => searchParams.get("assigned_to_me") === "true");

  // Debounce para pesquisa
  const searchTimeoutRef = React.useRef(null);

  // Actualizar filtros na URL
  const updateSearch = useCallback((value) => {
    setSearch(value);
    // Debounce: só actualiza a URL após 300ms sem input
    clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(() => {
      setSearchParams(prev => {
        if (value) prev.set("search", value);
        else prev.delete("search");
        return prev;
      }, { replace: true });
    }, 300);
  }, [setSearchParams]);

  const updateHasProcessFilter = useCallback((value) => {
    setHasProcessFilter(value);
    setSearchParams(prev => {
      if (value === "all") prev.delete("has_process");
      else prev.set("has_process", value);
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const updateSort = useCallback((value) => {
    const [field, order] = value.split('_');
    setSortField(field);
    setSortOrder(order);
    setSearchParams(prev => {
      prev.set("sort_field", field);
      prev.set("sort_order", order);
      return prev;
    }, { replace: true });
  }, [setSearchParams]);

  const updateAssignedToMe = useCallback((value) => {
    setAssignedToMe(value);
    setSearchParams(prev => {
      if (value) prev.set("assigned_to_me", "true");
      else prev.delete("assigned_to_me");
      return prev;
    }, { replace: true });
  }, [setSearchParams]);
  
  // CreateProcessModal — Abre com cliente pré-selecionado
  const [createProcessModal, setCreateProcessModal] = useState({ open: false, client: null });

  // Client details dialog
  const [detailsDialog, setDetailsDialog] = useState({ open: false, client: null });
  const [detailsLoading, setDetailsLoading] = useState(false);

  // Auto-abrir modal de detalhes quando vem da notificação (?clientId=xxx)
  useEffect(() => {
    const clientIdFromUrl = searchParams.get("clientId");
    if (clientIdFromUrl && !detailsDialog.open) {
      // Limpar o param da URL para não re-abrir ao navegar de volta
      setSearchParams(prev => {
        prev.delete("clientId");
        return prev;
      }, { replace: true });
      // Buscar detalhes do cliente e abrir modal
      setDetailsLoading(true);
      fetch(`${API_URL}/api/clients/${clientIdFromUrl}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(res => res.ok ? res.json() : Promise.reject("Erro"))
        .then(data => setDetailsDialog({ open: true, client: data }))
        .catch(() => toast.error("Erro ao carregar detalhes do cliente"))
        .finally(() => setDetailsLoading(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  const userRole = user?.role || "";
  const isIndexacao = userRole === "indexacao";
  
  // Verificar permissões
  const canAssign = userRole !== "indexacao";

  const fetchClients = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.append("search", search);
      if (hasProcessFilter !== "all") params.append("has_process", hasProcessFilter);
      if (assignedToMe || isIndexacao) params.append("assigned_to_me", "true");
      // PACOTE BN — Sala de Triagem: inclui leads + pre_registo + processos sem indexador
      params.append("triage_mode", "true");
      params.append("sort_field", sortField);
      params.append("sort_order", sortOrder);
      params.append("limit", "100");

      const response = await fetch(`${API_URL}/api/clients/registered?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setClients(data.clients || []);
        setTotal(data.total || 0);
      } else {
        toast.error("Erro ao carregar clientes");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar clientes");
    } finally {
      setLoading(false);
    }
  }, [token, search, hasProcessFilter, sortField, sortOrder, assignedToMe, isIndexacao]);

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  const handleViewClientDetails = async (clientId) => {
    setDetailsLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/clients/${clientId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setDetailsDialog({ open: true, client: data });
      } else {
        toast.error("Erro ao carregar detalhes do cliente");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar detalhes do cliente");
    } finally {
      setDetailsLoading(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Users className="h-6 w-6 text-primary" />
              Registo de Clientes
            </h1>
            <p className="text-muted-foreground text-sm mt-1">
              Leads pendentes de triagem — clique "Criar Processo" para aprovar
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate('/formulario-consultor')}
              className="gap-2"
              data-testid="preview-form-btn"
            >
              <Eye className="h-4 w-4" />
              Pré-visualizar Formulário
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchClients}
              className="gap-2"
            >
              <RefreshCw className="h-4 w-4" />
              Actualizar
            </Button>
          </div>
        </div>

        {/* Stats - Melhorado com progress bars */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="border-l-4 border-l-blue-500">
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-blue-100 dark:bg-blue-900/30 rounded-xl">
                    <Users className="h-5 w-5 text-blue-600" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold">{total}</p>
                    <p className="text-xs text-muted-foreground">Total Registados</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-green-500">
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-green-100 dark:bg-green-900/30 rounded-xl">
                    <CheckCircle className="h-5 w-5 text-green-600" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold">
                      {clients.filter(c => c.has_process).length}
                    </p>
                    <p className="text-xs text-muted-foreground">Com Processo</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-green-600">
                    {total > 0 ? Math.round((clients.filter(c => c.has_process).length / total) * 100) : 0}%
                  </p>
                </div>
              </div>
              <div className="mt-2 h-1.5 bg-muted rounded-full overflow-hidden">
                <div 
                  className="h-full bg-green-500 rounded-full transition-all duration-500"
                  style={{ width: `${total > 0 ? (clients.filter(c => c.has_process).length / total) * 100 : 0}%` }}
                />
              </div>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-orange-500">
            <CardContent className="pt-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-orange-100 dark:bg-orange-900/30 rounded-xl">
                    <XCircle className="h-5 w-5 text-orange-600" />
                  </div>
                  <div>
                    <p className="text-2xl font-bold">
                      {clients.filter(c => !c.has_process).length}
                    </p>
                    <p className="text-xs text-muted-foreground">Leads Pendentes</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="text-sm font-medium text-orange-600">
                    {total > 0 ? Math.round((clients.filter(c => !c.has_process).length / total) * 100) : 0}%
                  </p>
                </div>
              </div>
              <div className="mt-2 h-1.5 bg-muted rounded-full overflow-hidden">
                <div 
                  className="h-full bg-orange-500 rounded-full transition-all duration-500"
                  style={{ width: `${total > 0 ? (clients.filter(c => !c.has_process).length / total) * 100 : 0}%` }}
                />
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filters */}
        <Card>
          <CardContent className="pt-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="relative w-full sm:flex-1 sm:min-w-[200px]">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Pesquisar por nome, email ou NIF..."
                  value={search}
                  onChange={(e) => updateSearch(e.target.value)}
                  className="pl-10"
                />
              </div>
              
              <Select value={hasProcessFilter} onValueChange={updateHasProcessFilter}>
                <SelectTrigger className="w-full sm:w-[160px]">
                  <Filter className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Filtrar..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="true">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="h-4 w-4 text-green-600" />
                      Com Processo
                    </div>
                  </SelectItem>
                  <SelectItem value="false">
                    <div className="flex items-center gap-2">
                      <XCircle className="h-4 w-4 text-orange-600" />
                      Sem Processo
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
              
              <Select value={`${sortField}_${sortOrder}`} onValueChange={updateSort}>
                <SelectTrigger className="w-full sm:w-[155px]">
                  <ArrowUpDown className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Ordenar" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="created_at_desc">Mais Recentes</SelectItem>
                  <SelectItem value="created_at_asc">Mais Antigos</SelectItem>
                  <SelectItem value="nome_asc">Nome (A-Z)</SelectItem>
                  <SelectItem value="nome_desc">Nome (Z-A)</SelectItem>
                </SelectContent>
              </Select>
              
              {isIndexacao && (
                <Button
                  variant={assignedToMe ? "default" : "outline"}
                  size="sm"
                  onClick={() => updateAssignedToMe(!assignedToMe)}
                  className="gap-2"
                >
                  <Users className="h-4 w-4" />
                  Atribuídos a Mim
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Clients List - Design melhorado */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg flex items-center gap-2">
              <Users className="h-5 w-5" />
              Clientes Registados ({total})
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <TableSkeleton rows={6} columns={5} />
            ) : clients.length === 0 ? (
              <div className="text-center py-16">
                <div className="mx-auto w-16 h-16 bg-muted rounded-full flex items-center justify-center mb-4">
                  <Users className="h-8 w-8 text-muted-foreground/50" />
                </div>
                <p className="text-muted-foreground font-medium">
                  Nenhum cliente encontrado
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  Os clientes que se registarem aparecerão aqui
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {/* Table Header */}
                <div className="hidden md:grid grid-cols-12 gap-3 px-4 py-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider bg-muted/30 rounded-lg border">
                  <div className="col-span-3">Cliente</div>
                  <div className="col-span-2">Contacto</div>
                  <div className="col-span-2">NIF</div>
                  <div className="col-span-2">Estado</div>
                  <div className="col-span-2">Data Registo</div>
                  <div className="col-span-1 text-right">Acções</div>
                </div>

                {/* Rows - Design melhorado */}
                {clients.map((client) => (
                  <div
                    key={client.id}
                    className={`grid grid-cols-1 md:grid-cols-12 gap-3 px-4 py-4 items-center hover:bg-primary/5 rounded-xl border transition-all duration-200 ${
                      client.has_process 
                        ? 'border-l-4 border-l-green-500 bg-green-50/30 dark:bg-green-900/10' 
                        : 'border-l-4 border-l-orange-500 bg-orange-50/30 dark:bg-orange-900/10'
                    }`}
                  >
                    <div className="col-span-3">
                      <div className="flex items-center gap-3">
                        <div className={`h-10 w-10 rounded-full flex items-center justify-center font-semibold shrink-0 ${
                          client.has_process 
                            ? 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300' 
                            : 'bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300'
                        }`}>
                          {safeString(client.nome).charAt(0)?.toUpperCase() || "?"}
                        </div>
                        <div className="min-w-0 flex-1 overflow-hidden">
                          <button
                            onClick={() => handleViewClientDetails(client.id)}
                            className="font-semibold text-left hover:text-primary transition-colors cursor-pointer block truncate w-full"
                            title={safeString(client.nome)}
                          >
                            {safeString(client.nome)}
                          </button>
                          {client.fonte && (
                            <Badge variant="outline" className="text-[10px] mt-1 px-1.5 py-0">
                              {safeString(client.fonte)}
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    
                    <div className="col-span-2 space-y-1.5 min-w-0">
                      {client.contacto?.email && (
                        <div className="flex items-center gap-1.5 text-sm text-muted-foreground min-w-0">
                          <Mail className="h-3.5 w-3.5 flex-shrink-0" />
                          <span className="truncate" title={safeString(client.contacto.email)}>{safeString(client.contacto.email)}</span>
                        </div>
                      )}
                      {client.contacto?.telefone && (
                        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                          <Phone className="h-3.5 w-3.5 flex-shrink-0" />
                          <span className="whitespace-nowrap">{safeString(client.contacto.telefone)}</span>
                        </div>
                      )}
                    </div>
                    
                    <div className="col-span-2">
                      {client.nif ? (
                        <div className="flex items-center gap-1.5 px-2 py-1 bg-muted/50 rounded-md w-fit">
                          <Hash className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="font-mono text-sm font-medium">{safeString(client.nif)}</span>
                        </div>
                      ) : (
                        <span className="text-muted-foreground text-sm italic">Não preenchido</span>
                      )}
                    </div>
                    
                    <div className="col-span-2">
                      {/* PACOTE BN — Badges de Sala de Triagem */}
                      {/* Prioridade: pre_registo > ready_for_indexing > Tem/Sem Processo */}
                      {client.triage_status === "pre_registo" ? (
                        <div className="flex flex-col gap-1">
                          <Badge
                            className="bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-700 text-xs px-2 py-1"
                            data-testid={`triage-badge-pre-registo-${client.id}`}
                          >
                            <FileInput className="h-3 w-3 mr-1" />
                            Pré-Registo (A preencher Portal)
                          </Badge>
                          {client.processes?.length > 0 && (
                            <span className="text-xs text-muted-foreground font-mono">
                              #{safeString(client.processes[0].process_number)}
                            </span>
                          )}
                        </div>
                      ) : client.triage_status === "ready_for_indexing" ? (
                        <div className="flex flex-col gap-1">
                          <Badge
                            className="bg-blue-600 text-white text-xs px-2 py-1"
                            data-testid={`triage-badge-ready-${client.id}`}
                          >
                            <ClipboardList className="h-3 w-3 mr-1" />
                            Pronto para Indexação (Na fila de espera)
                          </Badge>
                          {client.processes?.length > 0 && (
                            <span className="text-xs text-muted-foreground font-mono">
                              #{safeString(client.processes[0].process_number)}
                            </span>
                          )}
                        </div>
                      ) : client.has_process ? (
                        <div className="flex flex-col gap-1">
                          <Badge className="bg-green-600 text-white text-xs px-2 py-1">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Tem Processo
                          </Badge>
                          {client.processes?.length > 0 && (
                            <span className="text-xs text-muted-foreground font-mono">
                              #{safeString(client.processes[0].process_number)}
                            </span>
                          )}
                        </div>
                      ) : (
                        <Badge variant="outline" className="text-orange-600 border-orange-300 bg-orange-50 dark:bg-orange-900/20 text-xs px-2 py-1">
                          <XCircle className="h-3 w-3 mr-1" />
                          Sem Processo
                        </Badge>
                      )}
                    </div>
                    
                    <div className="col-span-2 text-sm">
                      <div className="flex items-center gap-1.5 text-muted-foreground">
                        <Calendar className="h-3.5 w-3.5" />
                        <span>{formatDateTime(client.created_at)}</span>
                      </div>
                      {client.assigned_to_name && (
                        <div className="text-xs mt-1.5 flex items-center gap-1 text-primary">
                          <User className="h-3 w-3" />
                          {safeString(client.assigned_to_name)}
                        </div>
                      )}
                    </div>
                    
                    <div className="col-span-1 flex justify-end gap-1">
                      {client.has_process && client.processes?.length > 0 && (
                        <Button
                          variant="default"
                          size="sm"
                          // FIX (Pacote K): navegar para o primeiro processo ATIVO
                          // (não eliminado) em vez de processes[0], que pode ser
                          // um processo antigo eliminado.
                          onClick={() => {
                            const activeProc = client.processes.find(
                              (p) => !p.is_deleted && p.status !== "eliminado"
                            ) || client.processes[0];
                            navigate(`/process/${activeProc.id}`);
                          }}
                          title="Ver processo"
                          className="h-8"
                        >
                          <Eye className="h-4 w-4 mr-1" />
                          Ver
                        </Button>
                      )}
                      {!client.has_process && canAssign && (
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => setCreateProcessModal({ open: true, client })}
                          title="Criar Processo a partir deste registo"
                          className="h-8"
                        >
                          <FileText className="h-4 w-4 mr-1" />
                          Criar Processo
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* CreateProcessModal — Triagem: Criar Processo a partir do Registo */}
      <CreateProcessModal
        open={createProcessModal.open}
        onOpenChange={(open) => setCreateProcessModal({ open, client: open ? createProcessModal.client : null })}
        onSuccess={(data) => {
          // Processo criado com sucesso → lead desaparece dos registos
          setCreateProcessModal({ open: false, client: null });
          toast.success(`Processo #${data.process_number} criado com sucesso`);
          fetchClients(); // Atualizar lista (lead convertido já não aparece)
          // Navegar para o novo processo
          if (data.id) {
            navigate(`/process/${data.id}`);
          }
        }}
        preSelectedClient={createProcessModal.client ? {
          id: createProcessModal.client.id,
          name: createProcessModal.client.nome,
          nif: createProcessModal.client.nif || createProcessModal.client.dados_pessoais?.nif || "",
          email: createProcessModal.client.contacto?.email || "",
          phone: createProcessModal.client.contacto?.telefone || "",
        } : null}
      />

      {/* Client Details Dialog */}
      <Dialog open={detailsDialog.open} onOpenChange={(open) => setDetailsDialog({ open, client: detailsDialog.client })}>
        <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <User className="h-5 w-5" />
              Detalhes do Cliente
            </DialogTitle>
            <DialogDescription>
              Informações completas do cliente
            </DialogDescription>
          </DialogHeader>

          {detailsLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : detailsDialog.client ? (
            <div className="py-4 space-y-6">
              {/* Nome e Info Básica */}
              <div className="flex items-center gap-4 pb-4 border-b">
                <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
                  <span className="text-2xl font-bold text-primary">
                    {safeString(detailsDialog.client.nome).charAt(0)?.toUpperCase() || "?"}
                  </span>
                </div>
                <div>
                  <h3 className="text-xl font-bold">{safeString(detailsDialog.client.nome)}</h3>
                  <div className="flex items-center gap-2 mt-1">
                    {detailsDialog.client.fonte && (
                      <Badge variant="outline">{safeString(detailsDialog.client.fonte)}</Badge>
                    )}
                    {detailsDialog.client.nif && (
                      <Badge variant="secondary" className="font-mono">
                        NIF: {safeString(detailsDialog.client.nif)}
                      </Badge>
                    )}
                  </div>
                </div>
              </div>

              {/* Contactos */}
              <div>
                <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <Phone className="h-4 w-4" />
                  Contactos
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {detailsDialog.client.contacto?.email && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Mail className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{safeString(detailsDialog.client.contacto.email)}</span>
                    </div>
                  )}
                  {detailsDialog.client.contacto?.telefone && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Phone className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{safeString(detailsDialog.client.contacto.telefone)}</span>
                    </div>
                  )}
                  {detailsDialog.client.contacto?.email_secundario && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Mail className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{safeString(detailsDialog.client.contacto.email_secundario)}</span>
                    </div>
                  )}
                  {detailsDialog.client.contacto?.telefone_secundario && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Phone className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{safeString(detailsDialog.client.contacto.telefone_secundario)}</span>
                    </div>
                  )}
                  {!detailsDialog.client.contacto?.email && !detailsDialog.client.contacto?.telefone && (
                    <p className="text-sm text-muted-foreground col-span-2">Sem contactos registados</p>
                  )}
                </div>
              </div>

              {/* Dados Pessoais */}
              <div>
                <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <User className="h-4 w-4" />
                  Dados Pessoais
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Calendar className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Data de Nascimento</p>
                      <p className="text-sm">{detailsDialog.client.dados_pessoais?.data_nascimento ? formatDate(detailsDialog.client.dados_pessoais.data_nascimento) : <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Naturalidade</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_pessoais?.naturalidade) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Nacionalidade</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_pessoais?.nacionalidade) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Heart className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Estado Civil</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_pessoais?.estado_civil) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Briefcase className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Profissão</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_pessoais?.profissao) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Documento ID</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_pessoais?.documento_id) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Hash className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">NIF</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_pessoais?.nif) || safeString(detailsDialog.client.nif) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-2 p-2 bg-muted/50 rounded-lg">
                    <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div>
                      <p className="text-xs text-muted-foreground">Morada Fiscal</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_pessoais?.morada_fiscal) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Dados Financeiros */}
              <div>
                <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <DollarSign className="h-4 w-4" />
                  Dados Financeiros
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <DollarSign className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Rendimento Mensal</p>
                      <p className="text-sm font-medium">
                        {detailsDialog.client.dados_financeiros?.rendimento_mensal
                          ? formatCurrency(safeString(detailsDialog.client.dados_financeiros.rendimento_mensal))
                          : <span className="text-muted-foreground italic">Não preenchido</span>}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <DollarSign className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Rendimento Anual</p>
                      <p className="text-sm font-medium">
                        {detailsDialog.client.dados_financeiros?.rendimento_anual
                          ? formatCurrency(safeString(detailsDialog.client.dados_financeiros.rendimento_anual))
                          : <span className="text-muted-foreground italic">Não preenchido</span>}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Tipo de Contrato</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_financeiros?.tipo_contrato) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Building className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Empresa</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_financeiros?.empresa) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Antiguidade no Emprego</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_financeiros?.antiguidade_emprego) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Trabalha no Estrangeiro</p>
                      <p className="text-sm">{safeString(detailsDialog.client.dados_financeiros?.trabalha_estrangeiro) === "sim" ? "Sim" : safeString(detailsDialog.client.dados_financeiros?.trabalha_estrangeiro) === "nao" ? "Não" : <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg col-span-2">
                    <CreditCard className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Contas de Crédito Abertas</p>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {Array.isArray(detailsDialog.client.dados_financeiros?.tem_creditos_activos) && detailsDialog.client.dados_financeiros.tem_creditos_activos.length > 0
                          ? detailsDialog.client.dados_financeiros.tem_creditos_activos.map((banco, idx) => (
                              <span key={idx} className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">
                                {safeString(banco)}
                              </span>
                            ))
                          : detailsDialog.client.dados_financeiros?.tem_creditos_activos === true
                            ? <span className="text-orange-600 text-sm">Sim</span>
                            : <span className="text-muted-foreground italic text-sm">Não preenchido</span>
                        }
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Metadados */}
              <div className="pt-4 border-t">

                {/* Dados Imobiliários */}
                {detailsDialog.client.dados_imobiliarios && Object.keys(detailsDialog.client.dados_imobiliarios).length > 0 && (
                  <div className="mb-6">
                    <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                      <Building className="h-4 w-4" />
                      Dados do Imóvel / Projeto
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {Object.entries(detailsDialog.client.dados_imobiliarios).map(([key, value]) => (
                        value !== null && value !== undefined && value !== "" && (
                          <div key={key} className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                            <FileText className="h-4 w-4 text-muted-foreground" />
                            <div>
                              <p className="text-xs text-muted-foreground capitalize">{key.replace(/_/g, " ")}</p>
                              <p className="text-sm">{typeof value === "boolean" ? (value ? "Sim" : "Não") : Array.isArray(value) ? value.map(v => safeString(v)).join(", ") : safeString(value)}</p>
                            </div>
                          </div>
                        )
                      ))}
                    </div>
                  </div>
                )}

                {/* 2º Titular */}
                {detailsDialog.client.titular2_data && (
                  <div className="mb-6">
                    <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                      <Users className="h-4 w-4" />
                      2.º Titular
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {Object.entries(detailsDialog.client.titular2_data).map(([key, value]) => (
                        value !== null && value !== undefined && value !== "" && (
                          <div key={key} className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                            <User className="h-4 w-4 text-muted-foreground" />
                            <div>
                              <p className="text-xs text-muted-foreground capitalize">{key.replace(/_/g, " ")}</p>
                              <p className="text-sm">{safeString(value)}</p>
                            </div>
                          </div>
                        )
                      ))}
                    </div>
                  </div>
                )}

                <div className="grid grid-cols-2 gap-4 text-sm text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <Calendar className="h-4 w-4" />
                    <span>Registado em: {formatDate(detailsDialog.client.created_at)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    <span>Actualizado em: {formatDate(detailsDialog.client.updated_at)}</span>
                  </div>
                </div>
              </div>

              {/* PACOTE CK — Notas com fallback notas || notes */}
              {(detailsDialog.client.notas || detailsDialog.client.notes) && (
                <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                  <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                    <FileText className="h-4 w-4 text-yellow-600" />
                    Notas
                  </h4>
                  <p className="text-sm whitespace-pre-wrap">{safeString(detailsDialog.client.notas || detailsDialog.client.notes) || 'Sem observações'}</p>
                </div>
              )}
            </div>
          ) : null}

          <DialogFooter className="flex-col gap-2 sm:flex-row">
            <Button
              variant="outline"
              onClick={() => setDetailsDialog({ open: false, client: null })}
            >
              Fechar
            </Button>
            {detailsDialog.client?.has_process && detailsDialog.client?.processes?.length > 0 && (
              <Button
                onClick={() => {
                  setDetailsDialog({ open: false, client: null });
                  // FIX (Pacote K): navegar para o primeiro processo ATIVO
                  const procs = detailsDialog.client.processes;
                  const activeProc = procs.find(
                    (p) => !p.is_deleted && p.status !== "eliminado"
                  ) || procs[0];
                  navigate(`/process/${activeProc.id}`);
                }}
              >
                <Eye className="h-4 w-4 mr-2" />
                Ver Processo
              </Button>
            )}
            {canAssign && (
              <Button
                onClick={() => {
                  const client = detailsDialog.client;
                  setDetailsDialog({ open: false, client: null });
                  // Abrir o CreateProcessModal já wired abaixo, pré-selecionando o cliente.
                  setCreateProcessModal({ open: true, client });
                }}
              >
                <FileText className="h-4 w-4 mr-2" />
                Adicionar Processo
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default ClientRegistrationsPage;
