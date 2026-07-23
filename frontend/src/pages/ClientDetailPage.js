/**
 * ClientDetailPage — Página de ficha detalhada de um cliente.
 *
 * PORQUÊ: Antes desta página, o botão "Ver Ficha" nos clientes navegava para o
 * primeiro processo do cliente, não para uma página própria do cliente. Esta página
 * centraliza todos os dados do cliente (pessoais, contacto, processos associados)
 * numa vista dedicada, seguindo o padrão visual premium CRM do PowerCell.
 *
 * ROTA: /cliente/:id (ID do cliente, não do processo)
 *
 * @context {AuthContext} — Consome user para autenticação e permissões
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Separator } from "../components/ui/separator";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { AIBadge, getFieldMeta, buildManualMetadata } from "../components/ui/AIBadge";
import {
  ArrowLeft,
  User,
  Users,
  Phone,
  Mail,
  Hash,
  MapPin,
  Briefcase,
  Heart,
  Calendar,
  Tag,
  ArrowRight,
  Loader2,
  AlertCircle,
  RefreshCw,
  Info,
  StickyNote,
  FolderOpen,
  FileStack,
  Pencil,
  Check,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { getClient, getClientFiles, updateClient } from "../services/api";
import { pt } from "date-fns/locale";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { safeFormat } from "../lib/utils";
import { extractErrorMessage } from "../utils/extractErrorMessage";

/**
 * Calcula a cor de texto (preto ou branco) com base na luminosidade da cor de fundo.
 */
const getContrastColor = (bgColor) => {
  if (!bgColor) return "#ffffff";
  const namedColors = {
    yellow: "#EAB308",
    orange: "#F97316",
    blue: "#3B82F6",
    green: "#22C55E",
    red: "#EF4444",
    purple: "#A855F7",
    gray: "#6B7280",
    grey: "#6B7280",
  };
  let hex = namedColors[bgColor?.toLowerCase()] || bgColor;
  if (!hex.startsWith("#")) return "#ffffff";
  const clean = hex.replace("#", "");
  const r = parseInt(clean.substring(0, 2), 16);
  const g = parseInt(clean.substring(2, 4), 16);
  const b = parseInt(clean.substring(4, 6), 16);
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return luminance > 0.55 ? "#1a1a1a" : "#ffffff";
};

/**
 * Formata um tipo de processo: substitui underscores por espaços e capitaliza.
 */
