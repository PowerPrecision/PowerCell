/**
 * ClientRegistrationsPage - Página de Registo de Clientes
 * Mostra clientes que completaram o formulário de registo público
 * 
 * ACESSO: Todos os utilizadores
 * 
 * Funcionalidades:
 * - Listar clientes registados
 * - Filtros: com/sem processo, pesquisa
 * - Ordenação por data de registo (defeito)
 * - Atribuir cliente a utilizador (cria processo)
 */
import React, { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
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
  UserPlus,
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
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { TableSkeleton } from "../components/ui/skeletons";
import CreateProcessModal from "../components/CreateProcessModal";

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
  
  // Assign dialog
  const [assignDialog, setAssignDialog] = useState({ open: false, client: null });
  const [assignLoading, setAssignLoading] = useState(false);

  // Client details dialog
  const [detailsDialog, setDetailsDialog] = useState({ open: false, client: null });
  const [detailsLoading, setDetailsLoading] = useState(false);

  // Create process modal (pre-filled from client details)
  const [showCreateProcess, setShowCreateProcess] = useState(false);
  const [preSelectedClient, setPreSelectedClient] = useState(null);

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
  }, [token, search, hasProcessFilter, sortField, sortOrder, assignedToMe, isIndexacao]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetchClients();
  }, [fetchClients]);

  const handleAssignClient = async (clientId) => {
    setAssignLoading(true);
    try {
      const response = await fetch(
        `${API_URL}/api/clients/${clientId}/assign?create_process=true`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const data = await response.json();
        toast.success(data.message);
        setAssignDialog({ open: false, client: null });
        fetchClients();
        
        // Se criou processo, navegar para ele
        if (data.process_id) {
          navigate(`/process/${data.process_id}`);
        }
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao atribuir cliente");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao atribuir cliente");
    } finally {
      setAssignLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    try {
      return new Date(dateStr).toLocaleString("pt-PT", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      });
    } catch {
      return dateStr;
    }
  };

  const formatDateOnly = (dateStr) => {
    if (!dateStr) return "-";
    try {
      return new Date(dateStr).toLocaleDateString("pt-PT", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric"
      });
    } catch {
      return dateStr;
    }
  };

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
              Clientes que completaram o formulário de registo
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
                    <p className="text-xs text-muted-foreground">Sem Processo</p>
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
                          {client.nome?.charAt(0)?.toUpperCase() || "?"}
                        </div>
                        <div className="min-w-0 flex-1 overflow-hidden">
                          <button
                            onClick={() => handleViewClientDetails(client.id)}
                            className="font-semibold text-left hover:text-primary transition-colors cursor-pointer block truncate w-full"
                            title={client.nome}
                          >
                            {client.nome}
                          </button>
                          {client.fonte && (
                            <Badge variant="outline" className="text-[10px] mt-1 px-1.5 py-0">
                              {client.fonte}
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    
                    <div className="col-span-2 space-y-1.5 min-w-0">
                      {client.contacto?.email && (
                        <div className="flex items-center gap-1.5 text-sm text-muted-foreground min-w-0">
                          <Mail className="h-3.5 w-3.5 flex-shrink-0" />
                          <span className="truncate" title={client.contacto.email}>{client.contacto.email}</span>
                        </div>
                      )}
                      {client.contacto?.telefone && (
                        <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                          <Phone className="h-3.5 w-3.5 flex-shrink-0" />
                          <span className="whitespace-nowrap">{client.contacto.telefone}</span>
                        </div>
                      )}
                    </div>
                    
                    <div className="col-span-2">
                      {client.nif ? (
                        <div className="flex items-center gap-1.5 px-2 py-1 bg-muted/50 rounded-md w-fit">
                          <Hash className="h-3.5 w-3.5 text-muted-foreground" />
                          <span className="font-mono text-sm font-medium">{client.nif}</span>
                        </div>
                      ) : (
                        <span className="text-muted-foreground text-sm italic">Não preenchido</span>
                      )}
                    </div>
                    
                    <div className="col-span-2">
                      {client.has_process ? (
                        <div className="flex flex-col gap-1">
                          <Badge className="bg-green-600 text-white text-xs px-2 py-1">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Tem Processo
                          </Badge>
                          {client.processes?.length > 0 && (
                            <span className="text-xs text-muted-foreground font-mono">
                              #{client.processes[0].process_number}
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
                        <span>{formatDate(client.created_at)}</span>
                      </div>
                      {client.assigned_to_name && (
                        <div className="text-xs mt-1.5 flex items-center gap-1 text-primary">
                          <User className="h-3 w-3" />
                          {client.assigned_to_name}
                        </div>
                      )}
                    </div>
                    
                    <div className="col-span-1 flex justify-end gap-1">
                      {client.has_process && client.processes?.length > 0 && (
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => navigate(`/process/${client.processes[0].id}`)}
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
                          onClick={() => setAssignDialog({ open: true, client })}
                          title="Atribuir e criar processo"
                          className="h-8"
                        >
                          <UserPlus className="h-4 w-4 mr-1" />
                          Atribuir
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

      {/* Assign Dialog */}
      <Dialog open={assignDialog.open} onOpenChange={(open) => setAssignDialog({ open, client: assignDialog.client })}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserPlus className="h-5 w-5" />
              Atribuir Cliente
            </DialogTitle>
            <DialogDescription>
              Atribuir {assignDialog.client?.nome} a si próprio e criar um novo processo.
            </DialogDescription>
          </DialogHeader>

          <div className="py-4">
            <div className="space-y-4">
              <div className="bg-muted/50 rounded-lg p-4">
                <p className="text-sm font-medium">Dados do Cliente:</p>
                <div className="mt-2 space-y-1 text-sm text-muted-foreground">
                  {assignDialog.client?.contacto?.email && (
                    <p>Email: {assignDialog.client.contacto.email}</p>
                  )}
                  {assignDialog.client?.contacto?.telefone && (
                    <p>Telefone: {assignDialog.client.contacto.telefone}</p>
                  )}
                  {assignDialog.client?.nif && (
                    <p>NIF: {assignDialog.client.nif}</p>
                  )}
                </div>
              </div>

              <p className="text-sm text-muted-foreground">
                Ao atribuir este cliente, será criado automaticamente um novo processo de crédito habitação associado ao seu utilizador.
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setAssignDialog({ open: false, client: null })}
            >
              Cancelar
            </Button>
            <Button
              onClick={() => handleAssignClient(assignDialog.client?.id)}
              disabled={assignLoading}
            >
              {assignLoading ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <UserPlus className="h-4 w-4 mr-2" />
              )}
              Atribuir e Criar Processo
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
                    {detailsDialog.client.nome?.charAt(0)?.toUpperCase() || "?"}
                  </span>
                </div>
                <div>
                  <h3 className="text-xl font-bold">{detailsDialog.client.nome}</h3>
                  <div className="flex items-center gap-2 mt-1">
                    {detailsDialog.client.fonte && (
                      <Badge variant="outline">{detailsDialog.client.fonte}</Badge>
                    )}
                    {detailsDialog.client.nif && (
                      <Badge variant="secondary" className="font-mono">
                        NIF: {detailsDialog.client.nif}
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
                      <span className="text-sm">{detailsDialog.client.contacto.email}</span>
                    </div>
                  )}
                  {detailsDialog.client.contacto?.telefone && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Phone className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{detailsDialog.client.contacto.telefone}</span>
                    </div>
                  )}
                  {detailsDialog.client.contacto?.email_secundario && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Mail className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{detailsDialog.client.contacto.email_secundario}</span>
                    </div>
                  )}
                  {detailsDialog.client.contacto?.telefone_secundario && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Phone className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{detailsDialog.client.contacto.telefone_secundario}</span>
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
                      <p className="text-sm">{detailsDialog.client.dados_pessoais?.data_nascimento ? formatDateOnly(detailsDialog.client.dados_pessoais.data_nascimento) : <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Naturalidade</p>
                      <p className="text-sm">{detailsDialog.client.dados_pessoais?.naturalidade || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Nacionalidade</p>
                      <p className="text-sm">{detailsDialog.client.dados_pessoais?.nacionalidade || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Heart className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Estado Civil</p>
                      <p className="text-sm">{detailsDialog.client.dados_pessoais?.estado_civil || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Briefcase className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Profissão</p>
                      <p className="text-sm">{detailsDialog.client.dados_pessoais?.profissao || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Documento ID</p>
                      <p className="text-sm">{detailsDialog.client.dados_pessoais?.documento_id || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Hash className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">NIF</p>
                      <p className="text-sm">{detailsDialog.client.dados_pessoais?.nif || detailsDialog.client.nif || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-start gap-2 p-2 bg-muted/50 rounded-lg">
                    <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                    <div>
                      <p className="text-xs text-muted-foreground">Morada Fiscal</p>
                      <p className="text-sm">{detailsDialog.client.dados_pessoais?.morada_fiscal || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
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
                          ? new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(detailsDialog.client.dados_financeiros.rendimento_mensal)
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
                          ? new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(detailsDialog.client.dados_financeiros.rendimento_anual)
                          : <span className="text-muted-foreground italic">Não preenchido</span>}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Tipo de Contrato</p>
                      <p className="text-sm">{detailsDialog.client.dados_financeiros?.tipo_contrato || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Building className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Empresa</p>
                      <p className="text-sm">{detailsDialog.client.dados_financeiros?.empresa || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Clock className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Antiguidade no Emprego</p>
                      <p className="text-sm">{detailsDialog.client.dados_financeiros?.antiguidade_emprego || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <MapPin className="h-4 w-4 text-muted-foreground" />
                    <div>
                      <p className="text-xs text-muted-foreground">Trabalha no Estrangeiro</p>
                      <p className="text-sm">{detailsDialog.client.dados_financeiros?.trabalha_estrangeiro === "sim" ? "Sim" : detailsDialog.client.dados_financeiros?.trabalha_estrangeiro === "nao" ? "Não" : <span className="text-muted-foreground italic">Não preenchido</span>}</p>
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
                                {banco}
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
                              <p className="text-sm">{typeof value === "boolean" ? (value ? "Sim" : "Não") : Array.isArray(value) ? value.join(", ") : String(value)}</p>
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
                              <p className="text-sm">{String(value)}</p>
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

              {/* Notas */}
              {detailsDialog.client.notas && (
                <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                  <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                    <FileText className="h-4 w-4 text-yellow-600" />
                    Notas
                  </h4>
                  <p className="text-sm whitespace-pre-wrap">{detailsDialog.client.notas}</p>
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
                  navigate(`/process/${detailsDialog.client.processes[0].id}`);
                }}
              >
                <Eye className="h-4 w-4 mr-2" />
                Ver Processo
              </Button>
            )}
            {canAssign && (
              <Button
                onClick={() => {
                  setPreSelectedClient({
                    id: detailsDialog.client.id,
                    name: detailsDialog.client.nome,
                    nif: detailsDialog.client.nif || detailsDialog.client.dados_pessoais?.nif || "",
                    email: detailsDialog.client.contacto?.email || "",
                    phone: detailsDialog.client.contacto?.telefone || "",
                  });
                  setDetailsDialog({ open: false, client: null });
                  setShowCreateProcess(true);
                }}
              >
                <FileText className="h-4 w-4 mr-2" />
                Adicionar Processo
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Create Process Modal (pre-filled client from details dialog) */}
      <CreateProcessModal
        open={showCreateProcess}
        onOpenChange={(open) => {
          setShowCreateProcess(open);
          if (!open) setPreSelectedClient(null);
        }}
        preSelectedClient={preSelectedClient}
        onSuccess={() => fetchClients()}
      />
    </DashboardLayout>
  );
};

export default ClientRegistrationsPage;
