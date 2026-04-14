/**
 * DocumentRecipientsManager — Gestor de destinatários para envio de documentação por email.
 *
 * PORQUÊ: No processo de crédito habitação, múltiplos destinatários precisam receber documentação
 * (banco, solicitor, mediador, cliente). Este componente centraliza a gestão de destinatários
 * com validação de emails e templates personalizados.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import 'react-quill-new/dist/quill.snow.css';
/**
 * DocumentRecipientsManager — Gestão visual de destinatários para envio de documentação bancária.
 *
 * PORQUÊ: O envio de documentação para balcões bancários é uma operação frequente no
 * crédito habitação. Antes deste componente, os destinatários eram configurados via JSON
 * no backend, o que era propenso a erros e pouco acessível para administradores.
 * Este componente oferece uma interface visual para adicionar, editar, remover e
 * activar/desactivar destinatários sem tocar em JSON. Também inclui um editor de
 * templates de email com variáveis de template ({client_name}, {process_number}, etc.)
 * e gestão de múltiplos emails TO (destinatário principal).
 *
 * DECISÕES ARQUITECTURAIS:
 * - Auto-save em cada operação (toggle activo, eliminar, adicionar) — sem botão de
 *   "guardar" explícito, reduzindo o risco de perda de dados.
 * - Múltiplos emails TO com adição individual ou em lote (vírgula/ponto-e-vírgula/espaço).
 * - Template de email com ReactQuill (WYSIWYG) e variáveis de template clicáveis para
 *   copia rápida (1º proponente, 2º proponente, crédito, remetente).
 * - Validação automática de email em cada destinatário antes de guardar.
 * - Permissões restritas a admin/CEO — outros utilizadores veem apenas o formulário.
 * - Template padrão HTML profissional pré-preenchido com campos de crédito habitação.
 *
 * @param {Object} props
 * @param {string} props.token — Token JWT de autenticação
 * @param {Object} props.user — Utilizador autenticado ({ role, … }) para verificação de permissões
 *
 * @example
 * <DocumentRecipientsManager
 *   token={jwtToken}
 *   user={currentUser}
 * />
 * // Usado dentro de SystemConfigPage como tab
 */
import React, { useState, useEffect } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "./ui/card";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import { Switch } from "./ui/switch";
import { Textarea } from "./ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "./ui/alert-dialog";
import { ScrollArea } from "./ui/scroll-area";
import { Separator } from "./ui/separator";
import {
  Plus,
  Pencil,
  Trash2,
  Building2,
  Mail,
  Check,
  X,
  Save,
  Loader2,
  GripVertical,
  Eye,
  AlertCircle,
} from "lucide-react";
import { toast } from "sonner";
import ReactQuill from 'react-quill-new';

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

