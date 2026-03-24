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

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ClientRegistrationsPage = () => {
  const { token, user } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [clients, setClients] = useState([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [hasProcessFilter, setHasProcessFilter] = useState("all");
  const [sortField, setSortField] = useState("created_at");
  const [sortOrder, setSortOrder] = useState("desc");
  const [assignedToMe, setAssignedToMe] = useState(false);
  
  // Assign dialog
  const [assignDialog, setAssignDialog] = useState({ open: false, client: null });
  const [assignLoading, setAssignLoading] = useState(false);

  // Client details dialog
  const [detailsDialog, setDetailsDialog] = useState({ open: false, client: null });
  const [detailsLoading, setDetailsLoading] = useState(false);

  const userRole = user?.role || "";
  const isIndexacao = userRole === "indexacao";
  
  // Verificar permissões
  const canAssign = userRole !== "gestor_documentos" && userRole !== "indexacao";

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
  }, [token, search, hasProcessFilter, sortField, sortOrder, assignedToMe, isIndexacao]);

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

        {/* Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                  <Users className="h-5 w-5 text-blue-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{total}</p>
                  <p className="text-xs text-muted-foreground">Total Registados</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                  <CheckCircle className="h-5 w-5 text-green-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">
                    {clients.filter(c => c.has_process).length}
                  </p>
                  <p className="text-xs text-muted-foreground">Com Processo</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-orange-100 dark:bg-orange-900/30 rounded-lg">
                  <XCircle className="h-5 w-5 text-orange-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">
                    {clients.filter(c => !c.has_process).length}
                  </p>
                  <p className="text-xs text-muted-foreground">Sem Processo</p>
                </div>
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
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-10"
                />
              </div>
              
              <Select value={hasProcessFilter} onValueChange={setHasProcessFilter}>
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
              
              <Select value={`${sortField}_${sortOrder}`} onValueChange={(v) => {
                const [field, order] = v.split('_');
                setSortField(field);
                setSortOrder(order);
              }}>
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
                  onClick={() => setAssignedToMe(!assignedToMe)}
                  className="gap-2"
                >
                  <Users className="h-4 w-4" />
                  Atribuídos a Mim
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Clients List */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Clientes Registados ({total})</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <TableSkeleton rows={6} columns={5} />
            ) : clients.length === 0 ? (
              <div className="text-center py-12">
                <Users className="h-12 w-12 mx-auto text-muted-foreground/50 mb-4" />
                <p className="text-muted-foreground">
                  Nenhum cliente encontrado
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {/* Table Header */}
                <div className="grid grid-cols-12 gap-2 px-3 py-2 text-sm font-medium text-muted-foreground border-b bg-muted/50">
                  <div className="col-span-3">Cliente</div>
                  <div className="col-span-2">Contacto</div>
                  <div className="col-span-2">NIF</div>
                  <div className="col-span-2">Estado</div>
                  <div className="col-span-2">Data Registo</div>
                  <div className="col-span-1 text-right">Acções</div>
                </div>

                {/* Rows */}
                {clients.map((client) => (
                  <div
                    key={client.id}
                    className="grid grid-cols-12 gap-2 px-3 py-3 items-center hover:bg-muted/50 rounded-lg border-b"
                  >
                    <div className="col-span-3">
                      <div className="flex items-center gap-3">
                        <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center">
                          <span className="text-sm font-medium text-primary">
                            {client.nome?.charAt(0)?.toUpperCase() || "?"}
                          </span>
                        </div>
                        <div>
                          <button
                            onClick={() => handleViewClientDetails(client.id)}
                            className="font-medium text-left hover:text-primary transition-colors cursor-pointer"
                          >
                            {client.nome}
                          </button>
                          {client.fonte && (
                            <Badge variant="outline" className="text-xs mt-1">
                              {client.fonte}
                            </Badge>
                          )}
                        </div>
                      </div>
                    </div>
                    
                    <div className="col-span-2 space-y-1">
                      {client.contacto?.email && (
                        <div className="flex items-center gap-1 text-sm text-muted-foreground">
                          <Mail className="h-3 w-3" />
                          <span className="truncate">{client.contacto.email}</span>
                        </div>
                      )}
                      {client.contacto?.telefone && (
                        <div className="flex items-center gap-1 text-sm text-muted-foreground">
                          <Phone className="h-3 w-3" />
                          {client.contacto.telefone}
                        </div>
                      )}
                    </div>
                    
                    <div className="col-span-2">
                      {client.nif ? (
                        <div className="flex items-center gap-1">
                          <Hash className="h-3 w-3 text-muted-foreground" />
                          <span className="font-mono text-sm">{client.nif}</span>
                        </div>
                      ) : (
                        <span className="text-muted-foreground text-sm">-</span>
                      )}
                    </div>
                    
                    <div className="col-span-2">
                      {client.has_process ? (
                        <div className="flex flex-col gap-1">
                          <Badge className="bg-green-600 text-white text-xs">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Tem Processo
                          </Badge>
                          {client.processes?.length > 0 && (
                            <span className="text-xs text-muted-foreground">
                              #{client.processes[0].process_number}
                            </span>
                          )}
                        </div>
                      ) : (
                        <Badge variant="outline" className="text-orange-600 border-orange-300 text-xs">
                          <XCircle className="h-3 w-3 mr-1" />
                          Sem Processo
                        </Badge>
                      )}
                    </div>
                    
                    <div className="col-span-2 text-sm text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {formatDate(client.created_at)}
                      </div>
                      {client.assigned_to_name && (
                        <div className="text-xs mt-1">
                          Atribuído a: {client.assigned_to_name}
                        </div>
                      )}
                    </div>
                    
                    <div className="col-span-1 flex justify-end gap-1">
                      {client.has_process && client.processes?.length > 0 && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => navigate(`/process/${client.processes[0].id}`)}
                          title="Ver processo"
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                      )}
                      {!client.has_process && canAssign && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setAssignDialog({ open: true, client })}
                          title="Atribuir e criar processo"
                          className="text-primary hover:text-primary"
                        >
                          <UserPlus className="h-4 w-4" />
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
                  {detailsDialog.client.dados_pessoais?.data_nascimento && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Calendar className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Data de Nascimento</p>
                        <p className="text-sm">{formatDateOnly(detailsDialog.client.dados_pessoais.data_nascimento)}</p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_pessoais?.naturalidade && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <MapPin className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Naturalidade</p>
                        <p className="text-sm">{detailsDialog.client.dados_pessoais.naturalidade}</p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_pessoais?.nacionalidade && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <MapPin className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Nacionalidade</p>
                        <p className="text-sm">{detailsDialog.client.dados_pessoais.nacionalidade}</p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_pessoais?.estado_civil && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Heart className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Estado Civil</p>
                        <p className="text-sm">{detailsDialog.client.dados_pessoais.estado_civil}</p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_pessoais?.profissao && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Briefcase className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Profissão</p>
                        <p className="text-sm">{detailsDialog.client.dados_pessoais.profissao}</p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_pessoais?.documento_id && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Documento ID</p>
                        <p className="text-sm">{detailsDialog.client.dados_pessoais.documento_id}</p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_pessoais?.morada_fiscal && (
                    <div className="flex items-start gap-2 p-2 bg-muted/50 rounded-lg col-span-2">
                      <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                      <div>
                        <p className="text-xs text-muted-foreground">Morada Fiscal</p>
                        <p className="text-sm">{detailsDialog.client.dados_pessoais.morada_fiscal}</p>
                      </div>
                    </div>
                  )}
                  {!detailsDialog.client.dados_pessoais?.data_nascimento &&
                   !detailsDialog.client.dados_pessoais?.naturalidade &&
                   !detailsDialog.client.dados_pessoais?.nacionalidade &&
                   !detailsDialog.client.dados_pessoais?.estado_civil &&
                   !detailsDialog.client.dados_pessoais?.profissao &&
                   !detailsDialog.client.dados_pessoais?.morada_fiscal && (
                    <p className="text-sm text-muted-foreground col-span-2">Sem dados pessoais registados</p>
                  )}
                </div>
              </div>

              {/* Dados Financeiros */}
              <div>
                <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <DollarSign className="h-4 w-4" />
                  Dados Financeiros
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {detailsDialog.client.dados_financeiros?.rendimento_mensal && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <DollarSign className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Rendimento Mensal</p>
                        <p className="text-sm font-medium">
                          {new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(detailsDialog.client.dados_financeiros.rendimento_mensal)}
                        </p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_financeiros?.rendimento_anual && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <DollarSign className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Rendimento Anual</p>
                        <p className="text-sm font-medium">
                          {new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(detailsDialog.client.dados_financeiros.rendimento_anual)}
                        </p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_financeiros?.tipo_contrato && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Tipo de Contrato</p>
                        <p className="text-sm">{detailsDialog.client.dados_financeiros.tipo_contrato}</p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_financeiros?.empresa && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Building className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Empresa</p>
                        <p className="text-sm">{detailsDialog.client.dados_financeiros.empresa}</p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_financeiros?.antiguidade_emprego && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Clock className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Antiguidade no Emprego</p>
                        <p className="text-sm">{detailsDialog.client.dados_financeiros.antiguidade_emprego}</p>
                      </div>
                    </div>
                  )}
                  {detailsDialog.client.dados_financeiros?.tem_creditos_activos !== undefined && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <CreditCard className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Créditos Activos</p>
                        <p className="text-sm">
                          {detailsDialog.client.dados_financeiros.tem_creditos_activos ? (
                            <span className="text-orange-600">
                              Sim - {detailsDialog.client.dados_financeiros.valor_creditos_activos
                                ? new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(detailsDialog.client.dados_financeiros.valor_creditos_activos)
                                : 'Valor não especificado'}
                            </span>
                          ) : (
                            <span className="text-green-600">Não</span>
                          )}
                        </p>
                      </div>
                    </div>
                  )}
                  {!detailsDialog.client.dados_financeiros?.rendimento_mensal &&
                   !detailsDialog.client.dados_financeiros?.tipo_contrato &&
                   !detailsDialog.client.dados_financeiros?.empresa && (
                    <p className="text-sm text-muted-foreground col-span-2">Sem dados financeiros registados</p>
                  )}
                </div>
              </div>

              {/* Metadados */}
              <div className="pt-4 border-t">
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

          <DialogFooter>
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
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </DashboardLayout>
  );
};

export default ClientRegistrationsPage;
