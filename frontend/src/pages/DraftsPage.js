/**
 * DraftsPage - Gestao de Rascunhos
 * Pagina dedicada a rascunhos de documentos e templates
 *
 * Separada do FormManagementPage para evitar partilha de rota/componente.
 * Disponivel para admin, ceo e administrativo.
 */
import React, { useState, useEffect, useCallback } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../components/ui/alert-dialog";
import { toast } from "sonner";
import {
  FileText,
  Plus,
  Search,
  Edit,
  Trash2,
  Copy,
  Download,
  Clock,
  User,
  Tag,
  Loader2,
  FileDown,
  Eye,
  FileSignature,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Categorias de rascunhos
const CATEGORIAS = [
  { id: "email", label: "Emails", color: "bg-blue-500" },
  { id: "contrato", label: "Contratos", color: "bg-purple-500" },
  { id: "proposta", label: "Propostas", color: "bg-green-500" },
  { id: "carta", label: "Cartas", color: "bg-orange-500" },
  { id: "outro", label: "Outros", color: "bg-gray-500" },
];

const DraftsPage = () => {
  const [drafts, setDrafts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [previewDialog, setPreviewDialog] = useState(false);
  const [selectedDraft, setSelectedDraft] = useState(null);
  const [formData, setFormData] = useState({
    titulo: "",
    categoria: "email",
    descricao: "",
    conteudo: "",
    tags: "",
  });

  const fetchDrafts = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/drafts`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setDrafts(data.drafts || []);
      }
      // Se 404, a endpoint ainda nao existe no backend — mostrar lista vazia silenciosamente
    } catch (error) {
      // Silently fail — drafts endpoint may not exist yet
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDrafts();
  }, [fetchDrafts]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      const token = localStorage.getItem("token");
      const method = selectedDraft ? "PUT" : "POST";
      const url = selectedDraft
        ? `${API_URL}/api/drafts/${selectedDraft.id}`
        : `${API_URL}/api/drafts`;

      const response = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          ...formData,
          tags: formData.tags.split(",").map(t => t.trim()).filter(t => t),
        }),
      });

      if (response.ok) {
        toast.success(selectedDraft ? "Rascunho actualizado" : "Rascunho criado");
        setDialogOpen(false);
        resetForm();
        fetchDrafts();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao guardar rascunho");
      }
    } catch (error) {
      toast.error("Erro ao guardar rascunho");
    }
  };

  const handleDelete = async (id) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/drafts/${id}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.ok) {
        toast.success("Rascunho eliminado");
        fetchDrafts();
      }
    } catch (error) {
      toast.error("Erro ao eliminar rascunho");
    }
  };

  const handleCopy = async (draft) => {
    try {
      await navigator.clipboard.writeText(draft.conteudo);
      toast.success("Conteudo copiado para a area de transferencia");
    } catch (error) {
      toast.error("Erro ao copiar");
    }
  };

  const handleDownload = (draft) => {
    const blob = new Blob([draft.conteudo], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${draft.titulo.replace(/\s+/g, "_")}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleEdit = (draft) => {
    setSelectedDraft(draft);
    setFormData({
      titulo: draft.titulo,
      categoria: draft.categoria,
      descricao: draft.descricao || "",
      conteudo: draft.conteudo,
      tags: (draft.tags || []).join(", "),
    });
    setDialogOpen(true);
  };

  const handlePreview = (draft) => {
    setSelectedDraft(draft);
    setPreviewDialog(true);
  };

  const resetForm = () => {
    setSelectedDraft(null);
    setFormData({
      titulo: "",
      categoria: "email",
      descricao: "",
      conteudo: "",
      tags: "",
    });
  };

  const filteredDrafts = drafts.filter((draft) => {
    const matchesSearch =
      draft.titulo.toLowerCase().includes(searchTerm.toLowerCase()) ||
      draft.descricao?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (draft.tags || []).some(tag =>
        tag.toLowerCase().includes(searchTerm.toLowerCase())
      );
    const matchesCategory =
      selectedCategory === "all" || draft.categoria === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const formatDate = (dateStr) => {
    if (!dateStr) return "N/D";
    try {
      return new Date(dateStr).toLocaleDateString("pt-PT");
    } catch {
      return dateStr;
    }
  };

  const getCategoryLabel = (categoryId) => {
    const cat = CATEGORIAS.find(c => c.id === categoryId);
    return cat?.label || categoryId;
  };

  const getCategoryColor = (categoryId) => {
    const cat = CATEGORIAS.find(c => c.id === categoryId);
    return cat?.color || "bg-gray-500";
  };

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold">Rascunhos</h1>
            <p className="text-muted-foreground">
              Rascunhos de emails, documentos e propostas
            </p>
          </div>
          <div className="flex gap-2">
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button onClick={resetForm}>
                  <Plus className="h-4 w-4 mr-2" />
                  Novo Rascunho
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
                <form onSubmit={handleSubmit}>
                  <DialogHeader>
                    <DialogTitle>
                      {selectedDraft ? "Editar Rascunho" : "Novo Rascunho"}
                    </DialogTitle>
                    <DialogDescription>
                      Crie ou edite um rascunho para uso futuro
                    </DialogDescription>
                  </DialogHeader>
                  <div className="grid gap-4 py-4">
                    <div className="grid gap-2">
                      <Label htmlFor="titulo">Titulo *</Label>
                      <Input
                        id="titulo"
                        value={formData.titulo}
                        onChange={(e) =>
                          setFormData({ ...formData, titulo: e.target.value })
                        }
                        placeholder="Ex: Proposta de credito - Joao Silva"
                        required
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="grid gap-2">
                        <Label htmlFor="categoria">Categoria *</Label>
                        <Select
                          value={formData.categoria}
                          onValueChange={(value) =>
                            setFormData({ ...formData, categoria: value })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {CATEGORIAS.map((cat) => (
                              <SelectItem key={cat.id} value={cat.id}>
                                {cat.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="grid gap-2">
                        <Label htmlFor="tags">Tags (separadas por virgula)</Label>
                        <Input
                          id="tags"
                          value={formData.tags}
                          onChange={(e) =>
                            setFormData({ ...formData, tags: e.target.value })
                          }
                          placeholder="Ex: credito, habitação, proposta"
                        />
                      </div>
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="descricao">Descricao</Label>
                      <Input
                        id="descricao"
                        value={formData.descricao}
                        onChange={(e) =>
                          setFormData({ ...formData, descricao: e.target.value })
                        }
                        placeholder="Breve descricao do rascunho"
                      />
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="conteudo">Conteudo *</Label>
                      <Textarea
                        id="conteudo"
                        value={formData.conteudo}
                        onChange={(e) =>
                          setFormData({ ...formData, conteudo: e.target.value })
                        }
                        placeholder="Escreva aqui o conteudo do rascunho..."
                        rows={15}
                        required
                        className="font-mono text-sm"
                      />
                      <p className="text-xs text-muted-foreground">
                        Dica: Use placeholders como [NOME_CLIENTE], [DATA], [VALOR] para facilitar a substituicao
                      </p>
                    </div>
                  </div>
                  <DialogFooter>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setDialogOpen(false)}
                    >
                      Cancelar
                    </Button>
                    <Button type="submit">
                      {selectedDraft ? "Actualizar" : "Criar"}
                    </Button>
                  </DialogFooter>
                </form>
              </DialogContent>
            </Dialog>
          </div>
        </div>

        {/* Filtros */}
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Pesquisar rascunhos..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-9"
            />
          </div>
          <Select
            value={selectedCategory}
            onValueChange={setSelectedCategory}
          >
            <SelectTrigger className="w-full sm:w-[200px]">
              <SelectValue placeholder="Todas as categorias" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas as categorias</SelectItem>
              {CATEGORIAS.map((cat) => (
                <SelectItem key={cat.id} value={cat.id}>
                  {cat.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Estatisticas */}
        <div className="grid gap-4 md:grid-cols-5">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium">Total</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{drafts.length}</div>
            </CardContent>
          </Card>
          {CATEGORIAS.map((cat) => (
            <Card key={cat.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">{cat.label}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {drafts.filter((d) => d.categoria === cat.id).length}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Lista de Rascunhos */}
        <Card>
          <CardHeader>
            <CardTitle>Rascunhos</CardTitle>
            <CardDescription>
              {filteredDrafts.length} rascunho(s) encontrado(s)
            </CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : filteredDrafts.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <FileSignature className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Nenhum rascunho encontrado</p>
                {drafts.length === 0 && (
                  <p className="text-sm mt-2">
                    Clique em "Novo Rascunho" para criar o primeiro
                  </p>
                )}
              </div>
            ) : (
              <ScrollArea className="h-[300px] sm:h-[500px]">
                <div className="grid gap-4">
                  {filteredDrafts.map((draft) => (
                    <Card key={draft.id} className="hover:shadow-md transition-shadow">
                      <CardContent className="pt-4">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-2">
                              <Badge className={getCategoryColor(draft.categoria)}>
                                {getCategoryLabel(draft.categoria)}
                              </Badge>
                              {(draft.tags || []).slice(0, 3).map((tag) => (
                                <Badge key={tag} variant="outline" className="text-xs">
                                  <Tag className="h-3 w-3 mr-1" />
                                  {tag}
                                </Badge>
                              ))}
                            </div>
                            <h3 className="font-semibold text-lg truncate">
                              {draft.titulo}
                            </h3>
                            {draft.descricao && (
                              <p className="text-sm text-muted-foreground mt-1">
                                {draft.descricao}
                              </p>
                            )}
                            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                              <span className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {formatDate(draft.created_at)}
                              </span>
                              <span className="flex items-center gap-1">
                                <User className="h-3 w-3" />
                                {draft.created_by_name || "Sistema"}
                              </span>
                              <span>
                                {draft.conteudo?.length || 0} caracteres
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handlePreview(draft)}
                              title="Visualizar"
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleCopy(draft)}
                              title="Copiar"
                            >
                              <Copy className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleDownload(draft)}
                              title="Descarregar"
                            >
                              <FileDown className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleEdit(draft)}
                              title="Editar"
                            >
                              <Edit className="h-4 w-4" />
                            </Button>
                            <AlertDialog>
                              <AlertDialogTrigger asChild>
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  className="text-red-500 hover:text-red-600"
                                  title="Eliminar"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </AlertDialogTrigger>
                              <AlertDialogContent>
                                <AlertDialogHeader>
                                  <AlertDialogTitle>Eliminar Rascunho?</AlertDialogTitle>
                                  <AlertDialogDescription>
                                    Esta accao nao pode ser revertida. O rascunho sera
                                    permanentemente eliminado.
                                  </AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                  <AlertDialogCancel>Cancelar</AlertDialogCancel>
                                  <AlertDialogAction
                                    onClick={() => handleDelete(draft.id)}
                                    className="bg-red-500 hover:bg-red-600"
                                  >
                                    Eliminar
                                  </AlertDialogAction>
                                </AlertDialogFooter>
                              </AlertDialogContent>
                            </AlertDialog>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>

        {/* Dialog de Preview */}
        <Dialog open={previewDialog} onOpenChange={setPreviewDialog}>
          <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{selectedDraft?.titulo}</DialogTitle>
              <DialogDescription>
                {selectedDraft?.descricao}
              </DialogDescription>
            </DialogHeader>
            <ScrollArea className="h-[60vh] mt-4">
              <pre className="whitespace-pre-wrap font-mono text-sm bg-muted p-4 rounded-lg">
                {selectedDraft?.conteudo}
              </pre>
            </ScrollArea>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => handleCopy(selectedDraft)}
              >
                <Copy className="h-4 w-4 mr-2" />
                Copiar
              </Button>
              <Button
                variant="outline"
                onClick={() => handleDownload(selectedDraft)}
              >
                <FileDown className="h-4 w-4 mr-2" />
                Descarregar
              </Button>
              <Button onClick={() => setPreviewDialog(false)}>
                Fechar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default DraftsPage;
