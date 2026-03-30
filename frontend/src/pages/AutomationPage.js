/**
 * O22 - Página de Automação de Workflows "No-Code"
 * Interface para criar regras "Se X, Então Y"
 */
import React, { useState, useEffect, useCallback } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Switch } from "../components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";
import { useAuth } from "../contexts/AuthContext";
import {
  Zap, Plus, Trash2, Edit2, Play, Pause,
  ArrowRight, ChevronRight, RefreshCw
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const TRIGGER_LABELS = {
  process_status_changed: "Estado do processo alterado",
  process_created: "Novo processo criado",
  document_uploaded: "Documento carregado",
  process_stale: "Processo sem atualização",
  client_registered: "Novo cliente registado",
};

const ACTION_LABELS = {
  send_notification: "Enviar notificação",
  change_status: "Alterar estado",
  assign_user: "Atribuir utilizador",
  add_comment: "Adicionar comentário",
  send_email: "Enviar email",
};

const AutomationPage = () => {
  const { token } = useAuth();
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingRule, setEditingRule] = useState(null);
  const [triggers, setTriggers] = useState([]);
  const [actions, setActions] = useState([]);

  const [form, setForm] = useState({
    name: "",
    description: "",
    trigger: "",
    trigger_config: {},
    action: "",
    action_config: {},
    is_active: true,
  });

  const headers = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const fetchRules = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/automation/rules`, { headers });
      if (res.ok) {
        const data = await res.json();
        setRules(data.rules || []);
      }
    } catch { /* silent */ }
    setLoading(false);
  }, [token]);

  const fetchConfig = useCallback(async () => {
    try {
      const [tRes, aRes] = await Promise.all([
        fetch(`${API_URL}/api/admin/automation/triggers`, { headers }),
        fetch(`${API_URL}/api/admin/automation/actions`, { headers }),
      ]);
      if (tRes.ok) setTriggers((await tRes.json()).triggers || []);
      if (aRes.ok) setActions((await aRes.json()).actions || []);
    } catch { /* silent */ }
  }, [token]);

  useEffect(() => {
    fetchRules();
    fetchConfig();
  }, [fetchRules, fetchConfig]);

  const handleSave = async () => {
    if (!form.name || !form.trigger || !form.action) {
      toast.error("Preencha nome, trigger e ação");
      return;
    }
    try {
      const url = editingRule
        ? `${API_URL}/api/admin/automation/rules/${editingRule.id}`
        : `${API_URL}/api/admin/automation/rules`;
      const method = editingRule ? "PUT" : "POST";
      
      const res = await fetch(url, { method, headers, body: JSON.stringify(form) });
      if (res.ok) {
        toast.success(editingRule ? "Regra atualizada" : "Regra criada");
        setShowDialog(false);
        setEditingRule(null);
        resetForm();
        fetchRules();
      } else {
        const err = await res.json();
        toast.error(err.detail || "Erro ao guardar");
      }
    } catch {
      toast.error("Erro de rede");
    }
  };

  const handleDelete = async (ruleId, ruleName) => {
    try {
      const res = await fetch(`${API_URL}/api/admin/automation/rules/${ruleId}`, {
        method: "DELETE", headers
      });
      if (res.ok) {
        setRules(prev => prev.filter(r => r.id !== ruleId));
        toast.success(`Regra "${ruleName}" eliminada`);
      }
    } catch {
      toast.error("Erro ao eliminar");
    }
  };

  const handleToggle = async (rule) => {
    try {
      const res = await fetch(`${API_URL}/api/admin/automation/rules/${rule.id}`, {
        method: "PUT", headers,
        body: JSON.stringify({ is_active: !rule.is_active })
      });
      if (res.ok) {
        setRules(prev => prev.map(r => r.id === rule.id ? { ...r, is_active: !r.is_active } : r));
        toast.success(rule.is_active ? "Regra desativada" : "Regra ativada");
      }
    } catch { /* silent */ }
  };

  const openEdit = (rule) => {
    setEditingRule(rule);
    setForm({
      name: rule.name,
      description: rule.description || "",
      trigger: rule.trigger,
      trigger_config: rule.trigger_config || {},
      action: rule.action,
      action_config: rule.action_config || {},
      is_active: rule.is_active,
    });
    setShowDialog(true);
  };

  const resetForm = () => {
    setForm({ name: "", description: "", trigger: "", trigger_config: {}, action: "", action_config: {}, is_active: true });
  };

  const selectedTrigger = triggers.find(t => t.id === form.trigger);
  const selectedAction = actions.find(a => a.id === form.action);

  if (loading) {
    return (
      <DashboardLayout>
        <div className="space-y-6">
          <div className="h-7 w-56 bg-muted animate-pulse rounded" />
          <div className="space-y-3">
            {[1,2,3].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded-lg" />)}
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="automation-page">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
              <Zap className="h-6 w-6 text-amber-500" />
              Automacoes
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Regras "Se X, Entao Y" para automatizar o seu workflow
            </p>
          </div>
          <Button onClick={() => { resetForm(); setEditingRule(null); setShowDialog(true); }} data-testid="create-rule-btn">
            <Plus className="h-4 w-4 mr-2" />
            Nova Regra
          </Button>
        </div>

        {/* Rules List */}
        {rules.length === 0 ? (
          <Card className="border-dashed">
            <CardContent className="py-12 text-center">
              <Zap className="h-12 w-12 mx-auto text-muted-foreground/30 mb-4" />
              <p className="text-muted-foreground">Nenhuma regra de automacao criada</p>
              <Button variant="outline" className="mt-4" onClick={() => { resetForm(); setShowDialog(true); }}>
                <Plus className="h-4 w-4 mr-2" />
                Criar primeira regra
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {rules.map(rule => (
              <Card key={rule.id} className={`transition-opacity ${!rule.is_active ? "opacity-50" : ""}`} data-testid={`rule-card-${rule.id}`}>
                <CardContent className="p-4">
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      <div className={`h-9 w-9 rounded-lg flex items-center justify-center shrink-0 ${rule.is_active ? "bg-amber-100 dark:bg-amber-900/30" : "bg-muted"}`}>
                        <Zap className={`h-4 w-4 ${rule.is_active ? "text-amber-600" : "text-muted-foreground"}`} />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="font-medium text-sm truncate">{rule.name}</p>
                          {!rule.is_active && <Badge variant="secondary" className="text-[10px]">Inativa</Badge>}
                        </div>
                        <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-0.5">
                          <Badge variant="outline" className="text-[10px] px-1.5">{TRIGGER_LABELS[rule.trigger] || rule.trigger}</Badge>
                          <ArrowRight className="h-3 w-3" />
                          <Badge variant="outline" className="text-[10px] px-1.5">{ACTION_LABELS[rule.action] || rule.action}</Badge>
                          {rule.execution_count > 0 && (
                            <span className="ml-2">Executada {rule.execution_count}x</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Switch
                        checked={rule.is_active}
                        onCheckedChange={() => handleToggle(rule)}
                        aria-label={`Ativar/desativar regra ${rule.name}`}
                      />
                      <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => openEdit(rule)} aria-label="Editar regra">
                        <Edit2 className="h-3.5 w-3.5" />
                      </Button>
                      <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => handleDelete(rule.id, rule.name)} aria-label="Eliminar regra">
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Create/Edit Dialog */}
        <Dialog open={showDialog} onOpenChange={setShowDialog}>
          <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="rule-dialog">
            <DialogHeader>
              <DialogTitle>{editingRule ? "Editar Regra" : "Nova Regra de Automacao"}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label>Nome da Regra</Label>
                <Input
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder="Ex: Notificar diretor quando processo aprovado"
                  data-testid="rule-name-input"
                />
              </div>
              <div>
                <Label>Descricao (opcional)</Label>
                <Textarea
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="Breve descricao do que esta regra faz"
                  rows={2}
                />
              </div>

              {/* Trigger Selection */}
              <div className="p-3 border rounded-lg bg-blue-50/50 dark:bg-blue-950/20 space-y-3">
                <Label className="text-blue-700 dark:text-blue-300 font-medium">SE (Trigger)</Label>
                <Select value={form.trigger} onValueChange={v => setForm({ ...form, trigger: v, trigger_config: {} })}>
                  <SelectTrigger data-testid="trigger-select">
                    <SelectValue placeholder="Selecionar trigger..." />
                  </SelectTrigger>
                  <SelectContent>
                    {triggers.map(t => (
                      <SelectItem key={t.id} value={t.id}>{t.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {/* Trigger config fields */}
                {selectedTrigger?.config_fields?.map(field => (
                  <div key={field.key}>
                    <Label className="text-xs">{field.label}</Label>
                    <Input
                      value={form.trigger_config[field.key] || ""}
                      onChange={e => setForm({
                        ...form,
                        trigger_config: { ...form.trigger_config, [field.key]: field.type === "number" ? Number(e.target.value) : e.target.value }
                      })}
                      type={field.type === "number" ? "number" : "text"}
                      placeholder={field.default?.toString() || ""}
                    />
                  </div>
                ))}
              </div>

              <div className="flex justify-center">
                <ChevronRight className="h-5 w-5 text-muted-foreground rotate-90" />
              </div>

              {/* Action Selection */}
              <div className="p-3 border rounded-lg bg-green-50/50 dark:bg-green-950/20 space-y-3">
                <Label className="text-green-700 dark:text-green-300 font-medium">ENTAO (Acao)</Label>
                <Select value={form.action} onValueChange={v => setForm({ ...form, action: v, action_config: {} })}>
                  <SelectTrigger data-testid="action-select">
                    <SelectValue placeholder="Selecionar acao..." />
                  </SelectTrigger>
                  <SelectContent>
                    {actions.map(a => (
                      <SelectItem key={a.id} value={a.id}>{a.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {/* Action config fields */}
                {selectedAction?.config_fields?.map(field => (
                  <div key={field.key}>
                    <Label className="text-xs">{field.label}</Label>
                    {field.type === "textarea" ? (
                      <Textarea
                        value={form.action_config[field.key] || ""}
                        onChange={e => setForm({
                          ...form,
                          action_config: { ...form.action_config, [field.key]: e.target.value }
                        })}
                        rows={2}
                      />
                    ) : (
                      <Input
                        value={form.action_config[field.key] || ""}
                        onChange={e => setForm({
                          ...form,
                          action_config: { ...form.action_config, [field.key]: e.target.value }
                        })}
                      />
                    )}
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between">
                <Label>Ativa</Label>
                <Switch checked={form.is_active} onCheckedChange={v => setForm({ ...form, is_active: v })} />
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => { setShowDialog(false); setEditingRule(null); }}>Cancelar</Button>
              <Button onClick={handleSave} data-testid="save-rule-btn">
                {editingRule ? "Guardar Alteracoes" : "Criar Regra"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default AutomationPage;
