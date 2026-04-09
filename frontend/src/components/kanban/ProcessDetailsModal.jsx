/**
 * ProcessDetailsModal Component
 * 
 * Modal de detalhes do processo - visualização rápida sem navegar para a página completa.
 * 
 * RESPONSABILIDADE ÚNICA:
 * - Gerir o estado do modal de detalhes
 * - Renderizar informações resumidas do processo
 * - Fornecer link para página completa
 * 
 * PERFORMANCE:
 * - Estado isolado do componente pai
 * - Não causa re-renders no KanbanBoard quando o utilizador digita em campos
 */
import React, { memo, useCallback } from 'react';
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
import { User, Mail, Phone, Home, MapPin, Euro, Calendar, Users } from 'lucide-react';

const ProcessDetailsModal = memo(({
  open,
  onOpenChange,
  process,
}) => {
  const navigate = useNavigate();

  const handleOpenFullPage = useCallback(() => {
    onOpenChange?.(false);
    navigate(`/process/${process?.id}`);
  }, [navigate, onOpenChange, process?.id]);

  if (!process) return null;

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
            >
              Abrir Página Completa
            </Button>
          </DialogTitle>
          <DialogDescription id="process-dialog-description" className="sr-only">
            Visualização resumida dos detalhes do processo do cliente
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-6 mt-4">
          {/* Cliente Info */}
          <div className="space-y-3">
            <h3 className="font-semibold text-lg flex items-center gap-2">
              <User className="h-5 w-5 text-primary" />
              Informações do Cliente
            </h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <p className="text-muted-foreground">Nome</p>
                <p className="font-medium">{process.client_name}</p>
              </div>
              {process.client_email && (
                <div>
                  <p className="text-muted-foreground">Email</p>
                  <p className="font-medium flex items-center gap-1">
                    <Mail className="h-3 w-3" />
                    {process.client_email}
                  </p>
                </div>
              )}
              {process.client_phone && (
                <div>
                  <p className="text-muted-foreground">Telefone</p>
                  <p className="font-medium flex items-center gap-1">
                    <Phone className="h-3 w-3" />
                    {process.client_phone}
                  </p>
                </div>
              )}
              {process.client_nif && (
                <div>
                  <p className="text-muted-foreground">NIF</p>
                  <p className="font-medium">{process.client_nif}</p>
                </div>
              )}
            </div>
          </div>

          {/* Imóvel Info */}
          <div className="space-y-3">
            <h3 className="font-semibold text-lg flex items-center gap-2">
              <Home className="h-5 w-5 text-primary" />
              Informações do Imóvel
            </h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {process.property_type && (
                <div>
                  <p className="text-muted-foreground">Tipo</p>
                  <p className="font-medium capitalize">{process.property_type}</p>
                </div>
              )}
              {process.property_location && (
                <div>
                  <p className="text-muted-foreground">Localização</p>
                  <p className="font-medium flex items-center gap-1">
                    <MapPin className="h-3 w-3" />
                    {process.property_location}
                  </p>
                </div>
              )}
              {process.property_value && (
                <div>
                  <p className="text-muted-foreground">Valor do Imóvel</p>
                  <p className="font-medium text-emerald-600 flex items-center gap-1">
                    <Euro className="h-3 w-3" />
                    {process.property_value.toLocaleString('pt-PT')}€
                  </p>
                </div>
              )}
              {process.loan_amount && (
                <div>
                  <p className="text-muted-foreground">Valor Financiado</p>
                  <p className="font-medium flex items-center gap-1">
                    <Euro className="h-3 w-3" />
                    {process.loan_amount.toLocaleString('pt-PT')}€
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Status e Prioridade */}
          <div className="space-y-3">
            <h3 className="font-semibold text-lg">Estado e Prioridade</h3>
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
              {process.service_type && (
                <Badge variant="outline" className="capitalize">
                  {process.service_type.replace(/_/g, ' ')}
                </Badge>
              )}
            </div>
          </div>

          {/* Atribuições */}
          {(process.assigned_consultor_name || process.assigned_intermediario_name) && (
            <div className="space-y-3">
              <h3 className="font-semibold text-lg flex items-center gap-2">
                <Users className="h-5 w-5 text-primary" />
                Atribuições
              </h3>
              <div className="grid grid-cols-2 gap-3 text-sm">
                {process.assigned_consultor_name && (
                  <div>
                    <p className="text-muted-foreground">Consultor</p>
                    <p className="font-medium">{process.assigned_consultor_name}</p>
                  </div>
                )}
                {process.assigned_intermediario_name && (
                  <div>
                    <p className="text-muted-foreground">Intermediário</p>
                    <p className="font-medium">{process.assigned_intermediario_name}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Notas */}
          {process.notes && (
            <div className="space-y-3">
              <h3 className="font-semibold text-lg">Notas</h3>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{process.notes}</p>
            </div>
          )}

          {/* Datas */}
          <div className="space-y-3">
            <h3 className="font-semibold text-lg flex items-center gap-2">
              <Calendar className="h-5 w-5 text-primary" />
              Datas
            </h3>
            <div className="grid grid-cols-2 gap-3 text-sm">
              {process.created_at && (
                <div>
                  <p className="text-muted-foreground">Criado em</p>
                  <p className="font-medium">{new Date(process.created_at).toLocaleDateString('pt-PT')}</p>
                </div>
              )}
              {process.updated_at && (
                <div>
                  <p className="text-muted-foreground">Última atualização</p>
                  <p className="font-medium">{new Date(process.updated_at).toLocaleDateString('pt-PT')}</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
});

ProcessDetailsModal.displayName = 'ProcessDetailsModal';

export default ProcessDetailsModal;
