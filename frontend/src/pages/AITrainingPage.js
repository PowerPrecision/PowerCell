/**
 * AITrainingPage - Página de Treino do Agente IA
 * Permite configurar instruções personalizadas para o agente de análise de documentos
 */
import React, { useState, useEffect, useCallback } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Switch } from "../components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Textarea } from "../components/ui/textarea";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { toast } from "sonner";
import {
  Brain,
  Plus,
  Trash2,
  Save,
  Loader2,
  FileText,
  Users,
  Settings,
  Lightbulb,
  RefreshCw,
  Copy,
  Eye,
  Edit,
  CheckCircle,
  XCircle,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Categorias disponíveis
const CATEGORIES = [
  { value: "document_types", label: "Tipos de Documentos", icon: FileText, color: "blue" },
  { value: "field_mappings", label: "Mapeamento de Campos", icon: Settings, color: "green" },
  { value: "client_patterns", label: "Padrões de Clientes", icon: Users, color: "purple" },
  { value: "custom_rules", label: "Regras Personalizadas", icon: Settings, color: "orange" },
  { value: "extraction_tips", label: "Dicas de Extração", icon: Lightbulb, color: "yellow" },
];

// Componente de entrada de treino
const TrainingEntry = ({ entry, onEdit, onDelete, onToggle }) => {
  const category = CATEGORIES.find(c => c.value === entry.category);
  const Icon = category?.icon || FileText;
  
  return (
    <div className={`p-4 rounded-lg border ${entry.is_active ? 'bg-white dark:bg-gray-900' : 'bg-gray-50 dark:bg-gray-800/50 opacity-60'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className={`p-2 rounded-lg shrink-0 bg-${category?.color || 'gray'}-100 dark:bg-${category?.color || 'gray'}-900/30`}>
            <Icon className={`h-4 w-4 text-${category?.color || 'gray'}-600`} />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="font-medium text-sm truncate">{entry.title}</h4>
              <Badge variant="outline" className="text-xs">
                {category?.label || entry.category}
              </Badge>
              {!entry.is_active && (
                <Badge variant="secondary" className="text-xs">Inactivo</Badge>
              )}
            </div>
            <p className="text-sm text-muted-foreground mt-1 line-clamp-2">
              {entry.content}
            </p>
            {entry.examples && entry.examples.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {entry.examples.slice(0, 3).map((ex, i) => (
                  <Badge key={i} variant="outline" className="text-xs font-normal">
                    {ex}
                  </Badge>
                ))}
                {entry.examples.length > 3 && (
                  <Badge variant="outline" className="text-xs">
                    +{entry.examples.length - 3}
                  </Badge>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Switch
            checked={entry.is_active}
            onCheckedChange={() => onToggle(entry)}
            className="mr-2"
          />
          <Button variant="ghost" size="sm" onClick={() => onEdit(entry)}>
            <Edit className="h-4 w-4" />
          </Button>
          <Button 
            variant="ghost" 
            size="sm" 
            className="text-destructive hover:text-destructive"
            onClick={() => onDelete(entry)}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
};

const AITrainingPage = () => {
  const [entries, setEntries] = useState({});
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState("all");
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [isPromptDialogOpen, setIsPromptDialogOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generatedPrompt, setGeneratedPrompt] = useState("");
  const [editingEntry, setEditingEntry] = useState(null);
  const [formData, setFormData] = useState({
    category: "document_types",
    title: "",
    content: "",
    examples: "",
    is_active: true
  });

  const fetchEntries = useCallback(async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/admin/ai-training`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      if (response.ok) {
        const data = await response.json();
        setEntries(data.data || {});
      }
    } catch (error) {
      console.error("Erro ao carregar treino:", error);
      toast.error("Erro ao carregar dados de treino");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  const handleSave = async () => {
    if (!formData.title.trim() || !formData.content.trim()) {
      toast.error("Título e conteúdo são obrigatórios");
      return;
    }

    setSaving(true);
    try {
      const token = localStorage.getItem("token");
      const payload = {
        ...formData,
        examples: formData.examples.split("\n").filter(e => e.trim())
      };

      const url = editingEntry 
        ? `${API_URL}/api/admin/ai-training/${editingEntry.id}`
        : `${API_URL}/api/admin/ai-training`;
      
      const method = editingEntry ? "PUT" : "POST";

      const response = await fetch(url, {
        method,
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        toast.success(editingEntry ? "Entrada actualizada" : "Entrada adicionada");
        setIsDialogOpen(false);
        resetForm();
        fetchEntries();
      } else {
        const data = await response.json();
        toast.error(data.detail || "Erro ao guardar");
      }
    } catch (error) {
      toast.error("Erro ao guardar entrada");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (entry) => {
    if (!window.confirm(`Tem a certeza que deseja eliminar "${entry.title}"?`)) {
      return;
    }

    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/admin/ai-training/${entry.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.ok) {
        toast.success("Entrada eliminada");
        fetchEntries();
      }
    } catch (error) {
      toast.error("Erro ao eliminar");
    }
  };

  const handleToggle = async (entry) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/admin/ai-training/${entry.id}`, {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ is_active: !entry.is_active })
      });

      if (response.ok) {
        toast.success(entry.is_active ? "Entrada desactivada" : "Entrada activada");
        fetchEntries();
      }
    } catch (error) {
      toast.error("Erro ao actualizar");
    }
  };

  const handleEdit = (entry) => {
    setEditingEntry(entry);
    setFormData({
      category: entry.category,
      title: entry.title,
      content: entry.content,
      examples: (entry.examples || []).join("\n"),
      is_active: entry.is_active
    });
    setIsDialogOpen(true);
  };

  const resetForm = () => {
    setEditingEntry(null);
    setFormData({
      category: "document_types",
      title: "",
      content: "",
      examples: "",
      is_active: true
    });
  };

  const openCreateDialog = () => {
    resetForm();
    setIsDialogOpen(true);
  };

  const viewGeneratedPrompt = async () => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/admin/ai-training/prompt`, {
        headers: { Authorization: `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        setGeneratedPrompt(data.prompt || "Nenhuma entrada activa.");
        setIsPromptDialogOpen(true);
      }
    } catch (error) {
      toast.error("Erro ao gerar prompt");
    }
  };

  const copyPrompt = () => {
    navigator.clipboard.writeText(generatedPrompt);
    toast.success("Prompt copiado!");
  };

  // Filtrar entradas por categoria
  const getFilteredEntries = () => {
    if (activeCategory === "all") {
      return Object.values(entries).flat();
    }
    return entries[activeCategory] || [];
  };

  const filteredEntries = getFilteredEntries();
  const totalActive = Object.values(entries).flat().filter(e => e.is_active).length;
  const totalEntries = Object.values(entries).flat().length;

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Brain className="h-6 w-6" />
              Treino do Agente IA
            </h1>
            <p className="text-muted-foreground">
              Configure instruções personalizadas para o agente de análise de documentos
            </p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={fetchEntries}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Recarregar
            </Button>
            <Button variant="outline" onClick={viewGeneratedPrompt}>
              <Eye className="h-4 w-4 mr-2" />
              Ver Prompt
            </Button>
            <Button onClick={openCreateDialog} className="bg-teal-600 hover:bg-teal-700">
              <Plus className="h-4 w-4 mr-2" />
              Adicionar
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{totalEntries}</div>
              <p className="text-sm text-muted-foreground">Total de Entradas</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-green-600">{totalActive}</div>
              <p className="text-sm text-muted-foreground">Activas</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold text-gray-400">{totalEntries - totalActive}</div>
              <p className="text-sm text-muted-foreground">Inactivas</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-4">
              <div className="text-2xl font-bold">{Object.keys(entries).length}</div>
              <p className="text-sm text-muted-foreground">Categorias Usadas</p>
            </CardContent>
          </Card>
        </div>

        {/* Tabs por categoria */}
        <Tabs value={activeCategory} onValueChange={setActiveCategory}>
          <TabsList className="flex flex-wrap h-auto gap-1">
            <TabsTrigger value="all" className="gap-2">
              Todas ({totalEntries})
            </TabsTrigger>
            {CATEGORIES.map(cat => {
              const count = (entries[cat.value] || []).length;
              const Icon = cat.icon;
              return (
                <TabsTrigger key={cat.value} value={cat.value} className="gap-2">
                  <Icon className="h-4 w-4" />
                  <span className="hidden sm:inline">{cat.label}</span>
                  <Badge variant="secondary" className="ml-1">{count}</Badge>
                </TabsTrigger>
              );
            })}
          </TabsList>

          <TabsContent value={activeCategory} className="mt-6">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
              </div>
            ) : filteredEntries.length === 0 ? (
              <Card>
                <CardContent className="flex flex-col items-center justify-center py-12">
                  <Brain className="h-12 w-12 text-muted-foreground mb-4" />
                  <h3 className="text-lg font-medium mb-2">Nenhuma entrada de treino</h3>
                  <p className="text-muted-foreground text-center mb-4">
                    Adicione instruções personalizadas para melhorar a análise de documentos.
                  </p>
                  <Button onClick={openCreateDialog}>
                    <Plus className="h-4 w-4 mr-2" />
                    Adicionar Primeira Entrada
                  </Button>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {filteredEntries.map(entry => (
                  <TrainingEntry
                    key={entry.id}
                    entry={entry}
                    onEdit={handleEdit}
                    onDelete={handleDelete}
                    onToggle={handleToggle}
                  />
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Dialog de Criação/Edição */}
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogContent className="sm:max-w-[600px]">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Brain className="h-5 w-5" />
                {editingEntry ? "Editar Entrada" : "Nova Entrada de Treino"}
              </DialogTitle>
              <DialogDescription>
                Adicione instruções para o agente IA usar durante a análise de documentos.
              </DialogDescription>
            </DialogHeader>

            <div className="space-y-4 py-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Categoria *</Label>
                  <Select 
                    value={formData.category} 
                    onValueChange={(v) => setFormData(prev => ({ ...prev, category: v }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CATEGORIES.map(cat => (
                        <SelectItem key={cat.value} value={cat.value}>
                          <div className="flex items-center gap-2">
                            <cat.icon className="h-4 w-4" />
                            {cat.label}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Estado</Label>
                  <div className="flex items-center gap-2 h-10">
                    <Switch
                      checked={formData.is_active}
                      onCheckedChange={(v) => setFormData(prev => ({ ...prev, is_active: v }))}
                    />
                    <span className="text-sm">{formData.is_active ? "Activo" : "Inactivo"}</span>
                  </div>
                </div>
              </div>

              <div className="space-y-2">
                <Label>Título *</Label>
                <Input
                  placeholder="Ex: Padrões de Recibos de Vencimento"
                  value={formData.title}
                  onChange={(e) => setFormData(prev => ({ ...prev, title: e.target.value }))}
                />
              </div>

              <div className="space-y-2">
                <Label>Instruções / Conteúdo *</Label>
                <Textarea
                  placeholder="Descreva as instruções para o agente IA..."
                  value={formData.content}
                  onChange={(e) => setFormData(prev => ({ ...prev, content: e.target.value }))}
                  rows={6}
                />
                <p className="text-xs text-muted-foreground">
                  Seja específico. Por exemplo: "Quando encontrar um documento com 'Recibo de Vencimento' no título, extrair: nome, NIF, valor líquido, data de pagamento."
                </p>
              </div>

              <div className="space-y-2">
                <Label>Exemplos (um por linha)</Label>
                <Textarea
                  placeholder="Recibo_Vencimento_Janeiro.pdf&#10;RV_2024_02_JoaoSilva.pdf&#10;payslip_march.pdf"
                  value={formData.examples}
                  onChange={(e) => setFormData(prev => ({ ...prev, examples: e.target.value }))}
                  rows={3}
                />
              </div>
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                Cancelar
              </Button>
              <Button onClick={handleSave} disabled={saving} className="bg-teal-600 hover:bg-teal-700">
                {saving ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Save className="h-4 w-4 mr-2" />
                )}
                {editingEntry ? "Actualizar" : "Guardar"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>

        {/* Dialog do Prompt Gerado */}
        <Dialog open={isPromptDialogOpen} onOpenChange={setIsPromptDialogOpen}>
          <DialogContent className="sm:max-w-[700px] max-h-[80vh]">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Eye className="h-5 w-5" />
                Prompt de Treino Gerado
              </DialogTitle>
              <DialogDescription>
                Este prompt é usado pelo agente IA durante a análise de documentos.
              </DialogDescription>
            </DialogHeader>

            <ScrollArea className="h-[400px] rounded-md border p-4">
              <pre className="text-sm whitespace-pre-wrap font-mono">
                {generatedPrompt || "Nenhuma entrada activa."}
              </pre>
            </ScrollArea>

            <DialogFooter>
              <Button variant="outline" onClick={() => setIsPromptDialogOpen(false)}>
                Fechar
              </Button>
              <Button onClick={copyPrompt}>
                <Copy className="h-4 w-4 mr-2" />
                Copiar Prompt
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default AITrainingPage;
