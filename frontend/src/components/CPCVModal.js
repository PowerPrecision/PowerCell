/**
 * CPCVModal - Modal para gerar Contrato Promessa Compra e Venda
 * Permite preencher dados do CPCV e imprimir o documento com minuta
 */
import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Textarea } from "./ui/textarea";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import {
  FileSignature,
  Printer,
  Loader2,
  Building2,
  User,
  Users,
  CreditCard,
  Calendar,
  FileText,
  Eye,
} from "lucide-react";
import { toast } from "sonner";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Cores dos bancos portugueses
const BANK_COLORS = {
  "ABANCA": "bg-red-500 text-white",
  "BBVA": "bg-blue-600 text-white",
  "BEST": "bg-green-600 text-white",
  "BIG": "bg-orange-500 text-white",
  "BPI": "bg-yellow-400 text-yellow-900",
  "CGD": "bg-red-600 text-white",
  "Crédito Agrícola": "bg-green-500 text-white",
  "CTT": "bg-red-400 text-white",
  "Millennium bcp": "bg-red-500 text-white",
  "Novo Banco": "bg-gray-700 text-white",
  "Popular": "bg-blue-500 text-white",
  "Santander Totta": "bg-red-600 text-white",
  "Bankinter": "bg-blue-800 text-white",
  "ActivoBank": "bg-teal-500 text-white",
  "Eurobic": "bg-red-500 text-white",
};

