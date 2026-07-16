/**
 * ====================================================================
 * ClientDetailsModal — Componente Reutilizável de Detalhes do Cliente
 * ====================================================================
 * PACOTE CH — Extraído de ClientRegistrationsPage.js para reutilização
 * global. Mostra dados completos do cliente (contactos, dados pessoais,
 * financeiros, imobiliários, 2º titular) + bloco "Observações" (notas).
 *
 * PROPS:
 *   - open: boolean (controla visibilidade)
 *   - clientId: string | null (ID do cliente a carregar)
 *   - onClose: () => void (callback ao fechar)
 *   - onNavigateToProcess?: (processId: string) => void (opcional)
 *
 * USO:
 *   <ClientDetailsModal
 *     open={showModal}
 *     clientId={selectedClientId}
 *     onClose={() => setShowModal(false)}
 *     onNavigateToProcess={(pid) => navigate(`/process/${pid}`)}
 *   />
 * ====================================================================
 */
import React, { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import {
  User,
  Phone,
  Mail,
  MapPin,
  Heart,
  Briefcase,
  FileText,
  Hash,
  DollarSign,
  Building,
  Clock,
  Calendar,
  CreditCard,
  Users,
  StickyNote,
  Loader2,
  Sparkles,
  MessageSquare,
  ExternalLink,
  KeyRound,
} from "lucide-react";
import { safeString } from "../utils/safeString";
import { formatDate, formatDateTime } from "../lib/utils";
import { resendPortalAccess } from "../services/api";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ClientDetailsModal = ({
  open,
  clientId,
  onClose,
  onNavigateToProcess,
}) => {
  const [client, setClient] = useState(null);
  const [loading, setLoading] = useState(false);
  const [resendingPortal, setResendingPortal] = useState(false);

  // Carregar detalhes do cliente quando abre
  const fetchClient = useCallback(async (id) => {
    setLoading(true);
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(`${API_URL}/api/clients/${id}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setClient(data);
      }
    } catch (error) {
      console.error("Erro ao carregar detalhes do cliente:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open && clientId) {
      fetchClient(clientId);
    } else if (!open) {
      setClient(null);
    }
  }, [open, clientId, fetchClient]);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="h-5 w-5" />
            Detalhes do Cliente
          </DialogTitle>
          <DialogDescription>
            Informações completas do cliente
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : client ? (
          <div className="py-4 space-y-6">
            {/* Nome e Info Básica */}
            <div className="flex items-center gap-4 pb-4 border-b">
              <div className="h-16 w-16 rounded-full bg-primary/10 flex items-center justify-center">
                <span className="text-2xl font-bold text-primary">
                  {safeString(client.nome).charAt(0)?.toUpperCase() || "?"}
                </span>
              </div>
              <div>
                <h3 className="text-xl font-bold">{safeString(client.nome)}</h3>
                <div className="flex items-center gap-2 mt-1">
                  {client.fonte && (
                    <Badge variant="outline">{safeString(client.fonte)}</Badge>
                  )}
                  {client.nif && (
                    <Badge variant="secondary" className="font-mono">
                      NIF: {safeString(client.nif)}
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            {/* Contactos */}
            <div>
              <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <Phone className="h-4 w-4" />
                Contactos
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {client.contacto?.email && (
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Mail className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm">{safeString(client.contacto.email)}</span>
                  </div>
                )}
                {client.contacto?.telefone && (
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Phone className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm">{safeString(client.contacto.telefone)}</span>
                  </div>
                )}
                {client.contacto?.email_secundario && (
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Mail className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm">{safeString(client.contacto.email_secundario)}</span>
                  </div>
                )}
                {client.contacto?.telefone_secundario && (
                  <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                    <Phone className="h-4 w-4 text-muted-foreground" />
                    <span className="text-sm">{safeString(client.contacto.telefone_secundario)}</span>
                  </div>
                )}
                {!client.contacto?.email && !client.contacto?.telefone && (
                  <p className="text-sm text-muted-foreground col-span-2">Sem contactos registados</p>
                )}
              </div>
            </div>

            {/* Dados Pessoais */}
            <div>
              <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <User className="h-4 w-4" />
                Dados Pessoais
              </h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-xs text-muted-foreground">Data de Nascimento</p>
                    <p className="text-sm">{client.dados_pessoais?.data_nascimento ? formatDate(client.dados_pessoais.data_nascimento) : <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                  <MapPin className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-xs text-muted-foreground">Naturalidade</p>
                    <p className="text-sm">{safeString(client.dados_pessoais?.naturalidade) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                  <MapPin className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-xs text-muted-foreground">Nacionalidade</p>
                    <p className="text-sm">{safeString(client.dados_pessoais?.nacionalidade) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                  <Heart className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-xs text-muted-foreground">Estado Civil</p>
                    <p className="text-sm">{safeString(client.dados_pessoais?.estado_civil) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                  <Briefcase className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-xs text-muted-foreground">Profissão</p>
                    <p className="text-sm">{safeString(client.dados_pessoais?.profissao) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-xs text-muted-foreground">Documento ID</p>
                    <p className="text-sm">{safeString(client.dados_pessoais?.documento_id) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                  <Hash className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <p className="text-xs text-muted-foreground">NIF</p>
                    <p className="text-sm">{safeString(client.dados_pessoais?.nif) || safeString(client.nif) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                  </div>
                </div>
                <div className="flex items-start gap-2 p-2 bg-muted/50 rounded-lg">
                  <MapPin className="h-4 w-4 text-muted-foreground mt-0.5" />
                  <div>
                    <p className="text-xs text-muted-foreground">Morada Fiscal</p>
                    <p className="text-sm">{safeString(client.dados_pessoais?.morada_fiscal) || <span className="text-muted-foreground italic">Não preenchido</span>}</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Dados Financeiros */}
            {client.dados_financeiros && Object.keys(client.dados_financeiros).length > 0 && (
              <div>
                <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <DollarSign className="h-4 w-4" />
                  Dados Financeiros
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {client.dados_financeiros?.rendimento_mensal && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <DollarSign className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Rendimento Mensal</p>
                        <p className="text-sm font-medium">
                          {new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(safeString(client.dados_financeiros.rendimento_mensal))}
                        </p>
                      </div>
                    </div>
                  )}
                  {client.dados_financeiros?.tipo_contrato && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Tipo de Contrato</p>
                        <p className="text-sm">{safeString(client.dados_financeiros?.tipo_contrato)}</p>
                      </div>
                    </div>
                  )}
                  {client.dados_financeiros?.empresa && (
                    <div className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                      <Building className="h-4 w-4 text-muted-foreground" />
                      <div>
                        <p className="text-xs text-muted-foreground">Empresa</p>
                        <p className="text-sm">{safeString(client.dados_financeiros?.empresa)}</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 2º Titular */}
            {client.titular2_data && Object.keys(client.titular2_data).length > 0 && (
              <div>
                <h4 className="text-sm font-semibold mb-3 flex items-center gap-2">
                  <Users className="h-4 w-4" />
                  2.º Titular
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {Object.entries(client.titular2_data).map(([key, value]) => (
                    value !== null && value !== undefined && value !== "" && (
                      <div key={key} className="flex items-center gap-2 p-2 bg-muted/50 rounded-lg">
                        <User className="h-4 w-4 text-muted-foreground" />
                        <div>
                          <p className="text-xs text-muted-foreground capitalize">{key.replace(/_/g, " ")}</p>
                          <p className="text-sm">{safeString(value)}</p>
                        </div>
                      </div>
                    )
                  ))}
                </div>
              </div>
            )}

            {/* Metadados */}
            <div className="pt-4 border-t">
              <div className="grid grid-cols-2 gap-4 text-sm text-muted-foreground">
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4" />
                  <span>Registado em: {formatDate(client.created_at)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  <span>Atualizado em: {formatDate(client.updated_at)}</span>
                </div>
              </div>
            </div>

            {/* ============================================================
                PACOTE DA — Secção "Observações e IA" (INCONDICIONAL + AGREGADA)
                ============================================================
                A secção renderiza SEMPRE. Dentro dela:
                1. Notas da IA (ai_extracted_notes) — se houver
                2. Observações manuais (notas) — se houver
                3. Atividade Recente (latest_activity) — se houver
                CRÍTICO: Se TODOS vazios → fallback itálico cinza.
                ============================================================ */}
            {(() => {
              const hasAiNotes = !!safeString(client.ai_extracted_notes);
              const hasManualNotes = !!safeString(client.notas);
              const latestAct = client.latest_activity;
              const hasActivity = !!(latestAct && safeString(latestAct.comment));
              const hasAnyContent = hasAiNotes || hasManualNotes || hasActivity;

              if (!hasAnyContent) {
                return (
                  <div className="text-center py-6 px-4 bg-muted/30 rounded-lg border border-dashed">
                    <p className="text-sm text-muted-foreground italic">
                      Nenhuma observação, nota da IA ou atividade recente registada.
                    </p>
                  </div>
                );
              }

              return (
                <div className="space-y-4">
                  {/* ── Notas da IA (ai_extracted_notes) — só se houver ── */}
                  {hasAiNotes && (
                    <div className="bg-purple-50 dark:bg-purple-950/20 border border-purple-200 dark:border-purple-800 rounded-lg p-4">
                      <h4 className="text-sm font-semibold mb-2 flex items-center gap-2 text-purple-700 dark:text-purple-300">
                        <Sparkles className="h-4 w-4" />
                        Notas da IA
                        <span className="text-[9px] font-normal px-1.5 py-0.5 rounded border border-purple-300 text-purple-600">
                          Automático
                        </span>
                      </h4>
                      <p className="text-sm whitespace-pre-wrap text-purple-900 dark:text-purple-200">
                        {safeString(client.ai_extracted_notes)}
                      </p>
                    </div>
                  )}

                  {/* ── Observações manuais (client.notas) — só se houver ── */}
                  {hasManualNotes && (
                    <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                      <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                        <StickyNote className="h-4 w-4 text-amber-600" />
                        Observações
                      </h4>
                      <p className="text-sm whitespace-pre-wrap text-amber-900 dark:text-amber-200">
                        {safeString(client.notas)}
                      </p>
                    </div>
                  )}

                  {/* ── Atividade Recente (latest_activity) — só se houver ── */}
                  {hasActivity && (
                    <div className="bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                      <h4 className="text-sm font-semibold mb-2 flex items-center gap-2 text-blue-700 dark:text-blue-300">
                        <MessageSquare className="h-4 w-4" />
                        Atividade Recente
                      </h4>
                      <p className="text-sm whitespace-pre-wrap text-blue-900 dark:text-blue-200 mb-2">
                        {safeString(latestAct.comment)}
                      </p>
                      <div className="flex items-center gap-3 text-xs text-blue-600 dark:text-blue-400">
                        {latestAct.user_name && (
                          <span>por {safeString(latestAct.user_name)}</span>
                        )}
                        {latestAct.created_at && (
                          <span>{formatDateTime(latestAct.created_at)}</span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })()}
          </div>
        ) : null}

        {/* ============================================================
            PACOTE DC — Acesso ao Portal do Cliente
            ============================================================ */}
        {client?.portal_access && (
          <div className="mt-4 p-4 rounded-lg border border-teal-200 dark:border-teal-800 bg-teal-50/50 dark:bg-teal-950/20">
            <div className="flex items-center gap-2 mb-3">
              <KeyRound className="h-4 w-4 text-teal-600 dark:text-teal-400" />
              <h4 className="text-sm font-semibold text-teal-800 dark:text-teal-200">
                Acesso ao Portal do Cliente
              </h4>
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Código de Acesso:</span>
                <span className="font-mono font-bold text-base text-teal-700 dark:text-teal-300 tracking-wider">
                  {client.portal_access.portal_access_code || "—"}
                </span>
              </div>
              {client.portal_access.magic_link && (
                <div className="flex items-center justify-between gap-2">
                  <span className="text-muted-foreground">Link ativo:</span>
                  <a
                    href={client.portal_access.magic_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-blue-600 dark:text-blue-400 hover:underline text-xs truncate max-w-[280px]"
                    title={client.portal_access.magic_link}
                  >
                    {client.portal_access.magic_link}
                  </a>
                </div>
              )}
              {!client.portal_access.has_active_token && (
                <p className="text-xs text-amber-600 dark:text-amber-400">
                  Sem link ativo — clique em "Reenviar" para gerar um novo.
                </p>
              )}
            </div>
            <div className="mt-3 flex gap-2">
              <Button
                size="sm"
                variant="outline"
                className="gap-1.5 border-teal-300 text-teal-700 hover:bg-teal-100 dark:border-teal-700 dark:text-teal-300"
                disabled={resendingPortal}
                onClick={async () => {
                  setResendingPortal(true);
                  try {
                    const res = await resendPortalAccess(clientId);
                    toast.success("Email de acesso ao Portal reenviado com sucesso.");
                    const data = res.data;
                    setClient(prev => prev ? {
                      ...prev,
                      portal_access: {
                        portal_access_code: data.portal_access_code || prev.portal_access?.portal_access_code,
                        short_id: data.short_id,
                        magic_link: data.magic_link,
                        has_active_token: !!data.short_id,
                      },
                    } : prev);
                  } catch (err) {
                    const msg = err?.response?.data?.detail || err?.message || "Erro ao reenviar email.";
                    toast.error(msg, { duration: 6000 });
                  } finally {
                    setResendingPortal(false);
                  }
                }}
              >
                {resendingPortal ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Mail className="h-3.5 w-3.5" />
                )}
                Reenviar Acesso ao Portal
              </Button>
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>
          {/* PACOTE DB — Botão "Abrir Processo Completo" destacado no rodapé.
              Navega para /process/{id} (página dedicada de ProcessDetails).
              Só aparece se o cliente tem processo e o pai passou onNavigateToProcess. */}
          {client?.has_process && client?.processes?.length > 0 && onNavigateToProcess && (
            <Button
              onClick={() => {
                onClose();
                const procs = client.processes;
                const activeProc = procs.find(
                  (p) => !p.is_deleted && p.status !== "eliminado"
                ) || procs[0];
                onNavigateToProcess(activeProc.id);
              }}
              className="gap-2 bg-blue-600 hover:bg-blue-700 text-white font-medium"
            >
              <ExternalLink className="h-4 w-4" />
              Abrir Processo Completo
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ClientDetailsModal;
