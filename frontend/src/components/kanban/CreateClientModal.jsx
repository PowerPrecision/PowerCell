/**
 * CreateClientModal Component
 * 
 * Modal para criação de novo cliente/processo.
 * 
 * RESPONSABILIDADE ÚNICA:
 * - Gerir o estado do formulário de criação
 * - Validar campos obrigatórios
 * - Submeter criação de cliente
 * 
 * PERFORMANCE:
 * - Estado do formulário ISOLADO dentro deste componente
 * - Não causa re-renders no KanbanBoard quando o utilizador digita
 */
import React, { memo, useState, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '../ui/select';
import { Loader2, Plus } from 'lucide-react';
import { toast } from 'sonner';
import { createClientProcess } from '../../services/api';

const INITIAL_FORM_STATE = {
  client_name: '',
  client_email: '',
  client_phone: '',
  process_type: 'credito_habitacao',
};

const CreateClientModal = memo(({
  open,
  onOpenChange,
  onSuccess,
}) => {
  // Estado LOCAL do formulário - isolado do componente pai
  const [formData, setFormData] = useState(INITIAL_FORM_STATE);
  const [isCreating, setIsCreating] = useState(false);

  // Handlers memoizados
  const handleFieldChange = useCallback((field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  }, []);

  const handleClose = useCallback(() => {
    onOpenChange?.(false);
    // Reset form on close
    setFormData(INITIAL_FORM_STATE);
  }, [onOpenChange]);

  const handleCreate = useCallback(async () => {
    if (!formData.client_name.trim()) {
      toast.error('Por favor, introduza o nome do cliente');
      return;
    }

    setIsCreating(true);
    try {
      await createClientProcess({
        client_name: formData.client_name,
        client_email: formData.client_email,
        process_type: formData.process_type,
        personal_data: {
          nome_completo: formData.client_name,
          email: formData.client_email,
          telefone: formData.client_phone,
        },
      });

      toast.success(`Cliente "${formData.client_name}" criado com sucesso!`);
      handleClose();
      onSuccess?.();
    } catch (error) {
      console.error('Erro ao criar cliente:', error);
      toast.error(error.response?.data?.detail || 'Erro ao criar cliente');
    } finally {
      setIsCreating(false);
    }
  }, [formData, handleClose, onSuccess]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]" aria-describedby="create-client-description">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Criar Novo Cliente
          </DialogTitle>
          <DialogDescription id="create-client-description">
            Preencha os dados para criar um novo cliente no sistema.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4 py-4">
          <div className="space-y-2">
            <Label htmlFor="client_name">Nome do Cliente *</Label>
            <Input
              id="client_name"
              placeholder="Nome completo do cliente"
              value={formData.client_name}
              onChange={(e) => handleFieldChange('client_name', e.target.value)}
            />
          </div>
          
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="client_email">Email</Label>
              <Input
                id="client_email"
                type="email"
                placeholder="email@exemplo.com"
                value={formData.client_email}
                onChange={(e) => handleFieldChange('client_email', e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="client_phone">Telefone</Label>
              <Input
                id="client_phone"
                placeholder="+351 000 000 000"
                value={formData.client_phone}
                onChange={(e) => handleFieldChange('client_phone', e.target.value)}
              />
            </div>
          </div>
          
          <div className="space-y-2">
            <Label htmlFor="process_type">Tipo de Processo</Label>
            <Select 
              value={formData.process_type} 
              onValueChange={(v) => handleFieldChange('process_type', v)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="credito_habitacao">Crédito Habitação</SelectItem>
                <SelectItem value="credito_pessoal">Crédito Pessoal</SelectItem>
                <SelectItem value="credito_consolidado">Crédito Consolidado</SelectItem>
                <SelectItem value="credito_automovel">Crédito Automóvel</SelectItem>
                <SelectItem value="transferencia_credito">Transferência de Crédito</SelectItem>
                <SelectItem value="imobiliario">Imobiliário</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        
        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            Cancelar
          </Button>
          <Button 
            onClick={handleCreate} 
            disabled={isCreating || !formData.client_name.trim()}
            className="bg-teal-600 hover:bg-teal-700"
          >
            {isCreating ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                A criar...
              </>
            ) : (
              <>
                <Plus className="h-4 w-4 mr-2" />
                Criar Cliente
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});

CreateClientModal.displayName = 'CreateClientModal';

export default CreateClientModal;
