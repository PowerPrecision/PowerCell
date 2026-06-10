/**
 * HtmlImportModal - Modal para importação de dados de imóveis via HTML
 * 
 * Permite aos utilizadores colar HTML de páginas de imóveis (Idealista, Supercasa, etc.)
 * e extrair dados automaticamente usando IA.
 * Inclui bookmarklets para facilitar a cópia de dados directamente do browser.
 * Suporta navegação para links de agências para extrair mais dados.
 */
import React, { useState, useEffect } from "react";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Textarea } from "./ui/textarea";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { Input } from "./ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Separator } from "./ui/separator";
import { toast } from "sonner";
import {
  Home,
  Sparkles,
  Loader2,
  CheckCircle,
  ClipboardPaste,
  MapPin,
  Euro,
  Maximize,
  Building,
  User,
  Phone,
  Mail,
  FileText,
  Hash,
  Bed,
  Bath,
  AlertTriangle,
  Edit2,
  BookmarkPlus,
  Zap,
  Copy,
  ExternalLink,
  Link2,
  RefreshCw,
  Globe,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const HtmlImportModal = ({ open, onOpenChange, onLeadCreated }) => {
  const [htmlContent, setHtmlContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingDeepScrape, setLoadingDeepScrape] = useState(false);
  const [extractedData, setExtractedData] = useState(null);
  const [editMode, setEditMode] = useState(false);
  const [editedData, setEditedData] = useState({});
  const [activeTab, setActiveTab] = useState("paste");
  const [crmUrl, setCrmUrl] = useState("");
  const [confirmationStep, setConfirmationStep] = useState(false); // Novo: passo de confirmação

  useEffect(() => {
    setCrmUrl(window.location.origin);
  }, []);

  // Bookmarklet SIMPLES - copia dados para clipboard
  const getBookmarkletSimple = () => {
    return `javascript:(function(){var d={url:window.location.href,html:document.documentElement.outerHTML,title:document.title};navigator.clipboard.writeText(JSON.stringify(d)).then(function(){alert('Dados copiados! Cole no CRM para importar.');}).catch(function(){var t=document.createElement('textarea');t.value=JSON.stringify(d);document.body.appendChild(t);t.select();document.execCommand('copy');document.body.removeChild(t);alert('Dados copiados!');});})();`;
  };

  // Bookmarklet AVANÇADO - abre popup com opções
  // NOTA: Este código usa innerHTML porque É UM BOOKMARKLET - corre em
  // OUTROS websites, não na app React. Bookmarklets são scripts isolados
  // que não podem usar React components. Isto NÃO é uma violação do
  // paradigma React - é a única forma de criar overlays noutros sites.
  const getBookmarkletAdvanced = () => {
    const url = crmUrl || window.location.origin;
    return `javascript:(function(){var o=document.createElement('div');o.id='crm-overlay';o.style.cssText='position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.8);z-index:999999;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif';o.innerHTML='<div style="background:white;padding:24px;border-radius:12px;text-align:center;max-width:320px"><div style="font-size:32px;margin-bottom:12px">📋</div><div style="font-size:16px;font-weight:600;margin-bottom:8px">CRM Import</div><div style="font-size:13px;color:%23666;margin-bottom:16px">Os dados foram copiados para o clipboard</div><button onclick="window.open(%27${url}/leads%27,%27_blank%27);this.parentElement.parentElement.remove()" style="background:%23059669;color:white;border:none;padding:10px 20px;border-radius:8px;cursor:pointer;font-size:14px;width:100%">Abrir CRM</button><button onclick="this.parentElement.parentElement.remove()" style="background:transparent;border:1px solid %23ddd;padding:8px 16px;border-radius:8px;cursor:pointer;font-size:13px;margin-top:8px;width:100%">Fechar</button></div>';document.body.appendChild(o);var d={url:window.location.href,html:document.documentElement.outerHTML};navigator.clipboard.writeText(JSON.stringify(d));})();`;
  };

  const resetModal = () => {
    setHtmlContent("");
    setExtractedData(null);
    setEditMode(false);
    setEditedData({});
    setLoadingDeepScrape(false);
    setConfirmationStep(false);
  };

  const handleClose = () => {
    resetModal();
    onOpenChange(false);
  };

  const handleExtract = async () => {
    if (!htmlContent.trim()) {
      toast.error("Cole o conteúdo da página primeiro");
      return;
    }

    setLoading(true);
    setExtractedData(null);

    try {
      const token = localStorage.getItem("token");
      
      // Tentar parsear como JSON (do bookmarklet)
      let dataToSend = { html: htmlContent };
      try {
        const parsed = JSON.parse(htmlContent);
        if (parsed.html) {
          dataToSend = { html: parsed.html, url: parsed.url };
        }
      } catch {
        // Não é JSON, é HTML/texto directo
      }

      const response = await fetch(`${API_URL}/api/leads/extract-html`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(dataToSend),
      });

      if (response.ok) {
        const data = await response.json();
        setExtractedData(data);
        setEditedData(data);
        toast.success("Dados extraídos com sucesso!");
      } else {
        const error = await response.json();
        toast.error(extractErrorMessage(error.detail, "Erro ao extrair dados"));
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao processar dados");
    } finally {
      setLoading(false);
    }
  };

  // Navegar para o link da agência e extrair mais dados
  const handleDeepScrape = async () => {
    const agencyLink = extractedData?.agency_link;
    if (!agencyLink) {
      toast.error("Nenhum link de agência disponível");
      return;
    }

    setLoadingDeepScrape(true);

    try {
      const token = localStorage.getItem("token");
      
      // Usar endpoint de scraping por URL
      const response = await fetch(`${API_URL}/api/scraper/scrape`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ url: agencyLink, use_cache: false }),
      });

      const result = await response.json();
      
      if (response.ok && result.success && result.data) {
        const newData = result.data;
        
        // Merge dos dados - novos dados têm prioridade se não vazios
        const mergedData = { ...extractedData };
        
        // Campos que queremos actualizar do deep scrape
        const fieldsToMerge = [
          'titulo', 'preco', 'localizacao', 'tipologia', 'area', 'area_util',
          'quartos', 'casas_banho', 'descricao', 'agente_nome', 'agente_telefone',
          'agente_email', 'agencia_nome', 'referencia', 'foto_principal'
        ];
        
        for (const field of fieldsToMerge) {
          if (newData[field] && !mergedData[field]) {
            mergedData[field] = newData[field];
          }
        }
        
        // Guardar fonte do deep scrape
        mergedData._deep_scraped = true;
        mergedData._deep_source = agencyLink;
        
        // Se a referência do deep scrape é diferente, guardar ambas
        if (newData.referencia && mergedData.referencia && newData.referencia !== mergedData.referencia) {
          mergedData._referencia_original = mergedData.referencia;
          mergedData.referencia = newData.referencia;
        }
        
        setExtractedData(mergedData);
        setEditedData(mergedData);
        toast.success("Dados adicionais extraídos do site da agência!");
      } else {
        // Erro ou sem dados
        const errorMsg = result.error || "Não foi possível extrair dados do link";
        toast.error(errorMsg);
        
        // Se há dados parciais, mostrar
        if (result.data?.partial_data) {
          toast.info("Alguns dados parciais foram obtidos");
        }
      }
    } catch (error) {
      console.error("Erro no deep scrape:", error);
      toast.error("Erro ao navegar para o link da agência");
    } finally {
      setLoadingDeepScrape(false);
    }
  };

  const handleFieldChange = (field, value) => {
    setEditedData(prev => ({
      ...prev,
      [field]: value
    }));
  };

  const handleCreateLead = async () => {
    const dataToUse = editMode ? editedData : extractedData;
    if (!dataToUse) return;

    try {
      const token = localStorage.getItem("token");
      
      let leadUrl = dataToUse.url || dataToUse._source_url || "";
      
      if (leadUrl && !leadUrl.startsWith('http://') && !leadUrl.startsWith('https://')) {
        leadUrl = "";
      }
      
      const leadData = {
        url: leadUrl || `https://imported.local/${Date.now()}`,
        title: dataToUse.titulo || dataToUse.title || "Imóvel Importado",
        price: dataToUse.preco || dataToUse.price,
        location: dataToUse.localizacao || dataToUse.location,
        typology: dataToUse.tipologia || dataToUse.typology,
        area: dataToUse.area_util || dataToUse.area,
        photo_url: dataToUse.foto_principal || dataToUse.photo_url,
        notes: `Importado via HTML. ${dataToUse._deep_scraped ? `Deep scrape: ${dataToUse._deep_source}` : ''}`,
        consultant: dataToUse.agente_nome ? {
          name: dataToUse.agente_nome,
          phone: dataToUse.agente_telefone,
          email: dataToUse.agente_email,
          agency_name: dataToUse.agencia_nome,
        } : dataToUse.consultant,
      };
      
      const response = await fetch(`${API_URL}/api/leads`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(leadData),
      });

      if (response.ok) {
        toast.success("Lead criado com sucesso!");
        handleClose();
        if (onLeadCreated) {
          onLeadCreated();
        }
      } else {
        const errorData = await response.json();
        toast.error(extractErrorMessage(errorData.detail, "Erro ao criar lead"));
      }
    } catch (error) {
      console.error("Erro ao criar lead:", error);
      toast.error("Erro ao criar lead");
    }
  };

  const formatPrice = (price) => {
    if (!price) return "N/D";
    if (typeof price === 'number') {
      return `€${price.toLocaleString()}`;
    }
    return price;
  };

  const copyBookmarklet = (code, name) => {
    navigator.clipboard.writeText(code).then(() => {
      toast.success(`Código do bookmarklet "${name}" copiado!`);
    }).catch(() => {
      toast.error("Erro ao copiar");
    });
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-hidden flex flex-col p-0">
        <DialogHeader className="px-6 pt-6 pb-4 border-b">
          <DialogTitle className="flex items-center gap-2">
            <ClipboardPaste className="h-5 w-5 text-primary" />
            Importar Imóvel via HTML
          </DialogTitle>
          <DialogDescription>
            Cole o conteúdo de uma página de imóvel para extrair dados automaticamente
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto overflow-x-auto px-6 py-4 space-y-4">
          {!extractedData ? (
            <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="paste" className="flex items-center gap-2">
                  <ClipboardPaste className="h-4 w-4" />
                  Colar Página
                </TabsTrigger>
                <TabsTrigger value="bookmarklet" className="flex items-center gap-2">
                  <BookmarkPlus className="h-4 w-4" />
                  Bookmarklet
                </TabsTrigger>
              </TabsList>

              <TabsContent value="paste" className="space-y-4 mt-4">
                <div className="p-3 bg-blue-50 dark:bg-blue-950/50 rounded-lg text-sm">
                  <p className="text-blue-700 dark:text-blue-300">
                    <strong>Como usar:</strong> Na página do imóvel, prima <kbd className="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900 rounded text-xs mx-1">Ctrl+A</kbd> para seleccionar tudo, depois <kbd className="px-1.5 py-0.5 bg-blue-100 dark:bg-blue-900 rounded text-xs mx-1">Ctrl+C</kbd> para copiar e cole aqui.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="html-content">Conteúdo da Página</Label>
                  <Textarea
                    id="html-content"
                    placeholder="Cole aqui o conteúdo da página do imóvel (Ctrl+V)..."
                    value={htmlContent}
                    onChange={(e) => setHtmlContent(e.target.value)}
                    className="min-h-[180px] font-mono text-xs"
                    data-testid="html-import-textarea"
                  />
                  <p className="text-xs text-muted-foreground">
                    {htmlContent.length > 0 ? `${htmlContent.length.toLocaleString()} caracteres` : "Aguardando conteúdo..."}
                  </p>
                </div>
              </TabsContent>

              <TabsContent value="bookmarklet" className="space-y-4 mt-4">
                <p className="text-sm text-muted-foreground">
                  Arraste um dos botões para a sua barra de favoritos, ou copie o código:
                </p>
                
                {/* Bookmarklet Simples */}
                <div className="p-4 border rounded-lg">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Copy className="h-4 w-4 text-primary" />
                      <span className="font-medium">Copiar Imóvel</span>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => copyBookmarklet(getBookmarkletSimple(), "Copiar Imóvel")}
                      data-testid="copy-bookmarklet-simple"
                    >
                      <Copy className="h-3 w-3 mr-1" />
                      Copiar código
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground mb-3">
                    Copia os dados para o clipboard. Depois cole na aba "Colar Página".
                  </p>
                  <div className="flex flex-col items-center gap-3">
                    {/* Link para arrastar - não usa onClick */}
                    <a
                      href={getBookmarkletSimple()}
                      draggable="true"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg font-medium shadow hover:shadow-lg transition-shadow cursor-grab active:cursor-grabbing select-none"
                      title="Arraste para a barra de favoritos"
                      data-testid="bookmarklet-simple-drag"
                    >
                      <Sparkles className="h-4 w-4" />
                      Copiar Imóvel
                    </a>
                    <p className="text-xs text-muted-foreground text-center">
                      Arraste o botão acima para a barra de favoritos
                    </p>
                  </div>
                </div>
                
                {/* Bookmarklet Avançado */}
                <div className="p-4 border rounded-lg bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950/30 dark:to-emerald-950/30 border-green-200 dark:border-green-800">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Zap className="h-4 w-4 text-green-600" />
                      <span className="font-medium text-green-700 dark:text-green-400">Recomendado</span>
                      <Badge variant="secondary" className="text-xs">Com Popup</Badge>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => copyBookmarklet(getBookmarkletAdvanced(), "CRM Import")}
                      data-testid="copy-bookmarklet-advanced"
                    >
                      <Copy className="h-3 w-3 mr-1" />
                      Copiar código
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground mb-3">
                    Copia dados e mostra popup para abrir o CRM directamente.
                  </p>
                  <div className="flex flex-col items-center gap-3">
                    {/* Link para arrastar - não usa onClick */}
                    <a
                      href={getBookmarkletAdvanced()}
                      draggable="true"
                      className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-green-600 to-emerald-600 text-white rounded-lg font-medium shadow-lg hover:shadow-xl transition-shadow cursor-grab active:cursor-grabbing select-none"
                      title="Arraste para a barra de favoritos"
                      data-testid="bookmarklet-advanced-drag"
                    >
                      <Zap className="h-4 w-4" />
                      CRM Import
                    </a>
                    <p className="text-xs text-muted-foreground text-center">
                      Arraste o botão acima para a barra de favoritos
                    </p>
                  </div>
                </div>
                
                <div className="p-3 bg-amber-50 dark:bg-amber-950/50 rounded-lg text-sm">
                  <p className="text-amber-700 dark:text-amber-300">
                    <strong>Como usar:</strong>
                  </p>
                  <ol className="text-amber-700 dark:text-amber-300 text-xs mt-1 space-y-1 list-decimal ml-4">
                    <li>Arraste o botão verde para a barra de favoritos do browser</li>
                    <li>Vá à página do imóvel (Idealista, Supercasa, etc.)</li>
                    <li>Clique no favorito - os dados serão copiados</li>
                    <li>Volte aqui e cole (Ctrl+V) na aba "Colar Página"</li>
                  </ol>
                </div>
              </TabsContent>
            </Tabs>
          ) : (
            <ScrollArea className="max-h-[60vh]">
              <div className="space-y-4">
                {/* Header com badges */}
                <div className="flex items-center justify-between flex-wrap gap-2">
                  <div className="flex items-center gap-2">
                    {confirmationStep ? (
                      <>
                        <AlertTriangle className="h-5 w-5 text-amber-600" />
                        <span className="font-medium text-amber-700 dark:text-amber-400">Confirme antes de criar o lead</span>
                      </>
                    ) : (
                      <>
                        <CheckCircle className="h-5 w-5 text-green-600" />
                        <span className="font-medium text-green-700 dark:text-green-400">Dados Extraídos</span>
                      </>
                    )}
                    {extractedData._extracted_by && (
                      <Badge variant="outline" className="text-xs">
                        {extractedData._extracted_by}
                      </Badge>
                    )}
                    {extractedData._deep_scraped && (
                      <Badge variant="secondary" className="text-xs bg-blue-100 text-blue-700">
                        + Deep Scrape
                      </Badge>
                    )}
                  </div>
                  {editMode && (
                    <Badge variant="secondary" className="text-xs bg-amber-100 text-amber-700">
                      Modo de Edição
                    </Badge>
                  )}
                </div>

                {/* Aviso se poucos dados */}
                {!extractedData.titulo && !extractedData.preco && !extractedData.localizacao && (
                  <div className="p-3 bg-amber-50 dark:bg-amber-950/50 rounded-lg flex items-start gap-2">
                    <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                    <div className="text-sm text-amber-700 dark:text-amber-300">
                      <strong>Atenção:</strong> Poucos dados foram extraídos. Considere editar manualmente.
                    </div>
                  </div>
                )}

                {/* Aviso de confirmação final */}
                {confirmationStep && (
                  <div className="p-4 bg-green-50 dark:bg-green-950/50 rounded-lg border border-green-200 dark:border-green-800">
                    <div className="flex items-start gap-3">
                      <CheckCircle className="h-6 w-6 text-green-600 flex-shrink-0 mt-0.5" />
                      <div className="flex-1">
                        <h4 className="font-medium text-green-800 dark:text-green-300 mb-1">
                          Pronto para criar o lead?
                        </h4>
                        <p className="text-sm text-green-700 dark:text-green-400">
                          Reveja os dados abaixo. Se estiver tudo correcto, clique em "Criar Lead Agora".
                          {editMode && " Os dados editados serão usados."}
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {/* Link da Agência - Botão para navegar */}
                {extractedData.agency_link && (
                  <div className="p-4 border rounded-lg bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-950/30 dark:to-indigo-950/30 border-blue-200 dark:border-blue-800">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Link2 className="h-4 w-4 text-blue-600" />
                        <span className="font-medium text-blue-700 dark:text-blue-400">Link da Agência Detectado</span>
                      </div>
                      <div className="flex gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => window.open(extractedData.agency_link, '_blank')}
                        >
                          <ExternalLink className="h-3 w-3 mr-1" />
                          Abrir
                        </Button>
                        <Button
                          variant="default"
                          size="sm"
                          onClick={handleDeepScrape}
                          disabled={loadingDeepScrape}
                          className="bg-blue-600 hover:bg-blue-700"
                        >
                          {loadingDeepScrape ? (
                            <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                          ) : (
                            <RefreshCw className="h-3 w-3 mr-1" />
                          )}
                          Extrair Mais Dados
                        </Button>
                      </div>
                    </div>
                    <p className="text-xs text-blue-600 dark:text-blue-400 mt-2 truncate">
                      {extractedData.agency_link}
                    </p>
                  </div>
                )}

                {/* Grid de dados */}
                <div className="grid grid-cols-2 gap-3">
                  {/* Título */}
                  <div className="col-span-2 p-3 bg-muted/50 rounded-lg">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                      <Home className="h-3 w-3" /> Título
                    </Label>
                    {editMode ? (
                      <Input
                        value={editedData.titulo || editedData.title || ""}
                        onChange={(e) => handleFieldChange("titulo", e.target.value)}
                        placeholder="Título do imóvel"
                      />
                    ) : (
                      <p className="font-medium">{extractedData.titulo || extractedData.title || "N/D"}</p>
                    )}
                  </div>

                  {/* Preço */}
                  <div className="p-3 bg-muted/50 rounded-lg">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                      <Euro className="h-3 w-3" /> Preço
                    </Label>
                    {editMode ? (
                      <Input
                        type="number"
                        value={editedData.preco || editedData.price || ""}
                        onChange={(e) => handleFieldChange("preco", e.target.value ? Number(e.target.value) : null)}
                        placeholder="250000"
                      />
                    ) : (
                      <p className="font-bold text-lg text-green-600">
                        {formatPrice(extractedData.preco || extractedData.price)}
                      </p>
                    )}
                  </div>

                  {/* Localização */}
                  <div className="p-3 bg-muted/50 rounded-lg">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                      <MapPin className="h-3 w-3" /> Localização
                    </Label>
                    {editMode ? (
                      <Input
                        value={editedData.localizacao || editedData.location || ""}
                        onChange={(e) => handleFieldChange("localizacao", e.target.value)}
                        placeholder="Lisboa, Portugal"
                      />
                    ) : (
                      <p className="font-medium">{extractedData.localizacao || extractedData.location || "N/D"}</p>
                    )}
                  </div>

                  {/* Tipologia */}
                  <div className="p-3 bg-muted/50 rounded-lg">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                      <Bed className="h-3 w-3" /> Tipologia
                    </Label>
                    {editMode ? (
                      <Input
                        value={editedData.tipologia || editedData.typology || ""}
                        onChange={(e) => handleFieldChange("tipologia", e.target.value)}
                        placeholder="T2"
                      />
                    ) : (
                      <p className="font-medium">{extractedData.tipologia || extractedData.typology || "N/D"}</p>
                    )}
                  </div>

                  {/* Área */}
                  <div className="p-3 bg-muted/50 rounded-lg">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                      <Maximize className="h-3 w-3" /> Área
                    </Label>
                    {editMode ? (
                      <Input
                        value={editedData.area_util || editedData.area || ""}
                        onChange={(e) => handleFieldChange("area_util", e.target.value)}
                        placeholder="85"
                      />
                    ) : (
                      <p className="font-medium">
                        {(extractedData.area_util || extractedData.area) 
                          ? `${extractedData.area_util || extractedData.area} m²` 
                          : "N/D"}
                      </p>
                    )}
                  </div>

                  {/* Quartos e WC */}
                  <div className="p-3 bg-muted/50 rounded-lg">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                      <Bed className="h-3 w-3" /> Quartos / WC
                    </Label>
                    {editMode ? (
                      <div className="flex gap-2">
                        <Input
                          type="number"
                          value={editedData.quartos || ""}
                          onChange={(e) => handleFieldChange("quartos", e.target.value ? Number(e.target.value) : null)}
                          placeholder="Quartos"
                          className="w-20"
                        />
                        <Input
                          type="number"
                          value={editedData.casas_banho || ""}
                          onChange={(e) => handleFieldChange("casas_banho", e.target.value ? Number(e.target.value) : null)}
                          placeholder="WC"
                          className="w-20"
                        />
                      </div>
                    ) : (
                      <div className="flex gap-2">
                        {extractedData.quartos && <Badge variant="secondary">{extractedData.quartos} quartos</Badge>}
                        {extractedData.casas_banho && <Badge variant="outline">{extractedData.casas_banho} WC</Badge>}
                        {!extractedData.quartos && !extractedData.casas_banho && <span className="text-muted-foreground">N/D</span>}
                      </div>
                    )}
                  </div>

                  {/* Referência */}
                  <div className="p-3 bg-muted/50 rounded-lg">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                      <Hash className="h-3 w-3" /> Referência
                    </Label>
                    {editMode ? (
                      <Input
                        value={editedData.referencia || ""}
                        onChange={(e) => handleFieldChange("referencia", e.target.value)}
                        placeholder="REF123"
                      />
                    ) : (
                      <div>
                        <p className="font-mono text-sm">{extractedData.referencia || "N/D"}</p>
                        {extractedData._referencia_original && extractedData._referencia_original !== extractedData.referencia && (
                          <p className="text-xs text-muted-foreground mt-1">
                            (Original: {extractedData._referencia_original})
                          </p>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Agência */}
                  <div className="p-3 bg-muted/50 rounded-lg">
                    <Label className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                      <Building className="h-3 w-3" /> Agência
                    </Label>
                    {editMode ? (
                      <Input
                        value={editedData.agencia_nome || ""}
                        onChange={(e) => handleFieldChange("agencia_nome", e.target.value)}
                        placeholder="Nome da agência"
                      />
                    ) : (
                      <p className="font-medium">{extractedData.agencia_nome || extractedData.agency_name || "N/D"}</p>
                    )}
                  </div>

                  {/* Contacto */}
                  {(extractedData.agente_nome || extractedData.agente_telefone || extractedData.agente_email || editMode) && (
                    <div className="col-span-2 p-3 bg-muted/50 rounded-lg">
                      <Label className="text-xs text-muted-foreground flex items-center gap-1 mb-2">
                        <User className="h-3 w-3" /> Contacto
                      </Label>
                      {editMode ? (
                        <div className="grid grid-cols-3 gap-2">
                          <Input
                            value={editedData.agente_nome || ""}
                            onChange={(e) => handleFieldChange("agente_nome", e.target.value)}
                            placeholder="Nome"
                          />
                          <Input
                            value={editedData.agente_telefone || ""}
                            onChange={(e) => handleFieldChange("agente_telefone", e.target.value)}
                            placeholder="Telefone"
                          />
                          <Input
                            value={editedData.agente_email || ""}
                            onChange={(e) => handleFieldChange("agente_email", e.target.value)}
                            placeholder="Email"
                          />
                        </div>
                      ) : (
                        <div className="flex flex-wrap gap-3">
                          {extractedData.agente_nome && (
                            <span className="flex items-center gap-1">
                              <User className="h-3 w-3" /> {extractedData.agente_nome}
                            </span>
                          )}
                          {extractedData.agente_telefone && (
                            <a href={`tel:${extractedData.agente_telefone}`} className="flex items-center gap-1 text-blue-600 hover:underline">
                              <Phone className="h-3 w-3" /> {extractedData.agente_telefone}
                            </a>
                          )}
                          {extractedData.agente_email && (
                            <a href={`mailto:${extractedData.agente_email}`} className="flex items-center gap-1 text-blue-600 hover:underline">
                              <Mail className="h-3 w-3" /> {extractedData.agente_email}
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Descrição */}
                  {(extractedData.descricao || editMode) && (
                    <div className="col-span-2 p-3 bg-muted/50 rounded-lg">
                      <Label className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
                        <FileText className="h-3 w-3" /> Descrição
                      </Label>
                      {editMode ? (
                        <Textarea
                          value={editedData.descricao || ""}
                          onChange={(e) => handleFieldChange("descricao", e.target.value)}
                          placeholder="Descrição do imóvel"
                          className="min-h-[100px]"
                        />
                      ) : (
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                          {extractedData.descricao || extractedData.description}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </ScrollArea>
          )}
        </div>

        <Separator className="my-2" />

        <DialogFooter className="gap-2 sm:gap-0">
          {!extractedData ? (
            <>
              <Button variant="outline" onClick={handleClose}>
                Cancelar
              </Button>
              <Button 
                onClick={handleExtract} 
                disabled={loading || !htmlContent.trim()}
                data-testid="extract-html-btn"
              >
                {loading ? (
                  <>
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                    A extrair...
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4 mr-2" />
                    Extrair Dados
                  </>
                )}
              </Button>
            </>
          ) : !confirmationStep ? (
            // Passo de revisão dos dados
            <>
              <Button 
                variant="outline" 
                onClick={() => {
                  setExtractedData(null);
                  setEditMode(false);
                  setConfirmationStep(false);
                }}
              >
                Voltar
              </Button>
              <Button
                variant="outline"
                onClick={() => setEditMode(!editMode)}
              >
                <Edit2 className="h-4 w-4 mr-1" />
                {editMode ? "Ver Original" : "Editar Dados"}
              </Button>
              <Button 
                onClick={() => setConfirmationStep(true)}
                data-testid="confirm-data-btn"
              >
                <CheckCircle className="h-4 w-4 mr-2" />
                Confirmar Dados
              </Button>
            </>
          ) : (
            // Passo de confirmação final
            <>
              <Button 
                variant="outline" 
                onClick={() => setConfirmationStep(false)}
              >
                Voltar e Editar
              </Button>
              <Button 
                onClick={handleCreateLead}
                className="bg-green-600 hover:bg-green-700"
                data-testid="create-lead-from-html-btn"
              >
                <Building className="h-4 w-4 mr-2" />
                Criar Lead Agora
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default HtmlImportModal;
