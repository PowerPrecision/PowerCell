/**
 * ====================================================================
 * PÁGINA DE CONFIGURAÇÃO DE IA - CREDITOIMO (V2)
 * ====================================================================
 * Permite ao admin configurar:
 * - Modelos de IA disponíveis (adicionar/editar/remover)
 * - Tarefas de IA (adicionar/editar/remover)
 * - Qual modelo usar para cada tarefa
 * - Configurações de cache e notificações
 * ====================================================================
 */

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Label } from "../components/ui/label";
import { Input } from "../components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import { Separator } from "../components/ui/separator";
import { Switch } from "../components/ui/switch";
import { toast } from "sonner";
import {
  Sparkles,
  Bot,
  FileSearch,
  FileText,
  BarChart3,
  AlertTriangle,
  Save,
  Loader2,
  RefreshCw,
  Trash2,
  Database,
  Zap,
  DollarSign,
  CheckCircle,
  Info,
  Plus,
  Pencil,
  Settings2,
  Bell,
  X,
  TrendingUp,
  Activity,
  Clock,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Ícones por tarefa
const TASK_ICONS = {
  scraper_extraction: FileSearch,
  document_analysis: FileText,
  weekly_report: BarChart3,
  error_analysis: AlertTriangle,
};

// Cores por provider
const PROVIDER_COLORS = {
  gemini: "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  openai: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200",
  anthropic: "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
};

const AIConfigPage = () => {
  const { token } = useAuth();
  
  // Estado da configuração
  const [config, setConfig] = useState({});
  const [defaults, setDefaults] = useState({});
  const [availableModels, setAvailableModels] = useState({});
  const [taskDescriptions, setTaskDescriptions] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  
  // Estado dos modelos e tarefas
  const [models, setModels] = useState([]);
  const [tasks, setTasks] = useState([]);
  const [loadingModels, setLoadingModels] = useState(false);
  const [loadingTasks, setLoadingTasks] = useState(false);
  
  // Estado do cache
  const [cacheStats, setCacheStats] = useState(null);
  const [cacheSettings, setCacheSettings] = useState({ cache_limit: 1000, notify_at_percentage: 80 });
  const [clearingCache, setClearingCache] = useState(false);
  
  // Estado do uso de IA
  const [usageSummary, setUsageSummary] = useState(null);
  const [usageByTask, setUsageByTask] = useState([]);
  const [usageByModel, setUsageByModel] = useState([]);
  const [usageTrend, setUsageTrend] = useState([]);
  const [usagePeriod, setUsagePeriod] = useState("month");
  const [loadingUsage, setLoadingUsage] = useState(false);
  
  // Diálogos
  const [showModelDialog, setShowModelDialog] = useState(false);
  const [showTaskDialog, setShowTaskDialog] = useState(false);
  const [editingModel, setEditingModel] = useState(null);
  const [editingTask, setEditingTask] = useState(null);
  
  // Form states
  const [modelForm, setModelForm] = useState({ key: "", name: "", provider: "openai", cost_per_1k_tokens: 0.001, best_for: "" });
  const [taskForm, setTaskForm] = useState({ key: "", description: "", default_model: "gpt-4o-mini" });

  // Carregar configuração
  const loadConfig = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/ai-config`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (response.ok) {
        const data = await response.json();
        setConfig(data.current_config || {});
        setDefaults(data.defaults || {});
        setAvailableModels(data.available_models || {});
        setTaskDescriptions(data.task_descriptions || {});
        if (data.cache_settings) {
          setCacheSettings(data.cache_settings);
        }
      } else {
        toast.error("Erro ao carregar configuração de IA");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro de conexão");
    } finally {
      setLoading(false);
    }
  }, [token]);

  // Carregar modelos
  const loadModels = useCallback(async () => {
    setLoadingModels(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/ai-models`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setModels(data.models || []);
      }
    } catch (error) {
      console.error("Erro ao carregar modelos:", error);
    } finally {
      setLoadingModels(false);
    }
  }, [token]);

  // Carregar tarefas
  const loadTasks = useCallback(async () => {
    setLoadingTasks(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/ai-tasks`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setTasks(data.tasks || []);
      }
    } catch (error) {
      console.error("Erro ao carregar tarefas:", error);
    } finally {
      setLoadingTasks(false);
    }
  }, [token]);

  // Carregar estatísticas do cache
  const loadCacheStats = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/scraper/cache/stats`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (response.ok) {
        const data = await response.json();
        setCacheStats(data);
        
        // Mostrar notificação se necessário
        if (data.notification) {
          toast.warning(data.notification.message);
        }
      }
    } catch (error) {
      console.error("Erro ao carregar cache stats:", error);
    }
  }, [token]);

  // Carregar estatísticas de uso de IA
  const loadUsageStats = useCallback(async (period = usagePeriod) => {
    setLoadingUsage(true);
    try {
      const [summaryRes, byTaskRes, byModelRes, trendRes] = await Promise.all([
        fetch(`${API_URL}/api/admin/ai-usage/summary?period=${period}`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_URL}/api/admin/ai-usage/by-task?period=${period}`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_URL}/api/admin/ai-usage/by-model?period=${period}`, { headers: { Authorization: `Bearer ${token}` } }),
        fetch(`${API_URL}/api/admin/ai-usage/trend?days=30`, { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      
      if (summaryRes.ok) setUsageSummary(await summaryRes.json());
      if (byTaskRes.ok) setUsageByTask(await byTaskRes.json());
      if (byModelRes.ok) setUsageByModel(await byModelRes.json());
      if (trendRes.ok) setUsageTrend(await trendRes.json());
    } catch (error) {
      console.error("Erro ao carregar uso de IA:", error);
    } finally {
      setLoadingUsage(false);
    }
  }, [token, usagePeriod]);

  useEffect(() => {
    loadConfig();
    loadModels();
    loadTasks();
    loadCacheStats();
    loadUsageStats();
  }, [loadConfig, loadModels, loadTasks, loadCacheStats, loadUsageStats]);

  // Alterar modelo para uma tarefa
  const handleModelChange = (task, model) => {
    setConfig(prev => ({ ...prev, [task]: model }));
    setHasChanges(true);
  };

  // Guardar configuração
  const handleSave = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/ai-config`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(config),
      });
      
      if (response.ok) {
        toast.success("Configuração de IA guardada com sucesso");
        setHasChanges(false);
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao guardar configuração");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro de conexão");
    } finally {
      setSaving(false);
    }
  };

  // Restaurar defaults
  const handleRestoreDefaults = () => {
    setConfig({ ...defaults });
    setHasChanges(true);
    toast.info("Valores por defeito restaurados. Clique em Guardar para aplicar.");
  };

  // CRUD de Modelos
  const handleSaveModel = async () => {
    const url = editingModel 
      ? `${API_URL}/api/admin/ai-models/${editingModel.key}`
      : `${API_URL}/api/admin/ai-models`;
    
    const method = editingModel ? "PUT" : "POST";
    
    const payload = {
      ...modelForm,
      best_for: modelForm.best_for.split(",").map(s => s.trim()).filter(s => s)
    };
    
    try {
      const response = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      
      if (response.ok) {
        toast.success(editingModel ? "Modelo actualizado" : "Modelo adicionado");
        setShowModelDialog(false);
        setEditingModel(null);
        setModelForm({ key: "", name: "", provider: "openai", cost_per_1k_tokens: 0.001, best_for: "" });
        loadModels();
        loadConfig();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao guardar modelo");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    }
  };

  const handleDeleteModel = async (modelKey) => {
    if (!window.confirm(`Eliminar modelo "${modelKey}"?`)) return;
    
    try {
      const response = await fetch(`${API_URL}/api/admin/ai-models/${modelKey}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (response.ok) {
        toast.success("Modelo eliminado");
        loadModels();
        loadConfig();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao eliminar modelo");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    }
  };

  // CRUD de Tarefas
  const handleSaveTask = async () => {
    const url = editingTask 
      ? `${API_URL}/api/admin/ai-tasks/${editingTask.key}`
      : `${API_URL}/api/admin/ai-tasks`;
    
    const method = editingTask ? "PUT" : "POST";
    
    try {
      const response = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(taskForm),
      });
      
      if (response.ok) {
        toast.success(editingTask ? "Tarefa actualizada" : "Tarefa adicionada");
        setShowTaskDialog(false);
        setEditingTask(null);
        setTaskForm({ key: "", description: "", default_model: "gpt-4o-mini" });
        loadTasks();
        loadConfig();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao guardar tarefa");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    }
  };

  const handleDeleteTask = async (taskKey) => {
    if (!window.confirm(`Eliminar tarefa "${taskKey}"?`)) return;
    
    try {
      const response = await fetch(`${API_URL}/api/admin/ai-tasks/${taskKey}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (response.ok) {
        toast.success("Tarefa eliminada");
        loadTasks();
        loadConfig();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao eliminar tarefa");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    }
  };

  // Guardar configurações de cache
  const handleSaveCacheSettings = async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/cache-settings`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(cacheSettings),
      });
      
      if (response.ok) {
        toast.success("Configurações de cache guardadas");
      } else {
        toast.error("Erro ao guardar configurações");
      }
    } catch (error) {
      toast.error("Erro de conexão");
    }
  };

  // Limpar cache
  const handleClearCache = async () => {
    setClearingCache(true);
    try {
      const response = await fetch(`${API_URL}/api/scraper/cache/clear`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });
      
      if (response.ok) {
        const data = await response.json();
        toast.success(`Cache limpo: ${data.deleted_count} registos eliminados`);
        loadCacheStats();
      } else {
        toast.error("Erro ao limpar cache");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro de conexão");
    } finally {
      setClearingCache(false);
    }
  };

  // Editar modelo
  const startEditModel = (model) => {
    setEditingModel(model);
    setModelForm({
      key: model.key,
      name: model.name,
      provider: model.provider,
      cost_per_1k_tokens: model.cost_per_1k_tokens || 0.001,
      best_for: (model.best_for || []).join(", ")
    });
    setShowModelDialog(true);
  };

  // Editar tarefa
  const startEditTask = (task) => {
    setEditingTask(task);
    setTaskForm({
      key: task.key,
      description: task.description,
      default_model: task.default_model || "gpt-4o-mini"
    });
    setShowTaskDialog(true);
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-96">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="ai-config-page">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Sparkles className="h-6 w-6 text-primary" />
              Configuração de IA
            </h1>
            <p className="text-muted-foreground mt-1">
              Configure modelos, tarefas e cache do sistema de IA
            </p>
          </div>
          
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={handleRestoreDefaults}
              disabled={saving}
              data-testid="restore-defaults-btn"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Restaurar Defeitos
            </Button>
            <Button
              onClick={handleSave}
              disabled={!hasChanges || saving}
              data-testid="save-ai-config-btn"
            >
              {saving ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Save className="h-4 w-4 mr-2" />
              )}
              Guardar Alterações
            </Button>
          </div>
        </div>

        {/* Notificação de cache */}
        {cacheStats?.notification && (
          <Card className="bg-amber-50 dark:bg-amber-950 border-amber-200 dark:border-amber-800">
            <CardContent className="pt-4">
              <div className="flex items-start gap-3">
                <Bell className="h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="font-medium text-amber-800 dark:text-amber-200">
                    {cacheStats.notification.message}
                  </p>
                  <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                    {cacheStats.notification.action}
                  </p>
                </div>
                <Button variant="outline" size="sm" onClick={handleClearCache}>
                  Limpar Agora
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        <Tabs defaultValue="tasks" className="space-y-4">
          <TabsList>
            <TabsTrigger value="tasks" className="flex items-center gap-2">
              <Settings2 className="h-4 w-4" />
              Configuração de Tarefas
            </TabsTrigger>
            <TabsTrigger value="models" className="flex items-center gap-2">
              <Bot className="h-4 w-4" />
              Modelos de IA
            </TabsTrigger>
            <TabsTrigger value="usage" className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4" />
              Uso & Custos
            </TabsTrigger>
            <TabsTrigger value="cache" className="flex items-center gap-2">
              <Database className="h-4 w-4" />
              Cache & Notificações
            </TabsTrigger>
          </TabsList>

          {/* TAB: Configuração de Tarefas */}
          <TabsContent value="tasks" className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Configure qual modelo de IA usar para cada tarefa do sistema
              </p>
              <Dialog open={showTaskDialog} onOpenChange={setShowTaskDialog}>
                <DialogTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEditingTask(null);
                      setTaskForm({ key: "", description: "", default_model: "gpt-4o-mini" });
                    }}
                    data-testid="add-task-btn"
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Nova Tarefa
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{editingTask ? "Editar Tarefa" : "Nova Tarefa de IA"}</DialogTitle>
                    <DialogDescription>
                      Adicione uma nova tarefa que pode ser processada por IA
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label>Identificador (key)</Label>
                      <Input
                        value={taskForm.key}
                        onChange={(e) => setTaskForm(p => ({ ...p, key: e.target.value }))}
                        placeholder="ex: lead_scoring"
                        disabled={!!editingTask}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Descrição</Label>
                      <Input
                        value={taskForm.description}
                        onChange={(e) => setTaskForm(p => ({ ...p, description: e.target.value }))}
                        placeholder="ex: Pontuação automática de leads"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Modelo Padrão</Label>
                      <Select
                        value={taskForm.default_model}
                        onValueChange={(v) => setTaskForm(p => ({ ...p, default_model: v }))}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {models.map((m) => (
                            <SelectItem key={m.key} value={m.key}>{m.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setShowTaskDialog(false)}>
                      Cancelar
                    </Button>
                    <Button onClick={handleSaveTask}>
                      {editingTask ? "Actualizar" : "Adicionar"}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              {Object.entries(taskDescriptions).map(([task, description]) => {
                const TaskIcon = TASK_ICONS[task] || Bot;
                const currentModel = config[task] || defaults[task];
                const modelInfo = availableModels[currentModel] || {};
                const taskData = tasks.find(t => t.key === task);
                
                return (
                  <Card key={task} data-testid={`ai-task-card-${task}`}>
                    <CardHeader className="pb-3">
                      <div className="flex items-center justify-between">
                        <CardTitle className="flex items-center gap-2 text-base">
                          <TaskIcon className="h-5 w-5 text-primary" />
                          {description}
                        </CardTitle>
                        <div className="flex items-center gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() => startEditTask(taskData || { key: task, description })}
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          {taskData && !taskData.is_default && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-7 w-7 text-destructive"
                              onClick={() => handleDeleteTask(task)}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="space-y-2">
                        <Label>Modelo de IA</Label>
                        <Select
                          value={currentModel}
                          onValueChange={(value) => handleModelChange(task, value)}
                        >
                          <SelectTrigger data-testid={`select-model-${task}`}>
                            <SelectValue placeholder="Seleccione um modelo" />
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(availableModels).map(([key, model]) => (
                              <SelectItem key={key} value={key}>
                                <div className="flex items-center gap-2">
                                  <span>{model.name}</span>
                                  <Badge variant="outline" className="text-xs">
                                    {model.provider}
                                  </Badge>
                                </div>
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      
                      {modelInfo && (
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <Badge className={PROVIDER_COLORS[modelInfo.provider] || "bg-gray-100"}>
                            {modelInfo.provider?.toUpperCase()}
                          </Badge>
                          <span className="text-muted-foreground flex items-center gap-1">
                            <DollarSign className="h-3 w-3" />
                            {modelInfo.cost_per_1k_tokens?.toFixed(4)}€/1k tokens
                          </span>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          </TabsContent>

          {/* TAB: Modelos de IA */}
          <TabsContent value="models" className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Gerencie os modelos de IA disponíveis no sistema
              </p>
              <Dialog open={showModelDialog} onOpenChange={setShowModelDialog}>
                <DialogTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEditingModel(null);
                      setModelForm({ key: "", name: "", provider: "openai", cost_per_1k_tokens: 0.001, best_for: "" });
                    }}
                    data-testid="add-model-btn"
                  >
                    <Plus className="h-4 w-4 mr-2" />
                    Novo Modelo
                  </Button>
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{editingModel ? "Editar Modelo" : "Novo Modelo de IA"}</DialogTitle>
                    <DialogDescription>
                      Adicione um novo modelo de IA ao sistema
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-4">
                    <div className="space-y-2">
                      <Label>Identificador (key)</Label>
                      <Input
                        value={modelForm.key}
                        onChange={(e) => setModelForm(p => ({ ...p, key: e.target.value }))}
                        placeholder="ex: claude-3-sonnet"
                        disabled={!!editingModel}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Nome de Exibição</Label>
                      <Input
                        value={modelForm.name}
                        onChange={(e) => setModelForm(p => ({ ...p, name: e.target.value }))}
                        placeholder="ex: Claude 3 Sonnet"
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Provider</Label>
                      <Select
                        value={modelForm.provider}
                        onValueChange={(v) => setModelForm(p => ({ ...p, provider: v }))}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="openai">OpenAI</SelectItem>
                          <SelectItem value="gemini">Google Gemini</SelectItem>
                          <SelectItem value="anthropic">Anthropic</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label>Custo por 1k tokens (€)</Label>
                      <Input
                        type="number"
                        step="0.0001"
                        value={modelForm.cost_per_1k_tokens}
                        onChange={(e) => setModelForm(p => ({ ...p, cost_per_1k_tokens: parseFloat(e.target.value) }))}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Melhor Para (separado por vírgulas)</Label>
                      <Input
                        value={modelForm.best_for}
                        onChange={(e) => setModelForm(p => ({ ...p, best_for: e.target.value }))}
                        placeholder="ex: analysis, coding, documents"
                      />
                    </div>
                  </div>
                  <DialogFooter>
                    <Button variant="outline" onClick={() => setShowModelDialog(false)}>
                      Cancelar
                    </Button>
                    <Button onClick={handleSaveModel}>
                      {editingModel ? "Actualizar" : "Adicionar"}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            </div>

            {loadingModels ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {models.map((model) => (
                  <Card key={model.key} data-testid={`model-card-${model.key}`}>
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between">
                        <CardTitle className="text-base">{model.name}</CardTitle>
                        <div className="flex items-center gap-1">
                          <Badge className={PROVIDER_COLORS[model.provider] || "bg-gray-100"}>
                            {model.provider?.toUpperCase()}
                          </Badge>
                          {model.is_default && (
                            <Badge variant="secondary" className="text-xs">Padrão</Badge>
                          )}
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2 text-sm text-muted-foreground">
                        <p className="flex items-center gap-1">
                          <DollarSign className="h-3 w-3" />
                          {model.cost_per_1k_tokens?.toFixed(4)}€ / 1k tokens
                        </p>
                        <p className="flex items-center gap-1">
                          <Zap className="h-3 w-3" />
                          Melhor para: {(model.best_for || []).join(", ") || "-"}
                        </p>
                        <p className="text-xs font-mono text-muted-foreground/60">
                          Key: {model.key}
                        </p>
                      </div>
                      <Separator className="my-3" />
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          className="flex-1"
                          onClick={() => startEditModel(model)}
                        >
                          <Pencil className="h-3.5 w-3.5 mr-1" />
                          Editar
                        </Button>
                        {!model.is_default && (
                          <Button
                            variant="destructive"
                            size="sm"
                            onClick={() => handleDeleteModel(model.key)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          {/* TAB: Uso & Custos */}
          <TabsContent value="usage" className="space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Acompanhe o uso de IA e custos estimados por período
              </p>
              <div className="flex items-center gap-2">
                <Select value={usagePeriod} onValueChange={(v) => { setUsagePeriod(v); loadUsageStats(v); }}>
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="today">Hoje</SelectItem>
                    <SelectItem value="week">Última Semana</SelectItem>
                    <SelectItem value="month">Este Mês</SelectItem>
                    <SelectItem value="all">Tudo</SelectItem>
                  </SelectContent>
                </Select>
                <Button variant="outline" size="sm" onClick={() => loadUsageStats()}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {loadingUsage ? (
              <div className="flex items-center justify-center h-32">
                <Loader2 className="h-6 w-6 animate-spin" />
              </div>
            ) : (
              <>
                {/* Summary Cards */}
                <div className="grid gap-4 md:grid-cols-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Total de Chamadas</CardDescription>
                      <CardTitle className="text-2xl flex items-center gap-2">
                        <Activity className="h-5 w-5 text-primary" />
                        {usageSummary?.total_calls || 0}
                      </CardTitle>
                    </CardHeader>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Tokens Consumidos</CardDescription>
                      <CardTitle className="text-2xl flex items-center gap-2">
                        <Zap className="h-5 w-5 text-amber-500" />
                        {(usageSummary?.total_tokens || 0).toLocaleString()}
                      </CardTitle>
                    </CardHeader>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Custo Estimado</CardDescription>
                      <CardTitle className="text-2xl flex items-center gap-2">
                        <DollarSign className="h-5 w-5 text-green-500" />
                        €{(usageSummary?.total_cost_eur || 0).toFixed(4)}
                      </CardTitle>
                    </CardHeader>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Taxa de Sucesso</CardDescription>
                      <CardTitle className="text-2xl flex items-center gap-2">
                        <CheckCircle className="h-5 w-5 text-emerald-500" />
                        {(usageSummary?.success_rate || 0).toFixed(1)}%
                      </CardTitle>
                    </CardHeader>
                  </Card>
                </div>

                {/* Usage by Task */}
                <div className="grid gap-4 md:grid-cols-2">
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base flex items-center gap-2">
                        <FileSearch className="h-4 w-4 text-primary" />
                        Uso por Tarefa
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {usageByTask.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-4">
                          Nenhum uso registado neste período
                        </p>
                      ) : (
                        <div className="space-y-3">
                          {usageByTask.map((item) => (
                            <div key={item.task} className="flex items-center justify-between">
                              <div>
                                <p className="font-medium text-sm">{item.task}</p>
                                <p className="text-xs text-muted-foreground">
                                  {item.total_calls} chamadas • {item.total_tokens.toLocaleString()} tokens
                                </p>
                              </div>
                              <Badge variant="outline">€{item.total_cost_eur.toFixed(4)}</Badge>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base flex items-center gap-2">
                        <Bot className="h-4 w-4 text-primary" />
                        Uso por Modelo
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      {usageByModel.length === 0 ? (
                        <p className="text-sm text-muted-foreground text-center py-4">
                          Nenhum uso registado neste período
                        </p>
                      ) : (
                        <div className="space-y-3">
                          {usageByModel.map((item) => (
                            <div key={item.model} className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <Badge className={PROVIDER_COLORS[item.provider] || "bg-gray-100"} variant="secondary">
                                  {item.provider?.toUpperCase()}
                                </Badge>
                                <div>
                                  <p className="font-medium text-sm">{item.model}</p>
                                  <p className="text-xs text-muted-foreground">
                                    {item.total_calls} chamadas
                                  </p>
                                </div>
                              </div>
                              <Badge variant="outline">€{item.total_cost_eur.toFixed(4)}</Badge>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </div>

                {/* Trend (if data exists) */}
                {usageTrend.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base flex items-center gap-2">
                        <TrendingUp className="h-4 w-4 text-primary" />
                        Tendência Diária (últimos 30 dias)
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="h-24 flex items-end gap-1">
                        {usageTrend.slice(-30).map((day, i) => {
                          const maxCalls = Math.max(...usageTrend.map(d => d.total_calls)) || 1;
                          const height = (day.total_calls / maxCalls) * 100;
                          return (
                            <div
                              key={day.date}
                              className="flex-1 bg-primary/20 hover:bg-primary/40 rounded-t transition-colors"
                              style={{ height: `${Math.max(height, 5)}%` }}
                              title={`${day.date}: ${day.total_calls} chamadas, €${day.total_cost_eur.toFixed(4)}`}
                            />
                          );
                        })}
                      </div>
                      <div className="flex justify-between text-xs text-muted-foreground mt-2">
                        <span>{usageTrend[0]?.date}</span>
                        <span>{usageTrend[usageTrend.length - 1]?.date}</span>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </TabsContent>

          {/* TAB: Cache & Notificações */}
          <TabsContent value="cache" className="space-y-4">
            {/* Cache Stats */}
            <Card data-testid="scraper-cache-card">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Database className="h-5 w-5 text-primary" />
                  Cache de Scraping
                </CardTitle>
                <CardDescription>
                  URLs já processadas são guardadas em cache por {cacheStats?.cache_expiry_days || 7} dias
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  {cacheStats ? (
                    <div className="space-y-2">
                      <div className="flex flex-wrap items-center gap-4">
                        <div className="flex items-center gap-2">
                          <CheckCircle className="h-4 w-4 text-green-500" />
                          <span className="text-sm">
                            <strong>{cacheStats.valid_entries}</strong> entradas válidas
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <AlertTriangle className="h-4 w-4 text-amber-500" />
                          <span className="text-sm">
                            <strong>{cacheStats.expired_entries}</strong> expiradas
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Database className="h-4 w-4 text-muted-foreground" />
                          <span className="text-sm">
                            <strong>{cacheStats.total_entries}</strong> / {cacheStats.cache_limit} total
                          </span>
                        </div>
                      </div>
                      {/* Progress bar */}
                      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                        <div 
                          className={`h-2 rounded-full ${
                            cacheStats.percentage_used >= 80 ? 'bg-red-500' :
                            cacheStats.percentage_used >= 50 ? 'bg-amber-500' : 'bg-green-500'
                          }`}
                          style={{ width: `${Math.min(cacheStats.percentage_used, 100)}%` }}
                        />
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {cacheStats.percentage_used}% utilizado
                      </p>
                    </div>
                  ) : (
                    <span className="text-sm text-muted-foreground">A carregar estatísticas...</span>
                  )}
                  
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={loadCacheStats}
                      data-testid="refresh-cache-stats-btn"
                    >
                      <RefreshCw className="h-4 w-4 mr-2" />
                      Actualizar
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={handleClearCache}
                      disabled={clearingCache || !cacheStats?.total_entries}
                      data-testid="clear-cache-btn"
                    >
                      {clearingCache ? (
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4 mr-2" />
                      )}
                      Limpar Cache
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Configurações de Notificação */}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Bell className="h-5 w-5 text-primary" />
                  Configurações de Notificação
                </CardTitle>
                <CardDescription>
                  Configure quando receber alertas sobre o cache
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label>Limite do Cache (entradas)</Label>
                    <Input
                      type="number"
                      value={cacheSettings.cache_limit}
                      onChange={(e) => setCacheSettings(p => ({ ...p, cache_limit: parseInt(e.target.value) }))}
                      placeholder="1000"
                    />
                    <p className="text-xs text-muted-foreground">
                      Número máximo de URLs em cache antes de alertar
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label>Notificar quando atingir (%)</Label>
                    <Input
                      type="number"
                      min="50"
                      max="100"
                      value={cacheSettings.notify_at_percentage}
                      onChange={(e) => setCacheSettings(p => ({ ...p, notify_at_percentage: parseInt(e.target.value) }))}
                      placeholder="80"
                    />
                    <p className="text-xs text-muted-foreground">
                      Percentagem do limite para enviar alerta
                    </p>
                  </div>
                </div>
                <Button onClick={handleSaveCacheSettings} data-testid="save-cache-settings-btn">
                  <Save className="h-4 w-4 mr-2" />
                  Guardar Configurações
                </Button>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </DashboardLayout>
  );
};

export default AIConfigPage;
