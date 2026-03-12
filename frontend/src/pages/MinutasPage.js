/**
 * MinutasPage - Gestao de Minutas/Templates
 * Secção para guardar e gerir minutas/templates de documentos
 * Disponivel para todos os utilizadores
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
  Upload,
  FolderUp,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Categorias de minutas
const CATEGORIAS = [
  { id: "contrato", label: "Contratos", color: "bg-blue-500" },
  { id: "procuracao", label: "Procuracoes", color: "bg-purple-500" },
  { id: "declaracao", label: "Declaracoes", color: "bg-green-500" },
  { id: "carta", label: "Cartas", color: "bg-orange-500" },
  { id: "outro", label: "Outros", color: "bg-gray-500" },
];

const MinutasPage = () => {
  const [minutas, setMinutas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [previewDialog, setPreviewDialog] = useState(false);
  const [selectedMinuta, setSelectedMinuta] = useState(null);
  const [importDialogOpen, setImportDialogOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [formData, setFormData] = useState({
    titulo: "",
    categoria: "contrato",
    descricao: "",
    conteudo: "",
    tags: "",
  });

  const fileInputRef = React.useRef(null);

  const fetchMinutas = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/minutas`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setMinutas(data.minutas || []);
      }
    } catch (error) {
      console.error("Erro ao carregar minutas:", error);
      toast.error("Erro ao carregar minutas");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMinutas();
  }, [fetchMinutas]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    try {
      const token = localStorage.getItem("token");
      const method = selectedMinuta ? "PUT" : "POST";
      const url = selectedMinuta 
        ? `${API_URL}/api/minutas/${selectedMinuta.id}`
        : `${API_URL}/api/minutas`;
      
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
        toast.success(selectedMinuta ? "Minuta actualizada" : "Minuta criada");
        setDialogOpen(false);
        resetForm();
        fetchMinutas();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao guardar minuta");
      }
    } catch (error) {
      toast.error("Erro ao guardar minuta");
    }
  };

  const handleDelete = async (id) => {
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/minutas/${id}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });

      if (response.ok) {
        toast.success("Minuta eliminada");
        fetchMinutas();
      }
    } catch (error) {
      toast.error("Erro ao eliminar minuta");
    }
  };

  const handleCopy = async (minuta) => {
    try {
      await navigator.clipboard.writeText(minuta.conteudo);
      toast.success("Conteudo copiado para a area de transferencia");
    } catch (error) {
      toast.error("Erro ao copiar");
    }
  };

  const handleDownload = (minuta) => {
    const blob = new Blob([minuta.conteudo], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${minuta.titulo.replace(/\s+/g, "_")}.txt`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  const handleEdit = (minuta) => {
    setSelectedMinuta(minuta);
    setFormData({
      titulo: minuta.titulo,
      categoria: minuta.categoria,
      descricao: minuta.descricao || "",
      conteudo: minuta.conteudo,
      tags: (minuta.tags || []).join(", "),
    });
    setDialogOpen(true);
  };

  const handlePreview = (minuta) => {
    setSelectedMinuta(minuta);
    setPreviewDialog(true);
  };

  const resetForm = () => {
    setSelectedMinuta(null);
    setFormData({
      titulo: "",
      categoria: "contrato",
      descricao: "",
      conteudo: "",
      tags: "",
    });
  };

  const filteredMinutas = minutas.filter((minuta) => {
    const matchesSearch =
      minuta.titulo.toLowerCase().includes(searchTerm.toLowerCase()) ||
      minuta.descricao?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (minuta.tags || []).some(tag => 
        tag.toLowerCase().includes(searchTerm.toLowerCase())
      );
    const matchesCategory =
      selectedCategory === "all" || minuta.categoria === selectedCategory;
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

  // Importar minutas via ficheiros
  const handleImportFiles = async (event) => {
    const files = Array.from(event.target.files || []);
    if (files.length === 0) return;

    setImporting(true);
    setImportDialogOpen(false);
    
    const token = localStorage.getItem("token");
    let imported = 0;
    let errors = 0;

    toast.info(`A importar ${files.length} ficheiros...`);

    for (const file of files) {
      const formData = new FormData();
      formData.append("file", file);

      try {
        const response = await fetch(`${API_URL}/api/minutas/import`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        });

        if (response.ok) {
          imported++;
        } else {
          errors++;
          const data = await response.json();
          console.error(`Erro ao importar ${file.name}:`, data.detail);
        }
      } catch (error) {
        errors++;
        console.error(`Erro ao importar ${file.name}:`, error);
      }
    }

    setImporting(false);
    
    if (imported > 0) {
      toast.success(`${imported} minutas importadas com sucesso!`);
      fetchMinutas();
    }
    if (errors > 0) {
      toast.error(`${errors} ficheiros não foram importados`);
    }

    // Limpar input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-2xl font-bold">Minutas</h1>
            <p className="text-muted-foreground">
              Templates e minutas de documentos para reutilizar
            </p>
          </div>
          <div className="flex gap-2">
            {/* Botão de Importar */}
            <Dialog open={importDialogOpen} onOpenChange={setImportDialogOpen}>
              <DialogTrigger asChild>
                <Button variant="outline" disabled={importing}>
                  {importing ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4 mr-2" />
                  )}
                  Importar
                </Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle className="flex items-center gap-2">
                    <FolderUp className="h-5 w-5" />
                    Importar Minutas
                  </DialogTitle>
                  <DialogDescription>
                    Selecione ficheiros Word (.docx) ou PDF para importar como minutas
                  </DialogDescription>
                </DialogHeader>
                <div className="py-4 space-y-4">
                  <div className="border-2 border-dashed rounded-lg p-6 text-center">
                    <Upload className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
                    <p className="text-sm text-muted-foreground mb-4">
                      Arraste ficheiros aqui ou clique para selecionar
                    </p>
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      accept=".docx,.doc,.pdf,.txt"
                      onChange={handleImportFiles}
                      className="hidden"
                    />
                    <Button
                      variant="outline"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      Selecionar Ficheiros
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Formatos suportados: .docx, .doc, .pdf, .txt
                  </p>
                </div>
              </DialogContent>
            </Dialog>

            {/* Botão Nova Minuta */}
            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
              <DialogTrigger asChild>
                <Button onClick={resetForm}>
                  <Plus className="h-4 w-4 mr-2" />
                  Nova Minuta
                </Button>
              </DialogTrigger>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
              <form onSubmit={handleSubmit}>
                <DialogHeader>
                  <DialogTitle>
                    {selectedMinuta ? "Editar Minuta" : "Nova Minuta"}
                  </DialogTitle>
                  <DialogDescription>
                    Preencha os dados da minuta/template
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
                      placeholder="Ex: Contrato de Promessa de Compra e Venda"
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
                        placeholder="Ex: imovel, compra, venda"
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
                      placeholder="Breve descricao do uso desta minuta"
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
                      placeholder="Cole ou escreva aqui o conteudo da minuta..."
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
                    {selectedMinuta ? "Actualizar" : "Criar"}
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
              placeholder="Pesquisar minutas..."
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
              <div className="text-2xl font-bold">{minutas.length}</div>
            </CardContent>
          </Card>
          {CATEGORIAS.map((cat) => (
            <Card key={cat.id}>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">{cat.label}</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {minutas.filter((m) => m.categoria === cat.id).length}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Lista de Minutas */}
        <Card>
          <CardHeader>
            <CardTitle>Minutas</CardTitle>
            <CardDescription>
              {filteredMinutas.length} minuta(s) encontrada(s)
            </CardDescription>
          </CardHeader>
          <CardContent>
            {filteredMinutas.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Nenhuma minuta encontrada</p>
                {minutas.length === 0 && (
                  <p className="text-sm mt-2">
                    Clique em "Nova Minuta" para criar a primeira
                  </p>
                )}
              </div>
            ) : (
              <ScrollArea className="h-[500px]">
                <div className="grid gap-4">
                  {filteredMinutas.map((minuta) => (
                    <Card key={minuta.id} className="hover:shadow-md transition-shadow">
                      <CardContent className="pt-4">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-2">
                              <Badge className={getCategoryColor(minuta.categoria)}>
                                {getCategoryLabel(minuta.categoria)}
                              </Badge>
                              {(minuta.tags || []).slice(0, 3).map((tag) => (
                                <Badge key={tag} variant="outline" className="text-xs">
                                  <Tag className="h-3 w-3 mr-1" />
                                  {tag}
                                </Badge>
                              ))}
                            </div>
                            <h3 className="font-semibold text-lg truncate">
                              {minuta.titulo}
                            </h3>
                            {minuta.descricao && (
                              <p className="text-sm text-muted-foreground mt-1">
                                {minuta.descricao}
                              </p>
                            )}
                            <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                              <span className="flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {formatDate(minuta.created_at)}
                              </span>
                              <span className="flex items-center gap-1">
                                <User className="h-3 w-3" />
                                {minuta.created_by_name || "Sistema"}
                              </span>
                              <span>
                                {minuta.conteudo?.length || 0} caracteres
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handlePreview(minuta)}
                              title="Visualizar"
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleCopy(minuta)}
                              title="Copiar"
                            >
                              <Copy className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleDownload(minuta)}
                              title="Descarregar"
                            >
                              <FileDown className="h-4 w-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleEdit(minuta)}
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
                                  <AlertDialogTitle>Eliminar Minuta?</AlertDialogTitle>
                                  <AlertDialogDescription>
                                    Esta accao nao pode ser revertida. A minuta sera
                                    permanentemente eliminada.
                                  </AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                  <AlertDialogCancel>Cancelar</AlertDialogCancel>
                                  <AlertDialogAction
                                    onClick={() => handleDelete(minuta.id)}
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
          <DialogContent className="max-w-4xl max-h-[90vh]">
            <DialogHeader>
              <DialogTitle>{selectedMinuta?.titulo}</DialogTitle>
              <DialogDescription>
                {selectedMinuta?.descricao}
              </DialogDescription>
            </DialogHeader>
            <ScrollArea className="h-[60vh] mt-4">
              <pre className="whitespace-pre-wrap font-mono text-sm bg-muted p-4 rounded-lg">
                {selectedMinuta?.conteudo}
              </pre>
            </ScrollArea>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => handleCopy(selectedMinuta)}
              >
                <Copy className="h-4 w-4 mr-2" />
                Copiar
              </Button>
              <Button
                variant="outline"
                onClick={() => handleDownload(selectedMinuta)}
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

export default MinutasPage;
