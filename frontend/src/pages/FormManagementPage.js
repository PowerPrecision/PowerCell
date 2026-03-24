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
  Plus, Trash2, GripVertical, X, PenLine
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

const FormManagementPage = () => {
  const { token } = useAuth();
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

  const updateField = (idx, key, value) => {
    setFields(prev => {
      const updated = [...prev];
      updated[idx] = { ...updated[idx], [key]: value };
      return updated;
    });
    setHasChanges(true);
  };

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
          <div className="flex gap-2">
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
                    {stepFields.sort((a, b) => (a.order || 0) - (b.order || 0)).map((field) => (
                      <div
                        key={field.field_key}
                        className={`flex items-center justify-between p-3 rounded-lg border transition-all ${
                          field.is_visible
                            ? field.is_custom
                              ? "bg-emerald-50/50 dark:bg-emerald-900/10 border-emerald-200/50 dark:border-emerald-800/30"
                              : "bg-card border-border"
                            : "bg-muted/30 border-transparent opacity-60"
                        }`}
                        data-testid={`form-field-${field.field_key}`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
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
                    ))}
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
      </div>
    </DashboardLayout>
  );
};

export default FormManagementPage;
