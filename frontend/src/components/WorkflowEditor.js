/**
 * ====================================================================
 * EDITOR DE FLUXOS DE WORKFLOW - CREDITOIMO
 * ====================================================================
 * Componente para gerir os estados do workflow (fases do processo).
 * Permite criar, editar, reordenar e eliminar estados.
 * ====================================================================
 */

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "./ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Textarea } from "./ui/textarea";
import { toast } from "sonner";
import {
  Plus,
  Edit,
  Trash2,
  GripVertical,
  Loader2,
  Workflow,
  ArrowUp,
  ArrowDown,
  AlertTriangle,
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
        description: formData.description,
      });
      toast.success("Estado criado com sucesso");
      setIsCreateDialogOpen(false);
      resetForm();
      fetchStatuses();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao criar estado");
    } finally {
      setFormLoading(false);
    }
  };

  const handleEditStatus = async (e) => {
    e.preventDefault();
    if (!selectedStatus) return;

    setFormLoading(true);
    try {
      await updateWorkflowStatus(selectedStatus.id, {
        label: formData.label,
        order: formData.order,
        color: formData.color,
        description: formData.description,
      });
      toast.success("Estado atualizado com sucesso");
      setIsEditDialogOpen(false);
      resetForm();
      fetchStatuses();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao atualizar estado");
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
      toast.error(error.response?.data?.detail || "Erro ao eliminar estado");
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
    });
    setSelectedStatus(null);
  };

  const getColorClass = (color) => {
    const option = statusColorOptions.find((c) => c.value === color);
    return option ? option.class : "bg-gray-500";
  };

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
                Adicione, edite ou reordene as fases do processo
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
                    <span className="font-medium text-sm truncate">{status.label}</span>
                    {status.is_default && (
                      <Badge className="bg-blue-100 text-blue-800 text-xs flex-shrink-0">
                        Padrão
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-1 flex-shrink-0">
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
        <DialogContent aria-describedby="create-status-description">
          <DialogHeader>
            <DialogTitle>Criar Novo Estado</DialogTitle>
            <DialogDescription id="create-status-description">
              Defina as propriedades do novo estado do workflow.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreateStatus} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="create-label">Nome do Estado *</Label>
              <Input
                id="create-label"
                value={formData.label}
                onChange={(e) => setFormData({ ...formData, label: e.target.value })}
                placeholder="Ex: Clientes em Espera"
                required
              />
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
        <DialogContent aria-describedby="edit-status-description">
          <DialogHeader>
            <DialogTitle>Editar Estado</DialogTitle>
            <DialogDescription id="edit-status-description">
              Modifique as propriedades do estado selecionado.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleEditStatus} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="edit-label">Etiqueta (Nome Visível) *</Label>
              <Input
                id="edit-label"
                value={formData.label}
                onChange={(e) => setFormData({ ...formData, label: e.target.value })}
                required
              />
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
