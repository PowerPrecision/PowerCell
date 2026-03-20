/**
 * ClientRegistrationsAdminPage - Página de Administração de Registos de Clientes
 * Permite ao admin visualizar e editar os dados dos formulários de registo público
 */
import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
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
import { Textarea } from "../components/ui/textarea";
import { toast } from "sonner";
import {
  Users,
  Loader2,
  CheckCircle,
  XCircle,
  Clock,
  Edit,
  Trash2,
  Eye,
  FileText,
  User,
  Home,
  Briefcase,
  ExternalLink,
  Calendar,
  Mail,
  Phone,
  CreditCard,
  AlertCircle,
} from "lucide-react";
import { 
  StatCard, 
  ConfirmDeleteModal, 
  LoadingState, 
  EmptyState, 
  Pagination,
  AccessRestricted,
  AdminSearchFilter,
  PageHeader
} from "../components/admin/AdminPageShared";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Status badge component - específico para registos de clientes
const StatusBadge = ({ status }) => {
  const statusConfig = {
    clientes_espera: { label: "Clientes em Espera", color: "bg-yellow-100 text-yellow-800" },
    documents: { label: "Documentos", color: "bg-blue-100 text-blue-800" },
    analise: { label: "Análise", color: "bg-purple-100 text-purple-800" },
    aprovado: { label: "Aprovado", color: "bg-green-100 text-green-800" },
    rejeitado: { label: "Rejeitado", color: "bg-red-100 text-red-800" },
  };

  const config = statusConfig[status] || { label: status || "Sem estado", color: "bg-gray-100 text-gray-800" };

  return <Badge className={config.color}>{config.label}</Badge>;
};

// Source badge - específico para registos de clientes
const SourceBadge = ({ source }) => {
  if (source === "public_form") {
    return <Badge variant="outline" className="bg-green-50 text-green-700 border-green-300">Formulário Público</Badge>;
  }
  return <Badge variant="outline">Manual</Badge>;
};

// Opções de status para filtro
const CLIENT_STATUS_OPTIONS = [
  { value: "clientes_espera", label: "Clientes em Espera" },
  { value: "documents", label: "Documentos" },
  { value: "analise", label: "Análise" },
  { value: "aprovado", label: "Aprovado" },
  { value: "rejeitado", label: "Rejeitado" },
];

// Helper component for field errors
const FieldError = ({ children }) => (
  <p className="text-xs text-red-600 mt-1 flex items-start gap-1 font-medium">
    <AlertCircle className="h-3 w-3 mt-0.5 flex-shrink-0" />
    <span>{children}</span>
  </p>
);

// Validar NIF português
const validateNIF = (nif) => {
  if (!nif) return { valid: true }; // Campo opcional
  const cleanNif = nif.replace(/[^\d]/g, '');
  if (cleanNif.length !== 9) return { valid: false, message: "NIF deve ter 9 dígitos" };
  
  const digits = cleanNif.split('').map(Number);
  const weights = [9, 8, 7, 6, 5, 4, 3, 2];
  const sum = digits.slice(0, 8).reduce((acc, d, i) => acc + d * weights[i], 0);
  const remainder = sum % 11;
  const checkDigit = remainder > 1 ? 11 - remainder : 0;
  
  if (checkDigit !== digits[8]) {
    return { valid: false, message: "NIF inválido" };
  }
  return { valid: true };
};

