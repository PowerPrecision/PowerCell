/**
 * O22 - Página de Automação de Workflows "No-Code"
 * Pacote H — Construtor visual If/Then opinionado para CEO.
 *
 * O CEO não vê nem toca em JSON. A interface apresenta dois blocos
 * visuais claros:
 *   1. SE  — "Quando um processo transitar para a fase..." → Select
 *   2. ENTÃO — "O sistema deve criar uma tarefa" com:
 *        Título, Atribuir a (role), Urgência, Prazo (dias)
 *
 * O trigger é fixo (process_status_changed) e a ação é fixa
 * (create_task). O handleSave() compila as seleções visuais no
 * payload exato que POST /api/admin/automation/rules espera,
 * fazendo a ponte invisível para o utilizador.
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
  Zap, Plus, Trash2, Edit2,
  ArrowRight, ChevronRight
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Labels para os badges da lista de regras (suporta todos os tipos
// históricos — regras antigas de outros tipos continuam a aparecer).
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

// Roles disponíveis para atribuição de tarefa no builder visual.
// Alinhado com as roles que o motor de automação resolve no backend.
const TASK_ROLES = [
  { value: "consultor", label: "Consultor" },
  { value: "intermediario", label: "Intermediário" },
  { value: "mediador", label: "Mediador" },
  { value: "indexacao", label: "Indexação" },
];

const URGENCY_OPTIONS = [
  { value: "low", label: "Baixa" },
  { value: "medium", label: "Média" },
  { value: "high", label: "Alta" },
];

const AutomationPage = ({ embedded = false }) => {
  const { token } = useAuth();
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [editingRule, setEditingRule] = useState(null);
  // Fases do workflow para popular o Select do bloco IF.
  const [workflowStatuses, setWorkflowStatuses] = useState([]);

  // Estado do formulário — campos amigáveis para o CEO (não há JSON).
  const [form, setForm] = useState({
    name: "",
    description: "",
    // IF — fase que dispara a automação
    targetStatus: "",
    // THEN — detalhes da tarefa a criar
    taskTitle: "",
    taskRole: "",
    taskUrgency: "medium",
    taskDueDays: 2,
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

  // Busca as fases do workflow para o Select do bloco IF.
  // O endpoint /admin/workflow-statuses devolve objetos com
  // {name, label, order, ...}. Usamos name como value (é o que o
  // motor compara) e label como texto visível.
  const fetchWorkflowStatuses = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/admin/workflow-statuses`, { headers }).catch(() => null);
      if (res && res.ok) {
        const data = await res.json();
        const arr = Array.isArray(data) ? data : (data.statuses || data || []);
        setWorkflowStatuses(arr);
      }
    } catch { /* silent — o Select aparece vazio se falhar */ }
  }, [token]);

  useEffect(() => {
    fetchRules();
    fetchWorkflowStatuses();
  }, [fetchRules, fetchWorkflowStatuses]);

  // ================================================================
  // handleSave — compila as seleções visuais no payload exato que o
  // POST /api/admin/automation/rules espera. Ponte invisível.
  //   trigger: "process_status_changed" (fixo)
  //   trigger_config: { target_status: <workflow_status.name> }
  //   action: "create_task" (fixo)
  //   action_config: { title, urgency, assigned_role, due_in_days }
  // ================================================================
  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error("Indica um nome para a regra.");
      return;
    }
    if (!form.targetStatus) {
      toast.error("Escolhe a fase que dispara a automação (bloco SE).");
      return;
    }
    if (!form.taskTitle.trim()) {
      toast.error("Indica o título da tarefa (bloco ENTÃO).");
      return;
    }
    if (!form.taskRole) {
      toast.error("Escolhe a quem atribuir a tarefa.");
      return;
    }

    const payload = {
      name: form.name.trim(),
      description: form.description.trim(),
      trigger: "process_status_changed",
      trigger_config: { target_status: form.targetStatus },
      action: "create_task",
      action_config: {
        title: form.taskTitle.trim(),
        urgency: form.taskUrgency,
        assigned_role: form.taskRole,
        due_in_days: Number(form.taskDueDays) || 7,
      },
      is_active: form.is_active,
    };

    try {
      const url = editingRule
        ? `${API_URL}/api/admin/automation/rules/${editingRule.id}`
        : `${API_URL}/api/admin/automation/rules`;
      const method = editingRule ? "PUT" : "POST";

      const res = await fetch(url, { method, headers, body: JSON.stringify(payload) });
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

  // ================================================================
  // openEdit — reverse-compile: lê o payload do backend e traduz
  // para os campos amigáveis do formulário visual.
  // Se a regra não seguir o padrão opinionado (outro trigger/action),
  // mostra um aviso e prepara o formulário para conversão ao guardar.
  // ================================================================
  const openEdit = (rule) => {
    setEditingRule(rule);
    const isOpinionated =
      rule.trigger === "process_status_changed" && rule.action === "create_task";

    setForm({
      name: rule.name || "",
      description: rule.description || "",
      targetStatus: rule.trigger_config?.target_status || "",
      taskTitle: rule.action_config?.title || "",
      taskRole: rule.action_config?.assigned_role || "",
      taskUrgency: rule.action_config?.urgency || "medium",
      taskDueDays: rule.action_config?.due_in_days ?? 2,
      is_active: rule.is_active ?? true,
    });

    if (!isOpinionated) {
      toast.info(
        "Esta regra usa um tipo diferente. Ao guardar será convertida para o construtor visual (Se fase → Criar tarefa)."
      );
    }
    setShowDialog(true);
  };

  const resetForm = () => {
    setForm({
      name: "",
      description: "",
      targetStatus: "",
      taskTitle: "",
      taskRole: "",
      taskUrgency: "medium",
      taskDueDays: 2,
      is_active: true,
    });
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

        {/* ================================================================
            Create/Edit Dialog — Construtor Visual If/Then (Pacote H)
            Dois blocos: SE (fase) → ENTÃO (criar tarefa). Sem JSON.
           ================================================================ */}
        <Dialog open={showDialog} onOpenChange={setShowDialog}>
          <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto" data-testid="rule-dialog">
            <DialogHeader>
              <DialogTitle>{editingRule ? "Editar Regra" : "Nova Regra de Automacao"}</DialogTitle>
              <DialogDescription className="sr-only">
                {editingRule ? "Editar uma regra de automação existente" : "Criar uma nova regra de automação"}
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4">
              {/* Nome + Descrição */}
              <div>
                <Label>Nome da Regra *</Label>
                <Input
                  value={form.name}
                  onChange={e => setForm({ ...form, name: e.target.value })}
                  placeholder="Ex: Contactar cliente ao entrar em Análise Bancária"
                  data-testid="rule-name-input"
                />
              </div>
              <div>
                <Label>Descrição (opcional)</Label>
                <Input
                  value={form.description}
                  onChange={e => setForm({ ...form, description: e.target.value })}
                  placeholder="Breve explicação do objetivo desta automação"
                />
              </div>

              {/* ============================================================
                  BLOCO 1 — IF (Gatilho)
                  "Quando um processo transitar para a fase..." → Select.
                  Trigger fixo: process_status_changed.
                 ============================================================ */}
              <Card className="border-blue-200 bg-blue-50/60 dark:bg-blue-950/20 dark:border-blue-900">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <span className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-600 text-white text-xs font-bold">
                      1
                    </span>
                    <CardTitle className="text-base text-blue-700 dark:text-blue-300">
                      SE — Quando acontece isto…
                    </CardTitle>
                  </div>
                  <CardDescription className="text-blue-700/70 dark:text-blue-300/70">
                    Escolhe a fase do processo que vai disparar esta automação.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Label className="text-sm font-medium">
                    Quando um processo transitar para a fase…
                  </Label>
                  <Select
                    value={form.targetStatus}
                    onValueChange={v => setForm({ ...form, targetStatus: v })}
                  >
                    <SelectTrigger data-testid="if-status-select">
                      <SelectValue placeholder="Selecionar fase do workflow…" />
                    </SelectTrigger>
                    <SelectContent>
                      {workflowStatuses.map((s, i) => {
                        const val = s.name || s.id || s;
                        const label = s.label || s.name || s;
                        return <SelectItem key={s.id || i} value={val}>{label}</SelectItem>;
                      })}
                    </SelectContent>
                  </Select>
                  {form.targetStatus && (
                    <p className="text-xs text-muted-foreground">
                      A automação dispara sempre que um processo entrar em{" "}
                      <strong>
                        {workflowStatuses.find(s => (s.name || s.id) === form.targetStatus)?.label || form.targetStatus}
                      </strong>.
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Seta descendente entre os dois blocos */}
              <div className="flex justify-center" aria-hidden="true">
                <ChevronRight className="h-5 w-5 text-muted-foreground rotate-90" />
              </div>

              {/* ============================================================
                  BLOCO 2 — THEN (Ação)
                  Ação fixa: "Criar Tarefa Automática". O CEO só preenche
                  os detalhes: Título, Atribuir a, Urgência, Prazo.
                 ============================================================ */}
              <Card className="border-green-200 bg-green-50/60 dark:bg-green-950/20 dark:border-green-900">
                <CardHeader className="pb-3">
                  <div className="flex items-center gap-2">
                    <span className="flex h-7 w-7 items-center justify-center rounded-md bg-green-600 text-white text-xs font-bold">
                      2
                    </span>
                    <CardTitle className="text-base text-green-700 dark:text-green-300">
                      ENTÃO — O sistema deve fazer o seguinte…
                    </CardTitle>
                  </div>
                  <CardDescription className="text-green-700/70 dark:text-green-300/70">
                    É criada automaticamente uma tarefa com os detalhes abaixo.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* Badge fixa — o CEO vê que a ação é "Criar Tarefa",
                      sem poder escolher outro tipo de ação. */}
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="gap-1">
                      <Zap className="h-3 w-3" /> Criar Tarefa Automática
                    </Badge>
                  </div>

                  {/* Título da tarefa */}
                  <div className="space-y-1.5">
                    <Label className="text-sm font-medium">Título da tarefa *</Label>
                    <Input
                      value={form.taskTitle}
                      onChange={e => setForm({ ...form, taskTitle: e.target.value })}
                      placeholder="Ex: Ligar ao Cliente"
                      data-testid="then-task-title"
                    />
                    <p className="text-xs text-muted-foreground">
                      Podes usar <code className="text-[10px]">{'{client_name}'}</code> e{" "}
                      <code className="text-[10px]">{'{status}'}</code> para preencher automaticamente.
                    </p>
                  </div>

                  {/* Atribuir a (role) */}
                  <div className="space-y-1.5">
                    <Label className="text-sm font-medium">Atribuir a *</Label>
                    <Select
                      value={form.taskRole}
                      onValueChange={v => setForm({ ...form, taskRole: v })}
                    >
                      <SelectTrigger data-testid="then-task-role">
                        <SelectValue placeholder="Selecionar responsável…" />
                      </SelectTrigger>
                      <SelectContent>
                        {TASK_ROLES.map(r => (
                          <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  {/* Urgência + Prazo (lado a lado no desktop) */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <Label className="text-sm font-medium">Urgência</Label>
                      <Select
                        value={form.taskUrgency}
                        onValueChange={v => setForm({ ...form, taskUrgency: v })}
                      >
                        <SelectTrigger data-testid="then-task-urgency">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {URGENCY_OPTIONS.map(u => (
                            <SelectItem key={u.value} value={u.value}>{u.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-sm font-medium">Prazo (dias)</Label>
                      <Input
                        type="number"
                        min={1}
                        value={form.taskDueDays}
                        onChange={e =>
                          setForm({ ...form, taskDueDays: e.target.value === "" ? "" : Number(e.target.value) })
                        }
                        placeholder="Ex: 2"
                        data-testid="then-task-due-days"
                      />
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Toggle ativa */}
              <div className="flex items-center justify-between rounded-lg border p-3">
                <div>
                  <Label className="text-sm font-medium">Regra ativa</Label>
                  <p className="text-xs text-muted-foreground">Se inativa, a automação não executa.</p>
                </div>
                <Switch
                  checked={form.is_active}
                  onCheckedChange={v => setForm({ ...form, is_active: v })}
                />
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => { setShowDialog(false); setEditingRule(null); }}>Cancelar</Button>
              <Button onClick={handleSave} data-testid="save-rule-btn">
                {editingRule ? "Guardar Alterações" : "Guardar Regra"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
  );

  return embedded ? pageContent : <DashboardLayout>{pageContent}</DashboardLayout>;
};

export default AutomationPage;
