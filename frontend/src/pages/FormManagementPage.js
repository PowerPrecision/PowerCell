/**
 * FormManagementPage - Gestão do Formulário Público
 * 
 * ACESSO: Admin e CEO apenas
 * 
 * Funcionalidades:
 * - Listar todos os campos do formulário por passo
 * - Ativar/desativar campos
 * - Marcar campos como obrigatórios
 * - Repor configuração padrão
 */
import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import { Label } from "../components/ui/label";
import { toast } from "sonner";
import {
  FileText, Loader2, Save, RotateCcw, Eye, EyeOff, AlertCircle, CheckCircle
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const STEP_LABELS = {
  1: "Dados Pessoais",
  2: "Segundo Titular",
  3: "Dados do Imóvel",
  4: "Situação Financeira",
  5: "Histórico Bancário",
};

const FIELD_TYPE_LABELS = {
  text: "Texto",
  select: "Seleção",
  checkbox: "Checkboxes",
  radio: "Opção",
  date: "Data",
  number: "Número",
};

const FormManagementPage = () => {
  const { token } = useAuth();
  const [fields, setFields] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);

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
    if (!window.confirm("Tem a certeza que quer repor a configuração padrão? Todas as alterações serão perdidas.")) return;
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

  const groupedByStep = fields.reduce((acc, field, idx) => {
    const step = field.step || 1;
    if (!acc[step]) acc[step] = [];
    acc[step].push({ ...field, _idx: idx });
    return acc;
  }, {});

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="form-management-page">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <FileText className="h-6 w-6" />
              Gestão do Formulário
            </h1>
            <p className="text-muted-foreground mt-1">Controlar quais campos aparecem no formulário público de registo</p>
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
                    <CardTitle className="text-lg">
                      Passo {step} - {STEP_LABELS[Number(step)] || `Passo ${step}`}
                    </CardTitle>
                    <CardDescription>
                      {stepFields.filter(f => f.is_visible).length} de {stepFields.length} campos visíveis
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {stepFields.sort((a, b) => (a.order || 0) - (b.order || 0)).map((field) => (
                      <div
                        key={field.field_key}
                        className={`flex items-center justify-between p-3 rounded-lg border transition-all ${
                          field.is_visible
                            ? "bg-card border-border"
                            : "bg-muted/30 border-transparent opacity-60"
                        }`}
                        data-testid={`form-field-${field.field_key}`}
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          {field.is_visible ? (
                            <Eye className="h-4 w-4 text-green-600 shrink-0" />
                          ) : (
                            <EyeOff className="h-4 w-4 text-muted-foreground shrink-0" />
                          )}
                          <div className="min-w-0">
                            <p className="text-sm font-medium truncate">{field.label}</p>
                            <div className="flex items-center gap-2 mt-0.5">
                              <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                                {FIELD_TYPE_LABELS[field.field_type] || field.field_type}
                              </Badge>
                              <span className="text-[10px] text-muted-foreground font-mono">{field.field_key}</span>
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
                        </div>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              ))}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
};

export default FormManagementPage;
