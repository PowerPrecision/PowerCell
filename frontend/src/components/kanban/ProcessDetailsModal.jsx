/**
 * ProcessDetailsModal Component
 * 
 * Modal de detalhes do processo - visualização rápida sem navegar para a página completa.
 * 
 * FASE 3 — Paradigma Relacional:
 * - Interface dividida em duas secções claras: "Dados do Cliente" e "Dados do Processo"
 * - Dados do Cliente: Nome, Email, Telemóvel, NIF, Estado Civil (vindos do cliente via client_id)
 * - Dados do Processo: Imóvel, Valores, Crédito, Status, Prioridade
 * - O indicador visual mostra claramente a que entidade cada dado pertence
 * 
 * PERFORMANCE:
 * - Estado isolado do componente pai
 * - Não causa re-renders no KanbanBoard
 */
import React, { memo, useCallback, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Badge } from '../ui/badge';
import { User, Mail, Phone, Home, MapPin, Euro, Calendar, Users, AlertTriangle, Building2, CreditCard, FileText, ExternalLink } from 'lucide-react';
import { safeString } from '../../utils/safeString';
import { getClient } from '../../../services/api';

const ProcessDetailsModal = memo(({
  open,
  onOpenChange,
  process,
  isLockedByOther = false,
  lockedBy,
}) => {
  const navigate = useNavigate();
  const [clientData, setClientData] = useState(null);

  // ── FASE 3: Carregar dados do cliente via client_id ──
  useEffect(() => {
    if (!open || !process?.client_id) {
      setClientData(null);
      return;
    }
    let cancelled = false;
    const fetchClient = async () => {
      try {
        const res = await getClient(process.client_id);
        if (!cancelled) setClientData(res.data);
      } catch {
        // Fallback: usar dados embutidos no processo
        setClientData(null);
      }
    };
    fetchClient();
    return () => { cancelled = true; };
  }, [open, process?.client_id]);

  const handleOpenFullPage = useCallback(() => {
    onOpenChange?.(false);
    navigate(`/process/${process?.id}`);
  }, [navigate, onOpenChange, process?.id]);

  if (!process) return null;

  // Dados do Cliente — vindos do clientData (se disponível) ou do processo (fallback)
  const clientName = clientData?.nome || process.client_name || '';
  const clientEmail = clientData?.contacto?.email || process.client_email || '';
  const clientPhone = clientData?.contacto?.telefone || process.client_phone || '';
  const clientNif = clientData?.dados_pessoais?.nif || process.client_nif || process.personal_data?.nif || '';
  const clientEstadoCivil = clientData?.dados_pessoais?.estado_civil || process.personal_data?.estado_civil || '';

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" aria-describedby="process-dialog-description">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            <span>Detalhes do Processo</span>
            <Button 
              variant="outline" 
              size="sm"
              onClick={handleOpenFullPage}
              className="gap-1"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Abrir Página Completa
            </Button>
          </DialogTitle>
          <DialogDescription id="process-dialog-description" className="sr-only">
            Visualização resumida dos detalhes do processo do cliente
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-5 mt-4">
          {/* Lock collision warning */}
          {isLockedByOther && (
            <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600 dark:text-amber-400 shrink-0" />
              <p className="text-sm text-amber-800 dark:text-amber-200">
                <strong>{lockedBy}</strong> está a editar este processo neste momento. 
                Aguarde um instante para evitar conflitos.
              </p>
            </div>
          )}

          {/* ══════════════════════════════════════════════════════════
              SECÇÃO 1: DADOS DO CLIENTE
              Estes dados pertencem à entidade Cliente (coleção clients).
              Fonte de verdade: GET /clients/{client_id}
              ══════════════════════════════════════════════════════════ */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center h-6 w-6 rounded-full bg-teal-100 dark:bg-teal-900/30">
                <User className="h-3.5 w-3.5 text-teal-700 dark:text-teal-300" />
              </div>
              <h3 className="font-semibold text-lg">Dados do Cliente</h3>
              {process.client_id && (
                <Badge variant="outline" className="text-[10px] border-teal-300 text-teal-700 dark:border-teal-700 dark:text-teal-300 ml-auto">
                  Ficha do Cliente
                </Badge>
              )}
            </div>
            <div className="grid grid-cols-2 gap-3 text-sm bg-teal-50/50 dark:bg-teal-950/10 rounded-lg p-3 border border-teal-100 dark:border-teal-900/30">
              <div>
                <p className="text-muted-foreground text-xs">Nome</p>
                <p className="font-medium">{safeString(clientName)}</p>
              </div>
              {clientEmail && (
                <div>
                  <p className="text-muted-foreground text-xs">Email</p>
                  <p className="font-medium flex items-center gap-1">
                    <Mail className="h-3 w-3" />
                    {safeString(clientEmail)}
                  </p>
                </div>
              )}
              {clientPhone && (
                <div>
                  <p className="text-muted-foreground text-xs">Telefone</p>
                  <p className="font-medium flex items-center gap-1">
                    <Phone className="h-3 w-3" />
                    {safeString(clientPhone)}
                  </p>
                </div>
              )}
              {clientNif && (
                <div>
                  <p className="text-muted-foreground text-xs">NIF</p>
                  <p className="font-medium">{safeString(clientNif)}</p>
                </div>
              )}
              {clientEstadoCivil && (
                <div>
                  <p className="text-muted-foreground text-xs">Estado Civil</p>
                  <p className="font-medium capitalize">{safeString(clientEstadoCivil)}</p>
                </div>
              )}
            </div>
          </div>

          {/* ══════════════════════════════════════════════════════════
              SECÇÃO 2: DADOS DO PROCESSO / NEGÓCIO
              Estes dados pertencem à entidade Processo (coleção processes).
              ══════════════════════════════════════════════════════════ */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <div className="flex items-center justify-center h-6 w-6 rounded-full bg-blue-100 dark:bg-blue-900/30">
                <FileText className="h-3.5 w-3.5 text-blue-700 dark:text-blue-300" />
              </div>
              <h3 className="font-semibold text-lg">Dados do Processo</h3>
              <Badge variant="outline" className="text-[10px] border-blue-300 text-blue-700 dark:border-blue-700 dark:text-blue-300 ml-auto">
                Processo #{process.process_number || '—'}
              </Badge>
            </div>

            {/* Imóvel */}
            {(process.property_type || process.property_location || process.property_value || process.loan_amount) && (
              <div className="bg-blue-50/50 dark:bg-blue-950/10 rounded-lg p-3 border border-blue-100 dark:border-blue-900/30">
                <h4 className="text-xs font-medium text-muted-foreground mb-2 flex items-center gap-1">
                  <Home className="h-3 w-3" />
                  Imóvel
                </h4>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {process.property_type && (
                    <div>
                      <p className="text-muted-foreground text-xs">Tipo</p>
                      <p className="font-medium capitalize">{safeString(process.property_type)}</p>
                    </div>
                  )}
                  {process.property_location && (
                    <div>
                      <p className="text-muted-foreground text-xs">Localização</p>
                      <p className="font-medium flex items-center gap-1">
                        <MapPin className="h-3 w-3" />
                        {safeString(process.property_location)}
                      </p>
                    </div>
                  )}
                  {process.property_value && (
                    <div>
                      <p className="text-muted-foreground text-xs">Valor do Imóvel</p>
                      <p className="font-medium text-emerald-600 flex items-center gap-1">
                        <Euro className="h-3 w-3" />
                        {process.property_value.toLocaleString('pt-PT')}€
                      </p>
                    </div>
                  )}
                  {process.loan_amount && (
                    <div>
                      <p className="text-muted-foreground text-xs">Valor Financiado</p>
                      <p className="font-medium flex items-center gap-1">
                        <Euro className="h-3 w-3" />
                        {process.loan_amount.toLocaleString('pt-PT')}€
                      </p>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Status e Prioridade */}
            <div className="flex gap-2 flex-wrap">
              <Badge variant="outline" className="capitalize">
                {process.status?.replace(/_/g, ' ')}
              </Badge>
              {process.priority && (
                <Badge 
                  variant={process.priority === 'high' ? 'destructive' : 'secondary'}
                  className="capitalize"
                >
                  {process.priority === 'high' ? 'Alta' : process.priority === 'medium' ? 'Média' : 'Baixa'}
                </Badge>
              )}
              {process.prioridade && (
                <Badge 
                  variant={process.prioridade === 'alta' ? 'destructive' : process.prioridade === 'media' ? 'secondary' : 'outline'}
                  className="capitalize"
                >
                  {process.prioridade === 'alta' ? 'Alta' : process.prioridade === 'media' ? 'Média' : 'Baixa'}
                </Badge>
              )}
              {process.service_type && (
                <Badge variant="outline" className="capitalize">
                  {process.service_type.replace(/_/g, ' ')}
                </Badge>
              )}
              {process.process_type && (
                <Badge variant="outline" className="capitalize text-teal-700 border-teal-300">
                  {process.process_type.replace(/_/g, ' ')}
                </Badge>
              )}
            </div>
          </div>

          {/* Atribuições */}
          {(process.consultor_name || process.mediador_name || process.assigned_consultor_name || process.assigned_intermediario_name) && (
            <div className="space-y-3">
              <h3 className="font-semibold text-sm flex items-center gap-2">
                <Users className="h-4 w-4 text-primary" />
                Atribuições
              </h3>
              <div className="grid grid-cols-2 gap-3 text-sm">
                {(process.consultor_name || process.assigned_consultor_name) && (
                  <div>
                    <p className="text-muted-foreground text-xs">Consultor</p>
                    <p className="font-medium">{safeString(process.consultor_name || process.assigned_consultor_name)}</p>
                  </div>
                )}
                {(process.mediador_name || process.assigned_intermediario_name) && (
                  <div>
                    <p className="text-muted-foreground text-xs">Intermediário</p>
                    <p className="font-medium">{safeString(process.mediador_name || process.assigned_intermediario_name)}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Notas */}
          {process.notes && (
            <div className="space-y-2">
              <h3 className="font-semibold text-sm">Notas</h3>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{safeString(process.notes)}</p>
            </div>
          )}

          {/* Datas */}
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            {process.created_at && (
              <span className="flex items-center gap-1">
                <Calendar className="h-3 w-3" />
                Criado: {new Date(process.created_at).toLocaleDateString('pt-PT')}
              </span>
            )}
            {process.updated_at && (
              <span>
                Atualizado: {new Date(process.updated_at).toLocaleDateString('pt-PT')}
              </span>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
});

ProcessDetailsModal.displayName = 'ProcessDetailsModal';

export default ProcessDetailsModal;
