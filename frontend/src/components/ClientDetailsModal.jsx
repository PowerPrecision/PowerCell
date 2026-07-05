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
} from "lucide-react";
import { safeString } from "../utils/safeString";
import { formatDate } from "../lib/utils";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ClientDetailsModal = ({
  open,
  clientId,
  onClose,
  onNavigateToProcess,
}) => {
  const [client, setClient] = useState(null);
  const [loading, setLoading] = useState(false);

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
                PACOTE CZ — Secção "Observações e IA" (INCONDICIONAL)
                ============================================================
                Ambas as secções renderizam SEMPRE (sem && conditional).
                Se o campo estiver vazio, mostra fallback "Sem ...".
                Isto garante que a secção é visível mal a Modal abre.
                ============================================================ */}

            {/* ── Observações manuais (client.notas) — INCONDICIONAL ── */}
            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
              <h4 className="text-sm font-semibold mb-2 flex items-center gap-2">
                <StickyNote className="h-4 w-4 text-amber-600" />
                Observações
              </h4>
              {safeString(client.notas) ? (
                <p className="text-sm whitespace-pre-wrap text-amber-900 dark:text-amber-200">
                  {safeString(client.notas)}
                </p>
              ) : (
                <p className="text-sm text-amber-500 dark:text-amber-600 italic">
                  Sem observações manuais registadas.
                </p>
              )}
            </div>

            {/* ── Notas da IA (client.ai_extracted_notes) — INCONDICIONAL ── */}
            <div className="bg-purple-50 dark:bg-purple-950/20 border border-purple-200 dark:border-purple-800 rounded-lg p-4">
              <h4 className="text-sm font-semibold mb-2 flex items-center gap-2 text-purple-700 dark:text-purple-300">
                <Sparkles className="h-4 w-4" />
                Notas da IA
                <span className="text-[9px] font-normal px-1.5 py-0.5 rounded border border-purple-300 text-purple-600">
                  Automático
                </span>
              </h4>
              {safeString(client.ai_extracted_notes) ? (
                <p className="text-sm whitespace-pre-wrap text-purple-900 dark:text-purple-200">
                  {safeString(client.ai_extracted_notes)}
                </p>
              ) : (
                <p className="text-sm text-purple-400 dark:text-purple-500 italic">
                  Sem notas extraídas pela IA. As notas aparecerão aqui automaticamente após o processamento de documentos.
                </p>
              )}
            </div>
          </div>
        ) : null}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>
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
            >
              <FileText className="h-4 w-4 mr-2" />
              Ver Processo
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ClientDetailsModal;
