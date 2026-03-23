/**
 * RGPDAdminPage - Página de Administração de RGPD
 * Permite ao admin visualizar e editar os dados dos formulários RGPD assinados
 */
import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { toast } from "sonner";
import {
  FileText,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  Edit,
  Trash2,
  Send,
  Eye,
  Users,
  FileSignature,
  ExternalLink,
} from "lucide-react";
import { 
  StatCard, 
  ConfirmDeleteModal, 
  LoadingState, 
  EmptyState, 
  Pagination,
  AccessRestricted,
  AdminSearchFilter,
  PageHeader
} from "../components/admin/AdminPageShared";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Status badge component - específico para RGPD
const StatusBadge = ({ status }) => {
  const config = {
    pending: { label: "Pendente", color: "bg-yellow-100 text-yellow-800 border-yellow-300", icon: Clock },
    signed: { label: "Assinado", color: "bg-green-100 text-green-800 border-green-300", icon: CheckCircle },
    expired: { label: "Expirado", color: "bg-red-100 text-red-800 border-red-300", icon: XCircle },
    cancelled: { label: "Cancelado", color: "bg-gray-100 text-gray-800 border-gray-300", icon: XCircle },
  };

  const { label, color, icon: Icon } = config[status] || config.pending;

  return (
    <Badge variant="outline" className={`${color} flex items-center gap-1`}>
      <Icon className="h-3 w-3" />
      {label}
    </Badge>
  );
};

// Opções de status para filtro
const RGPD_STATUS_OPTIONS = [
  { value: "pending", label: "Pendente" },
  { value: "signed", label: "Assinado" },
  { value: "expired", label: "Expirado" },
  { value: "cancelled", label: "Cancelado" },
];