const DocumentRecipientsManager = ({ token, user }) => {
  // Estado
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recipients, setRecipients] = useState([]);
  const [enabled, setEnabled] = useState(false);
  const [emailTemplate, setEmailTemplate] = useState("");
  const [defaultTo, setDefaultTo] = useState("");
  const [defaultToName, setDefaultToName] = useState("");
  const [defaultToEmails, setDefaultToEmails] = useState([]);
  const [newToEmail, setNewToEmail] = useState("");
  const [hasChanges, setHasChanges] = useState(false);

  // Dialog states
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [editingRecipient, setEditingRecipient] = useState(null);
  const [deletingRecipient, setDeletingRecipient] = useState(null);

  // Form state
  const [formData, setFormData] = useState({
    name: "",
    email: "",
    active: true,
  });

  // Carregar dados
  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/emails/document-recipients`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setEnabled(data.enabled || false);
        setRecipients(data.recipients || []);
        setEmailTemplate(data.email_template || "");
        setDefaultTo(data.default_to || "");
        setDefaultTo(data.default_to || "geral@powerealestate.pt");
        setDefaultToName(data.default_to_name || "Power Real Estate");
        setDefaultToEmails(data.default_to_emails || []);
      }
    } catch (error) {
      console.error("Erro ao carregar configuração:", error);
      toast.error("Erro ao carregar configuração");
    } finally {
      setLoading(false);
    }
  };

  // Guardar configuração
  const saveConfig = async () => {
    setSaving(true);
    try {
      const response = await fetch(`${API_URL}/api/system-config/document_recipients`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          enabled,
          recipients: JSON.stringify(recipients),
          email_template: emailTemplate,
          default_to: defaultTo,
          default_to_name: defaultToName,
          default_to_emails: JSON.stringify(defaultToEmails.filter(e => e && e.includes("@"))),
        }),
      });

      if (response.ok) {
        toast.success("Configuração guardada com sucesso");
        setHasChanges(false);
        // Recarregar dados do servidor para confirmar que foi guardado corretamente
        await loadConfig();
      } else {
        const data = await response.json();
        toast.error(data.detail || "Erro ao guardar configuração");
      }
    } catch (error) {
      console.error("Erro ao guardar:", error);
      toast.error("Erro ao guardar configuração");
    } finally {
      setSaving(false);
    }
  };

  // Adicionar/Editar destinatário
  const openAddDialog = () => {
    setFormData({ name: "", email: "", active: true });
    setEditingRecipient(null);
    setShowEditDialog(true);
  };

  const openEditDialog = (recipient, index) => {
    setFormData({ ...recipient });
    setEditingRecipient({ ...recipient, index });
    setShowEditDialog(true);
  };

  const handleSaveRecipient = async () => {
    // Validações
    if (!formData.name.trim()) {
      toast.error("Nome é obrigatório");
      return;
    }
    if (!formData.email.trim()) {
      toast.error("Email é obrigatório");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      toast.error("Email inválido");
      return;
    }

    let newRecipients;
    if (editingRecipient) {
      // Editar existente
      newRecipients = recipients.map((r, i) =>
        i === editingRecipient.index ? { ...formData } : r
      );
    } else {
      // Adicionar novo
      newRecipients = [...recipients, { ...formData }];
    }

    // Guardar automaticamente
    try {
      const response = await fetch(`${API_URL}/api/system-config/document_recipients`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          enabled,
          recipients: JSON.stringify(newRecipients),
          email_template: emailTemplate,
          default_to: defaultTo,
          default_to_name: defaultToName,
          default_to_emails: JSON.stringify(defaultToEmails.filter(e => e && e.includes("@"))),
        }),
      });

      if (response.ok) {
        toast.success(editingRecipient ? "Destinatário actualizado com sucesso" : "Destinatário adicionado com sucesso");
        setRecipients(newRecipients);
        setHasChanges(false);
        setShowEditDialog(false);
        // Recarregar dados do servidor para confirmar
        await loadConfig();
      } else {
        const data = await response.json();
        toast.error(data.detail || "Erro ao guardar alterações");
      }
    } catch (error) {
      console.error("Erro ao guardar:", error);
      toast.error("Erro ao guardar destinatário");
    }
  };

  // Remover destinatário
  const openDeleteDialog = (recipient, index) => {
    setDeletingRecipient({ ...recipient, index });
    setShowDeleteDialog(true);
  };

  const handleDeleteRecipient = async () => {
    const newRecipients = recipients.filter((_, i) => i !== deletingRecipient.index);
    setRecipients(newRecipients);
    setShowDeleteDialog(false);
    
    // Guardar automaticamente após eliminar
    try {
      const response = await fetch(`${API_URL}/api/system-config/document_recipients`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          enabled,
          recipients: JSON.stringify(newRecipients),
          email_template: emailTemplate,
          default_to: defaultTo,
          default_to_name: defaultToName,
          default_to_emails: JSON.stringify(defaultToEmails.filter(e => e && e.includes("@"))),
        }),
      });

      if (response.ok) {
        toast.success("Destinatário removido com sucesso");
        setHasChanges(false);
        // Recarregar dados do servidor para confirmar
        await loadConfig();
      } else {
        const data = await response.json();
        toast.error(data.detail || "Erro ao guardar alterações");
        // Reverter localmente se falhou
        setRecipients(recipients);
      }
    } catch (error) {
      console.error("Erro ao eliminar:", error);
      toast.error("Erro ao eliminar destinatário");
      // Reverter localmente se falhou
      setRecipients(recipients);
    }
  };

  // Toggle activo
  const toggleActive = async (index) => {
    const newRecipients = recipients.map((r, i) =>
      i === index ? { ...r, active: !r.active } : r
    );
    setRecipients(newRecipients);

    // Guardar automaticamente
    try {
      const response = await fetch(`${API_URL}/api/system-config/document_recipients`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          enabled,
          recipients: JSON.stringify(newRecipients),
          email_template: emailTemplate,
          default_to: defaultTo,
          default_to_name: defaultToName,
          default_to_emails: JSON.stringify(defaultToEmails.filter(e => e && e.includes("@"))),
        }),
      });

      if (response.ok) {
        toast.success(newRecipients[index].active ? "Destinatário activado" : "Destinatário desactivado");
        setHasChanges(false);
      } else {
        const data = await response.json();
        toast.error(data.detail || "Erro ao guardar alterações");
        // Reverter se falhou
        setRecipients(recipients);
      }
    } catch (error) {
      console.error("Erro ao togglear:", error);
      toast.error("Erro ao actualizar destinatário");
      // Reverter se falhou
      setRecipients(recipients);
    }
  };

  // Template padrão HTML profissional
  const defaultTemplate = `<div style="font-family: 'Segoe UI', Arial, sans-serif; color: #333333; line-height: 1.6; max-width: 800px; margin: 0 auto;">
    <p>Estimado(a) Parceiro(a),</p>
    <p>Venho por este meio submeter o pedido de análise para <strong>Transferência de Crédito Habitação</strong>, relativamente ao(s) proponente(s) abaixo identificado(s).</p>

    <h3 style="color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin-top: 30px;">1º Proponente</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; width: 40%;"><strong>Nome:</strong></td><td>{p1_nome}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>E-mail:</strong></td><td>{p1_email}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Contacto:</strong></td><td>{p1_telefone}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Data de Nascimento:</strong></td><td>{p1_data_nascimento}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Documento de Identificação:</strong></td><td>{p1_tipo_doc}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Contribuinte (NIF):</strong></td><td>{p1_nif}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Estado Civil:</strong></td><td>{p1_estado_civil}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Regime de Casamento:</strong></td><td>{p1_regime_casamento}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Profissão:</strong></td><td>{p1_profissao}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Vínculo Laboral:</strong></td><td>{p1_vinculo}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Salário Líquido:</strong></td><td>{p1_salario}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Dependentes:</strong></td><td>{p1_dependentes}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Despesas Mensais:</strong></td><td>{p1_despesas}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Situação bancária (Insolvência/Incumprimento):</strong></td><td>{p1_situacao_bancaria}</td></tr>
    </table>

    <h3 style="color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin-top: 30px;">2º Proponente</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; width: 40%;"><strong>Nome:</strong></td><td>{p2_nome}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>E-mail:</strong></td><td>{p2_email}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Contacto:</strong></td><td>{p2_telefone}</td></tr>
    </table>

    <h3 style="color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin-top: 30px;">Dados do Crédito Atual</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; width: 50%;"><strong>Banco atual:</strong></td><td>{banco_atual}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Nº de titulares do empréstimo:</strong></td><td>{num_titulares}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Contrato celebrado há mais de 2 anos:</strong></td><td>{contrato_mais_2_anos}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Valor de aquisição do imóvel:</strong></td><td>{valor_aquisicao}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Montante em dívida:</strong></td><td>{montante_divida}</td></tr>
    </table>

    <h3 style="color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin-top: 30px;">Dados da Transferência Pretendida</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; width: 50%;"><strong>Valor de multiopções/extra pretendido:</strong></td><td>{valor_extra}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Localidade do imóvel:</strong></td><td>{localidade_imovel}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Existe possibilidade de fiador?:</strong></td><td>{possibilidade_fiador}</td></tr>
    </table>
    
    <p style="margin-top: 30px; margin-bottom: 30px;">Estou ao dispor para qualquer esclarecimento.</p>

    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
    <div style="font-size: 14px; color: #4b5563;">
        <p style="margin: 2px 0;"><strong>{sender_name}</strong></p>
        <p style="margin: 2px 0;">Tlm: {sender_phone}</p>
        <p style="margin: 2px 0;">Email: {sender_email}</p>
        <br>
        <p style="margin: 2px 0;"><strong>PrecisionCrédito</strong></p>
        <p style="margin: 2px 0;">Licença de Intermediação de Crédito nº 0005798AM</p>
    </div>
