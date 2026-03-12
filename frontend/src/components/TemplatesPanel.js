/**
 * TemplatesPanel - Painel de Templates e Minutas
 * Permite gerar e descarregar minutas preenchidas automaticamente
 * e aceder aos webmails para envio de emails
 */
import React, { useState } from 'react';
import axios from 'axios';
import { 
  FileText, 
  Download, 
  ExternalLink, 
  Mail, 
  AlertTriangle,
  FileSignature,
  Bell,
  Loader2,
  Copy,
  Check,
  AlertCircle,
  X
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { 
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from './ui/dialog';
import { Alert, AlertDescription, AlertTitle } from './ui/alert.jsx';
import { toast } from 'sonner';

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

// URLs dos webmails
const WEBMAIL_URLS = {
  precision: "http://webmail.precisioncredito.pt/",
  power: "https://webmail2.hcpro.pt/Mondo/lang/sys/login.aspx"
};

const TemplatesPanel = ({ processId, token }) => {
  const [loading, setLoading] = useState(null);
  const [showPreview, setShowPreview] = useState(false);
  const [previewContent, setPreviewContent] = useState({ title: '', content: '' });
  const [copied, setCopied] = useState(false);
  const [validationError, setValidationError] = useState(null);

  // Tipos de templates disponíveis
  const templates = [
    {
      id: 'cpcv',
      name: 'CPCV - Contrato Promessa',
      description: 'Contrato Promessa de Compra e Venda preenchido',
      icon: FileSignature,
      endpoint: `/api/templates/process/${processId}/cpcv`,
      downloadEndpoint: `/api/templates/process/${processId}/cpcv/download`,
    },
    {
      id: 'valuation-appeal',
      name: 'Apelação de Avaliação',
      description: 'Email para contestar avaliação bancária',
      icon: AlertTriangle,
      iconColor: 'text-amber-500',
      endpoint: `/api/templates/process/${processId}/valuation-appeal`,
      downloadEndpoint: `/api/templates/process/${processId}/valuation-appeal/download`,
    },
    {
      id: 'deed-reminder',
      name: 'Lembrete de Escritura',
      description: 'Email de lembrete para o cliente sobre a escritura',
      icon: Bell,
      endpoint: `/api/templates/process/${processId}/deed-reminder`,
      downloadEndpoint: `/api/templates/process/${processId}/deed-reminder/download`,
    },
  ];

  // Pré-visualizar template
  const handlePreview = async (template) => {
    setLoading(template.id);
    setValidationError(null);
    try {
      const response = await axios.get(`${API_URL}${template.endpoint}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      
      setPreviewContent({
        title: template.name,
        content: response.data.template || ''
      });
      setShowPreview(true);
    } catch (error) {
      // Verificar se é erro de validação (400)
      if (error.response?.status === 400) {
        const detail = error.response.data?.detail;
        if (detail?.missing_fields) {
          setValidationError({
            template: template.name,
            message: detail?.message || "Dados insuficientes",
            missingFields: detail?.missing_fields || [],
            fullMessage: detail?.missing_fields_message || ""
          });
          return;
        }
      }
      toast.error('Erro ao carregar template');
      console.error(error);
    } finally {
      setLoading(null);
    }
  };

  // Download do template
  const handleDownload = async (template) => {
    setLoading(`download-${template.id}`);
    setValidationError(null);
    try {
      const response = await axios.get(`${API_URL}${template.downloadEndpoint}`, {
        headers: { Authorization: `Bearer ${token}` },
        responseType: 'blob'
      });
      
      const blob = response.data;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${template.id}_${processId}.txt`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      
      toast.success('Template descarregado!');
    } catch (error) {
      // Verificar se é erro de validação (400)
      if (error.response?.status === 400) {
        // Para respostas blob com erro, precisamos converter
        try {
          const text = await error.response.data.text();
          const errorData = JSON.parse(text);
          const detail = errorData.detail;
          if (detail?.missing_fields) {
            setValidationError({
              template: template.name,
              message: detail?.message || "Dados insuficientes",
              missingFields: detail?.missing_fields || [],
              fullMessage: detail?.missing_fields_message || ""
            });
            return;
          }
        } catch (parseError) {
          console.error("Erro ao processar resposta de validação:", parseError);
        }
      }
      toast.error('Erro ao descarregar template');
      console.error(error);
    } finally {
      setLoading(null);
    }
  };

  // Copiar conteúdo
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(previewContent.content);
      setCopied(true);
      toast.success('Copiado para a área de transferência!');
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      toast.error('Erro ao copiar');
    }
  };

  // Abrir webmail
  const openWebmail = (webmail) => {
    window.open(WEBMAIL_URLS[webmail], '_blank');
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <FileText className="h-5 w-5 text-blue-600" />
            Templates e Minutas
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Alerta de Erro de Validação */}
          {validationError && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle className="flex items-center justify-between">
                <span>Dados em Falta para "{validationError.template}"</span>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="h-6 w-6 p-0"
                  onClick={() => setValidationError(null)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </AlertTitle>
              <AlertDescription>
                <p className="mb-2">Para gerar esta minuta, preencha os seguintes campos na ficha do cliente:</p>
                <ul className="list-disc pl-5 space-y-1">
                  {validationError.missingFields.map((field, idx) => (
                    <li key={idx} className="text-sm font-medium">{field}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {/* Botões de Webmail */}
          <div className="pb-3 border-b">
            <p className="text-sm text-muted-foreground mb-2">Abrir Webmail:</p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => openWebmail('precision')}
                className="flex-1"
                data-testid="webmail-precision-btn"
              >
                <Mail className="h-4 w-4 mr-2" />
                Precision
                <ExternalLink className="h-3 w-3 ml-1" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => openWebmail('power')}
                className="flex-1"
                data-testid="webmail-power-btn"
              >
                <Mail className="h-4 w-4 mr-2" />
                Power
                <ExternalLink className="h-3 w-3 ml-1" />
              </Button>
            </div>
          </div>

          {/* Lista de Templates */}
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">Minutas Disponíveis:</p>
            {templates.map((template) => {
              const Icon = template.icon;
              return (
                <div 
                  key={template.id}
                  className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <Icon className={`h-5 w-5 ${template.iconColor || 'text-gray-600'}`} />
                    <div>
                      <p className="font-medium text-sm">{template.name}</p>
                      <p className="text-xs text-muted-foreground">{template.description}</p>
                    </div>
                  </div>
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handlePreview(template)}
                      disabled={loading === template.id}
                      title="Pré-visualizar"
                      data-testid={`preview-${template.id}-btn`}
                    >
                      {loading === template.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <FileText className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleDownload(template)}
                      disabled={loading === `download-${template.id}`}
                      title="Descarregar"
                      data-testid={`download-${template.id}-btn`}
                    >
                      {loading === `download-${template.id}` ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Dialog de Pré-visualização */}
      <Dialog open={showPreview} onOpenChange={setShowPreview}>
        <DialogContent className="max-w-3xl max-h-[80vh]">
          <DialogHeader>
            <DialogTitle>{previewContent.title}</DialogTitle>
            <DialogDescription>
              Copie o texto abaixo e cole no corpo do email
            </DialogDescription>
          </DialogHeader>
          
          <div className="relative">
            <div className="absolute top-2 right-2 z-10">
              <Button 
                size="sm" 
                variant="secondary"
                onClick={handleCopy}
                data-testid="copy-template-btn"
              >
                {copied ? (
                  <>
                    <Check className="h-4 w-4 mr-1" />
                    Copiado!
                  </>
                ) : (
                  <>
                    <Copy className="h-4 w-4 mr-1" />
                    Copiar
                  </>
                )}
              </Button>
            </div>
            
            <pre className="bg-gray-50 p-4 rounded-lg text-sm overflow-auto max-h-[50vh] whitespace-pre-wrap font-mono border">
              {previewContent.content}
            </pre>
          </div>

          <div className="flex justify-between pt-4 border-t">
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => openWebmail('precision')}
              >
                <Mail className="h-4 w-4 mr-2" />
                Abrir Webmail Precision
              </Button>
              <Button
                variant="outline"
                onClick={() => openWebmail('power')}
              >
                <Mail className="h-4 w-4 mr-2" />
                Abrir Webmail Power
              </Button>
            </div>
            <Button variant="ghost" onClick={() => setShowPreview(false)}>
              Fechar
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default TemplatesPanel;