const formatProcessType = (type) => {
  if (!type) return "-";
  return type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

/**
 * Retorna a classe de cor do badge de prioridade.
 */
const getPriorityBadge = (priority) => {
  const p = (priority || "").toLowerCase();
  if (p === "alta" || p === "high")
    return "bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-300 dark:border-red-800";
  if (p === "media" || p === "medium")
    return "bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300 dark:border-yellow-800";
  if (p === "baixa" || p === "low")
    return "bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800";
  return "bg-gray-100 text-gray-800 border-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700";
};

/**
 * Retorna a classe de cor do badge de status.
 */
const getStatusBadgeClasses = (statusColor) => {
  return {
    backgroundColor: statusColor || "#6B7280",
    color: getContrastColor(statusColor),
  };
};

const formatDate = (dateString) => {
  if (!dateString || (typeof dateString !== 'string' && !(dateString instanceof Date))) return "-";
  return safeFormat(dateString, "dd MMM yyyy", { locale: pt });
};

/**
 * Returns a left-border color class based on process status color.
 */
const getStatusBorderClass = (statusColor) => {
  if (!statusColor) return "border-l-gray-400 dark:border-l-gray-600";
  // Convert common named colors to tailwind border classes
  const colorMap = {
    yellow: "border-l-yellow-500",
    orange: "border-l-orange-500",
    blue: "border-l-blue-500",
    green: "border-l-green-500",
    red: "border-l-red-500",
    purple: "border-l-purple-500",
    gray: "border-l-gray-400",
    grey: "border-l-gray-400",
  };
  const lower = statusColor.toLowerCase();
  if (colorMap[lower]) return colorMap[lower];
  // For hex colors, use inline style instead
  return null;
};

/**
 * Contact info row component for the profile card.
 * Supports inline editing when onEdit prop is provided.
 */
function ContactRow({ icon: Icon, label, children, editable, onEdit, saving, meta }) {
  const [editing, setEditing] = useState(false);
  const [editValue, setEditValue] = useState("");
  const inputRef = useRef(null);

  const startEdit = () => {
    // Extract current text value from children
    let currentValue = "";
    if (typeof children === "string") {
      currentValue = children;
    } else if (children?.props?.children) {
      currentValue = children.props.children;
    }
    setEditValue(currentValue || "");
    setEditing(true);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const cancelEdit = () => {
    setEditing(false);
    setEditValue("");
  };

  const saveEdit = () => {
    if (onEdit) {
      onEdit(editValue);
    }
    setEditing(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") saveEdit();
    if (e.key === "Escape") cancelEdit();
  };

  return (
    <div className="flex items-center gap-3 py-2.5 px-3 rounded-lg transition-all duration-200 hover:bg-muted/60 group">
      <div className="flex-shrink-0 p-2 rounded-md bg-muted/80 group-hover:bg-teal-50 dark:group-hover:bg-teal-900/20 transition-colors duration-200">
        <Icon className="h-4 w-4 text-muted-foreground group-hover:text-teal-600 dark:group-hover:text-teal-400 transition-colors duration-200" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1 mb-0.5">
          <p className="text-xs text-muted-foreground leading-none">{label}</p>
          {meta && <AIBadge {...meta} />}
        </div>
        {editing ? (
          <div className="flex items-center gap-1.5">
            <Input
              ref={inputRef}
              value={editValue}
              onChange={(e) => setEditValue(e.target.value)}
              onKeyDown={handleKeyDown}
              className="h-7 text-sm py-0"
              disabled={saving}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={saveEdit}
              disabled={saving}
              className="h-7 w-7 p-0 text-green-600 hover:text-green-700 hover:bg-green-50"
            >
              {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={cancelEdit}
              disabled={saving}
              className="h-7 w-7 p-0 text-red-500 hover:text-red-600 hover:bg-red-50"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5">
            <div className="font-medium text-sm truncate flex-1">{children}</div>
            {editable && (
              <Button
                variant="ghost"
                size="sm"
                onClick={startEdit}
                className="h-6 w-6 p-0 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-teal-600 hover:bg-teal-50"
              >
                <Pencil className="h-3 w-3" />
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Render-safe: garante que nunca se renderiza um objecto como React child. */
const renderSafe = (val) => (typeof val === 'string' || typeof val === 'number' ? val : "-");

export default function ClientDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [client, setClient] = useState(null);
  const [processes, setProcesses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [clientDocs, setClientDocs] = useState([]);
  const [docsLoading, setDocsLoading] = useState(false);
  const [savingField, setSavingField] = useState(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editForm, setEditForm] = useState({ nome: "", nif: "", email: "", telefone: "" });
  const [editSaving, setEditSaving] = useState(false);

  // Abrir modal de edição com dados atuais do cliente
  const openEditModal = () => {
    const contato = client?.contacto || {};
    const dadosPessoais = client?.dados_pessoais || {};
    setEditForm({
      nome: client?.nome || "",
      nif: dadosPessoais.nif || "",
      email: contato.email || "",
      telefone: contato.telefone || "",
    });
    setEditModalOpen(true);
  };

  // Guardar edição do cliente via modal
  const handleEditSave = async () => {
    setEditSaving(true);
    try {
      const payload = {};
      // Pacote CT: recolher caminhos de campos alterados para marcar proveniência manual
      const changedPaths = [];
      if (editForm.nome && editForm.nome !== client?.nome) {
        payload.nome = editForm.nome;
        changedPaths.push("nome");
      }
      const currentContato = client?.contacto || {};
      const currentDadosPessoais = client?.dados_pessoais || {};
      const emailChanged = editForm.email !== currentContato.email;
      const telefoneChanged = editForm.telefone !== currentContato.telefone;
      const contatoChanged = emailChanged || telefoneChanged;
      if (contatoChanged) {
        payload.contacto = {
          ...currentContato,
          email: editForm.email || currentContato.email,
          telefone: editForm.telefone || currentContato.telefone,
        };
        if (emailChanged) changedPaths.push("contacto.email");
        if (telefoneChanged) changedPaths.push("contacto.telefone");
      }
      const nifChanged = editForm.nif !== currentDadosPessoais.nif;
      if (nifChanged) {
        payload.dados_pessoais = {
          ...currentDadosPessoais,
          nif: editForm.nif,
        };
        changedPaths.push("dados_pessoais.nif");
      }

      // Pacote CT: anexar field_metadata com source="manual" para os campos alterados.
      // O backend (Pacote CS) faz merge seguro — preserva metadata dos restantes.
      const manualMeta = buildManualMetadata(changedPaths);
      if (manualMeta) {
        payload.field_metadata = manualMeta;
      }

      // Só fazer update se houver alterações
      if (Object.keys(payload).length > 0) {
        await updateClient(id, payload);
        // Atualizar estado local (inclui field_metadata para o AIBadge reagir)
        setClient((prev) => ({
          ...prev,
          ...(payload.nome && { nome: payload.nome }),
          ...(payload.contacto && { contacto: payload.contacto }),
          ...(payload.dados_pessoais && { dados_pessoais: payload.dados_pessoais }),
          ...(manualMeta && {
            field_metadata: { ...(prev.field_metadata || {}), ...manualMeta },
          }),
        }));
        toast.success("Dados do cliente atualizados com sucesso");
      }
      setEditModalOpen(false);
    } catch (err) {
      toast.error(extractErrorMessage(err.response?.data?.detail, "Erro ao atualizar dados do cliente"));
    } finally {
      setEditSaving(false);
    }
  };

  const fetchClientData = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      // Fetch client data (backend returns processes array with enriched data)
      const clientRes = await getClient(id);
      const clientData = clientRes.data;
      setClient(clientData);

      // Processes are now included in the client response from the backend
      if (clientData.processes && Array.isArray(clientData.processes)) {
        setProcesses(clientData.processes);
      } else {
        setProcesses([]);
      }
    } catch (err) {
      console.error("Erro ao carregar cliente:", err);
      if (err.response?.status === 404) {
        setError("Cliente não encontrado.");
      } else {
        setError("Erro ao carregar dados do cliente. Tente novamente.");
      }
      toast.error("Erro ao carregar dados do cliente");
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchClientData();
  }, [fetchClientData]);

  const fetchClientDocuments = useCallback(async () => {
    if (!id) return;
    setDocsLoading(true);
    try {
      const res = await getClientFiles(id);
      const docs = res.data?.files || res.data;
      setClientDocs(Array.isArray(docs) ? docs : []);
    } catch {
      // Silently ignore — docs section is supplementary
      setClientDocs([]);
    } finally {
      setDocsLoading(false);
    }
  }, [id]);

  useEffect(() => {
    fetchClientDocuments();
  }, [fetchClientDocuments, processes]);

  // Loading state
  if (loading) {
    return (
      <DashboardLayout title="Ficha do Cliente">
        <div className="flex items-center justify-center min-h-[400px]" data-testid="loading-state">
          <div className="flex flex-col items-center gap-3">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
            <p className="text-muted-foreground text-sm">A carregar ficha do cliente...</p>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  // Error state
  if (error || !client) {
    return (
      <DashboardLayout title="Ficha do Cliente">
        <div className="flex items-center justify-center min-h-[400px]">
          <div className="flex flex-col items-center gap-4 text-center max-w-md">
            <div className="p-4 bg-red-100 dark:bg-red-900/30 rounded-full">
              <AlertCircle className="h-8 w-8 text-red-600 dark:text-red-400" />
            </div>
            <h2 className="text-xl font-semibold">
              {error || "Cliente não encontrado"}
            </h2>
            <p className="text-muted-foreground text-sm">
              Não foi possível carregar os dados deste cliente.
            </p>
            <Button
              variant="outline"
              onClick={() => navigate("/clientes")}
              className="gap-2"
            >
              <ArrowLeft className="h-4 w-4" />
              Voltar aos Clientes
            </Button>
          </div>
        </div>
      </DashboardLayout>
    );
  }

  const contato = client.contacto || {};
  const dadosPessoais = client.dados_pessoais || {};

  return (
    <DashboardLayout title="Ficha do Cliente">
      <div className="space-y-6" data-testid="client-detail-page">
        {/* Header with back button */}
        <div className="flex items-center justify-between">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/clientes")}
            className="gap-2 text-muted-foreground hover:text-foreground transition-colors duration-200"
          >
            <ArrowLeft className="h-4 w-4" />
            Voltar
          </Button>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={openEditModal}
              className="gap-2 transition-colors duration-200"
            >
              <Pencil className="h-4 w-4" />
              Editar Cliente
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={fetchClientData}
              className="gap-2 text-muted-foreground hover:text-foreground transition-colors duration-200"
            >
              <RefreshCw className="h-4 w-4" />
              Atualizar
            </Button>
          </div>
        </div>

        {/* Main 2-column grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* ─── LEFT COLUMN: Profile Card (1/3) ─── */}
          <div className="lg:col-span-1">
            <Card className="rounded-xl shadow-sm overflow-hidden">
              {/* Gradient header with avatar */}
              <div className="bg-gradient-to-br from-teal-500 to-emerald-600 px-6 pt-8 pb-6 text-center relative">
                {/* Decorative circles */}
                <div className="absolute top-0 right-0 w-24 h-24 bg-white/10 rounded-full -translate-y-8 translate-x-8" />
                <div className="absolute bottom-0 left-0 w-16 h-16 bg-white/10 rounded-full translate-y-6 -translate-x-6" />

                <div className="relative">
                  <div className="h-20 w-20 rounded-full bg-white/20 backdrop-blur-sm flex items-center justify-center mx-auto ring-4 ring-white/30 shadow-lg">
                    <span className="text-3xl font-bold text-white">
                      {(typeof client.nome === 'string' && client.nome.charAt(0)?.toUpperCase()) || "?"}
                    </span>
                  </div>
                  <h1 className="text-2xl font-bold text-white mt-4 leading-tight">
                    {renderSafe(client.nome)}
                  </h1>
                  <p className="text-teal-100 text-sm mt-1">
                    Ficha do Cliente
                  </p>
                </div>
              </div>

              <CardContent className="p-0">
                {/* Contact info rows */}
                <div className="px-2 pt-4 pb-2 space-y-0.5">
                  <ContactRow
                    icon={Mail}
                    label="Email"
                    editable
                    saving={savingField === "email"}
                    meta={getFieldMeta("contacto.email", client?.field_metadata) || undefined}
                    onEdit={async (value) => {
                      setSavingField("email");
                      try {
                        await updateClient(id, {
                          contacto: { email: value },
                          field_metadata: buildManualMetadata(["contacto.email"]),
                        });
                        setClient((prev) => ({
                          ...prev,
                          contacto: { ...(prev.contacto || {}), email: value },
                          field_metadata: {
                            ...(prev.field_metadata || {}),
                            "contacto.email": { source: "manual", updated_at: new Date().toISOString() },
                          },
                        }));
                        toast.success("Email atualizado com sucesso");
                      } catch (err) {
                        toast.error(extractErrorMessage(err.response?.data?.detail, "Erro ao guardar email"));
                      } finally {
                        setSavingField(null);
                      }
                    }}
                  >
                    {contato.email ? (
                      <a
                        href={`mailto:${contato.email}`}
                        className="text-teal-600 dark:text-teal-400 hover:underline transition-all duration-200"
                      >
                        {contato.email}
                      </a>
                    ) : (
                      <span className="text-muted-foreground italic text-xs">Adicionar email...</span>
                    )}
                  </ContactRow>

                  <ContactRow
                    icon={Phone}
                    label="Telefone"
                    editable
                    saving={savingField === "telefone"}
                    meta={getFieldMeta("contacto.telefone", client?.field_metadata) || undefined}
                    onEdit={async (value) => {
                      setSavingField("telefone");
                      try {
                        await updateClient(id, {
                          contacto: { telefone: value },
                          field_metadata: buildManualMetadata(["contacto.telefone"]),
                        });
                        setClient((prev) => ({
                          ...prev,
                          contacto: { ...(prev.contacto || {}), telefone: value },
                          field_metadata: {
                            ...(prev.field_metadata || {}),
                            "contacto.telefone": { source: "manual", updated_at: new Date().toISOString() },
                          },
                        }));
                        toast.success("Telefone atualizado com sucesso");
                      } catch (err) {
                        toast.error(extractErrorMessage(err.response?.data?.detail, "Erro ao guardar telefone"));
                      } finally {
                        setSavingField(null);
                      }
                    }}
                  >
                    {contato.telefone ? (
                      <a
                        href={`tel:${contato.telefone}`}
                        className="text-teal-600 dark:text-teal-400 hover:underline transition-all duration-200"
                      >
                        {contato.telefone}
                      </a>
                    ) : (
                      <span className="text-muted-foreground italic text-xs">Adicionar telefone...</span>
                    )}
                  </ContactRow>

                  <ContactRow icon={Hash} label="NIF" meta={getFieldMeta("dados_pessoais.nif", client?.field_metadata) || undefined}>
                    <span className="font-mono">{renderSafe(dadosPessoais.nif)}</span>
                  </ContactRow>

                  <ContactRow icon={Heart} label="Estado Civil" meta={getFieldMeta("dados_pessoais.estado_civil", client?.field_metadata) || undefined}>
                    {renderSafe(dadosPessoais.estado_civil)}
                  </ContactRow>

                  <ContactRow icon={Briefcase} label="Profissão" meta={getFieldMeta("dados_pessoais.profissao", client?.field_metadata) || undefined}>
                    {renderSafe(dadosPessoais.profissao)}
                  </ContactRow>

                  <ContactRow icon={MapPin} label="Morada Fiscal" meta={getFieldMeta("dados_pessoais.morada_fiscal", client?.field_metadata) || undefined}>
                    {renderSafe(dadosPessoais.morada_fiscal)}
                  </ContactRow>
                </div>

                <div className="px-6">
                  <Separator />
                </div>

                {/* Fonte, Tags, Data de criação */}
                <div className="px-6 py-4 space-y-4">
                  {/* Fonte */}
                  <div className="flex items-center gap-3">
                    <Info className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <span className="text-sm text-muted-foreground">Fonte</span>
                    {typeof client.fonte === 'string' || typeof client.fonte === 'number' ? (
                      <Badge variant="outline" className="ml-auto text-xs border-teal-300 text-teal-700 dark:border-teal-700 dark:text-teal-300">
                        {client.fonte}
                      </Badge>
                    ) : (
                      <span className="ml-auto text-sm text-muted-foreground">-</span>
                    )}
                  </div>

                  {/* Tags */}
                  <div className="flex items-start gap-3">
                    <Tag className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
                    <span className="text-sm text-muted-foreground flex-shrink-0">Tags</span>
                    <div className="flex flex-wrap gap-1.5 ml-auto justify-end">
                      {Array.isArray(client.tags) && client.tags.length > 0 ? (
                        client.tags.map((tag, idx) => (
                          <Badge
                            key={idx}
                            variant="secondary"
                            className="text-xs bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                          >
                            {tag}
                          </Badge>
                        ))
                      ) : (
                        <span className="text-sm text-muted-foreground">-</span>
                      )}
                    </div>
                  </div>

                  {/* Data de criação */}
                  <div className="flex items-center gap-3">
                    <Calendar className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                    <span className="text-sm text-muted-foreground">Data de Criação</span>
                    <span className="ml-auto text-sm font-medium">{formatDate(client.created_at)}</span>
                  </div>
                </div>

                {/* Notes section */}
                {client.notas && (
                  <>
                    <div className="px-6">
                      <Separator />
                    </div>
                    <div className="px-6 py-4">
                      <div className="flex items-center gap-2 mb-2">
                        <StickyNote className="h-4 w-4 text-muted-foreground" />
                        <span className="text-xs text-muted-foreground uppercase tracking-wider font-medium">Notas</span>
                      </div>
                      <div className="bg-muted/50 rounded-lg p-3 text-sm whitespace-pre-wrap leading-relaxed border border-border/50">
                        {client.notas}
                      </div>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </div>

          {/* ─── RIGHT COLUMN: Process History (2/3) ─── */}
          <div className="lg:col-span-2">
            {/* Section header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-3">
                <FolderOpen className="h-5 w-5 text-teal-600 dark:text-teal-400" />
                <h2 className="text-lg font-semibold">Histórico de Processos</h2>
                <Badge className="bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300 border-0 text-xs font-medium px-2.5 py-0.5">
                  {processes.length}
                </Badge>
              </div>
              {processes.length > 0 && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                  {processes.filter((p) => p.is_active !== false).length} ativos
                </div>
              )}
            </div>

            {processes.length === 0 ? (
              /* Empty state */
              <Card className="rounded-xl shadow-sm">
                <CardContent className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="p-4 bg-muted/50 rounded-full mb-4">
                    <FolderOpen className="h-10 w-10 text-muted-foreground/40" />
                  </div>
                  <p className="text-muted-foreground font-medium">Sem processos associados</p>
                  <p className="text-muted-foreground/70 text-sm mt-1">
                    Este cliente ainda não tem processos registados.
                  </p>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-3">
                {processes.map((process) => {
                  const borderClass = getStatusBorderClass(process.status_color);
                  const hasInlineBorder = borderClass === null;

                  return (
                    <Card
                      key={process.id}
                      className={`rounded-xl shadow-sm transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 border-l-4 ${borderClass || ""}`}
                      style={hasInlineBorder ? { borderLeftColor: process.status_color } : undefined}
                    >
                      <CardContent className="p-5">
                        {/* Top row: Process number + badges */}
                        <div className="flex flex-wrap items-center gap-2 mb-3">
                          <span className="font-mono font-semibold text-sm text-foreground/80">
                            #{process.process_number || process.id?.substring(0, 8) || "-"}
                          </span>

                          {/* Badge: 2º Titular */}
                          {process.client_role === "2\u00BA titular" && (
                            <Badge className="text-xs font-medium bg-cyan-100 text-cyan-800 border-cyan-300 dark:bg-cyan-900/30 dark:text-cyan-300 dark:border-cyan-700 gap-1">
                              <Users className="h-3 w-3" />
                              2\u00BA Titular
                            </Badge>
                          )}

                          <Badge variant="outline" className="text-xs font-medium">
                            {formatProcessType(process.process_type)}
                          </Badge>

                          {process.status_label || process.status ? (
                            <Badge
                              className="text-xs font-medium"
                              style={getStatusBadgeClasses(process.status_color)}
                            >
                              {process.status_label || process.status}
                            </Badge>
                          ) : null}
                        </div>

                        {/* Nome do titular principal (se este cliente é 2º titular) */}
                        {process.client_role === "2\u00BA titular" && process.client_name && (
                          <div className="mb-3 text-xs text-muted-foreground flex items-center gap-1.5">
                            <User className="h-3 w-3" />
                            Titular principal: <span className="font-medium text-foreground">{process.client_name}</span>
                          </div>
                        )}

                        {/* Middle: Priority */}
                        {(process.prioridade || process.priority) && (
                          <div className="mb-3">
                            <Badge
                              variant="outline"
                              className={`text-xs ${getPriorityBadge(process.prioridade || process.priority)}`}
                            >
                              Prioridade: {process.prioridade || process.priority}
                            </Badge>
                          </div>
                        )}

                        {/* Bottom row: Date + Action */}
                        <div className="flex items-center justify-between pt-2 border-t border-border/50">
                          <div className="flex items-center gap-3 text-xs text-muted-foreground">
                            <div className="flex items-center gap-1.5">
                              <Calendar className="h-3.5 w-3.5" />
                              Criado em {formatDate(process.created_at)}
                            </div>
                            {process.updated_at && (
                              <div className="flex items-center gap-1">
                                Atualizado em {formatDate(process.updated_at)}
                              </div>
                            )}
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => navigate(`/process/${process.id}`)}
                            className="gap-1.5 text-teal-600 hover:text-teal-700 dark:text-teal-400 dark:hover:text-teal-300 hover:bg-teal-50 dark:hover:bg-teal-900/20 transition-all duration-200 font-medium text-xs h-8"
                          >
                            Abrir Processo
                            <ArrowRight className="h-3.5 w-3.5" />
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}

            {/* ─── DOCUMENTAÇÃO DO CLIENTE ─── */}
            <div className="mt-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <FileStack className="h-5 w-5 text-teal-600 dark:text-teal-400" />
                  <h2 className="text-lg font-semibold">Documentação do Cliente</h2>
                  <Badge className="bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-300 border-0 text-xs font-medium px-2.5 py-0.5">
                    {clientDocs.length}
                  </Badge>
                </div>
              </div>

              {docsLoading ? (
                <Card className="rounded-xl shadow-sm">
                  <CardContent className="flex items-center justify-center py-12">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </CardContent>
                </Card>
              ) : clientDocs.length === 0 ? (
                <Card className="rounded-xl shadow-sm">
                  <CardContent className="flex flex-col items-center justify-center py-12 text-center">
                    <div className="p-4 bg-muted/50 rounded-full mb-4">
                      <FileStack className="h-10 w-10 text-muted-foreground/40" />
                    </div>
                    <p className="text-muted-foreground font-medium">Sem documentação</p>
                    <p className="text-muted-foreground/70 text-sm mt-1">
                      Este cliente ainda não tem documentos associados.
                    </p>
                  </CardContent>
                </Card>
              ) : (
                <Card className="rounded-xl shadow-sm">
                  <CardHeader className="pb-2">
                    <CardDescription>
                      Documentos associados a este cliente
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="p-0">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Nome</TableHead>
                          <TableHead>Tipo</TableHead>
                          <TableHead>Data</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {Array.isArray(clientDocs) && clientDocs.map((doc, idx) => (
                          <TableRow key={doc.id || idx}>
                            <TableCell className="font-medium">{doc.name || doc.filename || "-"}</TableCell>
                            <TableCell>{doc.type || doc.category || "-"}</TableCell>
                            <TableCell>{formatDate(doc.created_at || doc.uploaded_at)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </div>

        {/* ── Modal: Editar Cliente ── */}
        <Dialog open={editModalOpen} onOpenChange={setEditModalOpen}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Pencil className="h-5 w-5 text-primary" />
                Editar Dados do Cliente
              </DialogTitle>
              <DialogDescription>
                Edite os dados base do cliente. As alterações serão sincronizadas automaticamente com todos os processos associados.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-2">
              <div className="space-y-2">
                <div className="flex items-center gap-1">
                  <Label htmlFor="edit-nome">Nome Completo</Label>
                  <AIBadge {...(getFieldMeta("nome", client?.field_metadata) || {})} />
                </div>
                <Input
                  id="edit-nome"
                  value={editForm.nome}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, nome: e.target.value }))}
                  placeholder="Nome do cliente"
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-1">
                  <Label htmlFor="edit-nif">NIF</Label>
                  <AIBadge {...(getFieldMeta("dados_pessoais.nif", client?.field_metadata) || {})} />
                </div>
                <Input
                  id="edit-nif"
                  value={editForm.nif}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, nif: e.target.value }))}
                  placeholder="123456789"
                  maxLength={9}
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-1">
                  <Label htmlFor="edit-email">Email</Label>
                  <AIBadge {...(getFieldMeta("contacto.email", client?.field_metadata) || {})} />
                </div>
                <Input
                  id="edit-email"
                  type="email"
                  value={editForm.email}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, email: e.target.value }))}
                  placeholder="email@exemplo.pt"
                />
              </div>
              <div className="space-y-2">
                <div className="flex items-center gap-1">
                  <Label htmlFor="edit-telefone">Telefone</Label>
                  <AIBadge {...(getFieldMeta("contacto.telefone", client?.field_metadata) || {})} />
                </div>
                <Input
                  id="edit-telefone"
                  value={editForm.telefone}
                  onChange={(e) => setEditForm((prev) => ({ ...prev, telefone: e.target.value }))}
                  placeholder="912345678"
                />
              </div>
            </div>
            <DialogFooter className="gap-2">
              <Button
                variant="outline"
                onClick={() => setEditModalOpen(false)}
                disabled={editSaving}
              >
                Cancelar
              </Button>
              <Button onClick={handleEditSave} disabled={editSaving}>
                {editSaving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    A guardar...
                  </>
                ) : (
                  <>
                    <Check className="h-4 w-4 mr-1" />
                    Guardar
                  </>
                )}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
}
