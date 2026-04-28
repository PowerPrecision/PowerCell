/**
 * FormManagementPage - Gestão WYSIWYG do Formulário Público
 *
 * ACESSO: Admin e CEO apenas
 *
 * Refactored with @hello-pangea/dnd for robust cross-container drag & drop
 * and WYSIWYG inline editing for visual parity with the public form.
 *
 * Layout: Two-column
 *   Left  — "Campos Ocultos" (hidden fields pool, drag source)
 *   Right — "Pré-visualização do Formulário" (WYSIWYG active fields by step)
 *
 * Single Source of Truth: The `fields` state array is the only state.
 *   - Derived views: availableFields, activeFieldsByStep (computed via useMemo)
 *   - Every mutation (toggle, reorder, add, delete, cross-step move)
 *     recalculates order_index globally
 *   - Save sends the normalized array to PUT /admin/form-config/fields
 *
 * WYSIWYG Features:
 *   - Each field renders as the actual input type the client sees
 *   - Inline label editing (click pencil icon → edit in place)
 *   - Eye icon toggle for visibility (hidden = opacity-40)
 *   - Asterisk icon toggle for required (shows red star)
 *   - Drag handle for reordering
 */
import React, { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import { Checkbox } from "../components/ui/checkbox";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "../components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "../components/ui/tooltip";
import { toast } from "sonner";
import {
  FileText, Loader2, Save, RotateCcw, Eye, EyeOff, AlertCircle,
  Plus, Trash2, GripVertical, X, PenLine, LayoutTemplate, Copy, Zap, Bookmark,
  GripHorizontal, Inbox, ArrowRightLeft, Star, Pencil, Check, GitBranch, Info,
  Settings, Eye as EyeIcon
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// ─── Constants ──────────────────────────────────────────────────────

const STEP_LABELS = {
  1: "Dados Pessoais",
  2: "Segundo Titular",
  3: "Dados do Imóvel",
  4: "Situação Financeira",
  5: "Créditos e Capital",
  6: "Confirmação / Consentimentos",
};

const FIELD_TYPE_LABELS = {
  text: "Texto",
  select: "Dropdown",
  checkbox: "Checkboxes",
  radio: "Opção Sim/Não",
  date: "Data",
  number: "Número",
  textarea: "Texto Longo",
  email: "Email",
  tel: "Telefone",
};

const FIELD_TYPES = [
  { value: "text", label: "Texto livre" },
  { value: "number", label: "Número" },
  { value: "date", label: "Data" },
  { value: "select", label: "Dropdown (escolha única)" },
  { value: "checkbox", label: "Checkboxes (escolha múltipla)" },
  { value: "radio", label: "Sim / Não" },
];

// ─── Helpers ────────────────────────────────────────────────────────

const normalizeFields = (rawFields) =>
  (rawFields || []).map((f, i) => ({
    ...f,
    order_index: f.order_index ?? f.order ?? i,
  }));

const prepareFieldsForSave = (fields) => {
  // Convert global order_index to per-step order values.
  // Backend sorts by (step, order) so order must be 1-based per-step.
  const sortedByIndex = [...fields].sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0));
  const perStepOrder = {};
  const stepCounters = {};
  for (const f of sortedByIndex) {
    const step = f.step || 1;
    stepCounters[step] = (stepCounters[step] || 0) + 1;
    perStepOrder[f.field_key] = stepCounters[step];
  }
  return fields.map((f) => ({
    ...f,
    order_index: f.order_index ?? 0,
    order: perStepOrder[f.field_key] ?? f.order ?? 0,
  }));
};

// ─── WYSIWYG Field Preview ─────────────────────────────────────────

/**
 * Renders a disabled form input matching what the client sees.
 * Used inside the admin WYSIWYG preview for visual parity.
 */
