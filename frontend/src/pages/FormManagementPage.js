/**
 * FormManagementPage - Gestão do Formulário Público
 * 
 * ACESSO: Admin e CEO apenas
 * 
 * Funcionalidades:
 * - Listar todos os campos do formulário por passo
 * - Ativar/desativar campos, marcar como obrigatórios
 * - Criar campos personalizados (texto, dropdown, checkbox, etc.)
 * - Eliminar campos personalizados
 * - Repor configuração padrão
 */
import React, { useState, useEffect, useCallback } from "react";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import { Textarea } from "../components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "../components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../components/ui/select";
import { toast } from "sonner";
import {
  FileText, Loader2, Save, RotateCcw, Eye, EyeOff, AlertCircle,
  Plus, Trash2, GripVertical, X, PenLine, LayoutTemplate, Copy, Zap, Bookmark,
  GripHorizontal
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const STEP_LABELS = {
  1: "Dados Pessoais",
  2: "Segundo Titular",
  3: "Dados do Imóvel",
  4: "Situação Financeira",
  5: "Histórico Bancário",
  6: "Informações Adicionais",
};

const FIELD_TYPE_LABELS = {
  text: "Texto",
  select: "Dropdown",
  checkbox: "Checkboxes",
  radio: "Opção Sim/Não",
  date: "Data",
  number: "Número",
};

const FIELD_TYPES = [
  { value: "text", label: "Texto livre" },
  { value: "number", label: "Número" },
  { value: "date", label: "Data" },
  { value: "select", label: "Dropdown (escolha única)" },
  { value: "checkbox", label: "Checkboxes (escolha múltipla)" },
  { value: "radio", label: "Sim / Não" },
];

/**
 * Componente sortable para cada campo do formulário (Drag & Drop).
 */
const SortableFieldItem = ({ id, field, updateField, handleDeleteCustomField }) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 50 : "auto",
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center justify-between p-3 rounded-lg border transition-all ${
        field.is_visible
          ? field.is_custom
            ? "bg-emerald-50/50 dark:bg-emerald-900/10 border-emerald-200/50 dark:border-emerald-800/30"
            : "bg-card border-border"
          : "bg-muted/30 border-transparent opacity-60"
      } ${isDragging ? "shadow-lg ring-2 ring-primary/20" : ""}`}
      data-testid={`form-field-${field.field_key}`}
    >
      {/* Drag Handle */}
      <button
        type="button"
        className="cursor-grab active:cursor-grabbing p-1 mr-1 text-muted-foreground hover:text-foreground transition-colors shrink-0"
        {...attributes}
        {...listeners}
        title="Arrastar para reordenar"
      >
        <GripHorizontal className="h-4 w-4" />
      </button>
      <div className="flex items-center gap-3 min-w-0 flex-1">
        {field.is_custom ? (
          <PenLine className="h-4 w-4 text-emerald-600 shrink-0" />
        ) : field.is_visible ? (
          <Eye className="h-4 w-4 text-green-600 shrink-0" />
        ) : (
          <EyeOff className="h-4 w-4 text-muted-foreground shrink-0" />
        )}
        <div className="min-w-0">
          <p className="text-sm font-medium truncate">
            {field.label}
            {field.is_custom && (
              <Badge className="ml-2 bg-emerald-100 text-emerald-700 text-[10px] px-1.5 py-0">Personalizado</Badge>
            )}
          </p>
          <div className="flex items-center gap-2 mt-0.5">
            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
              {FIELD_TYPE_LABELS[field.field_type] || field.field_type}
            </Badge>
            {field.options && field.options.length > 0 && (
              <span className="text-[10px] text-muted-foreground">{field.options.length} opções</span>
            )}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-4 shrink-0">
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground">Obrigatório</Label>
          <Switch
            checked={field.is_required}
            onCheckedChange={(v) => updateField(field._idx, "is_required", v)}
            disabled={!field.is_visible}
          />
        </div>
        <div className="flex items-center gap-2">
          <Label className="text-xs text-muted-foreground">Visível</Label>
          <Switch
            checked={field.is_visible}
            onCheckedChange={(v) => updateField(field._idx, "is_visible", v)}
          />
        </div>
        {field.is_custom && (
          <Button
            variant="ghost"
            size="sm"
            className="text-red-500 hover:text-red-700 hover:bg-red-50 h-8 w-8 p-0"
            onClick={() => handleDeleteCustomField(field.field_key)}
            data-testid={`delete-field-${field.field_key}`}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
};

const FormManagementPage = () => {
  const { token } = useAuth();

  // DnD sensors
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );
  const [fields, setFields] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Dialog para criar campo personalizado
  const [createDialog, setCreateDialog] = useState(false);
  const [newField, setNewField] = useState({
    label: "",
    step: "1",
    field_type: "text",
    is_required: false,
    placeholder: "",
    hint: "",
    options: [],
  });
  const [newOption, setNewOption] = useState("");
  const [creating, setCreating] = useState(false);

  // Templates state
  const [templates, setTemplates] = useState([]);
  const [templateDialog, setTemplateDialog] = useState(false);
  const [saveTemplateDialog, setSaveTemplateDialog] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [templateDesc, setTemplateDesc] = useState("");
  const [savingTemplate, setSavingTemplate] = useState(false);

  // Preview state
  const [previewDialog, setPreviewDialog] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/fields`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setFields(data.fields || []);
        setHasChanges(false);
      }
    } catch (err) {
      console.error(err);
      toast.error("Erro ao carregar configuração do formulário");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  const fetchTemplates = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/templates`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setTemplates(data.templates || []);
      }
    } catch (err) {
      console.error(err);
    }
  }, [token]);

  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  const updateField = (idx, key, value) => {
    setFields(prev => {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], [key]: value };
      return updated;
    });
    setHasChanges(true);
  };

  // DnD: reordenar campos dentro de um passo
  const handleDragEnd = useCallback((event, stepFields) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;

    // Encontrar os índices globais dos fields envolvidos
    const activeGlobalIdx = fields.findIndex(f => f.field_key === active.id);
    const overGlobalIdx = fields.findIndex(f => f.field_key === over.id);
    if (activeGlobalIdx === -1 || overGlobalIdx === -1) return;

    // Garantir que são do mesmo passo
    if (fields[activeGlobalIdx].step !== fields[overGlobalIdx].step) return;

    const reordered = arrayMove([...fields], activeGlobalIdx, overGlobalIdx);

    // Recalcular order_index para todos os campos do passo
    const step = fields[activeGlobalIdx].step;
    let order = 0;
    reordered.forEach(f => {
      if (f.step === step) {
        f.order = order++;
      }
    });

    setFields(reordered);
    setHasChanges(true);
  }, [fields]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/fields`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ fields }),
      });
      if (res.ok) {
        toast.success("Configuração guardada com sucesso");
        setHasChanges(false);
      } else {
        toast.error("Erro ao guardar configuração");
      }
    } catch {
      toast.error("Erro de rede");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!window.confirm("Tem a certeza? Todos os campos personalizados serão eliminados e as configurações voltam ao padrão.")) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/reset`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setFields(data.fields || []);
        setHasChanges(false);
        toast.success("Configuração reposta para valores padrão");
      }
    } catch {
      toast.error("Erro de rede");
    } finally {
      setSaving(false);
    }
  };

  const addOption = () => {
    if (!newOption.trim()) return;
    setNewField(prev => ({ ...prev, options: [...prev.options, newOption.trim()] }));
    setNewOption("");
  };

  const removeOption = (idx) => {
    setNewField(prev => ({
      ...prev,
      options: prev.options.filter((_, i) => i !== idx),
    }));
  };

  const handleCreateField = async () => {
    if (!newField.label.trim()) {
      toast.error("O nome do campo é obrigatório");
      return;
    }
    if (["select", "checkbox"].includes(newField.field_type) && newField.options.length === 0) {
      toast.error("Adicione pelo menos uma opção para este tipo de campo");
      return;
    }

    setCreating(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/custom-field`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          label: newField.label,
          step: parseInt(newField.step),
          field_type: newField.field_type,
          is_required: newField.is_required,
          options: ["select", "checkbox", "radio"].includes(newField.field_type) ? newField.options : null,
          placeholder: newField.placeholder || null,
          hint: newField.hint || null,
        }),
      });
      if (res.ok) {
        toast.success("Campo personalizado criado com sucesso");
        setCreateDialog(false);
        setNewField({ label: "", step: "1", field_type: "text", is_required: false, placeholder: "", hint: "", options: [] });
        setNewOption("");
        fetchConfig();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Erro ao criar campo");
      }
    } catch {
      toast.error("Erro de rede");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteCustomField = async (fieldKey) => {
    if (!window.confirm("Tem a certeza que quer eliminar este campo personalizado?")) return;
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/custom-field/${fieldKey}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast.success("Campo eliminado");
        fetchConfig();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Erro ao eliminar");
      }
    } catch {
      toast.error("Erro de rede");
    }
  };

  // Template actions
  const handleActivateTemplate = async (templateId, templateName) => {
    if (!window.confirm(`Ativar o template "${templateName}"? A configuração atual será substituída.`)) return;
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/templates/${templateId}/activate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast.success(`Template "${templateName}" ativado`);
        setTemplateDialog(false);
        fetchConfig();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Erro ao ativar template");
      }
    } catch {
      toast.error("Erro de rede");
    }
  };

  const handleDuplicateTemplate = async (templateId) => {
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/templates/${templateId}/duplicate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast.success("Template duplicado");
        fetchTemplates();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Erro ao duplicar");
      }
    } catch {
      toast.error("Erro de rede");
    }
  };

  const handleDeleteTemplate = async (templateId) => {
    if (!window.confirm("Eliminar este template?")) return;
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/templates/${templateId}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast.success("Template eliminado");
        fetchTemplates();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Erro ao eliminar");
      }
    } catch {
      toast.error("Erro de rede");
    }
  };

  const handleSaveAsTemplate = async () => {
    if (!templateName.trim()) {
      toast.error("Nome do template é obrigatório");
      return;
    }
    setSavingTemplate(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/templates`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ name: templateName, description: templateDesc }),
      });
      if (res.ok) {
        toast.success("Template guardado com sucesso");
        setSaveTemplateDialog(false);
        setTemplateName("");
        setTemplateDesc("");
        fetchTemplates();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Erro ao guardar");
      }
    } catch {
      toast.error("Erro de rede");
    } finally {
      setSavingTemplate(false);
    }
  };

  // Preview handler
  const handlePreviewTemplate = async (templateId) => {
    setPreviewLoading(true);
    setPreviewDialog(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/templates/${templateId}/preview`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setPreviewData({ ...data, _templateId: templateId });
      } else {
        toast.error("Erro ao carregar pré-visualização");
        setPreviewDialog(false);
      }
    } catch {
      toast.error("Erro de rede");
      setPreviewDialog(false);
    } finally {
      setPreviewLoading(false);
    }
  };

  const previewGroupedByStep = previewData?.fields?.reduce((acc, field) => {
    if (!field.is_visible) return acc;
    const step = field.step || 1;
    if (!acc[step]) acc[step] = [];
    acc[step].push(field);
    return acc;
  }, {}) || {};

  const groupedByStep = fields.reduce((acc, field, idx) => {
    const step = field.step || 1;
    if (!acc[step]) acc[step] = [];
    acc[step].push({ ...field, _idx: idx });
    return acc;
  }, {});

  const needsOptions = ["select", "checkbox"].includes(newField.field_type);

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="form-management-page">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <FileText className="h-6 w-6" />
              Gestão do Formulário
            </h1>
            <p className="text-muted-foreground mt-1">Controlar campos do formulário público e criar campos personalizados</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Button
              variant="outline"
              onClick={() => setTemplateDialog(true)}
              data-testid="templates-btn"
            >
              <LayoutTemplate className="h-4 w-4 mr-2" />
              Templates
            </Button>
            <Button
              variant="outline"
              onClick={() => setSaveTemplateDialog(true)}
              data-testid="save-as-template-btn"
            >
              <Bookmark className="h-4 w-4 mr-2" />
              Guardar como Template
            </Button>
            <Button
              variant="outline"
              onClick={handleReset}
              disabled={saving}
              data-testid="reset-form-config"
            >
              <RotateCcw className="h-4 w-4 mr-2" />
              Repor Padrão
            </Button>
            <Button
              onClick={() => setCreateDialog(true)}
              data-testid="create-custom-field"
              className="bg-emerald-600 hover:bg-emerald-700"
            >
              <Plus className="h-4 w-4 mr-2" />
              Novo Campo
            </Button>
            <Button
              onClick={handleSave}
              disabled={saving || !hasChanges}
              data-testid="save-form-config"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
              Guardar {hasChanges && "*"}
            </Button>
          </div>
        </div>

        {hasChanges && (
          <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 flex items-center gap-2">
            <AlertCircle className="h-4 w-4 text-amber-600 shrink-0" />
            <p className="text-sm text-amber-700 dark:text-amber-300">Tem alterações por guardar. Clique em "Guardar" para aplicar.</p>
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-6">
            {Object.entries(groupedByStep)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([step, stepFields]) => (
                <Card key={step}>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg flex items-center gap-2">
                      <span className="h-7 w-7 rounded-full bg-primary/10 flex items-center justify-center text-sm font-bold text-primary">{step}</span>
                      {STEP_LABELS[Number(step)] || `Passo ${step}`}
                    </CardTitle>
                    <CardDescription>
                      {stepFields.filter(f => f.is_visible).length} de {stepFields.length} campos visíveis
                      {stepFields.some(f => f.is_custom) && (
                        <span className="ml-2 text-emerald-600">
                          ({stepFields.filter(f => f.is_custom).length} personalizado{stepFields.filter(f => f.is_custom).length !== 1 ? "s" : ""})
                        </span>
                      )}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <DndContext
                      sensors={sensors}
                      collisionDetection={closestCenter}
                      onDragEnd={(event) => handleDragEnd(event, stepFields)}
                    >
                      <SortableContext
                        items={stepFields.map(f => f.field_key)}
                        strategy={verticalListSortingStrategy}
                      >
                        {stepFields.sort((a, b) => (a.order || 0) - (b.order || 0)).map((field) => (
                          <SortableFieldItem
                            key={field.field_key}
                            id={field.field_key}
                            field={field}
                            updateField={updateField}
                            handleDeleteCustomField={handleDeleteCustomField}
                          />
                        ))}
                      </SortableContext>
                    </DndContext>
                  </CardContent>
                </Card>
              ))}
          </div>
        )}

        {/* Create Custom Field Dialog */}
        <Dialog open={createDialog} onOpenChange={setCreateDialog}>
          <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Plus className="h-5 w-5" />
                Novo Campo Personalizado
              </DialogTitle>
              <DialogDescription>
                Criar um campo adicional no formulário público de registo
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-5 py-4">
              {/* Label */}
              <div className="space-y-2">
                <Label>Nome do campo <span className="text-red-500">*</span></Label>
                <Input
                  placeholder="Ex: País de residência fiscal"
                  value={newField.label}
                  onChange={(e) => setNewField(prev => ({ ...prev, label: e.target.value }))}
                  data-testid="new-field-label"
                />
              </div>

              {/* Type & Step */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Tipo de campo <span className="text-red-500">*</span></Label>
                  <Select value={newField.field_type} onValueChange={(v) => setNewField(prev => ({ ...prev, field_type: v, options: [] }))}>
                    <SelectTrigger data-testid="new-field-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {FIELD_TYPES.map(t => (
                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Passo do formulário <span className="text-red-500">*</span></Label>
                  <Select value={newField.step} onValueChange={(v) => setNewField(prev => ({ ...prev, step: v }))}>
                    <SelectTrigger data-testid="new-field-step">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(STEP_LABELS).map(([k, v]) => (
                        <SelectItem key={k} value={k}>{k}. {v}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              {/* Placeholder & Hint */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Placeholder</Label>
                  <Input
                    placeholder="Texto de exemplo no campo"
                    value={newField.placeholder}
                    onChange={(e) => setNewField(prev => ({ ...prev, placeholder: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Dica/Ajuda</Label>
                  <Input
                    placeholder="Texto de ajuda abaixo do campo"
                    value={newField.hint}
                    onChange={(e) => setNewField(prev => ({ ...prev, hint: e.target.value }))}
                  />
                </div>
              </div>

              {/* Required */}
              <div className="flex items-center gap-3">
                <Switch
                  checked={newField.is_required}
                  onCheckedChange={(v) => setNewField(prev => ({ ...prev, is_required: v }))}
                  data-testid="new-field-required"
                />
                <Label>Campo obrigatório</Label>
              </div>

              {/* Options editor (for select/checkbox) */}
              {needsOptions && (
                <div className="space-y-3 pt-2 border-t">
                  <Label className="text-base font-semibold">
                    Opções {newField.field_type === "select" ? "do Dropdown" : "dos Checkboxes"}
                    <span className="text-red-500 ml-1">*</span>
                  </Label>
                  
                  {newField.options.length > 0 && (
                    <div className="space-y-1.5">
                      {newField.options.map((opt, idx) => (
                        <div key={idx} className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                          <GripVertical className="h-4 w-4 text-muted-foreground shrink-0" />
                          <span className="text-sm flex-1">{opt}</span>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 w-6 p-0 text-red-500 hover:text-red-700"
                            onClick={() => removeOption(idx)}
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex gap-2">
                    <Input
                      placeholder="Nome da opção"
                      value={newOption}
                      onChange={(e) => setNewOption(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addOption())}
                      data-testid="new-option-input"
                    />
                    <Button
                      variant="outline"
                      onClick={addOption}
                      disabled={!newOption.trim()}
                      data-testid="add-option-btn"
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  {newField.options.length === 0 && (
                    <p className="text-xs text-amber-600">Adicione pelo menos uma opção</p>
                  )}
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setCreateDialog(false)}>Cancelar</Button>
              <Button
                onClick={handleCreateField}
                disabled={creating || !newField.label.trim() || (needsOptions && newField.options.length === 0)}
                data-testid="confirm-create-field"
                className="bg-emerald-600 hover:bg-emerald-700"
              >
                {creating ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Plus className="h-4 w-4 mr-2" />}
                Criar Campo
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Templates Dialog */}
        <Dialog open={templateDialog} onOpenChange={setTemplateDialog}>
          <DialogContent className="sm:max-w-xl max-h-[85vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <LayoutTemplate className="h-5 w-5" />
                Templates de Formulário
              </DialogTitle>
              <DialogDescription>
                Ative um template para substituir a configuração atual do formulário
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-3 py-4">
              {templates.length === 0 ? (
                <p className="text-center text-muted-foreground py-6">A carregar templates...</p>
              ) : (
                templates.map((tpl) => (
                  <div
                    key={tpl.id}
                    className={`p-4 rounded-lg border transition-all ${
                      tpl.is_system
                        ? "bg-blue-50/50 dark:bg-blue-900/10 border-blue-200/50"
                        : "bg-card border-border"
                    }`}
                    data-testid={`template-${tpl.id}`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-sm">{tpl.name}</p>
                          {tpl.is_system && (
                            <Badge className="bg-blue-100 text-blue-700 text-[10px]">Sistema</Badge>
                          )}
                        </div>
                        {tpl.description && (
                          <p className="text-xs text-muted-foreground mt-1">{tpl.description}</p>
                        )}
                        <p className="text-xs text-muted-foreground mt-1">{tpl.field_count} campos</p>
                      </div>
                      <div className="flex gap-1.5 shrink-0">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handlePreviewTemplate(tpl.id)}
                          data-testid={`preview-${tpl.id}`}
                          className="h-8"
                        >
                          <Eye className="h-3 w-3 mr-1" />
                          Ver
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => handleActivateTemplate(tpl.id, tpl.name)}
                          data-testid={`activate-${tpl.id}`}
                          className="h-8"
                        >
                          <Zap className="h-3 w-3 mr-1" />
                          Ativar
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleDuplicateTemplate(tpl.id)}
                          className="h-8"
                        >
                          <Copy className="h-3 w-3" />
                        </Button>
                        {!tpl.is_system && (
                          <Button
                            size="sm"
                            variant="ghost"
                            className="h-8 text-red-500 hover:text-red-700"
                            onClick={() => handleDeleteTemplate(tpl.id)}
                          >
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </DialogContent>
        </Dialog>

        {/* Save as Template Dialog */}
        <Dialog open={saveTemplateDialog} onOpenChange={setSaveTemplateDialog}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Bookmark className="h-5 w-5" />
                Guardar como Template
              </DialogTitle>
              <DialogDescription>
                Guardar a configuração atual do formulário como um template reutilizável
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label>Nome do template <span className="text-red-500">*</span></Label>
                <Input
                  placeholder="Ex: Crédito Habitação Personalizado"
                  value={templateName}
                  onChange={(e) => setTemplateName(e.target.value)}
                  data-testid="template-name-input"
                />
              </div>
              <div className="space-y-2">
                <Label>Descrição</Label>
                <Input
                  placeholder="Breve descrição do template"
                  value={templateDesc}
                  onChange={(e) => setTemplateDesc(e.target.value)}
                />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setSaveTemplateDialog(false)}>Cancelar</Button>
              <Button
                onClick={handleSaveAsTemplate}
                disabled={savingTemplate || !templateName.trim()}
                data-testid="confirm-save-template"
              >
                {savingTemplate ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Bookmark className="h-4 w-4 mr-2" />}
                Guardar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Template Preview Dialog */}
        <Dialog open={previewDialog} onOpenChange={(open) => { setPreviewDialog(open); if (!open) setPreviewData(null); }}>
          <DialogContent className="sm:max-w-3xl max-h-[90vh] overflow-y-auto">
            {previewLoading ? (
              <div className="flex flex-col items-center justify-center py-16">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground mb-3" />
                <p className="text-sm text-muted-foreground">A carregar pré-visualização...</p>
              </div>
            ) : previewData ? (
              <>
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <Eye className="h-5 w-5" />
                    Pré-visualização: {previewData.name}
                  </DialogTitle>
                  {previewData.description && (
                    <DialogDescription>{previewData.description}</DialogDescription>
                  )}
                </DialogHeader>

                <div className="py-4 space-y-6" data-testid="template-preview-content">
                  {/* Summary bar */}
                  <div className="flex items-center gap-4 text-sm text-muted-foreground bg-muted/50 p-3 rounded-lg">
                    <span>{previewData.fields?.length || 0} campos totais</span>
                    <span>{previewData.fields?.filter(f => f.is_required).length || 0} obrigatórios</span>
                    <span>{previewData.fields?.filter(f => f.is_custom).length || 0} personalizados</span>
                    {previewData.is_system && <Badge className="bg-blue-100 text-blue-700 text-xs">Sistema</Badge>}
                  </div>

                  {/* Steps preview */}
                  {Object.entries(previewGroupedByStep)
                    .sort(([a], [b]) => Number(a) - Number(b))
                    .map(([step, stepFields]) => (
                      <div key={step} className="space-y-3">
                        <div className="flex items-center gap-2">
                          <span className="h-7 w-7 rounded-full bg-primary flex items-center justify-center text-sm font-bold text-primary-foreground">{step}</span>
                          <h3 className="font-semibold text-sm">
                            {STEP_LABELS[Number(step)] || `Passo ${step}`}
                          </h3>
                          <Badge variant="outline" className="text-[10px]">{stepFields.length} campos</Badge>
                        </div>

                        <div className="ml-9 space-y-2">
                          {stepFields.sort((a, b) => (a.order || 0) - (b.order || 0)).map((field) => (
                            <div
                              key={field.field_key}
                              className={`p-3 rounded-lg border ${
                                field.is_custom
                                  ? "bg-emerald-50/50 dark:bg-emerald-900/10 border-emerald-200/50"
                                  : "bg-card border-border"
                              }`}
                            >
                              <div className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm font-medium">{field.label}</span>
                                  {field.is_required && (
                                    <span className="text-red-600 text-xs font-semibold">* obrigatório</span>
                                  )}
                                  {field.is_custom && (
                                    <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">Personalizado</Badge>
                                  )}
                                </div>
                                <Badge variant="outline" className="text-[10px]">
                                  {FIELD_TYPE_LABELS[field.field_type] || field.field_type}
                                </Badge>
                              </div>

                              {/* Mock field rendering */}
                              <div className="mt-2">
                                {field.field_type === "text" && (
                                  <div className="h-9 rounded-md border border-dashed border-muted-foreground/30 bg-muted/20 flex items-center px-3">
                                    <span className="text-xs text-muted-foreground">{field.placeholder || field.label}</span>
                                  </div>
                                )}
                                {field.field_type === "number" && (
                                  <div className="h-9 rounded-md border border-dashed border-muted-foreground/30 bg-muted/20 flex items-center px-3">
                                    <span className="text-xs text-muted-foreground">0.00</span>
                                  </div>
                                )}
                                {field.field_type === "date" && (
                                  <div className="h-9 rounded-md border border-dashed border-muted-foreground/30 bg-muted/20 flex items-center px-3">
                                    <span className="text-xs text-muted-foreground">dd/mm/aaaa</span>
                                  </div>
                                )}
                                {field.field_type === "select" && (
                                  <div className="h-9 rounded-md border border-dashed border-muted-foreground/30 bg-muted/20 flex items-center justify-between px-3">
                                    <span className="text-xs text-muted-foreground">Selecione...</span>
                                    <span className="text-xs text-muted-foreground">&#9662;</span>
                                  </div>
                                )}
                                {field.field_type === "radio" && (
                                  <div className="flex gap-2 mt-1">
                                    <div className="flex-1 h-8 rounded-md border border-dashed border-muted-foreground/30 bg-muted/20 flex items-center justify-center">
                                      <span className="text-xs text-muted-foreground">Sim</span>
                                    </div>
                                    <div className="flex-1 h-8 rounded-md border border-dashed border-muted-foreground/30 bg-muted/20 flex items-center justify-center">
                                      <span className="text-xs text-muted-foreground">Não</span>
                                    </div>
                                  </div>
                                )}
                                {field.field_type === "checkbox" && field.options && (
                                  <div className="flex flex-wrap gap-1.5 mt-1">
                                    {field.options.map((opt) => (
                                      <span key={opt} className="px-2.5 py-1 rounded-full text-xs border border-dashed border-muted-foreground/30 bg-muted/20 text-muted-foreground">
                                        {opt}
                                      </span>
                                    ))}
                                  </div>
                                )}
                              </div>

                              {field.hint && (
                                <p className="text-[10px] text-muted-foreground mt-1">{field.hint}</p>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                </div>

                <DialogFooter>
                  <Button variant="outline" onClick={() => setPreviewDialog(false)}>Fechar</Button>
                  <Button onClick={() => { const tid = previewData._templateId; const tname = previewData.name; setPreviewDialog(false); handleActivateTemplate(tid, tname); }} data-testid="activate-from-preview">
                    <Zap className="h-4 w-4 mr-2" />
                    Ativar este Template
                  </Button>
                </DialogFooter>
              </>
            ) : null}
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default FormManagementPage;
