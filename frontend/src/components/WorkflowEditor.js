/**
 * ====================================================================
 * EDITOR DE FLUXOS DE WORKFLOW - CREDITOIMO
 * ====================================================================
 * Componente para gerir os estados do workflow (fases do processo).
 * Permite criar, editar, reordenar e eliminar estados.
 * Inclui campos portal_label e visible_in_portal para controlo
 * do que o cliente vê no Portal do Cliente.
 * ====================================================================
 */
import { useState, useEffect } from "react";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Textarea } from "./ui/textarea";
import { Switch } from "./ui/switch";
import { toast } from "sonner";
import { safeLabel } from "./dashboard/DashboardShared";
import {
  Plus,
  Edit,
  Trash2,
  Loader2,
  Workflow,
  ArrowUp,
  ArrowDown,
  AlertTriangle,
  Eye,
  EyeOff,
  Globe,
  Activity,
  DollarSign,
  Clock,
  CalendarClock,
} from "lucide-react";
import {
  getWorkflowStatuses,
  createWorkflowStatus,
  updateWorkflowStatus,
  deleteWorkflowStatus,
} from "../services/api";

const statusColorOptions = [
  { value: "yellow", label: "Amarelo", class: "bg-yellow-500" },
  { value: "blue", label: "Azul", class: "bg-blue-500" },
  { value: "orange", label: "Laranja", class: "bg-orange-500" },
  { value: "green", label: "Verde", class: "bg-green-500" },
  { value: "red", label: "Vermelho", class: "bg-red-500" },
  { value: "purple", label: "Roxo", class: "bg-purple-500" },
];