const WysiwygFieldPreview = ({ field }) => {
  const { field_type, options, placeholder, label } = field;

  if (field_type === "select") {
    return (
      <Select disabled>
        <SelectTrigger className="h-10">
          <SelectValue placeholder={placeholder || `Selecionar ${label.toLowerCase()}...`} />
        </SelectTrigger>
        <SelectContent>
          {(options || []).map((opt) => (
            <SelectItem key={opt} value={opt}>{opt}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    );
  }

  if (field_type === "checkbox" && options && options.length > 0) {
    return (
      <div className="space-y-2">
        {options.slice(0, 6).map((opt) => (
          <label key={opt} className="flex items-center gap-2 text-sm text-muted-foreground cursor-default">
            <div className="h-4 w-4 rounded border border-muted-foreground/40 bg-muted/30" />
            {opt}
          </label>
        ))}
        {options.length > 6 && (
          <span className="text-xs text-muted-foreground">+{options.length - 6} mais opções</span>
        )}
      </div>
    );
  }

  if (field_type === "radio") {
    return (
      <div className="flex gap-4">
        {["Sim", "Não"].map((opt) => (
          <label key={opt} className="flex items-center gap-2 text-sm text-muted-foreground cursor-default">
            <div className="h-4 w-4 rounded-full border border-muted-foreground/40 bg-muted/30" />
            {opt}
          </label>
        ))}
      </div>
    );
  }

  if (field_type === "date") {
    return (
      <div className="h-10 rounded-md border border-input bg-muted/30 px-3 py-2 text-sm text-muted-foreground flex items-center">
        dd/mm/aaaa
      </div>
    );
  }

  if (field_type === "textarea") {
    return (
      <div className="h-20 rounded-md border border-input bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
        {placeholder || `Escreva aqui...`}
      </div>
    );
  }

  // text, number, email, tel
  const inputType = field_type === "number" ? "number" : field_type === "email" ? "email" : field_type === "tel" ? "tel" : "text";
  return (
    <Input
      type={inputType}
      disabled
      placeholder={placeholder || label}
      className="bg-muted/30"
    />
  );
};

// ─── WYSIWYG Field Card ────────────────────────────────────────────

/**
 * WYSIWYG card: renders the field as the client sees it + inline controls.
 * Controls are shown on hover/always for easy management.
 */
const WysiwygFieldCard = ({ field, isDragging, dragHandleProps, updateField, onEditField, handleRemoveField }) => {

  return (
    <div
      className={`group relative rounded-lg border p-4 transition-all ${
        field.is_visible
          ? field.is_custom
            ? "bg-card border-emerald-200/60 dark:border-emerald-800/40"
            : "bg-card border-border"
          : "bg-muted/20 border-muted-foreground/20 opacity-40"
      } ${isDragging ? "shadow-lg ring-2 ring-primary/30 scale-[1.01]" : ""}`}
      data-testid={`form-field-${field.field_key}`}
    >
      {/* ── Top row: drag handle + label + inline controls ── */}
      <div className="flex items-start gap-2">
        {/* Drag Handle */}
        <button
          type="button"
          className="cursor-grab active:cursor-grabbing mt-1 p-0.5 text-muted-foreground/50 hover:text-foreground transition-colors shrink-0"
          {...dragHandleProps}
          title="Arrastar para reordenar"
        >
          <GripVertical className="h-4 w-4" />
        </button>

        {/* Label + Input */}
        <div className="flex-1 min-w-0 space-y-2">
          {/* Label row */}
          <div className="flex items-center gap-1.5">
            <Label className="text-sm font-medium cursor-default select-none">
              {field.label}
              {field.is_required && field.is_visible && (
                <span className="text-red-500 ml-0.5">*</span>
              )}
            </Label>
            {field.is_custom && (
              <Badge className="bg-emerald-100 text-emerald-700 text-[10px] px-1.5 py-0 shrink-0">Personalizado</Badge>
            )}
            {field.depends_on && (
              <Badge className="bg-blue-100 text-blue-700 text-[10px] px-1.5 py-0 shrink-0 flex items-center gap-1" title={`Visível quando: ${field.depends_on.field} ${field.depends_on.value !== undefined ? "= " + field.depends_on.value : field.depends_on.not_value ? "≠ " + field.depends_on.not_value : field.depends_on.contains ? "contém " + field.depends_on.contains : field.depends_on.value_in ? "∈ [" + field.depends_on.value_in.join(", ") + "]" : ""}`}>
                <GitBranch className="h-3 w-3" />
                Condicional
              </Badge>
            )}
          </div>

          {/* WYSIWYG preview of the actual input */}
          <WysiwygFieldPreview field={field} />

          {/* Hint text */}
          {field.hint && (
            <p className="text-xs text-muted-foreground">{field.hint}</p>
          )}
        </div>

        {/* ── Inline Controls (right side) ── */}
        <div className="flex flex-col items-center gap-1 shrink-0 pt-0.5">
            {/* Edit Field (full dialog) */}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-muted-foreground/60 hover:text-foreground hover:bg-muted"
              onClick={() => onEditField(field)}
              title="Editar campo"
              data-testid={`edit-field-btn-${field.field_key}`}
            >
              <Pencil className="h-3.5 w-3.5" />
            </Button>

            {/* Visibility Toggle */}
            <Button
              variant="ghost"
              size="sm"
              className={`h-7 w-7 p-0 ${!field.is_visible ? "text-amber-500 bg-amber-50 dark:bg-amber-900/20" : "text-green-600 hover:text-green-700 hover:bg-green-50"}`}
              onClick={() => updateField(field.field_key, "is_visible", !field.is_visible)}
              title={field.is_visible ? "Ocultar campo" : "Mostrar campo"}
              data-testid={`toggle-visibility-${field.field_key}`}
            >
              {field.is_visible ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}
            </Button>

            {/* Required Toggle */}
            <Button
              variant="ghost"
              size="sm"
              className={`h-7 w-7 p-0 ${field.is_required ? "text-red-500 bg-red-50 dark:bg-red-900/20" : "text-muted-foreground/60 hover:text-foreground hover:bg-muted"}`}
              onClick={() => updateField(field.field_key, "is_required", !field.is_required)}
              disabled={!field.is_visible}
              title={field.is_required ? "Opcional" : "Obrigatório"}
              data-testid={`toggle-required-${field.field_key}`}
            >
              <Star className={`h-3.5 w-3.5 ${field.is_required ? "fill-red-500" : ""}`} />
            </Button>

            {/* Delete field (all fields) */}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-muted-foreground/60 hover:text-red-600 hover:bg-red-50"
              onClick={() => handleRemoveField(field)}
              title={field.is_custom ? "Eliminar campo" : "Ocultar campo"}
              data-testid={`delete-field-${field.field_key}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
      </div>
    </div>
  );
};

// ─── Compact Field Card (for hidden pool) ───────────────────────────

/**
 * Compact card for the "available fields" pool.
 * Shows field name, type badge, and drag handle.
 */
const CompactFieldCard = ({ field, isDragging, dragHandleProps }) => (
  <div
    className={`flex items-center gap-2 p-2.5 rounded-lg border transition-all ${
      field.is_custom
        ? "bg-emerald-50/50 dark:bg-emerald-900/10 border-emerald-200/50 dark:border-emerald-800/30"
        : "bg-muted/30 border-transparent"
    } ${isDragging ? "shadow-lg ring-2 ring-primary/20" : ""}`}
    data-testid={`form-field-${field.field_key}`}
  >
    <button
      type="button"
      className="cursor-grab active:cursor-grabbing p-0.5 text-muted-foreground/60 hover:text-foreground shrink-0"
      {...dragHandleProps}
      title="Arrastar para ativar"
    >
      <GripHorizontal className="h-4 w-4" />
    </button>

    <div className="flex items-center gap-2 min-w-0 flex-1">
      <EyeOff className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
      <span className="text-sm truncate">{field.label}</span>
      {field.is_custom && (
        <Badge className="bg-emerald-100 text-emerald-700 text-[10px] px-1.5 py-0 shrink-0">Personalizado</Badge>
      )}
    </div>

    <Badge variant="outline" className="text-[10px] px-1.5 py-0 shrink-0">
      {FIELD_TYPE_LABELS[field.field_type] || field.field_type}
    </Badge>
  </div>
);

// ─── Main Component ────────────────────────────────────────────────

const FormManagementPage = () => {
  const { token } = useAuth();

  // ── Core state (single source of truth) ──
  const [fields, setFields] = useState([]);
  const [stepConfig, setStepConfig] = useState({});
  const [stepLabels, setStepLabels] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

  // Dialog: create custom field
  const [createDialog, setCreateDialog] = useState(false);
  const [newField, setNewField] = useState({
    label: "", step: "1", field_type: "text",
    is_required: false, placeholder: "", hint: "", options: [],
  });
  const [newOption, setNewOption] = useState("");
  const [creating, setCreating] = useState(false);

  // Dialogs: templates
  const [templates, setTemplates] = useState([]);
  const [templateDialog, setTemplateDialog] = useState(false);
  const [saveTemplateDialog, setSaveTemplateDialog] = useState(false);
  const [templateName, setTemplateName] = useState("");
  const [templateDesc, setTemplateDesc] = useState("");
  const [savingTemplate, setSavingTemplate] = useState(false);

  // Dialog: preview
  const [previewDialog, setPreviewDialog] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Dialog: edit step visibility
  const [editingStep, setEditingStep] = useState(null);
  const [editStepFormData, setEditStepFormData] = useState({});

  // Dialog: create new step
  const [createStepDialog, setCreateStepDialog] = useState(false);
  const [newStepLabel, setNewStepLabel] = useState("");

  // Dialog: edit field
  const [editingField, setEditingField] = useState(null);
  const [editFormData, setEditFormData] = useState({});
  const [editOption, setEditOption] = useState("");

  // ── Data fetching ──
  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/fields`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setFields(normalizeFields(data.fields));
        setStepConfig(data.step_config || {});
        setStepLabels(data.step_labels || {});
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

  // ── Derived state ──
  const availableFields = useMemo(() =>
    fields
      .filter(f => !f.is_visible)
      .sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0)),
    [fields]
  );

  const activeFieldsByStep = useMemo(() => {
    const active = fields
      .filter(f => f.is_visible)
      .sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0));
    return active.reduce((acc, f) => {
      const step = f.step || 1;
      if (!acc[step]) acc[step] = [];
      acc[step].push(f);
      return acc;
    }, {});
  }, [fields]);

  const allSteps = useMemo(() =>
    [...new Set(fields.map(f => f.step || 1))].sort((a, b) => a - b),
    [fields]
  );

  const needsOptions = ["select", "checkbox"].includes(newField.field_type);

  // Fields with selectable options (for depends_on dropdown)
  const dependsOnFields = useMemo(() =>
    fields.filter(f => {
      if (!editingField || f.field_key === editingField.field_key) return false;
      return (f.field_type === "select" || f.field_type === "radio") && (f.options && f.options.length > 0);
    }),
    [fields, editingField]
  );

  // Options of the currently selected depends_on field
  const dependsOnFieldOptions = useMemo(() => {
    if (!editFormData.depends_on_field) return [];
    const found = fields.find(f => f.field_key === editFormData.depends_on_field);
    if (!found) return [];
    if (found.field_type === "radio") return ["Sim", "Não"];
    return found.options || [];
  }, [fields, editFormData.depends_on_field]);

  // ── Step config helpers ──
  // Available trigger fields for step-level depends_on (select/radio from PREVIOUS steps)
  const getStepTriggerFields = useCallback((targetStep) => {
    return fields.filter(f => {
      if (f.step >= targetStep) return false; // only from previous steps
      return (f.field_type === "select" || f.field_type === "radio") && f.options && f.options.length > 0 && f.is_visible;
    });
  }, [fields]);

  // Options for the step-level trigger field
  const getStepTriggerFieldOptions = useCallback((fieldKey) => {
    const found = fields.find(f => f.field_key === fieldKey);
    if (!found) return [];
    if (found.field_type === "radio") return ["Sim", "Não"];
    return found.options || [];
  }, [fields]);

  // Open step edit dialog
  const openStepEditDialog = useCallback((stepNum) => {
    const config = stepConfig[String(stepNum)];
    const dep = config?.depends_on || null;
    setEditingStep(stepNum);
    setEditStepFormData({
      enabled: !!dep,
      depends_on_field: dep?.field || "",
      depends_on_operator: dep?.not_value ? "not_value" : dep?.value_in ? "value_in" : "equals",
      depends_on_value: dep?.value || dep?.not_value || "",
      depends_on_values: dep?.value_in || [],
    });
  }, [stepConfig]);

  // Save step config — auto-saves to backend immediately
  const handleSaveStepConfig = useCallback(async () => {
    if (!editingStep) return;
    let newStepConfig;
    if (editStepFormData.enabled && editStepFormData.depends_on_field) {
      const dep = { field: editStepFormData.depends_on_field };
      if (editStepFormData.depends_on_operator === "equals") dep.value = editStepFormData.depends_on_value;
      else if (editStepFormData.depends_on_operator === "not_value") dep.not_value = editStepFormData.depends_on_value;
      else if (editStepFormData.depends_on_operator === "value_in") dep.value_in = editStepFormData.depends_on_values || [];
      newStepConfig = { ...stepConfig, [String(editingStep)]: { depends_on: dep } };
    } else {
      newStepConfig = { ...stepConfig };
      delete newStepConfig[String(editingStep)];
    }

    // Persist to backend immediately
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/fields`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ fields: prepareFieldsForSave(fields), step_config: newStepConfig, step_labels: stepLabels }),
      });
      if (res.ok) {
        setStepConfig(newStepConfig);
        setHasChanges(false);
        toast.success("Configuração do passo guardada com sucesso");
      } else {
        toast.error("Erro ao guardar configuração do passo");
      }
    } catch {
      toast.error("Erro de rede ao guardar");
    } finally {
      setSaving(false);
    }
    setEditingStep(null);
    setEditStepFormData({});
  }, [editingStep, editStepFormData, stepConfig, stepLabels, fields, token]);

  // Create a new step
  const handleCreateStep = useCallback(() => {
    const trimmed = newStepLabel.trim();
    if (!trimmed) {
      toast.error("O nome do passo é obrigatório");
      return;
    }
    const nextStepNum = Math.max(...allSteps, 0) + 1;
    setStepLabels(prev => ({ ...prev, [String(nextStepNum)]: trimmed }));
    setHasChanges(true);
    setCreateStepDialog(false);
    setNewStepLabel("");
    toast.success(`Passo ${nextStepNum} "${trimmed}" criado. Agora pode arrastar campos para ele.`);
  }, [newStepLabel, allSteps]);

  // Delete a step (only custom steps with no fields)
  const handleDeleteStep = useCallback((stepNum) => {
    const stepFields = activeFieldsByStep[stepNum] || [];
    if (stepFields.length > 0) {
      toast.error("Não pode eliminar um passo com campos. Mova os campos primeiro.");
      return;
    }
    // Remove step config and label
    setStepConfig(prev => {
      const next = { ...prev };
      delete next[String(stepNum)];
      return next;
    });
    setStepLabels(prev => {
      const next = { ...prev };
      delete next[String(stepNum)];
      return next;
    });
    setHasChanges(true);
    toast.success(`Passo ${stepNum} eliminado`);
  }, [activeFieldsByStep]);

  // ── Field mutations ──
  const updateField = useCallback((fieldKey, key, value) => {
    setFields(prev =>
      prev.map(f => f.field_key === fieldKey ? { ...f, [key]: value } : f)
    );
    setHasChanges(true);
  }, []);

  // ── DnD: onDragEnd ──
  const onDragEnd = useCallback((result) => {
    const { source, destination, draggableId } = result;

    if (!destination) return;

    if (
      source.droppableId === destination.droppableId &&
      source.index === destination.index
    ) return;

    setFields(prev => {
      const fieldIdx = prev.findIndex(f => f.field_key === draggableId);
      if (fieldIdx === -1) return prev;

      const field = { ...prev[fieldIdx] };
      const remaining = [...prev.slice(0, fieldIdx), ...prev.slice(fieldIdx + 1)];

      const dstId = destination.droppableId;

      if (dstId === "available") {
        field.is_visible = false;
        remaining.push(field);

      } else if (dstId.startsWith("step-")) {
        const destStep = parseInt(dstId.replace("step-", ""), 10);
        field.is_visible = true;
        field.step = destStep;

        const destStepKeys = remaining
          .filter(f => f.is_visible && f.step === destStep)
          .sort((a, b) => (a.order_index ?? 0) - (b.order_index ?? 0))
          .map(f => f.field_key);

        let insertIdx;
        if (destStepKeys.length === 0) {
          insertIdx = remaining.length;
          for (let i = remaining.length - 1; i >= 0; i--) {
            if (remaining[i].is_visible && remaining[i].step < destStep) {
              insertIdx = i + 1;
              break;
            }
          }
        } else if (destination.index >= destStepKeys.length) {
          const lastKey = destStepKeys[destStepKeys.length - 1];
          insertIdx = remaining.findIndex(f => f.field_key === lastKey) + 1;
        } else {
          const targetKey = destStepKeys[destination.index];
          insertIdx = remaining.findIndex(f => f.field_key === targetKey);
        }

        remaining.splice(insertIdx, 0, field);
      }

      return remaining.map((f, i) => ({ ...f, order_index: i }));
    });
    setHasChanges(true);
  }, []);

  // ── Save / Reset ──
  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/fields`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ fields: prepareFieldsForSave(fields), step_config: stepConfig, step_labels: stepLabels }),
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
        setFields(normalizeFields(data.fields));
        setStepConfig(data.step_config || {});
        setHasChanges(false);
        toast.success("Configuração reposta para valores padrão");
      }
    } catch {
      toast.error("Erro de rede");
    } finally {
      setSaving(false);
    }
  };

  // ── Create custom field ──
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

  // ── Edit field dialog ──
  const openEditDialog = (field) => {
    const dep = field.depends_on || null;
    setEditingField(field);
    setEditFormData({
      label: field.label || "",
      field_type: field.field_type || "text",
      step: String(field.step || 1),
      placeholder: field.placeholder || "",
      hint: field.hint || "",
      is_required: field.is_required || false,
      options: field.options ? [...field.options] : [],
      depends_on_enabled: !!dep,
      depends_on_field: dep?.field || "",
      depends_on_operator: dep?.value_in ? "value_in" : dep?.not_value ? "not_value" : dep?.contains ? "contains" : dep?.value !== undefined ? "equals" : "equals",
      depends_on_value: dep?.value || dep?.not_value || dep?.contains || "",
      depends_on_values: dep?.value_in || [],
    });
    setEditOption("");
  };

  const addEditOption = () => {
    if (!editOption.trim()) return;
    setEditFormData(prev => ({ ...prev, options: [...prev.options, editOption.trim()] }));
    setEditOption("");
  };

  const removeEditOption = (idx) => {
    setEditFormData(prev => ({ ...prev, options: prev.options.filter((_, i) => i !== idx) }));
  };

  const handleEditField = () => {
    if (!editingField) return;
    if (!editFormData.label.trim()) {
      toast.error("O nome do campo é obrigatório");
      return;
    }
    if (["select", "checkbox"].includes(editFormData.field_type) && (editFormData.options || []).length === 0) {
      toast.error("Adicione pelo menos uma opção para este tipo de campo");
      return;
    }

    const key = editingField.field_key;
    const currentField = fields.find(f => f.field_key === key) || editingField;

    if (editFormData.label.trim() !== (currentField.label || "")) {
      updateField(key, "label", editFormData.label.trim());
    }
    if (editFormData.field_type !== (currentField.field_type || "text")) {
      updateField(key, "field_type", editFormData.field_type);
      if (!["select", "checkbox"].includes(editFormData.field_type)) {
        updateField(key, "options", null);
      }
    }
    if (String(editFormData.step) !== String(currentField.step || 1)) {
      updateField(key, "step", parseInt(editFormData.step));
    }
    if (editFormData.placeholder !== (currentField.placeholder || "")) {
      updateField(key, "placeholder", editFormData.placeholder || null);
    }
    if (editFormData.hint !== (currentField.hint || "")) {
      updateField(key, "hint", editFormData.hint || null);
    }
    if (editFormData.is_required !== (currentField.is_required || false)) {
      updateField(key, "is_required", editFormData.is_required);
    }
    if (["select", "checkbox"].includes(editFormData.field_type)) {
      const currentOptions = currentField.options || [];
      if (JSON.stringify(editFormData.options) !== JSON.stringify(currentOptions)) {
        updateField(key, "options", editFormData.options);
      }
    }

    // Build depends_on object
    if (editFormData.depends_on_enabled && editFormData.depends_on_field) {
      const dep = { field: editFormData.depends_on_field };
      if (editFormData.depends_on_operator === "equals") dep.value = editFormData.depends_on_value;
      else if (editFormData.depends_on_operator === "not_value") dep.not_value = editFormData.depends_on_value;
      else if (editFormData.depends_on_operator === "contains") dep.contains = editFormData.depends_on_value;
      else if (editFormData.depends_on_operator === "value_in") dep.value_in = editFormData.depends_on_values || [];
      updateField(key, "depends_on", dep);
    } else {
      updateField(key, "depends_on", null);
    }

    setEditingField(null);
    setEditFormData({});
    setEditOption("");
    toast.success("Campo atualizado com sucesso");
  };

  const handleRemoveField = (field) => {
    if (field.is_custom) {
      handleDeleteCustomField(field.field_key);
    } else {
      updateField(field.field_key, "is_visible", false);
      toast.success(`Campo "${field.label}" ocultado`);
    }
  };

  const editNeedsOptions = ["select", "checkbox"].includes(editFormData.field_type);

  // ── Template actions ──
  const handleActivateTemplate = async (tplId, tplName) => {
    if (!window.confirm(`Ativar o template "${tplName}"? A configuração atual será substituída.`)) return;
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/templates/${tplId}/activate`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        toast.success(`Template "${tplName}" ativado`);
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

  const handleDuplicateTemplate = async (tplId) => {
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/templates/${tplId}/duplicate`, {
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

  const handleDeleteTemplate = async (tplId) => {
    if (!window.confirm("Eliminar este template?")) return;
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/templates/${tplId}`, {
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

  // ── Preview ──
  const handlePreviewTemplate = async (tplId) => {
    setPreviewLoading(true);
    setPreviewDialog(true);
    try {
      const res = await fetch(`${API_URL}/api/admin/form-config/templates/${tplId}/preview`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setPreviewData({ ...data, _templateId: tplId });
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

  const previewGroupedByStep = useMemo(() => {
    if (!previewData?.fields) return {};
    return previewData.fields
      .filter(f => f.is_visible)
      .reduce((acc, f) => {
        const step = f.step || 1;
        if (!acc[step]) acc[step] = [];
        acc[step].push(f);
        return acc;
      }, {});
  }, [previewData]);

  // ── Render ──
  return (
    <DashboardLayout>
      <TooltipProvider delayDuration={300}>
      <div className="space-y-6" data-testid="form-management-page">

        {/* ── Header ── */}
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <FileText className="h-6 w-6" />
              Gestão do Formulário
            </h1>
            <p className="text-muted-foreground mt-1">
              Edição visual WYSIWYG — arraste, edite labels e configure campos
            </p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Button variant="outline" onClick={() => setTemplateDialog(true)} data-testid="templates-btn">
              <LayoutTemplate className="h-4 w-4 mr-2" /> Templates
            </Button>
            <Button variant="outline" onClick={() => setSaveTemplateDialog(true)} data-testid="save-as-template-btn">
              <Bookmark className="h-4 w-4 mr-2" /> Guardar como Template
            </Button>
            <Button variant="outline" onClick={handleReset} disabled={saving} data-testid="reset-form-config">
              <RotateCcw className="h-4 w-4 mr-2" /> Repor Padrão
            </Button>
            <Button onClick={handleSave} disabled={saving || !hasChanges} data-testid="save-form-config">
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
              Guardar {hasChanges && "*"}
            </Button>
          </div>
        </div>

        {/* ── Unsaved changes warning ── */}
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
          <DragDropContext onDragEnd={onDragEnd}>
            <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-6">

              {/* ════════════════════════════════════════════════════════
                  LEFT COLUMN — Campos Ocultos (hidden fields pool)
                  ════════════════════════════════════════════════════════ */}
              <div className="space-y-4">
                <Card>
                  <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                      <Inbox className="h-4 w-4 text-muted-foreground" />
                      Campos Ocultos
                    </CardTitle>
                    <CardDescription className="text-xs">
                      {availableFields.length} campo{availableFields.length !== 1 ? "s" : ""} oculto{availableFields.length !== 1 ? "s" : ""} — arraste para ativar
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <Droppable droppableId="available">
                      {(provided, snapshot) => (
                        <div
                          ref={provided.innerRef}
                          {...provided.droppableProps}
                          className={`min-h-[120px] rounded-lg border-2 border-dashed transition-colors p-2 space-y-1.5 max-h-[60vh] overflow-y-auto ${
                            snapshot.isDraggingOver
                              ? "border-primary/50 bg-primary/5"
                              : "border-muted-foreground/20 bg-muted/20"
                          }`}
                        >
                          {availableFields.length === 0 && !snapshot.isDraggingOver ? (
                            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                              <Eye className="h-5 w-5 mb-2 text-green-500" />
                              <p className="text-xs text-center">Todos os campos estão ativos</p>
                            </div>
                          ) : (
                            availableFields.map((field, index) => (
                              <Draggable key={field.field_key} draggableId={field.field_key} index={index}>
                                {(provided, snapshot) => (
                                  <div
                                    ref={provided.innerRef}
                                    {...provided.draggableProps}
                                    style={provided.draggableProps.style}
                                  >
                                    <CompactFieldCard
                                      field={field}
                                      isDragging={snapshot.isDragging}
                                      dragHandleProps={provided.dragHandleProps}
                                    />
                                  </div>
                                )}
                              </Draggable>
                            ))
                          )}
                          {provided.placeholder}
                        </div>
                      )}
                    </Droppable>

                    {/* New custom field button */}
                    <Button
                      onClick={() => setCreateDialog(true)}
                      className="mt-4 w-full bg-emerald-600 hover:bg-emerald-700"
                      data-testid="create-custom-field"
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      Novo Campo
                    </Button>
                  </CardContent>
                </Card>

                {/* ── Legend ── */}
                <Card className="bg-muted/30">
                  <CardContent className="p-4 space-y-2">
                    <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Controles</p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Pencil className="h-3.5 w-3.5 shrink-0" /> <span>Editar campo</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Eye className="h-3.5 w-3.5 shrink-0 text-green-600" /> <span>Visível / Oculto</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Star className="h-3.5 w-3.5 shrink-0 text-red-500" /> <span>Obrigatório / Opcional</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Trash2 className="h-3.5 w-3.5 shrink-0 text-red-500" /> <span>Eliminar / Ocultar campo</span>
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <GripVertical className="h-3.5 w-3.5 shrink-0" /> <span>Arrastar para reordenar</span>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* ════════════════════════════════════════════════════════
                  RIGHT COLUMN — WYSIWYG Form Preview (steps with DnD)
                  ════════════════════════════════════════════════════════ */}
              <div className="space-y-6">
                {allSteps.map((step) => {
                  const stepFields = activeFieldsByStep[step] || [];
                  const stepDepConfig = stepConfig[String(step)];
                  const hasStepRule = !!stepDepConfig?.depends_on;
                  const isCustomStep = step > 6 || !!stepLabels[String(step)];
                  const stepLabel = stepLabels[String(step)] || STEP_LABELS[step] || `Passo ${step}`;

                  return (
                    <Card key={step} className={`overflow-hidden ${hasStepRule ? "ring-1 ring-blue-200 dark:ring-blue-800" : ""}`}>
                      <CardHeader className="pb-3 bg-muted/30 border-b">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className={`h-7 w-7 rounded-full flex items-center justify-center text-sm font-bold ${isCustomStep ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400" : "bg-primary text-primary-foreground"}`}>{step}</span>
                            <CardTitle className="text-lg">{stepLabel}</CardTitle>
                            {isCustomStep && (
                              <Badge className="bg-emerald-100 text-emerald-700 text-[10px] px-1.5 py-0">Personalizado</Badge>
                            )}
                            {hasStepRule && (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Badge className="bg-blue-100 text-blue-700 text-[10px] px-1.5 py-0 gap-1 cursor-help">
                                    <GitBranch className="h-3 w-3" />
                                    {stepDepConfig.depends_on.not_value ? "≠" : "="}{stepDepConfig.depends_on.value || stepDepConfig.depends_on.not_value || ""}
                                  </Badge>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p>Passo condicional: visível quando {stepDepConfig.depends_on.field} {stepDepConfig.depends_on.not_value ? `≠ ${stepDepConfig.depends_on.not_value}` : `= ${stepDepConfig.depends_on.value}`}</p>
                                </TooltipContent>
                              </Tooltip>
                            )}
                          </div>
                          <div className="flex items-center gap-1">
                            <Badge variant="outline" className="text-xs">
                              {stepFields.length} campo{stepFields.length !== 1 ? "s" : ""}
                            </Badge>
                            {/* Conditional step toggle */}
                            {step > 1 && (
                              <Button
                                variant={hasStepRule ? "default" : "outline"}
                                size="sm"
                                className={`h-7 gap-1 text-xs ${hasStepRule ? "bg-blue-600 hover:bg-blue-700 text-white" : "text-muted-foreground"}`}
                                onClick={() => openStepEditDialog(step)}
                                data-testid={`step-settings-btn-${step}`}
                              >
                                <GitBranch className="h-3 w-3" />
                                {hasStepRule ? "Condicional" : "Condicional"}
                              </Button>
                            )}
                            {/* Delete custom step */}
                            {isCustomStep && stepFields.length === 0 && (
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 w-7 p-0 text-red-500 hover:text-red-600 hover:bg-red-50"
                                    onClick={() => {
                                      if (window.confirm(`Eliminar o passo ${step} "${stepLabel}"?`)) handleDeleteStep(step);
                                    }}
                                    data-testid={`delete-step-btn-${step}`}
                                  >
                                    <Trash2 className="h-3.5 w-3.5" />
                                  </Button>
                                </TooltipTrigger>
                                <TooltipContent>Eliminar passo</TooltipContent>
                              </Tooltip>
                            )}
                          </div>
                        </div>
                        {stepFields.some(f => f.is_custom) && (
                          <CardDescription className="mt-1">
                            Inclui {stepFields.filter(f => f.is_custom).length} campo{stepFields.filter(f => f.is_custom).length !== 1 ? "s" : ""} personalizado{stepFields.filter(f => f.is_custom).length !== 1 ? "s" : ""}
                          </CardDescription>
                        )}
                        {hasStepRule && (
                          <CardDescription className="mt-1 text-blue-600 dark:text-blue-400">
                            <GitBranch className="h-3 w-3 inline mr-1" />
                            Visível quando "{stepDepConfig.depends_on.field}" {stepDepConfig.depends_on.not_value ? `≠ "${stepDepConfig.depends_on.not_value}"` : `= "${stepDepConfig.depends_on.value}"`}
                          </CardDescription>
                        )}
                      </CardHeader>
                      <CardContent className="p-4">
                        <Droppable droppableId={`step-${step}`}>
                          {(provided, snapshot) => (
                            <div
                              ref={provided.innerRef}
                              {...provided.droppableProps}
                              className={`min-h-[60px] rounded-lg transition-colors p-1 space-y-3 ${
                                snapshot.isDraggingOver
                                  ? "ring-2 ring-primary/30 ring-offset-2 bg-primary/[0.02]"
                                  : ""
                              }`}
                            >
                              {stepFields.length === 0 && !snapshot.isDraggingOver ? (
                                <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                                  <ArrowRightLeft className="h-4 w-4 mb-1.5 opacity-50" />
                                  <p className="text-xs">Arraste campos aqui</p>
                                </div>
                              ) : (
                                stepFields.map((field, index) => (
                                  <Draggable key={field.field_key} draggableId={field.field_key} index={index}>
                                    {(provided, snapshot) => (
                                      <div
                                        ref={provided.innerRef}
                                        {...provided.draggableProps}
                                        style={provided.draggableProps.style}
                                      >
                                        <WysiwygFieldCard
                                          field={field}
                                          isDragging={snapshot.isDragging}
                                          dragHandleProps={provided.dragHandleProps}
                                          updateField={updateField}
                                          onEditField={openEditDialog}
                                          handleRemoveField={handleRemoveField}
                                        />
                                      </div>
                                    )}
                                  </Draggable>
                                ))
                              )}
                              {provided.placeholder}
                            </div>
                          )}
                        </Droppable>
                      </CardContent>
                    </Card>
                  );
                })}
                {/* Add New Step button */}
                <Button
                  variant="outline"
                  className="w-full border-dashed border-2 border-muted-foreground/30 hover:border-primary/50 text-muted-foreground hover:text-foreground gap-2 py-6"
                  onClick={() => setCreateStepDialog(true)}
                  data-testid="create-step-btn"
                >
                  <Plus className="h-5 w-5" />
                  <span className="text-sm font-medium">Novo Passo</span>
                </Button>
              </div>

            </div>
          </DragDropContext>
        )}

        {/* ══════════════════════════════════════════════════════════════
            DIALOG: Create Custom Field
            ══════════════════════════════════════════════════════════════ */}
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
              <div className="space-y-2">
                <Label>Nome do campo <span className="text-red-500">*</span></Label>
                <Input
                  placeholder="Ex: País de residência fiscal"
                  value={newField.label}
                  onChange={(e) => setNewField(prev => ({ ...prev, label: e.target.value }))}
                  data-testid="new-field-label"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Tipo de campo <span className="text-red-500">*</span></Label>
                  <Select value={newField.field_type} onValueChange={(v) => setNewField(prev => ({ ...prev, field_type: v, options: [] }))}>
                    <SelectTrigger data-testid="new-field-type"><SelectValue /></SelectTrigger>
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
                    <SelectTrigger data-testid="new-field-step"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(STEP_LABELS).map(([k, v]) => (
                        <SelectItem key={k} value={k}>{k}. {v}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

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

              <div className="flex items-center gap-3">
                <Switch
                  checked={newField.is_required}
                  onCheckedChange={(v) => setNewField(prev => ({ ...prev, is_required: v }))}
                  data-testid="new-field-required"
                />
                <Label>Campo obrigatório</Label>
              </div>

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
                          <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-red-500 hover:text-red-700" onClick={() => removeOption(idx)}>
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
                    <Button variant="outline" onClick={addOption} disabled={!newOption.trim()} data-testid="add-option-btn">
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

        {/* ══════════════════════════════════════════════════════════════
            DIALOG: Create New Step
            ══════════════════════════════════════════════════════════════ */}
        <Dialog open={createStepDialog} onOpenChange={setCreateStepDialog}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Plus className="h-5 w-5" />
                Criar Novo Passo
              </DialogTitle>
              <DialogDescription>
                Adicione um novo passo ao formulário. Depois pode arrastar campos para ele
                e configurar a visibilidade condicional.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <Label>Nome do passo <span className="text-red-500">*</span></Label>
                <Input
                  placeholder="Ex: Documentação Adicional"
                  value={newStepLabel}
                  onChange={(e) => setNewStepLabel(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreateStep()}
                  data-testid="new-step-label-input"
                />
              </div>
              <div className="p-3 rounded-lg bg-muted/50 text-xs text-muted-foreground space-y-1">
                <p className="font-medium">Depois de criar:</p>
                <ul className="list-disc list-inside space-y-0.5 ml-1">
                  <li>Arraste campos existentes para o novo passo</li>
                  <li>Ou crie campos personalizados directamente nele</li>
                  <li>Configure a visibilidade condicional com o botão "Condicional"</li>
                </ul>
              </div>
            </div>

            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={() => { setCreateStepDialog(false); setNewStepLabel(""); }}>Cancelar</Button>
              <Button
                onClick={handleCreateStep}
                disabled={!newStepLabel.trim()}
                className="bg-emerald-600 hover:bg-emerald-700"
              >
                <Plus className="h-4 w-4 mr-1.5" />
                Criar Passo
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* ══════════════════════════════════════════════════════════════
            DIALOG: Step Visibility Configuration
            ══════════════════════════════════════════════════════════════ */}
        <Dialog open={!!editingStep} onOpenChange={(open) => { if (!open) setEditingStep(null); }}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Passo {editingStep} — Visibilidade Condicional
              </DialogTitle>
              <DialogDescription>
                Configure quando este passo deve ser visível no formulário público.
                O passo só aparece quando a condição definida for satisfeita.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-2">
              {/* Toggle: Enable/Disable conditional */}
              <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
                <div className="flex items-center gap-2">
                  <GitBranch className="h-4 w-4 text-blue-600" />
                  <Label className="text-sm font-medium">Passo condicional</Label>
                </div>
                <Switch
                  checked={editStepFormData.enabled || false}
                  onCheckedChange={(checked) => setEditStepFormData(prev => ({ ...prev, enabled: checked }))}
                />
              </div>

              {editStepFormData.enabled && (
                <>
                  {/* Trigger field selector */}
                  <div className="space-y-2">
                    <Label className="text-sm">
                      Quando o campo <span className="text-muted-foreground">(passo anterior)</span>
                    </Label>
                    <Select
                      value={editStepFormData.depends_on_field}
                      onValueChange={(val) => setEditStepFormData(prev => ({ ...prev, depends_on_field: val, depends_on_value: "" }))}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Selecionar campo..." />
                      </SelectTrigger>
                      <SelectContent>
                        {getStepTriggerFields(editingStep).map(f => (
                          <SelectItem key={f.field_key} value={f.field_key}>{f.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {getStepTriggerFields(editingStep).length === 0 && (
                      <p className="text-xs text-muted-foreground">
                        Não existem campos de seleção em passos anteriores. Adicione um campo dropdown/rádio num passo anterior.
                      </p>
                    )}
                  </div>

                  {/* Operator */}
                  {editStepFormData.depends_on_field && (
                    <div className="space-y-2">
                      <Label className="text-sm">Condição</Label>
                      <Select
                        value={editStepFormData.depends_on_operator || "equals"}
                        onValueChange={(val) => setEditStepFormData(prev => ({ ...prev, depends_on_operator: val, depends_on_value: "" }))}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="equals">Igual a</SelectItem>
                          <SelectItem value="not_value">Diferente de</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  )}

                  {/* Value */}
                  {editStepFormData.depends_on_field && (
                    <div className="space-y-2">
                      <Label className="text-sm">Valor</Label>
                      <Select
                        value={editStepFormData.depends_on_value || ""}
                        onValueChange={(val) => setEditStepFormData(prev => ({ ...prev, depends_on_value: val }))}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Selecionar valor..." />
                        </SelectTrigger>
                        <SelectContent>
                          {getStepTriggerFieldOptions(editStepFormData.depends_on_field).map(opt => (
                            <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  )}

                  {/* Preview */}
                  {editStepFormData.enabled && editStepFormData.depends_on_field && editStepFormData.depends_on_value && (
                    <div className="p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800">
                      <p className="text-xs text-blue-700 dark:text-blue-300 flex items-center gap-1.5">
                        <Info className="h-3.5 w-3.5 shrink-0" />
                        {editStepFormData.depends_on_operator === "not_value" ? (
                          <>Passo {editingStep} visível quando <strong>{fields.find(f => f.field_key === editStepFormData.depends_on_field)?.label}</strong> for diferente de <strong>"{editStepFormData.depends_on_value}"</strong></>
                        ) : (
                          <>Passo {editingStep} visível quando <strong>{fields.find(f => f.field_key === editStepFormData.depends_on_field)?.label}</strong> for <strong>"{editStepFormData.depends_on_value}"</strong></>
                        )}
                      </p>
                    </div>
                  )}
                </>
              )}

              {!editStepFormData.enabled && (
                <div className="p-3 rounded-lg bg-muted/50 text-center">
                  <p className="text-sm text-muted-foreground">Este passo será sempre visível no formulário público.</p>
                </div>
              )}
            </div>

            <DialogFooter className="gap-2">
              <Button variant="outline" onClick={() => setEditingStep(null)}>Cancelar</Button>
              <Button
                onClick={handleSaveStepConfig}
                disabled={(editStepFormData.enabled && (!editStepFormData.depends_on_field || !editStepFormData.depends_on_value)) || saving}
              >
                {saving ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> : <Check className="h-4 w-4 mr-1.5" />}
                {saving ? "A guardar..." : "Guardar"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* ══════════════════════════════════════════════════════════════
            DIALOG: Edit Field
            ══════════════════════════════════════════════════════════════ */}
        <Dialog open={!!editingField} onOpenChange={(open) => { if (!open) { setEditingField(null); setEditFormData({}); setEditOption(""); } }}>
          <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Pencil className="h-5 w-5" />
                Editar Campo
              </DialogTitle>
              <DialogDescription>
                Editar propriedades do campo "{editingField?.label || ""}"
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-5 py-4">
              <div className="space-y-2">
                <Label>Nome do campo <span className="text-red-500">*</span></Label>
                <Input
                  placeholder="Ex: País de residência fiscal"
                  value={editFormData.label || ""}
                  onChange={(e) => setEditFormData(prev => ({ ...prev, label: e.target.value }))}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Tipo de campo</Label>
                  <Select value={editFormData.field_type || "text"} onValueChange={(v) => setEditFormData(prev => ({ ...prev, field_type: v, options: [] }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {FIELD_TYPES.map(t => (
                        <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Passo do formulário</Label>
                  <Select value={editFormData.step || "1"} onValueChange={(v) => setEditFormData(prev => ({ ...prev, step: v }))}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {Object.entries(STEP_LABELS).map(([k, v]) => (
                        <SelectItem key={k} value={k}>{k}. {v}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Placeholder</Label>
                  <Input
                    placeholder="Texto de exemplo no campo"
                    value={editFormData.placeholder || ""}
                    onChange={(e) => setEditFormData(prev => ({ ...prev, placeholder: e.target.value }))}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Texto de ajuda</Label>
                  <Input
                    placeholder="Texto de ajuda abaixo do campo"
                    value={editFormData.hint || ""}
                    onChange={(e) => setEditFormData(prev => ({ ...prev, hint: e.target.value }))}
                  />
                </div>
              </div>

              <div className="flex items-center gap-3">
                <Switch
                  checked={editFormData.is_required || false}
                  onCheckedChange={(v) => setEditFormData(prev => ({ ...prev, is_required: v }))}
                />
                <Label>Campo obrigatório</Label>
              </div>

              {/* ── Conditional Visibility (depends_on) ── */}
              <div className="space-y-3 pt-2 border-t">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Label className="text-base font-semibold">Visibilidade Condicional</Label>
                    <Tooltip>
                        <TooltipTrigger asChild>
                          <button type="button" className="text-muted-foreground hover:text-foreground">
                            <Info className="h-3.5 w-3.5" />
                          </button>
                        </TooltipTrigger>
                        <TooltipContent>
                          <p>Este campo só aparece quando o campo dependente tiver o valor indicado.</p>
                        </TooltipContent>
                      </Tooltip>
                  </div>
                  <div className="flex items-center gap-2">
                    <Label className="text-sm text-muted-foreground">Mostrar apenas quando...</Label>
                    <Switch
                      checked={editFormData.depends_on_enabled || false}
                      onCheckedChange={(v) => setEditFormData(prev => ({ ...prev, depends_on_enabled: v }))}
                    />
                  </div>
                </div>

                {editFormData.depends_on_enabled && (
                  <div className="space-y-3 pl-1">
                    {/* Row: Campo dependente + Condição + Valor */}
                    <div className="grid grid-cols-[1fr_1fr_1fr] gap-2">
                      {/* Campo dependente */}
                      <div className="space-y-1">
                        <Label className="text-xs text-muted-foreground">Campo dependente</Label>
                        <Select
                          value={editFormData.depends_on_field || ""}
                          onValueChange={(v) => setEditFormData(prev => ({ ...prev, depends_on_field: v, depends_on_value: "", depends_on_values: [] }))}
                        >
                          <SelectTrigger className="h-9 text-sm">
                            <SelectValue placeholder="Selecionar campo..." />
                          </SelectTrigger>
                          <SelectContent>
                            {dependsOnFields.map(f => (
                              <SelectItem key={f.field_key} value={f.field_key}>{f.label}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      {/* Condição */}
                      <div className="space-y-1">
                        <Label className="text-xs text-muted-foreground">Condição</Label>
                        <Select
                          value={editFormData.depends_on_operator || "equals"}
                          onValueChange={(v) => setEditFormData(prev => ({ ...prev, depends_on_operator: v }))}
                        >
                          <SelectTrigger className="h-9 text-sm">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="equals">é igual a</SelectItem>
                            <SelectItem value="not_value">é diferente de</SelectItem>
                            <SelectItem value="contains">contém</SelectItem>
                            <SelectItem value="value_in">é um de</SelectItem>
                          </SelectContent>
                        </Select>
                      </div>

                      {/* Valor */}
                      <div className="space-y-1">
                        <Label className="text-xs text-muted-foreground">Valor</Label>
                        {editFormData.depends_on_operator === "value_in" ? (
                          <div className="max-h-24 overflow-y-auto rounded-md border px-2 py-1.5 bg-background">
                            {dependsOnFieldOptions.map(opt => (
                              <label key={opt} className="flex items-center gap-2 py-0.5 cursor-pointer">
                                <Checkbox
                                  checked={(editFormData.depends_on_values || []).includes(opt)}
                                  onCheckedChange={(checked) => {
                                    setEditFormData(prev => {
                                      const vals = prev.depends_on_values || [];
                                      return {
                                        ...prev,
                                        depends_on_values: checked
                                          ? [...vals, opt]
                                          : vals.filter(v => v !== opt),
                                      };
                                    });
                                  }}
                                />
                                <span className="text-xs">{opt}</span>
                              </label>
                            ))}
                          </div>
                        ) : dependsOnFieldOptions.length > 0 ? (
                          <Select
                            value={editFormData.depends_on_value || ""}
                            onValueChange={(v) => setEditFormData(prev => ({ ...prev, depends_on_value: v }))}
                          >
                            <SelectTrigger className="h-9 text-sm">
                              <SelectValue placeholder="Selecionar..." />
                            </SelectTrigger>
                            <SelectContent>
                              {dependsOnFieldOptions.map(opt => (
                                <SelectItem key={opt} value={opt}>{opt}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        ) : (
                          <Input
                            className="h-9 text-sm"
                            placeholder="Valor..."
                            value={editFormData.depends_on_value || ""}
                            onChange={(e) => setEditFormData(prev => ({ ...prev, depends_on_value: e.target.value }))}
                          />
                        )}
                      </div>
                    </div>

                    {/* Live description */}
                    {editFormData.depends_on_field && editFormData.depends_on_value && editFormData.depends_on_operator !== "value_in" && (
                      <p className="text-xs text-muted-foreground bg-muted/50 rounded px-2.5 py-1.5">
                        Visível quando <span className="font-medium text-foreground">{fields.find(f => f.field_key === editFormData.depends_on_field)?.label}</span>{" "}
                        {editFormData.depends_on_operator === "equals" ? "é igual a" : editFormData.depends_on_operator === "not_value" ? "é diferente de" : "contém"}{" "}
                        <span className="font-medium text-foreground">"{editFormData.depends_on_value}"</span>
                      </p>
                    )}
                    {editFormData.depends_on_field && editFormData.depends_on_operator === "value_in" && (editFormData.depends_on_values || []).length > 0 && (
                      <p className="text-xs text-muted-foreground bg-muted/50 rounded px-2.5 py-1.5">
                        Visível quando <span className="font-medium text-foreground">{fields.find(f => f.field_key === editFormData.depends_on_field)?.label}</span>{" "}
                        é um de: <span className="font-medium text-foreground">{editFormData.depends_on_values.join(", ")}</span>
                      </p>
                    )}
                  </div>
                )}
              </div>

              {editNeedsOptions && (
                <div className="space-y-3 pt-2 border-t">
                  <Label className="text-base font-semibold">
                    Opções {editFormData.field_type === "select" ? "do Dropdown" : "dos Checkboxes"}
                    <span className="text-red-500 ml-1">*</span>
                  </Label>

                  {(editFormData.options || []).length > 0 && (
                    <div className="space-y-1.5">
                      {(editFormData.options || []).map((opt, idx) => (
                        <div key={idx} className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                          <span className="text-sm flex-1">{opt}</span>
                          <Button variant="ghost" size="sm" className="h-6 w-6 p-0 text-red-500 hover:text-red-700" onClick={() => removeEditOption(idx)}>
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="flex gap-2">
                    <Input
                      placeholder="Nome da opção"
                      value={editOption}
                      onChange={(e) => setEditOption(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addEditOption())}
                    />
                    <Button variant="outline" onClick={addEditOption} disabled={!editOption.trim()}>
                      <Plus className="h-4 w-4" />
                    </Button>
                  </div>
                  {(editFormData.options || []).length === 0 && (
                    <p className="text-xs text-amber-600">Adicione pelo menos uma opção</p>
                  )}
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => { setEditingField(null); setEditFormData({}); setEditOption(""); }}>Cancelar</Button>
              <Button
                onClick={handleEditField}
                disabled={!editFormData.label?.trim() || (editNeedsOptions && (editFormData.options || []).length === 0)}
                className="bg-emerald-600 hover:bg-emerald-700"
              >
                <Save className="h-4 w-4 mr-2" />
                Guardar Alterações
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* ══════════════════════════════════════════════════════════════
            DIALOG: Templates
            ══════════════════════════════════════════════════════════════ */}
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
                          {tpl.is_system && <Badge className="bg-blue-100 text-blue-700 text-[10px]">Sistema</Badge>}
                        </div>
                        {tpl.description && <p className="text-xs text-muted-foreground mt-1">{tpl.description}</p>}
                        <p className="text-xs text-muted-foreground mt-1">{tpl.field_count} campos</p>
                      </div>
                      <div className="flex gap-1.5 shrink-0">
                        <Button size="sm" variant="outline" onClick={() => handlePreviewTemplate(tpl.id)} data-testid={`preview-${tpl.id}`} className="h-8">
                          <Eye className="h-3 w-3 mr-1" /> Ver
                        </Button>
                        <Button size="sm" onClick={() => handleActivateTemplate(tpl.id, tpl.name)} data-testid={`activate-${tpl.id}`} className="h-8">
                          <Zap className="h-3 w-3 mr-1" /> Ativar
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => handleDuplicateTemplate(tpl.id)} className="h-8">
                          <Copy className="h-3 w-3" />
                        </Button>
                        {!tpl.is_system && (
                          <Button size="sm" variant="ghost" className="h-8 text-red-500 hover:text-red-700" onClick={() => handleDeleteTemplate(tpl.id)}>
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

        {/* ══════════════════════════════════════════════════════════════
            DIALOG: Save as Template
            ══════════════════════════════════════════════════════════════ */}
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

        {/* ══════════════════════════════════════════════════════════════
            DIALOG: Template Preview
            ══════════════════════════════════════════════════════════════ */}
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
                  {previewData.description && <DialogDescription>{previewData.description}</DialogDescription>}
                </DialogHeader>

                <div className="py-4 space-y-6" data-testid="template-preview-content">
                  <div className="flex items-center gap-4 text-sm text-muted-foreground bg-muted/50 p-3 rounded-lg">
                    <span>{previewData.fields?.length || 0} campos totais</span>
                    <span>{previewData.fields?.filter(f => f.is_required).length || 0} obrigatórios</span>
                    <span>{previewData.fields?.filter(f => f.is_custom).length || 0} personalizados</span>
                    {previewData.is_system && <Badge className="bg-blue-100 text-blue-700 text-xs">Sistema</Badge>}
                  </div>

                  {Object.entries(previewGroupedByStep)
                    .sort(([a], [b]) => Number(a) - Number(b))
                    .map(([step, stepFields]) => (
                      <div key={step} className="space-y-3">
                        <div className="flex items-center gap-2">
                          <span className="h-7 w-7 rounded-full bg-primary flex items-center justify-center text-sm font-bold text-primary-foreground">{step}</span>
                          <h3 className="font-semibold text-sm">{STEP_LABELS[Number(step)] || `Passo ${step}`}</h3>
                          <Badge variant="outline" className="text-[10px]">{stepFields.length} campos</Badge>
                        </div>

                        <div className="ml-9 space-y-3">
                          {stepFields.sort((a, b) => (a.order_index ?? a.order ?? 0) - (b.order_index ?? b.order ?? 0)).map((field) => (
                            <div key={field.field_key} className={`p-4 rounded-lg border ${field.is_custom ? "bg-emerald-50/50 dark:bg-emerald-900/10 border-emerald-200/50" : "bg-card border-border"}`}>
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-sm font-medium">{field.label}</span>
                                {field.is_required && <span className="text-red-600 text-xs font-semibold">* obrigatório</span>}
                                {field.is_custom && <Badge className="bg-emerald-100 text-emerald-700 text-[10px]">Personalizado</Badge>}
                              </div>
                              <WysiwygFieldPreview field={field} />
                              {field.hint && <p className="text-[10px] text-muted-foreground mt-1.5">{field.hint}</p>}
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                </div>

                <DialogFooter>
                  <Button variant="outline" onClick={() => setPreviewDialog(false)}>Fechar</Button>
                  <Button
                    onClick={() => {
                      const tid = previewData._templateId;
                      const tname = previewData.name;
                      setPreviewDialog(false);
                      handleActivateTemplate(tid, tname);
                    }}
                    data-testid="activate-from-preview"
                  >
                    <Zap className="h-4 w-4 mr-2" />
                    Ativar este Template
                  </Button>
                </DialogFooter>
              </>
            ) : null}
          </DialogContent>
        </Dialog>

      </div>
      </TooltipProvider>
    </DashboardLayout>
  );
};

export default FormManagementPage;
