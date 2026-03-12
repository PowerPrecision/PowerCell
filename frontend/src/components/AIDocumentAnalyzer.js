/**
 * AIDocumentAnalyzer - Componente para análise de documentos com IA
 * Permite upload de ficheiros ou análise via URL externa (S3, Drive, etc.)
 * Preenche automaticamente os campos da ficha do cliente
 */
import { useState, useRef } from "react";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { ScrollArea } from "./ui/scroll-area";
import {
  Sparkles,
  Upload,
  Loader2,
  FileText,
  CheckCircle,
  Link,
  AlertCircle,
  ArrowRight,
  RotateCcw,
} from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "../contexts/AuthContext";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

// Tipos de documentos suportados
const DOCUMENT_TYPES = [
  { value: "cc", label: "Cartão de Cidadão", icon: "🪪" },
  { value: "recibo_vencimento", label: "Recibo de Vencimento", icon: "💰" },
  { value: "irs", label: "Declaração IRS", icon: "📋" },
  { value: "cpcv", label: "CPCV (Contrato Promessa)", icon: "📜" },
  { value: "simulacao_credito", label: "Simulação de Crédito", icon: "🏦" },
  { value: "caderneta_predial", label: "Caderneta Predial", icon: "🏠" },
  { value: "contrato_trabalho", label: "Contrato de Trabalho", icon: "📝" },
  { value: "extrato_bancario", label: "Extrato Bancário", icon: "💳" },
  { value: "outro", label: "Outro Documento", icon: "📄" },
];

// Mapeamento de campos extraídos para campos do formulário
const FIELD_LABELS = {
  nome_completo: "Nome Completo",
  nif: "NIF",
  numero_documento: "Nº Documento",
  data_nascimento: "Data Nascimento",
  data_validade: "Validade Doc.",
  naturalidade: "Naturalidade",
  nacionalidade: "Nacionalidade",
  sexo: "Sexo",
  morada: "Morada",
  codigo_postal: "Código Postal",
  localidade: "Localidade",
  salario_liquido: "Salário Líquido",
  salario_bruto: "Salário Bruto",
  empresa: "Empresa",
  tipo_contrato: "Tipo Contrato",
  categoria_profissional: "Categoria",
  rendimento_anual: "Rendimento Anual",
  rendimento_liquido_anual: "Rend. Líquido Anual",
};

