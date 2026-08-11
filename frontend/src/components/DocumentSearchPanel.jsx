/**
 * DocumentSearchPanel - Pesquisa e Categorização de Documentos
 * Permite pesquisar documentos por conteúdo e ver categorias IA
 */
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { Progress } from "./ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { toast } from "sonner";
import { safeDateStr } from "../lib/utils";
import {
  Search,
  FileText,
  Loader2,
  Tag,
  FolderOpen,
  Sparkles,
  RefreshCw,
  Filter,
  X,
  AlertCircle,
  Clock,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Cores para categorias
const CATEGORY_COLORS = {
  "Identificação": "bg-blue-100 text-blue-800 border-blue-200",
  "Rendimentos": "bg-green-100 text-green-800 border-green-200",
  "Emprego": "bg-purple-100 text-purple-800 border-purple-200",
  "Bancários": "bg-orange-100 text-orange-800 border-orange-200",
  "Imóvel": "bg-pink-100 text-pink-800 border-pink-200",
  "Contratos": "bg-yellow-100 text-yellow-800 border-yellow-200",
  "Fiscais": "bg-red-100 text-red-800 border-red-200",
  "Simulações": "bg-teal-100 text-teal-800 border-teal-200",
  "Outros": "bg-gray-100 text-gray-800 border-gray-200",
};

const getCategoryColor = (category) => {
  return CATEGORY_COLORS[category] || CATEGORY_COLORS["Outros"];
};

const DocumentSearchPanel = ({ processId }) => {
  const { token } = useAuth();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [metadata, setMetadata] = useState([]);
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [loading, setLoading] = useState(true);
  const [categorizing, setCategorizing] = useState(false);
  const [categorizationProgress, setCategorizationProgress] = useState(0);
  const [showCategorizeDialog, setShowCategorizeDialog] = useState(false);

  // Carregar metadados dos documentos
  const fetchMetadata = useCallback(async () => {
    if (!processId) return;
    
    try {
      const response = await fetch(
        `${API_URL}/api/documents/metadata/${processId}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setMetadata(data.documents || []);
        setCategories(data.categories || []);
      }
    } catch (error) {
      console.error("Erro ao carregar metadados:", error);
    } finally {
      setLoading(false);
    }
  }, [processId, token]);

  useEffect(() => {
    fetchMetadata();
  }, [fetchMetadata]);

  // Pesquisar documentos
  const handleSearch = async () => {
    if (searchQuery.length < 2) {
      toast.error("Digite pelo menos 2 caracteres para pesquisar");
      return;
    }

    setSearching(true);
    try {
      const response = await fetch(`${API_URL}/api/documents/search`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          query: searchQuery,
          process_id: processId,
          limit: 20,
        }),
      });

      if (response.ok) {
        const data = await response.json();
        setSearchResults(data.results || []);
        
        if (data.results.length === 0) {
          toast.info("Nenhum documento encontrado");
        }
      } else {
        toast.error("Erro na pesquisa");
      }
    } catch (error) {
      console.error("Erro na pesquisa:", error);
      toast.error("Erro ao pesquisar documentos");
    } finally {
      setSearching(false);
    }
  };

  // Categorizar todos os documentos
  const handleCategorizeAll = async () => {
    setCategorizing(true);
    setCategorizationProgress(10);

    try {
      const response = await fetch(
        `${API_URL}/api/documents/categorize-all/${processId}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      setCategorizationProgress(90);

      if (response.ok) {
        const data = await response.json();
        toast.success(
          `Categorização concluída: ${data.categorized} documentos categorizados`
        );
        fetchMetadata();
        setShowCategorizeDialog(false);
      } else {
        const error = await response.json();
        toast.error(extractErrorMessage(error.detail, "Erro ao categorizar documentos"));
      }
    } catch (error) {
      console.error("Erro ao categorizar:", error);
      toast.error("Erro ao categorizar documentos");
    } finally {
      setCategorizing(false);
      setCategorizationProgress(100);
    }
  };

  // Abrir documento no S3 - usa temporary_url se disponível
  const handleOpenDocument = async (s3Path, temporaryUrl = null) => {
    // Se já temos o temporary_url, usar directamente
    if (temporaryUrl) {
      window.open(temporaryUrl, "_blank");
      return;
    }
    
    // Fallback para o endpoint de download
    try {
      const response = await fetch(
        `${API_URL}/api/documents/client/${processId}/download?file_path=${encodeURIComponent(s3Path)}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const data = await response.json();
        window.open(data.url, "_blank");
      } else {
        toast.error("Erro ao obter link do documento");
      }
    } catch (error) {
      console.error("Erro ao abrir documento:", error);
      toast.error("Erro ao abrir documento");
    }
  };

  // Filtrar documentos por categoria
  const filteredDocuments = metadata.filter((doc) => {
    if (selectedCategory === "all") return true;
    if (selectedCategory === "uncategorized") return !doc.is_categorized;
    return doc.ai_category === selectedCategory;
  });

  // Contar documentos não categorizados
  const uncategorizedCount = metadata.filter((d) => !d.is_categorized).length;
  const categorizedCount = metadata.filter((d) => d.is_categorized).length;

  // Limpar pesquisa
  const clearSearch = () => {
    setSearchQuery("");
    setSearchResults([]);
  };

  if (loading) {
    return (
      <Card className="border-border">
        <CardContent className="p-6">
          <div className="flex items-center justify-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="text-sm text-muted-foreground">A carregar...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-border" data-testid="document-search-panel">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <Search className="h-4 w-4" />
            Pesquisa de Documentos
          </CardTitle>
          
          {/* Botão para categorizar todos */}
          <Dialog open={showCategorizeDialog} onOpenChange={setShowCategorizeDialog}>
            <DialogTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="text-purple-600 border-purple-200 hover:bg-purple-50"
                data-testid="categorize-all-btn"
              >
                <Sparkles className="h-4 w-4 mr-2" />
                Categorizar com IA
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Categorizar Documentos com IA</DialogTitle>
                <DialogDescription>
                  A IA irá analisar todos os documentos deste cliente e atribuir
                  categorias automaticamente.
                </DialogDescription>
              </DialogHeader>
              
              <div className="space-y-4 py-4">
                <div className="flex items-center justify-between text-sm">
                  <span>Total de documentos:</span>
                  <Badge variant="secondary">{metadata.length}</Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span>Já categorizados:</span>
                  <Badge className="bg-green-100 text-green-800">{categorizedCount}</Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span>Por categorizar:</span>
                  <Badge className="bg-orange-100 text-orange-800">{uncategorizedCount}</Badge>
                </div>

                {categorizing && (
                  <div className="space-y-2">
                    <Progress value={categorizationProgress} className="h-2" />
                    <p className="text-xs text-center text-muted-foreground">
                      A categorizar documentos...
                    </p>
                  </div>
                )}
              </div>

              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={() => setShowCategorizeDialog(false)}
                  disabled={categorizing}
                >
                  Cancelar
                </Button>
                <Button
                  onClick={handleCategorizeAll}
                  disabled={categorizing || uncategorizedCount === 0}
                  className="bg-purple-600 hover:bg-purple-700"
                >
                  {categorizing ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      A processar...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4 mr-2" />
                      Iniciar Categorização
                    </>
                  )}
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Barra de pesquisa */}
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Input
              placeholder="Pesquisar por nome, conteúdo, categoria..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && handleSearch()}
              className="pr-8"
              data-testid="document-search-input"
            />
            {searchQuery && (
              <button
                onClick={clearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
          <Button
            onClick={handleSearch}
            disabled={searching || searchQuery.length < 2}
            data-testid="search-btn"
          >
            {searching ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
          </Button>
        </div>

        {/* Resultados da pesquisa */}
        {searchResults.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium">
                Resultados ({searchResults.length})
              </h4>
              <Button
                variant="ghost"
                size="sm"
                onClick={clearSearch}
                className="text-xs"
              >
                Limpar pesquisa
              </Button>
            </div>
            <ScrollArea className="h-48">
              <div className="space-y-2">
                {searchResults.map((result) => (
                  <div
                    key={result.id}
                    className="p-3 bg-muted/50 rounded-lg hover:bg-muted cursor-pointer transition-colors"
                    onClick={() => handleOpenDocument(result.s3_path, result.temporary_url)}
                    data-testid={`search-result-${result.id}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText className="h-4 w-4 flex-shrink-0 text-red-500" />
                        <span className="text-sm font-medium truncate">
                          {result.filename}
                        </span>
                      </div>
                      {result.ai_category && (
                        <Badge
                          variant="outline"
                          className={`text-xs flex-shrink-0 ${getCategoryColor(result.ai_category)}`}
                        >
                          {result.ai_category}
                        </Badge>
                      )}
                    </div>
                    {result.matched_text && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                        {result.matched_text}
                      </p>
                    )}
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-xs text-muted-foreground">
                        Relevância: {Math.round(result.relevance_score * 10)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Filtro por categoria */}
        <div className="flex items-center gap-2">
          <Filter className="h-4 w-4 text-muted-foreground" />
          <Select value={selectedCategory} onValueChange={setSelectedCategory}>
            <SelectTrigger className="w-48 h-8 text-sm">
              <SelectValue placeholder="Filtrar por categoria" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas as categorias</SelectItem>
              <SelectItem value="uncategorized">
                Não categorizados ({uncategorizedCount})
              </SelectItem>
              {categories.map((cat) => (
                <SelectItem key={cat} value={cat}>
                  {cat}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="sm"
            onClick={fetchMetadata}
            className="h-8"
          >
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>

        {/* Lista de documentos categorizados */}
        {searchResults.length === 0 && (
          <ScrollArea className="h-64">
            <div className="space-y-2">
              {filteredDocuments.length === 0 ? (
                <div className="text-center py-8 text-muted-foreground">
                  <FolderOpen className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">Nenhum documento encontrado</p>
                </div>
              ) : (
                filteredDocuments.map((doc) => {
                  // Calcular urgência de expiração
                  let expiryUrgency = null;
                  let daysUntilExpiry = null;
                  if (doc.expiry_date) {
                    const today = new Date();
                    const expiry = new Date(safeDateStr(doc.expiry_date));
                    daysUntilExpiry = Math.ceil((expiry - today) / (1000 * 60 * 60 * 24));
                    
                    if (daysUntilExpiry < 0) {
                      expiryUrgency = "expired";
                    } else if (daysUntilExpiry < 7) {
                      expiryUrgency = "critical";
                    } else if (daysUntilExpiry < 30) {
                      expiryUrgency = "warning";
                    } else if (daysUntilExpiry <= 60) {
                      expiryUrgency = "attention";
                    }
                  }

                  return (
                    <div
                      key={doc.id}
                      className={`p-3 bg-muted/30 rounded-lg hover:bg-muted/50 cursor-pointer transition-colors border ${
                        expiryUrgency === "expired" ? "border-red-500 bg-red-50/50 dark:bg-red-900/20" :
                        expiryUrgency === "critical" ? "border-red-400 bg-red-50/30 dark:bg-red-900/10" :
                        expiryUrgency === "warning" ? "border-orange-400 bg-orange-50/30 dark:bg-orange-900/10" :
                        expiryUrgency === "attention" ? "border-yellow-400 bg-yellow-50/30 dark:bg-yellow-900/10" :
                        "border-border"
                      }`}
                      onClick={() => handleOpenDocument(doc.s3_path, doc.temporary_url)}
                      data-testid={`doc-${doc.id}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <FileText className="h-4 w-4 flex-shrink-0 text-red-500" />
                          <div className="min-w-0">
                            <span className="text-sm font-medium truncate block">
                              {doc.filename}
                            </span>
                            {doc.ai_summary && (
                              <p className="text-xs text-muted-foreground truncate">
                                {doc.ai_summary}
                              </p>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          {/* Indicador de Expiração */}
                          {expiryUrgency && (
                            <Badge
                              variant="outline"
                              className={`text-xs ${
                                expiryUrgency === "expired" ? "bg-red-600 text-white border-red-600" :
                                expiryUrgency === "critical" ? "bg-red-500 text-white border-red-500" :
                                expiryUrgency === "warning" ? "bg-orange-500 text-white border-orange-500" :
                                "bg-yellow-500 text-yellow-900 border-yellow-500"
                              }`}
                              title={`Expira em ${doc.expiry_date}`}
                            >
                              <AlertCircle className="h-3 w-3 mr-1" />
                              {expiryUrgency === "expired" ? "Expirado" :
                               daysUntilExpiry === 0 ? "Expira hoje" :
                               daysUntilExpiry === 1 ? "1 dia" :
                               `${daysUntilExpiry} dias`}
                            </Badge>
                          )}
                          {doc.is_categorized ? (
                            <Badge
                              variant="outline"
                              className={`text-xs ${getCategoryColor(doc.ai_category)}`}
                            >
                              {doc.ai_category}
                            </Badge>
                          ) : (
                            <Badge
                              variant="outline"
                              className="text-xs bg-gray-100 text-gray-600"
                            >
                              <Clock className="h-3 w-3 mr-1" />
                              Por categorizar
                            </Badge>
                          )}
                        </div>
                      </div>
                      
                      {/* Tags */}
                      {doc.ai_tags && doc.ai_tags.length > 0 && (
                        <div className="flex items-center gap-1 mt-2 flex-wrap">
                          <Tag className="h-3 w-3 text-muted-foreground" />
                          {doc.ai_tags.slice(0, 4).map((tag, idx) => (
                            <span
                              key={idx}
                              className="text-xs bg-muted px-1.5 py-0.5 rounded"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </ScrollArea>
        )}

        {/* Estatísticas */}
        <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t">
          <span>
            {categorizedCount} de {metadata.length} documentos categorizados
          </span>
          {categories.length > 0 && (
            <span>{categories.length} categorias</span>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default DocumentSearchPanel;