const CPCVModal = ({ open, onOpenChange, process, personalData, financialData, realEstateData, token }) => {
  const [loading, setLoading] = useState(false);
  const [minutas, setMinutas] = useState([]);
  const [selectedMinuta, setSelectedMinuta] = useState(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [generatedDocument, setGeneratedDocument] = useState("");

  // Estado do formulário CPCV
  const [cpcvData, setCpcvData] = useState({
    // Dados do Imóvel
    tipo_imovel: "",
    tipologia: "",
    area: "",
    morada_imovel: "",
    valor_imovel: "",
    matriz: "",
    artigo_matriz: "",
    
    // Dados do Vendedor
    vendedor_nome: "",
    vendedor_nif: "",
    vendedor_morada: "",
    vendedor_telefone: "",
    vendedor_email: "",
    vendedor_estado_civil: "",
    
    // Dados do Comprador Principal
    comprador_nome: "",
    comprador_nif: "",
    comprador_morada: "",
    comprador_telefone: "",
    comprador_email: "",
    comprador_estado_civil: "",
    
    // Co-comprador (se aplicável)
    co_comprador_nome: "",
    co_comprador_nif: "",
    co_comprador_morada: "",
    co_comprador_estado_civil: "",
    
    // Valores e Datas
    valor_sinal: "",
    data_cpcv: new Date().toISOString().split('T')[0],
    data_escritura_prevista: "",
    local_escritura: "",
    
    // Condições
    clausulas_especiais: "",
    penalizacao: "",
    
    // Mediador
    mediador_nome: "",
    mediador_ami: "",
  });

  // Carregar minutas CPCV disponíveis
  useEffect(() => {
    if (open) {
      fetchMinutas();
      preencherDadosProcesso();
    }
  }, [open, process, personalData, financialData, realEstateData]);

  const fetchMinutas = async () => {
    try {
      const response = await fetch(`${API_URL}/api/minutas`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        // Filtrar apenas minutas de contrato
        const cpcvMinutas = (data.minutas || []).filter(
          m => m.categoria === "contrato" && 
          (m.titulo?.toLowerCase().includes("cpcv") || 
           m.titulo?.toLowerCase().includes("promessa") ||
           m.tags?.some(t => t.toLowerCase().includes("cpcv")))
        );
        setMinutas(cpcvMinutas);
      }
    } catch (error) {
      console.error("Erro ao carregar minutas:", error);
    }
  };

  const preencherDadosProcesso = () => {
    if (!process) return;

    setCpcvData(prev => ({
      ...prev,
      // Dados do Imóvel
      tipo_imovel: realEstateData?.tipo_imovel || "",
      tipologia: realEstateData?.tipologia || realEstateData?.num_quartos || "",
      area: realEstateData?.area || "",
      morada_imovel: realEstateData?.morada_imovel || realEstateData?.localizacao || "",
      valor_imovel: realEstateData?.valor_imovel || financialData?.valor_pretendido || "",
      
      // Dados do Comprador Principal (cliente do processo)
      comprador_nome: process.client_name || personalData?.nome || "",
      comprador_nif: personalData?.nif || "",
      comprador_morada: personalData?.morada_fiscal || personalData?.morada || "",
      comprador_telefone: process.client_phone || personalData?.telefone || "",
      comprador_email: process.client_email || personalData?.email || "",
      comprador_estado_civil: personalData?.estado_civil || "",
      
      // Co-comprador (segundo titular)
      co_comprador_nome: process.second_client_name || process.titular2_data?.nome || process.titular2_data?.name || "",
      co_comprador_nif: process.titular2_data?.nif || "",
      co_comprador_morada: process.titular2_data?.morada_fiscal || "",
      co_comprador_estado_civil: process.titular2_data?.estado_civil || "",
      
      // Dados do Vendedor (proprietário)
      vendedor_nome: realEstateData?.owner_name || "",
      vendedor_telefone: realEstateData?.owner_phone || "",
      vendedor_email: realEstateData?.owner_email || "",
      
      // Valores
      valor_sinal: financialData?.valor_entrada || financialData?.capital_proprio || "",
      data_cpcv: realEstateData?.data_cpcv || new Date().toISOString().split('T')[0],
      data_escritura_prevista: realEstateData?.data_escritura_prevista || "",
      
      // Mediador
      mediador_nome: process.mediador_name || process.assigned_mediador_name || "",
    }));
  };

  const handleFieldChange = (field, value) => {
    setCpcvData(prev => ({ ...prev, [field]: value }));
  };

  const gerarDocumento = () => {
    if (!selectedMinuta) {
      toast.error("Selecione uma minuta/template");
      return;
    }

    let documento = selectedMinuta.conteudo;
    
    // Substituir placeholders
    const replacements = {
      // Imóvel
      '[TIPO_IMOVEL]': cpcvData.tipo_imovel || '___________',
      '[TIPOLOGIA]': cpcvData.tipologia || '___________',
      '[AREA]': cpcvData.area ? `${cpcvData.area} m²` : '___________',
      '[MORADA_IMOVEL]': cpcvData.morada_imovel || '___________',
      '[VALOR_IMOVEL]': cpcvData.valor_imovel ? `${Number(cpcvData.valor_imovel).toLocaleString('pt-PT')}€` : '___________',
      '[VALOR_IMOVEL_EXTENSO]': cpcvData.valor_imovel ? valorPorExtenso(Number(cpcvData.valor_imovel)) : '___________',
      '[MATRIZ]': cpcvData.matriz || '___________',
      '[ARTIGO_MATRIZ]': cpcvData.artigo_matriz || '___________',
      
      // Vendedor
      '[VENDEDOR_NOME]': cpcvData.vendedor_nome || '___________',
      '[VENDEDOR_NIF]': cpcvData.vendedor_nif || '___________',
      '[VENDEDOR_MORADA]': cpcvData.vendedor_morada || '___________',
      '[VENDEDOR_TELEFONE]': cpcvData.vendedor_telefone || '___________',
      '[VENDEDOR_EMAIL]': cpcvData.vendedor_email || '___________',
      '[VENDEDOR_ESTADO_CIVIL]': cpcvData.vendedor_estado_civil || '___________',
      
      // Comprador Principal
      '[COMPRADOR_NOME]': cpcvData.comprador_nome || '___________',
      '[COMPRADOR_NIF]': cpcvData.comprador_nif || '___________',
      '[COMPRADOR_MORADA]': cpcvData.comprador_morada || '___________',
      '[COMPRADOR_TELEFONE]': cpcvData.comprador_telefone || '___________',
      '[COMPRADOR_EMAIL]': cpcvData.comprador_email || '___________',
      '[COMPRADOR_ESTADO_CIVIL]': cpcvData.comprador_estado_civil || '___________',
      
      // Co-comprador
      '[CO_COMPRADOR_NOME]': cpcvData.co_comprador_nome || '___________',
      '[CO_COMPRADOR_NIF]': cpcvData.co_comprador_nif || '___________',
      '[CO_COMPRADOR_MORADA]': cpcvData.co_comprador_morada || '___________',
      '[CO_COMPRADOR_ESTADO_CIVIL]': cpcvData.co_comprador_estado_civil || '___________',
      
      // Valores e Datas
      '[VALOR_SINAL]': cpcvData.valor_sinal ? `${Number(cpcvData.valor_sinal).toLocaleString('pt-PT')}€` : '___________',
      '[VALOR_SINAL_EXTENSO]': cpcvData.valor_sinal ? valorPorExtenso(Number(cpcvData.valor_sinal)) : '___________',
      '[DATA_CPCV]': formatDate(cpcvData.data_cpcv),
      '[DATA_ESCRITURA]': formatDate(cpcvData.data_escritura_prevista) || '___________',
      '[LOCAL_ESCRITURA]': cpcvData.local_escritura || '___________',
      
      // Condições
      '[CLAUSULAS_ESPECIAIS]': cpcvData.clausulas_especiais || '',
      '[PENALIZACAO]': cpcvData.penalizacao || '___________',
      
      // Mediador
      '[MEDIADOR_NOME]': cpcvData.mediador_nome || '___________',
      '[MEDIADOR_AMI]': cpcvData.mediador_ami || '___________',
      
      // Data atual
      '[DATA_ATUAL]': formatDate(new Date().toISOString().split('T')[0]),
    };
    
    // Aplicar substituições
    for (const [placeholder, value] of Object.entries(replacements)) {
      documento = documento.split(placeholder).join(value);
    }
    
    return documento;
  };

  const handlePreview = () => {
    const doc = gerarDocumento();
    if (doc) {
      setGeneratedDocument(doc);
      setPreviewOpen(true);
    }
  };

  const handlePrint = () => {
    const doc = gerarDocumento();
    if (!doc) return;
    
    // Abrir janela de impressão
    const printWindow = window.open('', '_blank');
    printWindow.document.write(`
      <!DOCTYPE html>
      <html>
      <head>
        <title>CPCV - ${cpcvData.comprador_nome || 'Documento'}</title>
        <style>
          body {
            font-family: 'Times New Roman', serif;
            font-size: 12pt;
            line-height: 1.5;
            margin: 2cm;
            white-space: pre-wrap;
          }
          h1 {
            text-align: center;
            font-size: 14pt;
            margin-bottom: 1cm;
          }
          .header {
            text-align: center;
            margin-bottom: 1cm;
          }
          @media print {
            body { margin: 2cm; }
          }
        </style>
      </head>
      <body>
        <div class="header">
          <h1>CONTRATO DE PROMESSA DE COMPRA E VENDA</h1>
        </div>
        ${doc.replace(/\n/g, '<br>')}
      </body>
      </html>
    `);
    printWindow.document.close();
    printWindow.print();
  };

  const handleSaveToProcess = async () => {
    setLoading(true);
    try {
      // Guardar dados CPCV no processo
      const response = await fetch(`${API_URL}/api/processes/${process.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          real_estate_data: {
            ...realEstateData,
            data_cpcv: cpcvData.data_cpcv,
            tipologia: cpcvData.tipologia,
            area: cpcvData.area,
            morada_imovel: cpcvData.morada_imovel,
            valor_imovel: cpcvData.valor_imovel,
            data_escritura_prevista: cpcvData.data_escritura_prevista,
            owner_name: cpcvData.vendedor_nome,
            owner_phone: cpcvData.vendedor_telefone,
            owner_email: cpcvData.vendedor_email,
          },
          financial_data: {
            ...financialData,
            valor_entrada: cpcvData.valor_sinal,
          },
          vendedor: {
            nome: cpcvData.vendedor_nome,
            nif: cpcvData.vendedor_nif,
            morada: cpcvData.vendedor_morada,
            telefone: cpcvData.vendedor_telefone,
            email: cpcvData.vendedor_email,
            estado_civil: cpcvData.vendedor_estado_civil,
          },
        }),
      });
      
      if (response.ok) {
        toast.success("Dados CPCV guardados no processo");
      } else {
        throw new Error("Erro ao guardar");
      }
    } catch (error) {
      toast.error("Erro ao guardar dados CPCV");
    } finally {
      setLoading(false);
    }
  };

  // Função auxiliar para formatar data
  const formatDate = (dateStr) => {
    if (!dateStr) return "";
    try {
      const [year, month, day] = dateStr.split('-');
      return `${day} de ${getMonthName(parseInt(month))} de ${year}`;
    } catch {
      return dateStr;
    }
  };

  const getMonthName = (month) => {
    const months = [
      'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
      'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'
    ];
    return months[month - 1] || '';
  };

  // Função auxiliar para valor por extenso (simplificada)
  const valorPorExtenso = (valor) => {
    if (!valor || isNaN(valor)) return '___________';
    
    const unidades = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove'];
    const dezenas = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa'];
    const centenas = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos'];
    
    const milhares = Math.floor(valor / 1000);
    const resto = valor % 1000;
    
    let extenso = '';
    
    if (milhares > 0) {
      if (milhares === 1) {
        extenso = 'mil';
      } else {
        extenso = `${unidades[milhares]} mil`;
      }
    }
    
    if (resto > 0) {
      if (extenso) extenso += ' ';
      
      const cent = Math.floor(resto / 100);
      const dez = Math.floor((resto % 100) / 10);
      const uni = resto % 10;
      
      if (resto === 100) {
        extenso += 'cem';
      } else {
        if (cent > 0) extenso += centenas[cent];
        if (dez > 0 || uni > 0) {
          if (cent > 0) extenso += ' e ';
          if (resto % 100 < 20) {
            const especiais = ['dez', 'onze', 'doze', 'treze', 'catorze', 'quinze', 'dezasseis', 'dezassete', 'dezoito', 'dezanove'];
            extenso += especiais[resto % 100 - 10];
          } else {
            if (dez > 0) extenso += dezenas[dez];
            if (uni > 0) {
              if (dez > 0) extenso += ' e ';
              extenso += unidades[uni];
            }
          }
        }
      }
    }
    
    return `${extenso} euros`;
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileSignature className="h-5 w-5 text-indigo-600" />
              Contrato Promessa Compra e Venda (CPCV)
            </DialogTitle>
            <DialogDescription>
              Preencha os dados para gerar o documento CPCV
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-6 py-4">
            {/* Selecionar Template */}
            <div className="space-y-2">
              <Label>Template/Minuta</Label>
              <Select 
                value={selectedMinuta?.id || ""} 
                onValueChange={(v) => setSelectedMinuta(minutas.find(m => m.id === v))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Selecione um template CPCV" />
                </SelectTrigger>
                <SelectContent>
                  {minutas.length === 0 ? (
                    <div className="p-2 text-sm text-muted-foreground">
                      Nenhum template CPCV encontrado. Crie uma minuta com a tag "cpcv".
                    </div>
                  ) : (
                    minutas.map(minuta => (
                      <SelectItem key={minuta.id} value={minuta.id}>
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4" />
                          {minuta.titulo}
                        </div>
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
              {minutas.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  Dica: Vá a Minutas e crie um template com tag "cpcv"
                </p>
              )}
            </div>

            {/* Dados do Imóvel */}
            <Card className="p-4 border">
              <h4 className="font-medium text-sm flex items-center gap-2 mb-4">
                <Building2 className="h-4 w-4 text-indigo-600" />
                Dados do Imóvel
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs">Tipo de Imóvel</Label>
                  <Select 
                    value={cpcvData.tipo_imovel} 
                    onValueChange={(v) => handleFieldChange('tipo_imovel', v)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Tipo" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Apartamento">Apartamento</SelectItem>
                      <SelectItem value="Moradia">Moradia</SelectItem>
                      <SelectItem value="Terreno">Terreno</SelectItem>
                      <SelectItem value="Loja">Loja</SelectItem>
                      <SelectItem value="Escritório">Escritório</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Tipologia</Label>
                  <Input 
                    value={cpcvData.tipologia} 
                    onChange={(e) => handleFieldChange('tipologia', e.target.value)}
                    placeholder="Ex: T2"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Área (m²)</Label>
                  <Input 
                    value={cpcvData.area} 
                    onChange={(e) => handleFieldChange('area', e.target.value)}
                    placeholder="Ex: 100"
                  />
                </div>
                <div className="space-y-2 md:col-span-3">
                  <Label className="text-xs">Morada Completa</Label>
                  <Input 
                    value={cpcvData.morada_imovel} 
                    onChange={(e) => handleFieldChange('morada_imovel', e.target.value)}
                    placeholder="Rua, número, andar, código postal, localidade"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Valor do Imóvel (€)</Label>
                  <Input 
                    type="number"
                    value={cpcvData.valor_imovel} 
                    onChange={(e) => handleFieldChange('valor_imovel', e.target.value)}
                    placeholder="Ex: 250000"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Matriz</Label>
                  <Input 
                    value={cpcvData.matriz} 
                    onChange={(e) => handleFieldChange('matriz', e.target.value)}
                    placeholder="Matriz predial"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Artigo Matricial</Label>
                  <Input 
                    value={cpcvData.artigo_matriz} 
                    onChange={(e) => handleFieldChange('artigo_matriz', e.target.value)}
                    placeholder="Artigo"
                  />
                </div>
              </div>
            </Card>

            {/* Dados do Vendedor */}
            <Card className="p-4 border">
              <h4 className="font-medium text-sm flex items-center gap-2 mb-4">
                <User className="h-4 w-4 text-red-600" />
                Vendedor (Promitente Vendedor)
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div className="space-y-2 md:col-span-2">
                  <Label className="text-xs">Nome Completo</Label>
                  <Input 
                    value={cpcvData.vendedor_nome} 
                    onChange={(e) => handleFieldChange('vendedor_nome', e.target.value)}
                    placeholder="Nome do vendedor"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">NIF</Label>
                  <Input 
                    value={cpcvData.vendedor_nif} 
                    onChange={(e) => handleFieldChange('vendedor_nif', e.target.value)}
                    placeholder="123456789"
                    maxLength={9}
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label className="text-xs">Morada</Label>
                  <Input 
                    value={cpcvData.vendedor_morada} 
                    onChange={(e) => handleFieldChange('vendedor_morada', e.target.value)}
                    placeholder="Morada do vendedor"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Estado Civil</Label>
                  <Select 
                    value={cpcvData.vendedor_estado_civil} 
                    onValueChange={(v) => handleFieldChange('vendedor_estado_civil', v)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Estado civil" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Solteiro">Solteiro/a</SelectItem>
                      <SelectItem value="Casado">Casado/a</SelectItem>
                      <SelectItem value="Divorciado">Divorciado/a</SelectItem>
                      <SelectItem value="Viúvo">Viúvo/a</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Telefone</Label>
                  <Input 
                    value={cpcvData.vendedor_telefone} 
                    onChange={(e) => handleFieldChange('vendedor_telefone', e.target.value)}
                    placeholder="+351"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Email</Label>
                  <Input 
                    type="email"
                    value={cpcvData.vendedor_email} 
                    onChange={(e) => handleFieldChange('vendedor_email', e.target.value)}
                    placeholder="email@exemplo.pt"
                  />
                </div>
              </div>
            </Card>

            {/* Dados do Comprador Principal */}
            <Card className="p-4 border border-blue-200 bg-blue-50/50">
              <h4 className="font-medium text-sm flex items-center gap-2 mb-4">
                <User className="h-4 w-4 text-blue-600" />
                Comprador Principal (Promitente Comprador)
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div className="space-y-2 md:col-span-2">
                  <Label className="text-xs">Nome Completo</Label>
                  <Input 
                    value={cpcvData.comprador_nome} 
                    onChange={(e) => handleFieldChange('comprador_nome', e.target.value)}
                    placeholder="Nome do comprador"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">NIF</Label>
                  <Input 
                    value={cpcvData.comprador_nif} 
                    onChange={(e) => handleFieldChange('comprador_nif', e.target.value)}
                    placeholder="123456789"
                    maxLength={9}
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label className="text-xs">Morada</Label>
                  <Input 
                    value={cpcvData.comprador_morada} 
                    onChange={(e) => handleFieldChange('comprador_morada', e.target.value)}
                    placeholder="Morada do comprador"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Estado Civil</Label>
                  <Select 
                    value={cpcvData.comprador_estado_civil} 
                    onValueChange={(v) => handleFieldChange('comprador_estado_civil', v)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Estado civil" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Solteiro">Solteiro/a</SelectItem>
                      <SelectItem value="Casado">Casado/a</SelectItem>
                      <SelectItem value="Divorciado">Divorciado/a</SelectItem>
                      <SelectItem value="Viúvo">Viúvo/a</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Telefone</Label>
                  <Input 
                    value={cpcvData.comprador_telefone} 
                    onChange={(e) => handleFieldChange('comprador_telefone', e.target.value)}
                    placeholder="+351"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Email</Label>
                  <Input 
                    type="email"
                    value={cpcvData.comprador_email} 
                    onChange={(e) => handleFieldChange('comprador_email', e.target.value)}
                    placeholder="email@exemplo.pt"
                  />
                </div>
              </div>
            </Card>

            {/* Co-comprador (se existir) */}
            {(cpcvData.co_comprador_nome || process.second_client_name) && (
              <Card className="p-4 border border-indigo-200 bg-indigo-50/50">
                <h4 className="font-medium text-sm flex items-center gap-2 mb-4">
                  <Users className="h-4 w-4 text-indigo-600" />
                  Co-comprador (2º Titular)
                </h4>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <div className="space-y-2 md:col-span-2">
                    <Label className="text-xs">Nome Completo</Label>
                    <Input 
                      value={cpcvData.co_comprador_nome} 
                      onChange={(e) => handleFieldChange('co_comprador_nome', e.target.value)}
                      placeholder="Nome do co-comprador"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs">NIF</Label>
                    <Input 
                      value={cpcvData.co_comprador_nif} 
                      onChange={(e) => handleFieldChange('co_comprador_nif', e.target.value)}
                      placeholder="123456789"
                      maxLength={9}
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label className="text-xs">Morada</Label>
                    <Input 
                      value={cpcvData.co_comprador_morada} 
                      onChange={(e) => handleFieldChange('co_comprador_morada', e.target.value)}
                      placeholder="Morada do co-comprador"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs">Estado Civil</Label>
                    <Select 
                      value={cpcvData.co_comprador_estado_civil} 
                      onValueChange={(v) => handleFieldChange('co_comprador_estado_civil', v)}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Estado civil" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Solteiro">Solteiro/a</SelectItem>
                        <SelectItem value="Casado">Casado/a</SelectItem>
                        <SelectItem value="Divorciado">Divorciado/a</SelectItem>
                        <SelectItem value="Viúvo">Viúvo/a</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </Card>
            )}

            {/* Valores e Datas */}
            <Card className="p-4 border">
              <h4 className="font-medium text-sm flex items-center gap-2 mb-4">
                <CreditCard className="h-4 w-4 text-green-600" />
                Valores e Datas
              </h4>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs">Valor do Sinal (€)</Label>
                  <Input 
                    type="number"
                    value={cpcvData.valor_sinal} 
                    onChange={(e) => handleFieldChange('valor_sinal', e.target.value)}
                    placeholder="Ex: 25000"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Data do CPCV</Label>
                  <Input 
                    type="date"
                    value={cpcvData.data_cpcv} 
                    onChange={(e) => handleFieldChange('data_cpcv', e.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Data Prevista Escritura</Label>
                  <Input 
                    type="date"
                    value={cpcvData.data_escritura_prevista} 
                    onChange={(e) => handleFieldChange('data_escritura_prevista', e.target.value)}
                  />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label className="text-xs">Local da Escritura</Label>
                  <Input 
                    value={cpcvData.local_escritura} 
                    onChange={(e) => handleFieldChange('local_escritura', e.target.value)}
                    placeholder="Ex: Cartório Notarial de Lisboa"
                  />
                </div>
                <div className="space-y-2">
                  <Label className="text-xs">Penalização (%)</Label>
                  <Input 
                    value={cpcvData.penalizacao} 
                    onChange={(e) => handleFieldChange('penalizacao', e.target.value)}
                    placeholder="Ex: 10%"
                  />
                </div>
              </div>
            </Card>

            {/* Cláusulas Especiais */}
            <div className="space-y-2">
              <Label>Cláusulas Especiais</Label>
              <Textarea
                value={cpcvData.clausulas_especiais}
                onChange={(e) => handleFieldChange('clausulas_especiais', e.target.value)}
                placeholder="Cláusulas adicionais específicas deste contrato..."
                rows={4}
              />
            </div>

            {/* Mediador */}
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label className="text-xs">Mediador/Imobiliária</Label>
                <Input 
                  value={cpcvData.mediador_nome} 
                  onChange={(e) => handleFieldChange('mediador_nome', e.target.value)}
                  placeholder="Nome do mediador"
                />
              </div>
              <div className="space-y-2">
                <Label className="text-xs">Licença AMI</Label>
                <Input 
                  value={cpcvData.mediador_ami} 
                  onChange={(e) => handleFieldChange('mediador_ami', e.target.value)}
                  placeholder="Número AMI"
                />
              </div>
            </div>
          </div>

          <DialogFooter className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button 
              variant="outline" 
              onClick={handlePreview}
              disabled={!selectedMinuta}
            >
              <Eye className="h-4 w-4 mr-2" />
              Pré-visualizar
            </Button>
            <Button 
              variant="outline" 
              onClick={handleSaveToProcess}
              disabled={loading}
            >
              {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
              Guardar no Processo
            </Button>
            <Button 
              onClick={handlePrint}
              disabled={!selectedMinuta}
              className="bg-indigo-600 hover:bg-indigo-700"
            >
              <Printer className="h-4 w-4 mr-2" />
              Imprimir
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog de Pré-visualização */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="max-w-4xl max-h-[90vh]">
          <DialogHeader>
            <DialogTitle>Pré-visualização do CPCV</DialogTitle>
            <DialogDescription>
              Documento gerado com os dados preenchidos
            </DialogDescription>
          </DialogHeader>
          <ScrollArea className="h-[60vh] mt-4">
            <pre className="whitespace-pre-wrap font-mono text-sm bg-muted p-4 rounded-lg">
              {generatedDocument}
            </pre>
          </ScrollArea>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPreviewOpen(false)}>
              Fechar
            </Button>
            <Button onClick={handlePrint} className="bg-indigo-600 hover:bg-indigo-700">
              <Printer className="h-4 w-4 mr-2" />
              Imprimir
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

// Componente Card simplificado
const Card = ({ className, children, ...props }) => (
  <div className={`rounded-lg border bg-card ${className || ''}`} {...props}>
    {children}
  </div>
);

export default CPCVModal;