const AIDocumentAnalyzer = ({ processId, clientName, onDataExtracted }) => {
  const { token, user } = useAuth();
  const fileInputRef = useRef(null);
  
  const [isOpen, setIsOpen] = useState(false);
  const [activeMethod, setActiveMethod] = useState("upload");
  const [documentType, setDocumentType] = useState("cc");
  const [analyzing, setAnalyzing] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [documentUrl, setDocumentUrl] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // Reset dos dados extraídos pela IA
  const handleResetData = async () => {
    if (!window.confirm("Tem a certeza que deseja limpar todos os dados extraídos pela IA para este cliente?")) {
      return;
    }
    
    setResetting(true);
    try {
      const response = await fetch(`${API_URL}/api/ai/reset-client-data`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          process_id: processId,
          reset_personal: true,
          reset_financial: true,
          reset_real_estate: true,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Erro ao limpar dados");
      }

      const data = await response.json();
      toast.success(data.message);
      
      // Notificar o componente pai para atualizar os dados
      if (onDataExtracted) {
        onDataExtracted({
          personal_data: {},
          financial_data: {},
          real_estate_data: {},
        }, "reset");
      }
    } catch (err) {
      toast.error(err.message);
    } finally {
      setResetting(false);
    }
  };

  // Analisar documento via upload
  const handleAnalyzeUpload = async () => {
    if (!selectedFile) {
      toast.error("Selecione um ficheiro primeiro");
      return;
    }

    setAnalyzing(true);
    setError(null);
    setResult(null);

    try {
      // Converter ficheiro para base64
      const base64 = await fileToBase64(selectedFile);
      const mimeType = selectedFile.type || "application/octet-stream";

      const response = await fetch(`${API_URL}/api/ai/analyze-document`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          document_base64: base64,
          mime_type: mimeType,
          document_type: documentType,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Erro ao analisar documento");
      }

      const data = await response.json();
      setResult(data);
      toast.success("Documento analisado com sucesso!");
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    } finally {
      setAnalyzing(false);
    }
  };

  // Analisar documento via URL
  const handleAnalyzeUrl = async () => {
    if (!documentUrl) {
      toast.error("Cole o URL do documento");
      return;
    }

    setAnalyzing(true);
    setError(null);
    setResult(null);

    try {
      const response = await fetch(`${API_URL}/api/ai/analyze-document`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          document_url: documentUrl,
          document_type: documentType,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Erro ao analisar documento");
      }

      const data = await response.json();
      setResult(data);
      toast.success("Documento analisado com sucesso!");
    } catch (err) {
      setError(err.message);
      toast.error(err.message);
    } finally {
      setAnalyzing(false);
    }
  };

  // Converter ficheiro para base64
  const fileToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => {
        // Remover o prefixo "data:...;base64,"
        const base64 = reader.result.split(",")[1];
        resolve(base64);
      };
      reader.onerror = (error) => reject(error);
    });
  };

  // Aplicar dados extraídos ao processo
  const handleApplyData = () => {
    if (!result?.extracted_data) return;

    const extractedData = result.extracted_data;
    const mappedData = result.mapped_data || {};

    // Chamar callback com os dados para preencher o formulário
    onDataExtracted({
      extractedData,
      mappedData,
      documentType,
    });

    toast.success("Dados aplicados à ficha do cliente!");
    setIsOpen(false);
    resetState();
  };

  const resetState = () => {
    setSelectedFile(null);
    setDocumentUrl("");
    setResult(null);
    setError(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleClose = () => {
    setIsOpen(false);
    resetState();
  };

  return (
    <>
      <Dialog open={isOpen} onOpenChange={setIsOpen}>
        <DialogTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="bg-purple-50 border-purple-200 text-purple-700 hover:bg-purple-100"
            data-testid="ai-analyze-btn"
          >
            <Sparkles className="h-4 w-4 mr-1" />
            Analisar com IA
          </Button>
        </DialogTrigger>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-purple-500" />
              Análise de Documentos com IA
            </DialogTitle>
            <DialogDescription>
              Extraia automaticamente dados de documentos para preencher a ficha de {clientName || "cliente"}
            </DialogDescription>
          </DialogHeader>

        <div className="flex-1 overflow-y-auto py-4 space-y-4">
          {/* Tipo de documento */}
          <div className="space-y-2">
            <Label>Tipo de Documento</Label>
            <Select value={documentType} onValueChange={setDocumentType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DOCUMENT_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.icon} {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Método de análise */}
          <Tabs value={activeMethod} onValueChange={setActiveMethod}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="upload">
                <Upload className="h-4 w-4 mr-1" />
                Upload Ficheiro
              </TabsTrigger>
              <TabsTrigger value="url">
                <Link className="h-4 w-4 mr-1" />
                URL Externa
              </TabsTrigger>
            </TabsList>

            <TabsContent value="upload" className="space-y-3 mt-3">
              <div className="space-y-2">
                <Label>Ficheiro</Label>
                <Input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png,.webp"
                  onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                />
                <p className="text-xs text-muted-foreground">
                  PDF, JPG, PNG ou WebP. Máx. 10MB.
                </p>
              </div>
              {selectedFile && (
                <div className="flex items-center gap-2 p-2 bg-muted/50 rounded">
                  <FileText className="h-4 w-4 text-blue-500" />
                  <span className="text-sm truncate flex-1">{selectedFile.name}</span>
                  <Badge variant="outline">{(selectedFile.size / 1024 / 1024).toFixed(2)} MB</Badge>
                </div>
              )}
              <Button
                onClick={handleAnalyzeUpload}
                disabled={!selectedFile || analyzing}
                className="w-full bg-purple-600 hover:bg-purple-700"
              >
                {analyzing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    A analisar...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" />
                    Analisar Documento
                  </>
                )}
              </Button>
            </TabsContent>

            <TabsContent value="url" className="space-y-3 mt-3">
              <div className="space-y-2">
                <Label>URL do Documento</Label>
                <Input
                  placeholder="https://... ou s3://..."
                  value={documentUrl}
                  onChange={(e) => setDocumentUrl(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Cole o link directo do ficheiro (S3, Google Drive, etc.)
                </p>
              </div>
              <Button
                onClick={handleAnalyzeUrl}
                disabled={!documentUrl || analyzing}
                className="w-full bg-purple-600 hover:bg-purple-700"
              >
                {analyzing ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    A analisar...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" />
                    Analisar Documento
                  </>
                )}
              </Button>
            </TabsContent>
          </Tabs>

          {/* Erro */}
          {error && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
              <AlertCircle className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-medium text-red-800">Erro na análise</p>
                <p className="text-sm text-red-600">{error}</p>
              </div>
            </div>
          )}

          {/* Resultado */}
          {result && result.extracted_data && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-green-600">
                <CheckCircle className="h-5 w-5" />
                <span className="font-medium">Dados extraídos com sucesso!</span>
              </div>

              <ScrollArea className="h-[250px] border rounded-lg">
                <div className="p-3 space-y-2">
                  {Object.entries(result.extracted_data).map(([key, value]) => {
                    if (!value || key === "raw_response") return null;
                    const label = FIELD_LABELS[key] || key.replace(/_/g, " ");
                    return (
                      <div
                        key={key}
                        className="flex items-center justify-between p-2 bg-muted/30 rounded"
                      >
                        <span className="text-sm text-muted-foreground">{label}</span>
                        <span className="font-medium text-sm">{String(value)}</span>
                      </div>
                    );
                  })}
                </div>
              </ScrollArea>

              <Button
                onClick={handleApplyData}
                className="w-full bg-green-600 hover:bg-green-700"
              >
                <ArrowRight className="h-4 w-4 mr-2" />
                Aplicar Dados à Ficha
              </Button>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            Fechar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    
    {/* Botão de Reset - só visível para admin */}
    {user?.role === "admin" && (
      <Button
        variant="ghost"
        size="sm"
        className="text-red-500 hover:text-red-700 hover:bg-red-50"
        onClick={handleResetData}
        disabled={resetting}
        data-testid="ai-reset-btn"
        title="Limpar dados extraídos pela IA"
      >
        {resetting ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <RotateCcw className="h-4 w-4" />
        )}
      </Button>
    )}
    </>
  );
};

export default AIDocumentAnalyzer;