// Modal de Edição
const EditModal = ({ open, onClose, registration, onSave }) => {
  const [formData, setFormData] = useState({});
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState("personal");
  const [fieldErrors, setFieldErrors] = useState({});

  useEffect(() => {
    if (registration) {
      setFormData({
        client_name: registration.client_name || "",
        client_email: registration.client_email || "",
        client_phone: registration.client_phone || "",
        personal_data: registration.personal_data || {},
        titular2_data: registration.titular2_data || {},
        real_estate_data: registration.real_estate_data || {},
        financial_data: registration.financial_data || {},
      });
      setFieldErrors({});
    }
  }, [registration]);

  const handleChange = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    // Limpar erro do campo
    if (fieldErrors[field]) {
      setFieldErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };

  const handleNestedChange = (section, field, value) => {
    setFormData((prev) => ({
      ...prev,
      [section]: {
        ...(prev[section] || {}),
        [field]: value,
      },
    }));
    // Limpar erro do campo aninhado
    const errorKey = `${section}.${field}`;
    if (fieldErrors[errorKey]) {
      setFieldErrors((prev) => {
        const newErrors = { ...prev };
        delete newErrors[errorKey];
        return newErrors;
      });
    }
  };

  const validateForm = () => {
    const errors = {};
    
    // Validar NIF do titular
    if (formData.personal_data?.nif) {
      const nifCheck = validateNIF(formData.personal_data.nif);
      if (!nifCheck.valid) {
        errors["personal_data.nif"] = nifCheck.message;
      }
    }
    
    // Validar NIF do titular2
    if (formData.titular2_data?.nif) {
      const nif2Check = validateNIF(formData.titular2_data.nif);
      if (!nif2Check.valid) {
        errors["titular2_data.nif"] = nif2Check.message;
      }
    }
    
    // Validar email do titular2
    if (formData.titular2_data?.email) {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(formData.titular2_data.email)) {
        errors["titular2_data.email"] = "Email inválido";
      }
    }
    
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSave = async () => {
    // Validar antes de guardar
    if (!validateForm()) {
      toast.error("Por favor corrija os erros no formulário");
      return;
    }
    
    setSaving(true);
    try {
      await onSave(registration.id, formData);
      onClose();
    } catch (error) {
      // Erro já tratado no onSave
    } finally {
      setSaving(false);
    }
  };

  if (!registration) return null;

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Edit className="h-5 w-5" />
            Editar Registo de Cliente
          </DialogTitle>
          <DialogDescription>
            Edite os dados do registo. As alterações serão guardadas na base de dados.
          </DialogDescription>
        </DialogHeader>

        <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4">
          <TabsList className="grid w-full grid-cols-4">
            <TabsTrigger value="personal" className="gap-2">
              <User className="h-4 w-4" />
              <span className="hidden sm:inline">Dados Pessoais</span>
            </TabsTrigger>
            <TabsTrigger value="titular2" className="gap-2">
              <Users className="h-4 w-4" />
              <span className="hidden sm:inline">2º Titular</span>
            </TabsTrigger>
            <TabsTrigger value="imovel" className="gap-2">
              <Home className="h-4 w-4" />
              <span className="hidden sm:inline">Imóvel</span>
            </TabsTrigger>
            <TabsTrigger value="financeiro" className="gap-2">
              <Briefcase className="h-4 w-4" />
              <span className="hidden sm:inline">Financeiro</span>
            </TabsTrigger>
          </TabsList>

          <div className="py-4">
            {/* Dados de Contacto */}
            <div className="space-y-4 mb-6">
              <h4 className="font-medium text-sm text-muted-foreground">Dados de Contacto</h4>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label>Nome</Label>
                  <Input value={formData.client_name || ""} onChange={(e) => handleChange("client_name", e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Email</Label>
                  <Input type="email" value={formData.client_email || ""} onChange={(e) => handleChange("client_email", e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Telefone</Label>
                  <Input value={formData.client_phone || ""} onChange={(e) => handleChange("client_phone", e.target.value)} />
                </div>
              </div>
            </div>

            <TabsContent value="personal" className="space-y-4 mt-0">
              <h4 className="font-medium">Dados Pessoais do Titular</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>NIF</Label>
                  <Input 
                    value={formData.personal_data?.nif || ""} 
                    onChange={(e) => handleNestedChange("personal_data", "nif", e.target.value)} 
                    maxLength={9}
                    className={fieldErrors["personal_data.nif"] ? "border-red-500 focus-visible:ring-red-500 bg-red-50" : ""}
                  />
                  {fieldErrors["personal_data.nif"] && <FieldError>{fieldErrors["personal_data.nif"]}</FieldError>}
                </div>
                <div className="space-y-2">
                  <Label>Documento ID</Label>
                  <Input value={formData.personal_data?.documento_id || ""} onChange={(e) => handleNestedChange("personal_data", "documento_id", e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Data de Nascimento</Label>
                  <Input type="date" value={formData.personal_data?.birth_date || ""} onChange={(e) => handleNestedChange("personal_data", "birth_date", e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Estado Civil</Label>
                  <Select value={formData.personal_data?.estado_civil || ""} onValueChange={(v) => handleNestedChange("personal_data", "estado_civil", v)}>
                    <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="solteiro">Solteiro/a</SelectItem>
                      <SelectItem value="casado_adquiridos">Casado/a - Comunhão de Adquiridos</SelectItem>
                      <SelectItem value="casado_geral">Casado/a - Comunhão Geral</SelectItem>
                      <SelectItem value="casado_separacao">Casado/a - Separação de Bens</SelectItem>
                      <SelectItem value="divorciado">Divorciado/a</SelectItem>
                      <SelectItem value="viuvo">Viúvo/a</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Naturalidade</Label>
                  <Input value={formData.personal_data?.naturalidade || ""} onChange={(e) => handleNestedChange("personal_data", "naturalidade", e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Nacionalidade</Label>
                  <Input value={formData.personal_data?.nacionalidade || ""} onChange={(e) => handleNestedChange("personal_data", "nacionalidade", e.target.value)} />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label>Morada Fiscal</Label>
                  <Input value={formData.personal_data?.morada_fiscal || ""} onChange={(e) => handleNestedChange("personal_data", "morada_fiscal", e.target.value)} />
                </div>
              </div>
            </TabsContent>

            <TabsContent value="titular2" className="space-y-4 mt-0">
              <h4 className="font-medium">Dados do 2º Titular</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Nome</Label>
                  <Input value={formData.titular2_data?.name || ""} onChange={(e) => handleNestedChange("titular2_data", "name", e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Email</Label>
                  <Input 
                    type="email" 
                    value={formData.titular2_data?.email || ""} 
                    onChange={(e) => handleNestedChange("titular2_data", "email", e.target.value)}
                    className={fieldErrors["titular2_data.email"] ? "border-red-500 focus-visible:ring-red-500 bg-red-50" : ""}
                  />
                  {fieldErrors["titular2_data.email"] && <FieldError>{fieldErrors["titular2_data.email"]}</FieldError>}
                </div>
                <div className="space-y-2">
                  <Label>Telefone</Label>
                  <Input value={formData.titular2_data?.phone || ""} onChange={(e) => handleNestedChange("titular2_data", "phone", e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>NIF</Label>
                  <Input 
                    value={formData.titular2_data?.nif || ""} 
                    onChange={(e) => handleNestedChange("titular2_data", "nif", e.target.value)} 
                    maxLength={9}
                    className={fieldErrors["titular2_data.nif"] ? "border-red-500 focus-visible:ring-red-500 bg-red-50" : ""}
                  />
                  {fieldErrors["titular2_data.nif"] && <FieldError>{fieldErrors["titular2_data.nif"]}</FieldError>}
                </div>
                <div className="space-y-2">
                  <Label>Documento ID</Label>
                  <Input value={formData.titular2_data?.documento_id || ""} onChange={(e) => handleNestedChange("titular2_data", "documento_id", e.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label>Data de Nascimento</Label>
                  <Input type="date" value={formData.titular2_data?.birth_date || ""} onChange={(e) => handleNestedChange("titular2_data", "birth_date", e.target.value)} />
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label>Morada Fiscal</Label>
                  <Input value={formData.titular2_data?.morada_fiscal || ""} onChange={(e) => handleNestedChange("titular2_data", "morada_fiscal", e.target.value)} />
                </div>
              </div>
            </TabsContent>

            <TabsContent value="imovel" className="space-y-4 mt-0">
              <h4 className="font-medium">Dados do Imóvel</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Finalidade</Label>
                  <Select value={formData.real_estate_data?.finalidade || ""} onValueChange={(v) => handleNestedChange("real_estate_data", "finalidade", v)}>
                    <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="compra_imovel">Compra de Imóvel</SelectItem>
                      <SelectItem value="refinanciamento">Refinanciamento</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Tipo de Imóvel</Label>
                  <Select value={formData.real_estate_data?.tipo_imovel || ""} onValueChange={(v) => handleNestedChange("real_estate_data", "tipo_imovel", v)}>
                    <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="apartamento">Apartamento</SelectItem>
                      <SelectItem value="moradia">Moradia</SelectItem>
                      <SelectItem value="terreno">Terreno</SelectItem>
                      <SelectItem value="outro">Outro</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Nº Quartos</Label>
                  <Select value={formData.real_estate_data?.num_quartos || ""} onValueChange={(v) => handleNestedChange("real_estate_data", "num_quartos", v)}>
                    <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="T0">T0</SelectItem><SelectItem value="T1">T1</SelectItem>
                      <SelectItem value="T2">T2</SelectItem><SelectItem value="T3">T3</SelectItem>
                      <SelectItem value="T4">T4</SelectItem><SelectItem value="T5+">T5+</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2"><Label>Área (m²)</Label><Input type="number" value={formData.real_estate_data?.area_pretendida || ""} onChange={(e) => handleNestedChange("real_estate_data", "area_pretendida", e.target.value)} /></div>
                <div className="space-y-2"><Label>Valor Máximo (€)</Label><Input type="number" value={formData.real_estate_data?.valor_maximo_imovel || ""} onChange={(e) => handleNestedChange("real_estate_data", "valor_maximo_imovel", e.target.value)} /></div>
                <div className="space-y-2 md:col-span-2"><Label>Localização Pretendida</Label><Input value={formData.real_estate_data?.localizacao || ""} onChange={(e) => handleNestedChange("real_estate_data", "localizacao", e.target.value)} /></div>
                <div className="space-y-2 md:col-span-2"><Label>Outras Informações</Label><Textarea value={formData.real_estate_data?.outras_informacoes || ""} onChange={(e) => handleNestedChange("real_estate_data", "outras_informacoes", e.target.value)} rows={3} /></div>
              </div>
            </TabsContent>

            <TabsContent value="financeiro" className="space-y-4 mt-0">
              <h4 className="font-medium">Dados Financeiros</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2"><Label>Rendimento Mensal (€)</Label><Input type="number" value={formData.financial_data?.monthly_income || ""} onChange={(e) => handleNestedChange("financial_data", "monthly_income", e.target.value)} /></div>
                <div className="space-y-2"><Label>Renda Atual (€)</Label><Input type="number" value={formData.financial_data?.renda_habitacao_atual || ""} onChange={(e) => handleNestedChange("financial_data", "renda_habitacao_atual", e.target.value)} /></div>
                <div className="space-y-2"><Label>Capital Próprio (€)</Label><Input type="number" value={formData.financial_data?.capital_proprio || ""} onChange={(e) => handleNestedChange("financial_data", "capital_proprio", e.target.value)} /></div>
                <div className="space-y-2"><Label>Valor a Financiar (€)</Label><Input type="number" value={formData.financial_data?.valor_financiado || ""} onChange={(e) => handleNestedChange("financial_data", "valor_financiado", e.target.value)} /></div>
                <div className="space-y-2">
                  <Label>Chave Móvel Digital</Label>
                  <Select value={formData.financial_data?.chave_movel_digital || ""} onValueChange={(v) => handleNestedChange("financial_data", "chave_movel_digital", v)}>
                    <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="sim">Sim</SelectItem>
                      <SelectItem value="nao">Não</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Acesso Portal Finanças</Label>
                  <Select value={formData.financial_data?.acesso_portal_financas || ""} onValueChange={(v) => handleNestedChange("financial_data", "acesso_portal_financas", v)}>
                    <SelectTrigger><SelectValue placeholder="Selecione..." /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="portal_financas">Portal das Finanças</SelectItem>
                      <SelectItem value="seguranca_social">Segurança Social</SelectItem>
                      <SelectItem value="ambos">Ambos</SelectItem>
                      <SelectItem value="nenhuma">Nenhuma</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </TabsContent>
          </div>
        </Tabs>

        <DialogFooter className="mt-4">
          <Button variant="outline" onClick={onClose}>Cancelar</Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <CheckCircle className="h-4 w-4 mr-2" />}
            Guardar Alterações
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

// Modal de Visualização
const ViewModal = ({ open, onClose, registration }) => {
  if (!registration) return null;

  const formatDate = (dateStr) => {
    if (!dateStr) return "N/A";
    try { return new Date(dateStr).toLocaleString("pt-PT"); } catch { return dateStr; }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Eye className="h-5 w-5" />
            Detalhes do Registo
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Info Principal */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-muted-foreground">Cliente</p>
              <p className="font-medium text-lg">{registration.client_name}</p>
            </div>
            <div className="flex gap-2">
              <StatusBadge status={registration.status} />
              <SourceBadge source={registration.source} />
            </div>
          </div>

          {/* Contacto */}
          <Card>
            <CardHeader className="pb-2"><CardTitle className="text-sm">Contacto</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-4 text-sm">
              <div className="flex items-center gap-2"><Mail className="h-4 w-4 text-muted-foreground" /><span>{registration.client_email}</span></div>
              <div className="flex items-center gap-2"><Phone className="h-4 w-4 text-muted-foreground" /><span>{registration.client_phone || "N/A"}</span></div>
            </CardContent>
          </Card>

          {/* Dados Pessoais */}
          {registration.personal_data && (
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><User className="h-4 w-4" />Dados Pessoais</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                <div><p className="text-muted-foreground">NIF</p><p className="font-medium">{registration.personal_data.nif || "N/A"}</p></div>
                <div><p className="text-muted-foreground">Documento</p><p className="font-medium">{registration.personal_data.documento_id || "N/A"}</p></div>
                <div><p className="text-muted-foreground">Data Nascimento</p><p className="font-medium">{registration.personal_data.birth_date || "N/A"}</p></div>
                <div><p className="text-muted-foreground">Estado Civil</p><p className="font-medium">{registration.personal_data.estado_civil || "N/A"}</p></div>
                <div><p className="text-muted-foreground">Nacionalidade</p><p className="font-medium">{registration.personal_data.nacionalidade || "N/A"}</p></div>
                <div className="md:col-span-3"><p className="text-muted-foreground">Morada Fiscal</p><p className="font-medium">{registration.personal_data.morada_fiscal || "N/A"}</p></div>
              </CardContent>
            </Card>
          )}

          {/* Dados do Imóvel */}
          {registration.real_estate_data && (
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><Home className="h-4 w-4" />Dados do Imóvel</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                <div><p className="text-muted-foreground">Finalidade</p><p className="font-medium">{registration.real_estate_data.finalidade || "N/A"}</p></div>
                <div><p className="text-muted-foreground">Tipo</p><p className="font-medium">{registration.real_estate_data.tipo_imovel || "N/A"}</p></div>
                <div><p className="text-muted-foreground">Quartos</p><p className="font-medium">{registration.real_estate_data.num_quartos || "N/A"}</p></div>
                <div><p className="text-muted-foreground">Área (m²)</p><p className="font-medium">{registration.real_estate_data.area_pretendida || "N/A"}</p></div>
                <div><p className="text-muted-foreground">Valor Máximo</p><p className="font-medium">{registration.real_estate_data.valor_maximo_imovel ? `${Number(registration.real_estate_data.valor_maximo_imovel).toLocaleString("pt-PT")} €` : "N/A"}</p></div>
                <div className="md:col-span-3"><p className="text-muted-foreground">Localização</p><p className="font-medium">{registration.real_estate_data.localizacao || "N/A"}</p></div>
              </CardContent>
            </Card>
          )}

          {/* Dados Financeiros */}
          {registration.financial_data && (
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-sm flex items-center gap-2"><CreditCard className="h-4 w-4" />Dados Financeiros</CardTitle></CardHeader>
              <CardContent className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                <div><p className="text-muted-foreground">Rendimento Mensal</p><p className="font-medium">{registration.financial_data.monthly_income ? `${Number(registration.financial_data.monthly_income).toLocaleString("pt-PT")} €` : "N/A"}</p></div>
                <div><p className="text-muted-foreground">Capital Próprio</p><p className="font-medium">{registration.financial_data.capital_proprio ? `${Number(registration.financial_data.capital_proprio).toLocaleString("pt-PT")} €` : "N/A"}</p></div>
                <div><p className="text-muted-foreground">Chave Móvel Digital</p><p className="font-medium">{registration.financial_data.chave_movel_digital || "N/A"}</p></div>
              </CardContent>
            </Card>
          )}

          {/* Metadados */}
          <Card className="bg-muted/30">
            <CardContent className="pt-4 text-sm space-y-2">
              <div className="flex justify-between"><span className="text-muted-foreground">Processo nº</span><span className="font-mono">{registration.process_number || registration.id}</span></div>
              <div className="flex justify-between"><span className="text-muted-foreground">Registado em</span><span>{formatDate(registration.created_at)}</span></div>
              {registration.updated_at && <div className="flex justify-between"><span className="text-muted-foreground">Atualizado em</span><span>{formatDate(registration.updated_at)}</span></div>}
            </CardContent>
          </Card>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fechar</Button>
          <Button onClick={() => window.open(`/processo/${registration.id}`, "_blank")}><ExternalLink className="h-4 w-4 mr-2" />Ver Processo</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const ClientRegistrationsAdminPage = () => {
  const { token, user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [registrations, setRegistrations] = useState([]);
  const [stats, setStats] = useState(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  // Modals
  const [editModal, setEditModal] = useState({ open: false, registration: null });
  const [viewModal, setViewModal] = useState({ open: false, registration: null });
  const [deleteModal, setDeleteModal] = useState({ open: false, registration: null });
  const [actionLoading, setActionLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search) params.append("search", search);
      if (statusFilter) params.append("status", statusFilter);
      params.append("page", page);
      params.append("limit", 15);

      const response = await fetch(`${API_URL}/api/admin/client-registrations?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setRegistrations(data.registrations || []);
        setTotal(data.total || 0);
        setTotalPages(data.pages || 1);
      } else {
        toast.error("Erro ao carregar dados");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  }, [token, search, statusFilter, page]);

  const fetchStats = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/api/admin/client-registrations/stats/summary`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (error) {
      console.error("Erro ao carregar estatísticas:", error);
    }
  }, [token]);

  useEffect(() => {
    fetchData();
    fetchStats();
  }, [fetchData, fetchStats]);

  const handleEdit = (registration) => setEditModal({ open: true, registration });
  const handleView = (registration) => setViewModal({ open: true, registration });

  const handleSave = async (processId, formData) => {
    try {
      const response = await fetch(`${API_URL}/api/admin/client-registrations/${processId}`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });

      if (response.ok) {
        toast.success("Registo atualizado com sucesso");
        fetchData();
      } else {
        const error = await response.json();
        toast.error(error.detail || "Erro ao atualizar");
        throw new Error();
      }
    } catch (error) {
      toast.error("Erro ao atualizar registo");
      throw error;
    }
  };

  const handleDelete = async () => {
    if (!deleteModal.registration) return;

    setActionLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/admin/client-registrations/${deleteModal.registration.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        toast.success("Registo eliminado com sucesso");
        setDeleteModal({ open: false, registration: null });
        fetchData();
        fetchStats();
      } else {
        toast.error("Erro ao eliminar");
      }
    } catch (error) {
      toast.error("Erro ao eliminar registo");
    } finally {
      setActionLoading(false);
    }
  };

  // Verificar acesso
  const accessDenied = <AccessRestricted userRole={user?.role} />;
  if (accessDenied) {
    return <DashboardLayout>{accessDenied}</DashboardLayout>;
  }

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <PageHeader
          icon={Users}
          title="Registos de Clientes"
          description="Visualize e edite os dados dos formulários de registo público"
          onRefresh={() => { fetchData(); fetchStats(); }}
        />

        {/* Estatísticas */}
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard title="Total de Registos" value={stats.total} icon={Users} color="text-blue-600" />
            <StatCard title="Hoje" value={stats.today} icon={Calendar} color="text-green-600" />
            <StatCard title="Esta Semana" value={stats.this_week} icon={Clock} color="text-purple-600" />
            <StatCard title="Este Mês" value={stats.this_month} icon={FileText} color="text-orange-600" />
          </div>
        )}

        {/* Filtros */}
        <AdminSearchFilter
          search={search}
          onSearchChange={(v) => { setSearch(v); setPage(1); }}
          statusFilter={statusFilter}
          onStatusChange={(v) => { setStatusFilter(v); setPage(1); }}
          statusOptions={CLIENT_STATUS_OPTIONS}
          searchPlaceholder="Pesquisar por nome, email ou NIF..."
        />

        {/* Lista */}
        <Card>
          <CardHeader><CardTitle className="text-lg">Registos ({total})</CardTitle></CardHeader>
          <CardContent>
            {loading ? (
              <LoadingState />
            ) : registrations.length === 0 ? (
              <EmptyState icon={Users} message="Nenhum registo encontrado" />
            ) : (
              <div className="space-y-2">
                {/* Table Header */}
                <div className="grid grid-cols-12 gap-2 px-3 py-2 text-sm font-medium text-muted-foreground border-b">
                  <div className="col-span-3">Cliente</div>
                  <div className="col-span-2">NIF</div>
                  <div className="col-span-2">Origem</div>
                  <div className="col-span-2">Estado</div>
                  <div className="col-span-1">Data</div>
                  <div className="col-span-2 text-right">Ações</div>
                </div>

                {/* Rows */}
                {registrations.map((reg) => (
                  <div key={reg.id} className="grid grid-cols-12 gap-2 px-3 py-3 items-center hover:bg-muted/50 rounded-lg">
                    <div className="col-span-3">
                      <p className="font-medium truncate">{reg.client_name}</p>
                      <p className="text-xs text-muted-foreground truncate">{reg.client_email}</p>
                    </div>
                    <div className="col-span-2 text-sm">{reg.personal_data?.nif || "-"}</div>
                    <div className="col-span-2"><SourceBadge source={reg.source} /></div>
                    <div className="col-span-2"><StatusBadge status={reg.status} /></div>
                    <div className="col-span-1 text-sm text-muted-foreground">{reg.created_at ? new Date(reg.created_at).toLocaleDateString("pt-PT") : "-"}</div>
                    <div className="col-span-2 flex justify-end gap-1">
                      <Button variant="ghost" size="sm" onClick={() => handleView(reg)} title="Ver detalhes"><Eye className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="sm" onClick={() => handleEdit(reg)} title="Editar"><Edit className="h-4 w-4" /></Button>
                      <Button variant="ghost" size="sm" onClick={() => setDeleteModal({ open: true, registration: reg })} title="Eliminar" className="text-red-600 hover:text-red-700 hover:bg-red-50"><Trash2 className="h-4 w-4" /></Button>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Pagination */}
            <Pagination page={page} totalPages={totalPages} total={total} onPageChange={setPage} />
          </CardContent>
        </Card>
      </div>

      {/* Modals */}
      <EditModal open={editModal.open} onClose={() => setEditModal({ open: false, registration: null })} registration={editModal.registration} onSave={handleSave} />
      <ViewModal open={viewModal.open} onClose={() => setViewModal({ open: false, registration: null })} registration={viewModal.registration} />
      <ConfirmDeleteModal
        open={deleteModal.open}
        onClose={() => setDeleteModal({ open: false, registration: null })}
        onConfirm={handleDelete}
        title="Confirmar Eliminação"
        description="Tem a certeza que deseja eliminar este registo? Esta ação não pode ser revertida e irá remover todos os dados do processo."
        itemName={deleteModal.registration?.client_name}
        itemDetails={deleteModal.registration ? `${deleteModal.registration.client_email} • Processo: #${deleteModal.registration.process_number || deleteModal.registration.id}` : ""}
        loading={actionLoading}
      />
    </DashboardLayout>
  );
};

export default ClientRegistrationsAdminPage;