const WorkflowEditor = () => {
  const [statuses, setStatuses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [formLoading, setFormLoading] = useState(false);
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [selectedStatus, setSelectedStatus] = useState(null);
  const [formData, setFormData] = useState({
    name: "",
    label: "",
    order: 1,
    color: "blue",
    description: "",
    portal_label: "",
    visible_in_portal: true,
    // PACOTE BS — Dynamic Workflow Purpose Flags
    // null = não configurado (fallback ativo no backend); true/false = configurado
    is_active: null,
    trigger_finance: null,
    trigger_countdown: null,
    trigger_property_check: null,
    trigger_deed_reminder: null,
  });

  useEffect(() => {
    fetchStatuses();
  }, []);

  const fetchStatuses = async () => {
    try {
      setLoading(true);
      const response = await getWorkflowStatuses();
      setStatuses(response.data.sort((a, b) => a.order - b.order));
    } catch (error) {
      toast.error("Erro ao carregar estados");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateStatus = async (e) => {
    e.preventDefault();
    if (!formData.label) {
      toast.error("Nome do estado é obrigatório");
      return;
    }

    setFormLoading(true);
    try {
      await createWorkflowStatus({
        name: formData.label.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, ""),
        label: formData.label,
        order: formData.order || statuses.length + 1,
        color: formData.color,
        description: formData.description || undefined,
        portal_label: formData.portal_label || undefined,
        visible_in_portal: formData.visible_in_portal,
        // PACOTE BS — Dynamic Workflow Purpose Flags
        is_active: formData.is_active,
        trigger_finance: formData.trigger_finance,
        trigger_countdown: formData.trigger_countdown,
        trigger_property_check: formData.trigger_property_check,
        trigger_deed_reminder: formData.trigger_deed_reminder,
      });
      toast.success("Estado criado com sucesso");
      setIsCreateDialogOpen(false);
      resetForm();
      fetchStatuses();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao criar estado"));
    } finally {
      setFormLoading(false);
    }
  };

  const handleEditStatus = async (e) => {
    e.preventDefault();
    if (!selectedStatus) return;

    setFormLoading(true);
    try {
      const payload = {
        label: formData.label,
        order: formData.order,
        color: formData.color,
        description: formData.description || undefined,
        portal_label: formData.portal_label || null,
        visible_in_portal: formData.visible_in_portal,
        // PACOTE BS — Dynamic Workflow Purpose Flags
        is_active: formData.is_active,
        trigger_finance: formData.trigger_finance,
        trigger_countdown: formData.trigger_countdown,
        trigger_property_check: formData.trigger_property_check,
        trigger_deed_reminder: formData.trigger_deed_reminder,
      };
      await updateWorkflowStatus(selectedStatus.id, payload);
      toast.success("Estado atualizado com sucesso");
      setIsEditDialogOpen(false);
      resetForm();
      fetchStatuses();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao atualizar estado"));
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeleteStatus = async () => {
    if (!selectedStatus) return;

    setFormLoading(true);
    try {
      const response = await deleteWorkflowStatus(selectedStatus.id);
      const processesMoved = response.data?.processes_moved || 0;
      const movedTo = response.data?.moved_to;

      if (processesMoved > 0) {
        toast.success(`Estado eliminado. ${processesMoved} processo(s) movido(s) para "${movedTo || 'Clientes em Espera'}"`);
      } else {
        toast.success("Estado eliminado com sucesso");
      }

      setIsDeleteDialogOpen(false);
      setSelectedStatus(null);
      fetchStatuses();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao eliminar estado"));
    } finally {
      setFormLoading(false);
    }
  };

  const handleMoveStatus = async (status, direction) => {
    const currentIndex = statuses.findIndex((s) => s.id === status.id);
    const newIndex = direction === "up" ? currentIndex - 1 : currentIndex + 1;

    if (newIndex < 0 || newIndex >= statuses.length) return;

    const otherStatus = statuses[newIndex];

    try {
      // Trocar as ordens
      await Promise.all([
        updateWorkflowStatus(status.id, { order: otherStatus.order }),
        updateWorkflowStatus(otherStatus.id, { order: status.order }),
      ]);
      fetchStatuses();
      toast.success("Ordem atualizada");
    } catch (error) {
      toast.error("Erro ao reordenar");
    }
  };

  const openEditDialog = (status) => {
    setSelectedStatus(status);
    setFormData({
      name: status.name,
      label: status.label,
      order: status.order,
      color: status.color,
      description: status.description || "",
      portal_label: status.portal_label || "",
      visible_in_portal: status.visible_in_portal !== false,
      // PACOTE BS — Dynamic Workflow Purpose Flags (lê do status existente; null = fallback)
      is_active: status.is_active ?? null,
      trigger_finance: status.trigger_finance ?? null,
      trigger_countdown: status.trigger_countdown ?? null,
      trigger_property_check: status.trigger_property_check ?? null,
      trigger_deed_reminder: status.trigger_deed_reminder ?? null,
    });
    setIsEditDialogOpen(true);
  };

  const openDeleteDialog = (status) => {
    setSelectedStatus(status);
    setIsDeleteDialogOpen(true);
  };

  const resetForm = () => {
    setFormData({
      label: "",
      order: statuses.length + 1,
      color: "blue",
      description: "",
      portal_label: "",
      visible_in_portal: true,
      // PACOTE BS — reset flags a null (fallback ativo)
      is_active: null,
      trigger_finance: null,
      trigger_countdown: null,
      trigger_property_check: null,
      trigger_deed_reminder: null,
    });
    setSelectedStatus(null);
  };

  const getColorClass = (color) => {
    const option = statusColorOptions.find((c) => c.value === color);
    return option ? option.class : "bg-gray-500";
  };

  // ====================================================================
  // PACOTE BS — Automações e Gatilhos do Sistema
  // ====================================================================
  // Secção reutilizável com 4 Switches que controlam as flags de
  // comportamento lidas pelo move_process_kanban (Pacote BR).
  // Cada switch bounda uma propriedade do workflow_statuses:
  //   is_active, trigger_finance, trigger_countdown, trigger_deed_reminder
  // Nota: trigger_property_check não tem switch dedicado porque é derivado
  // (no backend cobre ch_aprovado/fase_escritura/escritura_agendada) — mas
  // está incluído no payload para configuração avançada via API se necessário.
  // null = não configurado (fallback ativo); true/false = configurado pelo admin.
  // ====================================================================
  const renderAutomationTriggersSection = (prefix) => (
    <div className="space-y-3 p-4 bg-gradient-to-br from-teal-50/50 to-emerald-50/30 dark:from-teal-950/20 dark:to-emerald-950/10 border border-teal-200/50 dark:border-teal-800/30 rounded-lg" data-testid={`${prefix}-automation-triggers`}>
      <div className="flex items-center gap-2 pb-2 border-b border-teal-200/50 dark:border-teal-800/30">
        <Workflow className="h-4 w-4 text-teal-600" />
        <h4 className="text-sm font-semibold text-teal-800 dark:text-teal-300">
          Automações e Gatilhos do Sistema
        </h4>
      </div>
      <p className="text-xs text-muted-foreground -mt-1">
        Configure o comportamento automático do processo nesta fase. Deixe desligado para usar o comportamento por defeito do sistema.
      </p>

      {/* is_active — Considerar processo Ativo nesta fase */}
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-0.5 flex-1 min-w-0">
          <Label htmlFor={`${prefix}-is-active`} className="text-sm font-medium flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5 text-emerald-600" />
            Considerar processo Ativo nesta fase
          </Label>
          <p className="text-xs text-muted-foreground">
            Se desligado, o processo fica inativo (sai dos dashboards ativos e liberta slot do indexador)
          </p>
        </div>
        <Switch
          id={`${prefix}-is-active`}
          checked={formData.is_active === true}
          onCheckedChange={(checked) => setFormData({ ...formData, is_active: checked })}
          data-testid={`${prefix}-switch-is-active`}
        />
      </div>

      {/* trigger_finance — Disparar fecho financeiro e comissões */}
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-0.5 flex-1 min-w-0">
          <Label htmlFor={`${prefix}-trigger-finance`} className="text-sm font-medium flex items-center gap-1.5">
            <DollarSign className="h-3.5 w-3.5 text-green-600" />
            Disparar fecho financeiro e comissões
          </Label>
          <p className="text-xs text-muted-foreground">
            Cria snapshot financeiro (ProcessFinance) ao entrar nesta fase
          </p>
        </div>
        <Switch
          id={`${prefix}-trigger-finance`}
          checked={formData.trigger_finance === true}
          onCheckedChange={(checked) => setFormData({ ...formData, trigger_finance: checked })}
          data-testid={`${prefix}-switch-trigger-finance`}
        />
      </div>

      {/* trigger_countdown — Iniciar contagem decrescente de 90 dias */}
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-0.5 flex-1 min-w-0">
          <Label htmlFor={`${prefix}-trigger-countdown`} className="text-sm font-medium flex items-center gap-1.5">
            <Clock className="h-3.5 w-3.5 text-blue-600" />
            Iniciar contagem decrescente de 90 dias
          </Label>
          <p className="text-xs text-muted-foreground">
            Regista a data de aprovação bancária e inicia o countdown de 90 dias
          </p>
        </div>
        <Switch
          id={`${prefix}-trigger-countdown`}
          checked={formData.trigger_countdown === true}
          onCheckedChange={(checked) => setFormData({ ...formData, trigger_countdown: checked })}
          data-testid={`${prefix}-switch-trigger-countdown`}
        />
      </div>

      {/* trigger_deed_reminder — Ativar lembrete de agendamento de escritura */}
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-0.5 flex-1 min-w-0">
          <Label htmlFor={`${prefix}-trigger-deed-reminder`} className="text-sm font-medium flex items-center gap-1.5">
            <CalendarClock className="h-3.5 w-3.5 text-purple-600" />
            Ativar lembrete de agendamento de escritura
          </Label>
          <p className="text-xs text-muted-foreground">
            Cria lembrete automático 15 dias antes da data da escritura (requer data definida)
          </p>
        </div>
        <Switch
          id={`${prefix}-trigger-deed-reminder`}
          checked={formData.trigger_deed_reminder === true}
          onCheckedChange={(checked) => setFormData({ ...formData, trigger_deed_reminder: checked })}
          data-testid={`${prefix}-switch-trigger-deed-reminder`}
        />
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-blue-900" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Workflow className="h-5 w-5 text-blue-900" />
                Gestão de Estados do Workflow
              </CardTitle>
              <CardDescription>
                Adicione, edite ou reordene as fases do processo.
                <span className="block text-xs mt-1 text-muted-foreground">
                  <Globe className="h-3 w-3 inline mr-1" />
                  O campo &quot;Nome no Portal&quot; permite definir um nome diferente para o cliente ver.
                </span>
              </CardDescription>
            </div>
            <Button
              onClick={() => {
                resetForm();
                setIsCreateDialogOpen(true);
              }}
              className="bg-teal-600 hover:bg-teal-700"
              data-testid="add-workflow-status-btn"
            >
              <Plus className="h-4 w-4 mr-2" />
              Novo Estado
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
            {statuses.map((status, index) => (
              <div
                key={status.id}
                className="flex items-center gap-2 p-2 bg-muted/30 rounded-lg border hover:bg-muted/50 transition-colors"
                data-testid={`workflow-status-${status.name}`}
              >
                <div className="flex gap-0.5">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5"
                    disabled={index === 0}
                    onClick={() => handleMoveStatus(status, "up")}
                  >
                    <ArrowUp className="h-3 w-3" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5"
                    disabled={index === statuses.length - 1}
                    onClick={() => handleMoveStatus(status, "down")}
                  >
                    <ArrowDown className="h-3 w-3" />
                  </Button>
                </div>

                <div className={`w-3 h-3 rounded-full ${getColorClass(status.color)} flex-shrink-0`} />

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="font-medium text-sm truncate">{safeLabel(status.label)}</span>
                    {status.is_default && (
                      <Badge className="bg-blue-100 text-blue-800 text-xs flex-shrink-0">
                        Padrão
                      </Badge>
                    )}
                    {status.portal_label && (
                      <Badge className="bg-emerald-100 text-emerald-700 text-xs flex-shrink-0" variant="outline">
                        <Globe className="h-2.5 w-2.5 mr-1" />
                        {status.portal_label}
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1 flex-shrink-0">
                  {/* Portal visibility indicator */}
                  <span className={`text-xs flex items-center gap-0.5 ${status.visible_in_portal !== false ? "text-emerald-600" : "text-gray-400"}`} title={status.visible_in_portal !== false ? "Visível no portal" : "Oculto no portal"}>
                    {status.visible_in_portal !== false ? <Eye className="h-3 w-3" /> : <EyeOff className="h-3 w-3" />}
                  </span>
                  <span className="text-xs text-muted-foreground hidden sm:inline">
                    #{status.order}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7"
                    onClick={() => openEditDialog(status)}
                  >
                    <Edit className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 text-destructive hover:text-destructive"
                    onClick={() => openDeleteDialog(status)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}

            {statuses.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                <Workflow className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Nenhum estado configurado</p>
                <p className="text-sm">Clique em &ldquo;Novo Estado&rdquo; para começar</p>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Dialog Criar Estado */}
      <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
        <DialogContent aria-describedby="create-status-description" className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Criar Novo Estado</DialogTitle>
            <DialogDescription id="create-status-description">
              Defina as propriedades do novo estado do workflow.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateStatus} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="create-label">Nome do Estado (Interno) *</Label>
              <Input
                id="create-label"
                value={formData.label}
                onChange={(e) => setFormData({ ...formData, label: e.target.value })}
                placeholder="Ex: Clientes em Espera"
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-portal-label" className="flex items-center gap-1.5">
                <Globe className="h-3.5 w-3.5 text-emerald-600" />
                Nome no Portal do Cliente
              </Label>
              <Input
                id="create-portal-label"
                value={formData.portal_label}
                onChange={(e) => setFormData({ ...formData, portal_label: e.target.value })}
                placeholder="Ex: Em Espera (deixe vazio para usar o nome interno)"
              />
              <p className="text-xs text-muted-foreground">
                Se definido, este é o nome que o cliente vê no portal. Se vazio, usa o nome interno.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="create-order">Ordem</Label>
                <Input
                  id="create-order"
                  type="number"
                  min="1"
                  value={formData.order}
                  onChange={(e) =>
                    setFormData({ ...formData, order: parseInt(e.target.value) || 1 })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="create-color">Cor</Label>
                <Select
                  value={formData.color}
                  onValueChange={(value) => setFormData({ ...formData, color: value })}
                >
                  <SelectTrigger id="create-color">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {statusColorOptions.map((color) => (
                      <SelectItem key={color.value} value={color.value}>
                        <div className="flex items-center gap-2">
                          <div className={`w-3 h-3 rounded-full ${color.class}`} />
                          {color.label}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="create-description">Descrição (opcional)</Label>
              <Textarea
                id="create-description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Descreva o propósito deste estado..."
                rows={2}
              />
            </div>
            <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
              <div className="space-y-0.5">
                <Label htmlFor="create-visible-portal" className="text-sm font-medium flex items-center gap-1.5">
                  <Eye className="h-3.5 w-3.5" />
                  Visível no Portal do Cliente
                </Label>
                <p className="text-xs text-muted-foreground">
                  Se desativado, esta etapa não aparece no stepper do portal
                </p>
              </div>
              <Switch
                id="create-visible-portal"
                checked={formData.visible_in_portal}
                onCheckedChange={(checked) => setFormData({ ...formData, visible_in_portal: checked })}
              />
            </div>
            {/* PACOTE BS — Automações e Gatilhos do Sistema (Criar) */}
            {renderAutomationTriggersSection("create")}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsCreateDialogOpen(false)}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={formLoading}
                className="bg-teal-600 hover:bg-teal-700"
              >
                {formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar Estado"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Dialog Editar Estado */}
      <Dialog open={isEditDialogOpen} onOpenChange={setIsEditDialogOpen}>
        <DialogContent aria-describedby="edit-status-description" className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Editar Estado</DialogTitle>
            <DialogDescription id="edit-status-description">
              Modifique as propriedades do estado selecionado.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEditStatus} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-label">Etiqueta (Nome Interno) *</Label>
              <Input
                id="edit-label"
                value={formData.label}
                onChange={(e) => setFormData({ ...formData, label: e.target.value })}
                required
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit-portal-label" className="flex items-center gap-1.5">
                <Globe className="h-3.5 w-3.5 text-emerald-600" />
                Nome no Portal do Cliente
              </Label>
              <Input
                id="edit-portal-label"
                value={formData.portal_label}
                onChange={(e) => setFormData({ ...formData, portal_label: e.target.value })}
                placeholder="Ex: Em Espera (deixe vazio para usar o nome interno)"
              />
              <p className="text-xs text-muted-foreground">
                Se definido, este é o nome que o cliente vê no portal. Se vazio, usa o nome interno.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="edit-order">Ordem</Label>
                <Input
                  id="edit-order"
                  type="number"
                  min="1"
                  value={formData.order}
                  onChange={(e) =>
                    setFormData({ ...formData, order: parseInt(e.target.value) || 1 })
                  }
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-color">Cor</Label>
                <Select
                  value={formData.color}
                  onValueChange={(value) => setFormData({ ...formData, color: value })}
                >
                  <SelectTrigger id="edit-color">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {statusColorOptions.map((color) => (
                      <SelectItem key={color.value} value={color.value}>
                        <div className="flex items-center gap-2">
                          <div className={`w-3 h-3 rounded-full ${color.class}`} />
                          {color.label}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-description">Descrição (opcional)</Label>
              <Textarea
                id="edit-description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                rows={2}
              />
            </div>
            <div className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
              <div className="space-y-0.5">
                <Label htmlFor="edit-visible-portal" className="text-sm font-medium flex items-center gap-1.5">
                  <Eye className="h-3.5 w-3.5" />
                  Visível no Portal do Cliente
                </Label>
                <p className="text-xs text-muted-foreground">
                  Se desativado, esta etapa não aparece no stepper do portal
                </p>
              </div>
              <Switch
                id="edit-visible-portal"
                checked={formData.visible_in_portal}
                onCheckedChange={(checked) => setFormData({ ...formData, visible_in_portal: checked })}
              />
            </div>
            {/* PACOTE BS — Automações e Gatilhos do Sistema (Editar) */}
            {renderAutomationTriggersSection("edit")}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setIsEditDialogOpen(false)}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                disabled={formLoading}
                className="bg-teal-600 hover:bg-teal-700"
              >
                {formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Guardar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Dialog Confirmar Eliminação */}
      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent aria-describedby="delete-status-description">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" />
              Eliminar Estado
            </DialogTitle>
            <DialogDescription id="delete-status-description" className="sr-only">
              Confirme a eliminação do estado selecionado.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <p>
              Tem a certeza que deseja eliminar o estado{" "}
              <strong>&ldquo;{selectedStatus?.label}&rdquo;</strong>?
            </p>
            <p className="text-sm text-muted-foreground mt-2">
              Se existirem processos neste estado, serão movidos automaticamente para &ldquo;Clientes em Espera&rdquo;.
            </p>
            {selectedStatus?.is_default && (
              <p className="text-sm text-amber-600 mt-2 flex items-center gap-1">
                <AlertTriangle className="h-4 w-4" />
                Este é um estado padrão do sistema.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setIsDeleteDialogOpen(false)}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteStatus}
              disabled={formLoading}
            >
              {formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Eliminar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default WorkflowEditor;
