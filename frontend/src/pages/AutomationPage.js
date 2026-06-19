/**
 * O22 - Página de Automação de Workflows "No-Code"
 * Pacote D — Construtor visual If/Then com selects do shadcn/ui.
 * Interface para criar regras "Se X, Então Y" SEM inputs de JSON em bruto.
 *
 * Tipos de config_fields suportados (vindos do backend /admin/automation/*):
 * - text              → <Input type="text">
 * - number            → <Input type="number">
 * - textarea          → <Textarea>
 * - select            → <Select> com field.options (+ field.option_labels opcional)
 * - select_status     → <Select> populado por /admin/workflow-statuses
 * - select_role       → <Select> com roles internos hardcoded (admin/ceo/diretor/...)
 * - select_user       → <Select> populado por /users
 * - select_email_template → <Select> populado por /email-templates (se disponível)
 */
import React, { useState, useEffect, useCallback } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Switch } from "../components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
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
  create_task: "Criar tarefa",
};

// Roles internos para o select_role (alinhado com backend/models/auth.py UserRole)
const INTERNAL_ROLES = [
  { value: "admin", label: "Administrador" },
  { value: "ceo", label: "CEO" },
  { value: "diretor", label: "Diretor" },
  { value: "consultor", label: "Consultor" },
  { value: "intermediario", label: "Intermediário" },
  { value: "administrativo", label: "Administrativo" },
  { value: "indexacao", label: "Indexação" },
];