</div>`;

  // Todas as variáveis disponíveis para templates
  const availableVariables = [
    { name: "{client_name}", desc: "Nome do cliente" },
    { name: "{client_nif}", desc: "NIF do cliente" },
    { name: "{process_number}", desc: "Número do processo" },
    { name: "{documents_list}", desc: "Lista de documentos anexados" },
    { name: "---", desc: "--- 1º Proponente ---" },
    { name: "{p1_nome}", desc: "Nome completo" },
    { name: "{p1_email}", desc: "E-mail" },
    { name: "{p1_telefone}", desc: "Contacto telefónico" },
    { name: "{p1_data_nascimento}", desc: "Data de nascimento" },
    { name: "{p1_tipo_doc}", desc: "Documento de identificação" },
    { name: "{p1_nif}", desc: "Contribuinte (NIF)" },
    { name: "{p1_estado_civil}", desc: "Estado civil" },
    { name: "{p1_regime_casamento}", desc: "Regime de casamento" },
    { name: "{p1_profissao}", desc: "Profissão" },
    { name: "{p1_vinculo}", desc: "Vínculo laboral" },
    { name: "{p1_salario}", desc: "Salário líquido" },
    { name: "{p1_dependentes}", desc: "Nº de dependentes" },
    { name: "{p1_despesas}", desc: "Despesas mensais" },
    { name: "{p1_situacao_bancaria}", desc: "Situação bancária" },
    { name: "---", desc: "--- 2º Proponente ---" },
    { name: "{p2_nome}", desc: "Nome completo" },
    { name: "{p2_email}", desc: "E-mail" },
    { name: "{p2_telefone}", desc: "Contacto telefónico" },
    { name: "---", desc: "--- Crédito Atual ---" },
    { name: "{banco_atual}", desc: "Banco atual" },
    { name: "{num_titulares}", desc: "Nº de titulares" },
    { name: "{contrato_mais_2_anos}", desc: "Contrato > 2 anos" },
    { name: "{valor_aquisicao}", desc: "Valor de aquisição" },
    { name: "{montante_divida}", desc: "Montante em dívida" },
    { name: "---", desc: "--- Transferência ---" },
    { name: "{valor_extra}", desc: "Valor multiopções/extra" },
    { name: "{localidade_imovel}", desc: "Localidade do imóvel" },
    { name: "{possibilidade_fiador}", desc: "Possibilidade de fiador" },
    { name: "---", desc: "--- Remetente ---" },
    { name: "{sender_name}", desc: "Nome do remetente" },
    { name: "{sender_email}", desc: "E-mail do remetente" },
    { name: "{sender_phone}", desc: "Telefone do remetente" },
  ];

  // Adicionar múltiplos emails TO (separados por vírgula, ponto-e-vírgula ou espaço)
  const addMultipleEmails = (input) => {
    if (!input || !input.trim()) return;
    
    // Separar por vírgula, ponto-e-vírgula, ou espaço
    const parts = input.split(/[,;\s]+/).filter(e => e.trim());
    const newEmails = [];
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    
    for (const part of parts) {
      const email = part.trim().toLowerCase();
      if (email && emailRegex.test(email)) {
        // Evitar duplicados
        if (!defaultToEmails.includes(email) && !newEmails.includes(email)) {
          newEmails.push(email);
        }
      }
    }
    
    if (newEmails.length > 0) {
      setDefaultToEmails(prev => [...prev, ...newEmails]);
      setNewToEmail("");
      setHasChanges(true);
    } else if (parts.length > 0) {
      toast.error("Nenhum email válido encontrado. Use formato: email@exemplo.pt");
    }
  };

  // Verificar permissões
  const canEdit = user?.role?.match(/admin|ceo/i);

  if (loading) {
    return (
      <Card>
        <CardContent className="py-12 flex items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!canEdit) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Building2 className="h-5 w-5" />
            Destinatários de Documentação
          </CardTitle>
          <CardDescription>
            Apenas administradores podem configurar destinatários.
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-primary" />
              Destinatários de Documentação
            </CardTitle>
            <CardDescription>
              Configure os balcões/bancos para envio de documentação de clientes
            </CardDescription>
          </div>
          {hasChanges && (
            <Badge variant="outline" className="bg-yellow-50 text-yellow-700">
              Alterações por guardar
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Activar/Desactivar */}
        <div className="flex items-center justify-between p-4 border rounded-lg">
          <div>
            <Label className="font-medium">Activar Envio de Documentação</Label>
            <p className="text-sm text-muted-foreground">
              Permite o envio de documentação para balcões directamente a partir dos processos
            </p>
          </div>
          <Switch
            checked={enabled}
            onCheckedChange={(v) => {
              setEnabled(v);
              setHasChanges(true);
            }}
          />
        </div>

        {enabled && (
          <>
            {/* Configuração do Email Principal (TO) — Múltiplos emails */}
            <div className="space-y-4">
              <h4 className="font-medium flex items-center gap-2">
                <Mail className="h-4 w-4" />
                Email Principal (TO) — Múltiplos Destinatários
              </h4>
              <p className="text-sm text-muted-foreground">
                Adicione todos os emails que devem receber a documentação no campo TO. 
                Pode separar múltiplos emails ou adicioná-los individualmente.
              </p>
              
              {/* Campo de input rápido para adicionar emails */}
              <div className="flex gap-2">
                <Input
                  placeholder="email@exemplo.pt"
                  value={newToEmail}
                  onChange={(e) => setNewToEmail(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === ",") {
                      e.preventDefault();
                      addMultipleEmails(newToEmail);
                    }
                  }}
                />
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => addMultipleEmails(newToEmail)}
                  disabled={!newToEmail.trim()}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  Adicionar
                </Button>
              </div>

              {/* Nome do remetente TO */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Nome TO</Label>
                  <Input
                    placeholder="Power Real Estate"
                    value={defaultToName}
                    onChange={(e) => {
                      setDefaultToName(e.target.value);
                      setHasChanges(true);
                    }}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Email TO primário (compatibilidade)</Label>
                  <Input
                    placeholder="geral@powerealestate.pt"
                    value={defaultTo}
                    onChange={(e) => {
                      setDefaultTo(e.target.value);
                      setHasChanges(true);
                    }}
                  />
                </div>
              </div>

              {/* Lista de emails TO */}
              {defaultToEmails.length > 0 && (
                <div className="space-y-2">
                  <Label className="text-sm text-muted-foreground">
                    {defaultToEmails.length} destinatário(s) TO configurado(s)
                  </Label>
                  <div className="flex flex-wrap gap-2">
                    {defaultToEmails.map((email, index) => (
                      <Badge
                        key={index}
                        variant="secondary"
                        className="flex items-center gap-1 pl-3 pr-1 py-1.5"
                      >
                        <Mail className="h-3 w-3 mr-1" />
                        <span className="text-sm">{email}</span>
                        <button
                          type="button"
                          onClick={() => {
                            setDefaultToEmails(prev => prev.filter((_, i) => i !== index));
                            setHasChanges(true);
                          }}
                          className="ml-1 h-5 w-5 rounded-full hover:bg-muted flex items-center justify-center"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <Separator />

            {/* Lista de Destinatários */}
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="font-medium">Destinatários (BCC)</h4>
                  <p className="text-sm text-muted-foreground">
                    Balcões/bancos que receberão a documentação em BCC (cópia oculta)
                  </p>
                </div>
                <Button onClick={openAddDialog} size="sm">
                  <Plus className="h-4 w-4 mr-2" />
                  Adicionar Destinatário
                </Button>
              </div>

              {recipients.length === 0 ? (
                <div className="text-center py-8 border-2 border-dashed rounded-lg">
                  <Building2 className="h-12 w-12 mx-auto text-muted-foreground opacity-50" />
                  <p className="mt-2 text-muted-foreground">
                    Nenhum destinatário configurado
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Clique em "Adicionar Destinatário" para começar
                  </p>
                </div>
              ) : (
                <ScrollArea className="h-64">
                  <div className="space-y-2">
                    {recipients.map((recipient, index) => (
                      <div
                        key={index}
                        className={`flex items-center gap-3 p-3 border rounded-lg ${
                          !recipient.active ? "opacity-50 bg-muted" : ""
                        }`}
                      >
                        <Building2 className="h-5 w-5 text-muted-foreground" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="font-medium truncate">
                              {recipient.name}
                            </span>
                            {!recipient.active && (
                              <Badge variant="outline" className="text-xs">
                                Inactivo
                              </Badge>
                            )}
                          </div>
                          <span className="text-sm text-muted-foreground truncate block">
                            {recipient.email}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Switch
                            checked={recipient.active}
                            onCheckedChange={() => toggleActive(index)}
                          />
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openEditDialog(recipient, index)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => openDeleteDialog(recipient, index)}
                          >
                            <Trash2 className="h-4 w-4 text-red-500" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              )}
            </div>

            <Separator />

            {/* Template do Email */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div>
                  <Label className="font-medium">Template do Email</Label>
                  <p className="text-sm text-muted-foreground">
                    Personalize a mensagem que será enviada
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setEmailTemplate(defaultTemplate);
                    setHasChanges(true);
                  }}
                >
                  Restaurar Predefinição
                </Button>
              </div>
              <div className="border rounded-md overflow-hidden">
                <ReactQuill
                  theme="snow"
                  value={emailTemplate}
                  onChange={(val) => {
                    setEmailTemplate(val);
                    setHasChanges(true);
                  }}
                  placeholder="Escreva o template do email..."
                  modules={{
                    toolbar: [
                      [{ 'header': [1, 2, 3, false] }],
                      ['bold', 'italic', 'underline', 'strike'],
                      [{ 'color': [] }, { 'background': [] }],
                      [{ 'list': 'ordered' }, { 'list': 'bullet' }],
                      [{ 'align': [] }],
                      ['link'],
                      ['clean'],
                    ],
                  }}
                  formats={['header', 'bold', 'italic', 'underline', 'strike', 'color', 'background', 'list', 'align', 'link']}
                  style={{ minHeight: '200px' }}
                />
              </div>
              <div className="bg-muted p-3 rounded-lg">
                <p className="text-xs font-medium mb-2">Variáveis disponíveis (clique para copiar):</p>
                <div className="max-h-48 overflow-y-auto">
                  <div className="flex flex-wrap gap-1.5">
                    {availableVariables.map((v, i) => (
                      v.name === "---" ? (
                        <span key={i} className="w-full text-xs text-muted-foreground font-medium mt-2 mb-1">{v.desc}</span>
                      ) : (
                        <Badge
                          key={i}
                          variant="outline"
                          className="font-mono text-xs cursor-pointer hover:bg-primary/10"
                          onClick={() => {
                            navigator.clipboard.writeText(v.name);
                            toast.success(`Copiado: ${v.name}`);
                          }}
                          title={v.desc}
                        >
                          {v.name}
                        </Badge>
                      )
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </>
        )}

        {/* Botões de Acção */}
        <div className="flex items-center justify-end gap-2 pt-4 border-t">
          <Button variant="outline" onClick={loadConfig} disabled={saving}>
            Cancelar
          </Button>
          <Button onClick={saveConfig} disabled={saving || !hasChanges}>
            {saving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                A guardar...
              </>
            ) : (
              <>
                <Save className="h-4 w-4 mr-2" />
                Guardar Configuração
              </>
            )}
          </Button>
        </div>
      </CardContent>

      {/* Dialog Adicionar/Editar Destinatário */}
      <Dialog open={showEditDialog} onOpenChange={setShowEditDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingRecipient ? "Editar Destinatário" : "Adicionar Destinatário"}
            </DialogTitle>
            <DialogDescription>
              Configure o balcão/banco que receberá a documentação
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Nome do Balcão/Banco *</Label>
              <Input
                id="name"
                placeholder="Ex: Millennium BCP, Santander, CGD..."
                value={formData.name}
                onChange={(e) =>
                  setFormData({ ...formData, name: e.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email *</Label>
              <Input
                id="email"
                type="email"
                placeholder="balcao@banco.pt"
                value={formData.email}
                onChange={(e) =>
                  setFormData({ ...formData, email: e.target.value })
                }
              />
            </div>
            <div className="flex items-center justify-between">
              <div>
                <Label>Activo</Label>
                <p className="text-sm text-muted-foreground">
                  Destinatários inactivos não aparecem na lista de envio
                </p>
              </div>
              <Switch
                checked={formData.active}
                onCheckedChange={(v) => setFormData({ ...formData, active: v })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowEditDialog(false)}>
              Cancelar
            </Button>
            <Button onClick={handleSaveRecipient}>
              {editingRecipient ? "Guardar Alterações" : "Adicionar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog Confirmar Remoção */}
      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remover Destinatário</AlertDialogTitle>
            <AlertDialogDescription>
              Tem a certeza que deseja remover <strong>{deletingRecipient?.name}</strong>?
              <br />
              Esta ação não pode ser desfeita.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteRecipient} className="bg-red-600 hover:bg-red-700">
              Remover
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  );
};

export default DocumentRecipientsManager;

