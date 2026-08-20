/**
 * AIAnalysisTab - Componente de Análise de Documentos por IA (Admin)
 * PACOTE DU: envia JSON { document_base64, mime_type, document_type }
 * alinhado com POST /ai/analyze-document.
 */
import { useState } from "react";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Sparkles, Loader2, FileText, CheckCircle, Copy } from "lucide-react";
import { toast } from "sonner";
import { analyzeDocument } from "../../services/api";

const DOCUMENT_TYPES = [
  { value: "cc", label: "Cartão de Cidadão" },
  { value: "recibo_vencimento", label: "Recibo de Vencimento" },
  { value: "irs", label: "Declaração IRS" },
  { value: "cpcv", label: "CPCV" },
  { value: "caderneta_predial", label: "Caderneta Predial" },
  { value: "outro", label: "Outro Documento" },
];

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const result = String(reader.result || "");
      resolve(result.includes(",") ? result.split(",")[1] : result);
    };
    reader.onerror = (error) => reject(error);
  });
}

const AIAnalysisTab = () => {
  const [file, setFile] = useState(null);
  const [documentType, setDocumentType] = useState("cc");
  const [analyzing, setAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState(null);

  const handleAnalyze = async () => {
    if (!file) {
      toast.error("Selecione um ficheiro primeiro");
      return;
    }
    setAnalyzing(true);
    setAnalysisResult(null);
    try {
      const document_base64 = await fileToBase64(file);
      const response = await analyzeDocument({
        document_base64,
        mime_type: file.type || "application/octet-stream",
        document_type: documentType,
      });
      setAnalysisResult(response.data?.extracted_data || response.data);
      toast.success("Documento analisado com sucesso!");
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao analisar documento"));
    } finally {
      setAnalyzing(false);
    }
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success("Copiado!");
  };

  const resultEntries = analysisResult && typeof analysisResult === "object"
    ? Object.entries(analysisResult)
    : [];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Análise de Documentos com IA
          </CardTitle>
          <CardDescription>
            Utilize inteligência artificial para extrair informação de documentos automaticamente
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>Tipo de Documento</Label>
            <Select value={documentType} onValueChange={setDocumentType}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {DOCUMENT_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Ficheiro</Label>
            <Input
              type="file"
              accept=".pdf,.jpg,.jpeg,.png"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
            />
            <p className="text-xs text-muted-foreground">PDF ou imagem (JPG, PNG). Max 10MB.</p>
          </div>
          <Button
            onClick={handleAnalyze}
            disabled={!file || analyzing}
            className="w-full"
          >
            {analyzing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                A analisar...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4 mr-2" />
                Analisar com IA
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-lg">Resultado da Análise</CardTitle>
        </CardHeader>
        <CardContent>
          {!analysisResult ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p>O resultado da análise aparecerá aqui</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-primary">
                <CheckCircle className="h-5 w-5" />
                <span className="font-medium">Análise concluída</span>
              </div>

              <div className="bg-muted/30 rounded-lg p-4 space-y-3 max-h-[400px] overflow-y-auto">
                {resultEntries.map(([key, value]) => {
                  if (!value || key === "raw_response") return null;
                  const label = key.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
                  return (
                    <div key={key} className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <p className="text-xs text-muted-foreground">{label}</p>
                        <p className="font-medium break-words">{typeof value === "object" ? JSON.stringify(value) : String(value)}</p>
                      </div>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        onClick={() => copyToClipboard(typeof value === "object" ? JSON.stringify(value) : String(value))}
                      >
                        <Copy className="h-3 w-3" />
                      </Button>
                    </div>
                  );
                })}
              </div>

              <p className="text-xs text-muted-foreground mt-4">
                Dica: Pode copiar os valores e colar diretamente nos campos do processo.
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default AIAnalysisTab;