// Modal de Edição
const EditModal = ({ open, onClose, rgpd, onSave }) => {
  const [formData, setFormData] = useState({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (rgpd?.consent_data) {
      setFormData(rgpd.consent_data);
    }
  }, [rgpd]);

  const handleChange = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(rgpd.id, formData);
      onClose();
    } catch (error) {
      // Erro já tratado no onSave
    } finally {
      setSaving(false);
    }
  };

  if (!rgpd) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Edit className="h-5 w-5" />
            Editar Dados RGPD
          </DialogTitle>
          <DialogDescription>
            Edite os dados do formulário RGPD. As alterações serão guardadas na base de dados.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="nome">Nome Completo</Label>
              <Input
                id="nome"
                value={formData.nome || ""}
                onChange={(e) => handleChange("nome", e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="contribuinte">Contribuinte (NIF)</Label>
              <Input
                id="contribuinte"
                value={formData.contribuinte || ""}
                onChange={(e) => handleChange("contribuinte", e.target.value)}
                maxLength={9}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="tipo_documento">Tipo de Documento</Label>
              <Select
                value={formData.tipo_documento || ""}
                onValueChange={(v) => handleChange("tipo_documento", v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Selecione..." />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cartao_de_cidadao">Cartão de Cidadão</SelectItem>
                  <SelectItem value="bilhete_de_identidade">Bilhete de Identidade</SelectItem>
                  <SelectItem value="passaporte">Passaporte</SelectItem>
                  <SelectItem value="carta_de_conducao">Carta de Condução</SelectItem>
                  <SelectItem value="autorizacao_de_residencia">Autorização de Residência</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="numero_documento">Número do Documento</Label>
              <Input
                id="numero_documento"
                value={formData.numero_documento || ""}
                onChange={(e) => handleChange("numero_documento", e.target.value)}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="validade_documento">Validade do Documento</Label>
              <Input
                id="validade_documento"
                value={formData.validade_documento || ""}
                onChange={(e) => handleChange("validade_documento", e.target.value)}
                placeholder="DD/MM/AAAA"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="codigo_postal">Código Postal</Label>
              <Input
                id="codigo_postal"
                value={formData.codigo_postal || ""}
                onChange={(e) => handleChange("codigo_postal", e.target.value)}
                placeholder="0000-000"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="morada">Morada</Label>
            <Textarea
              id="morada"
              value={formData.morada || ""}
              onChange={(e) => handleChange("morada", e.target.value)}
              rows={2}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="concelho">Concelho</Label>
            <Input
              id="concelho"
              value={formData.concelho || ""}
              onChange={(e) => handleChange("concelho", e.target.value)}
            />
          </div>

          {formData.assinatura && (
            <div className="space-y-2">
              <Label>Assinatura Guardada</Label>
              <div className="border rounded p-2 bg-muted/30">
                <img
                  src={formData.assinatura}
                  alt="Assinatura"
                  className="max-h-24 mx-auto"
                />
              </div>
            </div>
          )}

          <div className="bg-blue-50 dark:bg-blue-950/30 p-3 rounded-lg text-sm">
            <p><strong>Data de Assinatura:</strong> {formData.data_assinatura || "N/A"}</p>
            <p><strong>Processo:</strong> {rgpd.process_id}</p>
            <p><strong>Email do Cliente:</strong> {rgpd.client_email}</p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : (
              <CheckCircle className="h-4 w-4 mr-2" />
            )}
            Guardar Alterações
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

// Modal de Visualização
const ViewModal = ({ open, onClose, rgpd, process }) => {
  if (!rgpd) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            Detalhes do RGPD
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Info Principal */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Cliente</p>
              <p className="font-medium">{rgpd.client_name}</p>
            </div>
            <StatusBadge status={rgpd.status} />
          </div>

          {/* Dados do Formulário */}
          {rgpd.consent_data && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Dados do Formulário</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-muted-foreground">Nome</p>
                    <p className="font-medium">{rgpd.consent_data.nome}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Contribuinte</p>
                    <p className="font-medium">{rgpd.consent_data.contribuinte}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Tipo Documento</p>
                    <p className="font-medium">{rgpd.consent_data.tipo_documento?.replace(/_/g, " ")}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Nº Documento</p>
                    <p className="font-medium">{rgpd.consent_data.numero_documento}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Validade</p>
                    <p className="font-medium">{rgpd.consent_data.validade_documento || "N/A"}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Código Postal</p>
                    <p className="font-medium">{rgpd.consent_data.codigo_postal || "N/A"}</p>
                  </div>
                </div>
                <div>
                  <p className="text-muted-foreground">Morada</p>
                  <p className="font-medium">{rgpd.consent_data.morada}</p>
                </div>
                {rgpd.consent_data.concelho && (
                  <div>
                    <p className="text-muted-foreground">Concelho</p>
                    <p className="font-medium">{rgpd.consent_data.concelho}</p>
                  </div>
                )}
                {rgpd.consent_data.assinatura && (
                  <div>
                    <p className="text-muted-foreground">Assinatura</p>
                    <img
                      src={rgpd.consent_data.assinatura}
                      alt="Assinatura"
                      className="border rounded p-2 bg-muted/30 max-h-32"
                    />
                  </div>
                )}
                {rgpd.consent_data.data_assinatura && (
                  <div>
                    <p className="text-muted-foreground">Data da Assinatura</p>
                    <p className="font-medium">{rgpd.consent_data.data_assinatura}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Metadados */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Metadados</CardTitle>
            </CardHeader>
            <CardContent className="text-sm space-y-2">
              <div className="flex justify-between">
                <span className="text-muted-foreground">ID do Pedido</span>
                <span className="font-mono text-xs">{rgpd.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Processo</span>
                <span>{process?.process_number || rgpd.process_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Email do Cliente</span>
                <span>{rgpd.client_email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Criado em</span>
                <span>{new Date(rgpd.created_at).toLocaleString("pt-PT")}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Criado por</span>
                <span>{rgpd.created_by_name}</span>
              </div>
              {rgpd.signed_at && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Assinado em</span>
                  <span>{new Date(rgpd.signed_at).toLocaleString("pt-PT")}</span>
                </div>
              )}
              {rgpd.token_expires_at && rgpd.status === "pending" && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Expira em</span>
                  <span>{new Date(rgpd.token_expires_at).toLocaleString("pt-PT")}</span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>
          {process && (
            <Button onClick={() => window.open(`/processes/${rgpd.process_id}`, "_blank")}>
              <ExternalLink className="h-4 w-4 mr-2" />
              Ver Processo
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const RGPDAdminPage = () => {
  const { token, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [requests, setRequests] = useState([]);
  const [stats, setStats] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  // Modals
  const [editModal, setEditModal] = useState({ open: false, rgpd: null });
  const [viewModal, setViewModal] = useState({ open: false, rgpd: null, process: null });
  const [deleteModal, setDeleteModal] = useState({ open: false, rgpd: null });
  const [actionLoading, setActionLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.append("search", search);
      if (statusFilter) params.append("status", statusFilter);
      params.append("page", page);
      params.append("limit", 15);

      const response = await fetch(`${API_URL}/api/rgpd/admin/all?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setRequests(data.requests || []);
        setTotal(data.total || 0);
        setTotalPages(data.pages || 1);
      } else {
        toast.error("Erro ao carregar dados");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  }, [token, search, statusFilter, page]);

  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/rgpd/admin/stats/summary`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error("Erro ao carregar estatísticas:", error);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
    fetchStats();
  }, [fetchData, fetchStats]);

  const handleEdit = (rgpd) => {
    setEditModal({ open: true, rgpd });
  };

  const handleView = async (rgpd) => {
    try {
      const response = await fetch(`${API_URL}/api/rgpd/admin/${rgpd.id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setViewModal({ open: true, rgpd: data.rgpd, process: data.process });
      }
    } catch (error) {
      toast.error("Erro ao carregar detalhes");
    }
  };

  const handleSave = async (requestId, formData) => {
    try {
      const response = await fetch(`${API_URL}/api/rgpd/admin/${requestId}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(formData),
      });

      if (response.ok) {
        toast.success("RGPD atualizado com sucesso");
        fetchData();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao atualizar");
        throw new Error();
      }
    } catch (error) {
      toast.error("Erro ao atualizar RGPD");
      throw error;
    }
  };

  const handleDelete = async () => {
    if (!deleteModal.rgpd) return;

    setActionLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/rgpd/admin/${deleteModal.rgpd.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        toast.success("RGPD eliminado com sucesso");
        setDeleteModal({ open: false, rgpd: null });
        fetchData();
        fetchStats();
      } else {
        toast.error("Erro ao eliminar");
      }
    } catch (error) {
      toast.error("Erro ao eliminar RGPD");
    } finally {
      setActionLoading(false);
    }
  };

  const handleResend = async (rgpd) => {
    setActionLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/rgpd/admin/${rgpd.id}/resend`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        toast.success("Email reenviado com sucesso");
        fetchData();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao reenviar");
      }
    } catch (error) {
      toast.error("Erro ao reenviar email");
    } finally {
      setActionLoading(false);
    }
  };

  // Verificar acesso
  const accessDenied = <AccessRestricted userRole={user?.role} allowedRoles={["admin", "staff"]} />;
  if (accessDenied) {
    return <DashboardLayout>{accessDenied}</DashboardLayout>;
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <PageHeader
          icon={FileSignature}
          title="Gestão de RGPD"
          description="Visualize e edite os dados dos formulários RGPD assinados"
          onRefresh={() => { fetchData(); fetchStats(); }}
        />

        {/* Estatísticas */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <StatCard title="Total" value={stats.total} icon={FileText} color="text-blue-600" />
            <StatCard title="Assinados" value={stats.signed} icon={CheckCircle} color="text-green-600" />
            <StatCard title="Pendentes" value={stats.pending} icon={Clock} color="text-yellow-600" />
            <StatCard title="Expirados" value={stats.expired} icon={XCircle} color="text-red-600" />
            <StatCard title="Assinados Hoje" value={stats.signed_today} icon={Users} color="text-purple-600" />
          </div>
        )}

        {/* Filtros */}
        <AdminSearchFilter
          search={search}
          onSearchChange={(v) => { setSearch(v); setPage(1); }}
          statusFilter={statusFilter}
          onStatusChange={(v) => { setStatusFilter(v); setPage(1); }}
          statusOptions={RGPD_STATUS_OPTIONS}
          searchPlaceholder="Pesquisar por nome ou NIF..."
        />

        {/* Lista */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Pedidos de RGPD ({total})</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <LoadingState />
            ) : requests.length === 0 ? (
              <EmptyState icon={FileText} message="Nenhum RGPD encontrado" />
            ) : (
              <div className="space-y-2">
                {/* Table Header */}
                <div className="grid grid-cols-12 gap-2 px-3 py-2 text-sm font-medium text-muted-foreground border-b">
                  <div className="col-span-3">Cliente</div>
                  <div className="col-span-2">NIF</div>
                  <div className="col-span-2">Estado</div>
                  <div className="col-span-2">Data</div>
                  <div className="col-span-3 text-right">Ações</div>
                </div>

                {/* Rows */}
                {requests.map((rgpd) => (
                  <div
                    key={rgpd.id}
                    className="grid grid-cols-12 gap-2 px-3 py-3 items-center hover:bg-muted/50 rounded-lg"
                  >
                    <div className="col-span-3">
                      <p className="font-medium truncate">{rgpd.client_name}</p>
                      <p className="text-xs text-muted-foreground truncate">{rgpd.client_email}</p>
                    </div>
                    <div className="col-span-2 text-sm">
                      {rgpd.consent_data?.contribuinte || "-"}
                    </div>
                    <div className="col-span-2">
                      <StatusBadge status={rgpd.status} />
                    </div>
                    <div className="col-span-2 text-sm text-muted-foreground">
                      {rgpd.signed_at
                        ? new Date(rgpd.signed_at).toLocaleDateString("pt-PT")
                        : new Date(rgpd.created_at).toLocaleDateString("pt-PT")}
                    </div>
                    <div className="col-span-3 flex justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => handleView(rgpd)} title="Ver detalhes">
                        <Eye className="h-4 w-4" />
                      </Button>
                      {rgpd.status === "signed" && (
                        <Button variant="ghost" size="sm" onClick={() => handleEdit(rgpd)} title="Editar">
                          <Edit className="h-4 w-4" />
                        </Button>
                      )}
                      {rgpd.status === "pending" && (
                        <Button variant="ghost" size="sm" onClick={() => handleResend(rgpd)} disabled={actionLoading} title="Reenviar email">
                          <Send className="h-4 w-4" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeleteModal({ open: true, rgpd })}
                        title="Eliminar"
                        className="text-red-600 hover:text-red-700 hover:bg-red-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Pagination */}
            <Pagination page={page} totalPages={totalPages} total={total} onPageChange={setPage} />
          </CardContent>
        </Card>
      </div>

      {/* Modals */}
      <EditModal
        open={editModal.open}
        onClose={() => setEditModal({ open: false, rgpd: null })}
        rgpd={editModal.rgpd}
        onSave={handleSave}
      />

      <ViewModal
        open={viewModal.open}
        onClose={() => setViewModal({ open: false, rgpd: null, process: null })}
        rgpd={viewModal.rgpd}
        process={viewModal.process}
      />

      <ConfirmDeleteModal
        open={deleteModal.open}
        onClose={() => setDeleteModal({ open: false, rgpd: null })}
        onConfirm={handleDelete}
        title="Confirmar Eliminação"
        description="Tem a certeza que deseja eliminar este RGPD? Esta ação não pode ser revertida."
        itemName={deleteModal.rgpd?.client_name}
        itemDetails={deleteModal.rgpd ? `${deleteModal.rgpd.client_email} • Estado: ${deleteModal.rgpd.status}` : ""}
        loading={actionLoading}
      />
    </DashboardLayout>
  );
};

export default RGPDAdminPage;
