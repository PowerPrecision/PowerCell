/**
 * DocumentChecklist - Checklist de documentos do sistema de armazenamento
 * Verifica se os documentos esperados estão na pasta do cliente
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "./ui/card";
import { Badge } from "./ui/badge";
import { Progress } from "./ui/progress";
import { ScrollArea } from "./ui/scroll-area";
import { Textarea } from "./ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "./ui/dialog";
import { toast } from "sonner";
import {
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  FileText,
  FolderOpen,
  RefreshCw,
  Loader2,
  ClipboardList,
  Upload,
  Info,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Ícone baseado no status
const StatusIcon = ({ status }) => {
  switch (status) {
    case "presente":
      return <CheckCircle className="h-5 w-5 text-green-500" />;
    case "em_falta":
      return <XCircle className="h-5 w-5 text-red-500" />;
    case "expirado":
      return <AlertTriangle className="h-5 w-5 text-orange-500" />;
    case "a_expirar":
      return <Clock className="h-5 w-5 text-yellow-500" />;
    default:
      return <FileText className="h-5 w-5 text-gray-400" />;
  }
};

// Badge de status
const StatusBadge = ({ status }) => {
  const variants = {
    presente: "bg-green-100 text-green-700 border-green-200",
    em_falta: "bg-red-100 text-red-700 border-red-200",
    expirado: "bg-orange-100 text-orange-700 border-orange-200",
    a_expirar: "bg-yellow-100 text-yellow-700 border-yellow-200",
    nao_verificado: "bg-gray-100 text-gray-700 border-gray-200",
  };

  const labels = {
    presente: "Presente",
    em_falta: "Em Falta",
    expirado: "Expirado",
    a_expirar: "A Expirar",
    nao_verificado: "Não Verificado",
  };

  return (
    <Badge variant="outline" className={variants[status] || variants.nao_verificado}>
      {labels[status] || status}
    </Badge>
  );
};

const DocumentChecklist = ({ processId, clientName, onUpdate }) => {
  const { token } = useAuth();
  const [checklist, setChecklist] = useState(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [filesInput, setFilesInput] = useState("");
  
  // Ref para o input de pasta (substitui document.getElementById)
  const folderInputRef = useRef(null);

  // Carregar checklist existente
  const fetchChecklist = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_URL}/api/storage/process/${processId}/checklist`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setChecklist(data);
      }
    } catch (error) {
      console.error("Erro ao carregar checklist:", error);
    } finally {
      setLoading(false);
    }
  }, [processId, token]);

  useEffect(() => {
    fetchChecklist();
  }, [fetchChecklist]);

  // Gerar checklist a partir da lista de ficheiros
  const handleGenerateChecklist = async () => {
    if (!filesInput.trim()) {
      toast.error("Cole a lista de ficheiros da pasta");
      return;
    }

    // Converter texto em lista de ficheiros
    const files = filesInput
      .split("\n")
      .map((f) => f.trim())
      .filter((f) => f.length > 0);

    if (files.length === 0) {
      toast.error("Nenhum ficheiro válido encontrado");
      return;
    }

    setGenerating(true);
    try {
      const response = await fetch(
        `${API_URL}/api/storage/process/${processId}/checklist`,
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(files),
        }
      );

      if (response.ok) {
        const data = await response.json();
        setChecklist(data);
        setIsDialogOpen(false);
        setFilesInput("");
        toast.success(
          `Checklist gerada: ${data.resumo.percentagem_conclusao}% completo`
        );
        if (onUpdate) onUpdate(data);
      } else {
        const error = await response.json();
        toast.error(extractErrorMessage(error.detail, "Erro ao gerar checklist"));
      }
    } catch (error) {
      console.error("Erro ao gerar checklist:", error);
      toast.error("Erro ao gerar checklist");
    } finally {
      setGenerating(false);
    }
  };

  // Handle file upload to get filenames
  const handleFolderSelect = (e) => {
    const files = Array.from(e.target.files || []);
    const fileNames = files.map((f) => f.name).join("\n");
    setFilesInput(fileNames);
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  const hasChecklist = checklist?.checklist?.length > 0;
  const resumo = checklist?.resumo || {};

  return (
    <>
      <Card data-testid="document-checklist">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-lg flex items-center gap-2">
                <ClipboardList className="h-5 w-5" />
                Checklist de Documentos
              </CardTitle>
              <CardDescription>
                Verificação dos documentos na pasta do cliente
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsDialogOpen(true)}
              data-testid="update-checklist-btn"
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Atualizar
            </Button>
          </div>
        </CardHeader>

        <CardContent>
          {hasChecklist ? (
            <div className="space-y-4">
              {/* Resumo */}
              <div className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium">Progresso</span>
                  <span className="text-sm text-muted-foreground">
                    {resumo.encontrados_obrigatorios || 0} /{" "}
                    {resumo.total_obrigatorios || 0} obrigatórios
                  </span>
                </div>
                <Progress
                  value={resumo.percentagem_conclusao || 0}
                  className="h-2"
                />
                <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
                  <span>{resumo.percentagem_conclusao || 0}% completo</span>
                  {resumo.em_falta_obrigatorios > 0 && (
                    <span className="text-red-500">
                      {resumo.em_falta_obrigatorios} em falta
                    </span>
                  )}
                </div>
              </div>

              {/* Lista de documentos */}
              <ScrollArea className="h-[300px]">
                <div className="space-y-2">
                  {checklist.checklist.map((doc) => (
                    <div
                      key={doc.id}
                      className={`flex items-center justify-between p-3 rounded-lg border ${
                        doc.status === "presente"
                          ? "bg-green-50 border-green-200"
                          : doc.status === "em_falta" && doc.obrigatorio
                          ? "bg-red-50 border-red-200"
                          : doc.status === "em_falta"
                          ? "bg-gray-50 border-gray-200"
                          : "bg-yellow-50 border-yellow-200"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <StatusIcon status={doc.status} />
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium">
                              {doc.nome}
                            </span>
                            {doc.obrigatorio && (
                              <Badge variant="secondary" className="text-xs">
                                Obrigatório
                              </Badge>
                            )}
                          </div>
                          {doc.ficheiros?.length > 0 && (
                            <p className="text-xs text-muted-foreground mt-1">
                              {doc.ficheiros.slice(0, 2).join(", ")}
                              {doc.ficheiros.length > 2 &&
                                ` +${doc.ficheiros.length - 2} mais`}
                            </p>
                          )}
                        </div>
                      </div>
                      <StatusBadge status={doc.status} />
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>
          ) : (
            <div className="text-center py-8">
              <FolderOpen className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
              <p className="text-muted-foreground mb-4">
                Checklist ainda não gerada
              </p>
              <Button onClick={() => setIsDialogOpen(true)}>
                <Upload className="h-4 w-4 mr-2" />
                Verificar Documentos
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Dialog para input de ficheiros */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Verificar Documentos</DialogTitle>
            <DialogDescription>
              Cole a lista de ficheiros da pasta de armazenamento ou selecione a
              pasta local
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {/* Info */}
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex gap-2">
              <Info className="h-5 w-5 text-blue-500 flex-shrink-0" />
              <div className="text-sm text-blue-700">
                <p className="font-medium">Como obter a lista de ficheiros:</p>
                <ol className="list-decimal list-inside mt-1 space-y-1">
                  <li>Abra a pasta do cliente no sistema de armazenamento</li>
                  <li>Seleccione todos os ficheiros (Ctrl+A)</li>
                  <li>Copie os nomes ou use o botão "Seleccionar Pasta"</li>
                </ol>
              </div>
            </div>

            {/* Opção: Seleccionar pasta */}
            <div>
              <label className="block">
                <input
                  ref={folderInputRef}
                  type="file"
                  webkitdirectory="true"
                  directory="true"
                  multiple
                  onChange={handleFolderSelect}
                  className="hidden"
                />
                <Button
                  variant="outline"
                  className="w-full"
                  onClick={() => folderInputRef.current?.click()}
                >
                  <FolderOpen className="h-4 w-4 mr-2" />
                  Seleccionar Pasta Local
                </Button>
              </label>
            </div>

            <div className="text-center text-sm text-muted-foreground">ou</div>

            {/* Textarea para colar nomes */}
            <div className="space-y-2">
              <Textarea
                value={filesInput}
                onChange={(e) => setFilesInput(e.target.value)}
                placeholder="Cole aqui a lista de ficheiros (um por linha):&#10;CC_titular.pdf&#10;Recibo_Janeiro.pdf&#10;IRS_2024.pdf&#10;..."
                rows={8}
                data-testid="files-input"
              />
              <p className="text-xs text-muted-foreground">
                {filesInput.split("\n").filter((f) => f.trim()).length} ficheiros
                detectados
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleGenerateChecklist}
              disabled={generating || !filesInput.trim()}
            >
              {generating ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <CheckCircle className="h-4 w-4 mr-2" />
              )}
              Verificar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default DocumentChecklist;