const AutomationPage = ({ embedded = false }) => {
  const { token } = useAuth();
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingRule, setEditingRule] = useState(null);
  const [triggers, setTriggers] = useState([]);
  const [actions, setActions] = useState([]);
  // Pacote D — dados para popular os Selects dos config_fields
  const [workflowStatuses, setWorkflowStatuses] = useState([]);
  const [users, setUsers] = useState([]);

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

  // Pacote D — Buscar workflow statuses e utilizadores para popular os
  // Selects dos config_fields (select_status, select_user). Evita que o
  // utilizador tenha de digitar o ID do estado/utilizador num input de
  // texto — agora escolhe de uma dropdown.
  const fetchSelectOptions = useCallback(async () => {
    try {
      const [sRes, uRes] = await Promise.all([
        fetch(`${API_URL}/api/admin/workflow-statuses`, { headers }).catch(() => null),
        fetch(`${API_URL}/api/users`, { headers }).catch(() => null),
      ]);
      if (sRes && sRes.ok) {
        const sData = await sRes.json();
        // workflow-statuses devolve {statuses: [...]} ou array direto
        const arr = Array.isArray(sData) ? sData : (sData.statuses || sData || []);
        setWorkflowStatuses(arr);
      }
      if (uRes && uRes.ok) {
        const uData = await uRes.json();
        // /users devolve {users: [...]} ou array direto
        const arr = Array.isArray(uData) ? uData : (uData.users || uData || []);
        setUsers(arr);
      }
    } catch { /* silent — os Selects aparecem vazios se falhar */ }
  }, [token]);

  useEffect(() => {
    fetchRules();
    fetchConfig();
    fetchSelectOptions();
  }, [fetchRules, fetchConfig, fetchSelectOptions]);

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
        toast.error(extractErrorMessage(err.detail, "Erro ao guardar"));
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

  // ================================================================
  // Pacote D — Render helper para config_fields.
  // Renderiza o controlo certo consoante o `type` do field:
  //   text/number  → <Input>
  //   textarea     → <Textarea>
  //   select       → <Select> com field.options (+ option_labels)
  //   select_status→ <Select> com workflowStatuses do backend
  //   select_role  → <Select> com INTERNAL_ROLES
  //   select_user  → <Select> com users do backend
  //   select_email_template → <Select> (vazio por agora — sem endpoint)
  // Nunca mostra um input de JSON em bruto — o utilizador escolhe
  // sempre de uma dropdown ou digita texto curto.
  // ================================================================
  const renderConfigField = (field, configKey) => {
    const value = form[configKey]?.[field.key] ?? "";
    const setVal = (v) => setForm({
      ...form,
      [configKey]: { ...form[configKey], [field.key]: v }
    });

    // Para selects, shadcn/ui usa string vazia como placeholder; garantir
    // que o value é sempre string (evita warning "value undefined").
    const safeValue = value === null || value === undefined ? "" : String(value);

    if (field.type === "textarea") {
      return (
        <Textarea
          value={value}
          onChange={e => setVal(e.target.value)}
          rows={2}
          placeholder={field.default?.toString() || ""}
        />
      );
    }

    if (field.type === "number") {
      return (
        <Input
          value={value}
          onChange={e => setVal(e.target.value === "" ? "" : Number(e.target.value))}
          type="number"
          placeholder={field.default?.toString() || ""}
        />
      );
    }

    if (field.type === "select") {
      const options = field.options || [];
      const labels = field.option_labels || {};
      return (
        <Select value={safeValue} onValueChange={v => setVal(v)}>
          <SelectTrigger>
            <SelectValue placeholder={field.default ? labels[field.default] || field.default : "Selecionar..."} />
          </SelectTrigger>
          <SelectContent>
            {options.map(opt => (
              <SelectItem key={opt} value={opt}>{labels[opt] || opt}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }

    if (field.type === "select_status") {
      // workflow-statuses pode ter {id, name} ou {name} — usar name como
      // value e label (o backend compara por string de status).
      return (
        <Select value={safeValue} onValueChange={v => setVal(v)}>
          <SelectTrigger>
            <SelectValue placeholder="Selecionar estado..." />
          </SelectTrigger>
          <SelectContent>
            {workflowStatuses.map((s, i) => {
              const val = s.name || s.id || s;
              const label = s.label || s.name || s;
              return <SelectItem key={s.id || i} value={val}>{label}</SelectItem>;
            })}
          </SelectContent>
        </Select>
      );
    }

    if (field.type === "select_role") {
      return (
        <Select value={safeValue} onValueChange={v => setVal(v)}>
          <SelectTrigger>
            <SelectValue placeholder="Selecionar role..." />
          </SelectTrigger>
          <SelectContent>
            {INTERNAL_ROLES.map(r => (
              <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }

    if (field.type === "select_user") {
      return (
        <Select value={safeValue} onValueChange={v => setVal(v)}>
          <SelectTrigger>
            <SelectValue placeholder="Selecionar utilizador..." />
          </SelectTrigger>
          <SelectContent>
            {users.map(u => (
              <SelectItem key={u.id} value={u.id}>{u.name} ({u.email})</SelectItem>
            ))}
          </SelectContent>
        </Select>
      );
    }

    if (field.type === "select_email_template") {
      // Sem endpoint de templates ainda — mostrar input de texto como
      // fallback transitório. Quando houver endpoint, substituir por Select.
      return (
        <Input
          value={value}
          onChange={e => setVal(e.target.value)}
          placeholder="ID do template (ex: welcome_email)"
        />
      );
    }

    // Default: text
    return (
      <Input
        value={value}
        onChange={e => setVal(e.target.value)}
        type="text"
        placeholder={field.default?.toString() || ""}
      />
    );
  };

  if (loading) {
    const loadingContent = (
      <div className="space-y-6">
        <div className="h-7 w-56 bg-muted animate-pulse rounded" />
        <div className="space-y-3">
          {[1,2,3].map(i => <div key={i} className="h-20 bg-muted animate-pulse rounded-lg" />)}
        </div>
      </div>
    );
    return embedded ? loadingContent : <DashboardLayout>{loadingContent}</DashboardLayout>;
  }

  const pageContent = (
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
              <DialogDescription className="sr-only">
                {editingRule ? "Editar uma regra de automação existente" : "Criar uma nova regra de automação"}
              </DialogDescription>
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
                {/* Trigger config fields — Pacote D: renderiza Selects
                    para select_status/select_role/select_user em vez de
                    inputs de texto em bruto. */}
                {selectedTrigger?.config_fields?.map(field => (
                  <div key={field.key}>
                    <Label className="text-xs">{field.label}</Label>
                    {renderConfigField(field, "trigger_config")}
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
                {/* Action config fields — Pacote D: renderiza Selects
                    para select/select_status/select_role/select_user.
                    Ex: "Criar tarefa: [Input: título], urgência: [Select],
                    atribuída a [Select: role]". */}
                {selectedAction?.config_fields?.map(field => (
                  <div key={field.key}>
                    <Label className="text-xs">{field.label}</Label>
                    {renderConfigField(field, "action_config")}
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
  );

  return embedded ? pageContent : <DashboardLayout>{pageContent}</DashboardLayout>;
};

export default AutomationPage;
