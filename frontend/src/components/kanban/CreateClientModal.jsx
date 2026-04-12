/**
 * CreateClientModal Component
 * 
 * Modal para criação de novo processo com pesquisa inteligente de clientes.
 * 
 * RESPONSABILIDADE ÚNICA:
 * - Pesquisa de clientes existentes via autocomplete
 * - Criação de novo cliente inline se não encontrado
 * - Submeter criação de processo
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
import SmartClientSearch from '../SmartClientSearch';

const INITIAL_FORM_STATE = {
  process_type: 'credito_habitacao',
};

const CreateClientModal = memo(({
  open,
  onOpenChange,
  onSuccess,
}) => {
  const [formData, setFormData] = useState(INITIAL_FORM_STATE);
  const [isCreating, setIsCreating] = useState(false);
  const [selectedClient, setSelectedClient] = useState(null);

  const handleClose = useCallback(() => {
    onOpenChange?.(false);
    setFormData(INITIAL_FORM_STATE);
    setSelectedClient(null);
  }, [onOpenChange]);

  const handleCreate = useCallback(async () => {
    if (!selectedClient) {
      toast.error('Selecione ou crie um cliente');
      return;
    }

    setIsCreating(true);
    try {
      const payload = {
        process_type: formData.process_type,
        personal_data: {
          nome_completo: selectedClient.name,
          email: selectedClient.email,
          telefone: selectedClient.phone,
          ...(selectedClient.nif ? { nif: selectedClient.nif } : {}),
        },
      };

      // Se cliente existente, passar o ID para o backend
      if (selectedClient.id) {
        payload.client_id = selectedClient.id;
        payload.client_name = selectedClient.name;
        payload.client_email = selectedClient.email;
      }

      await createClientProcess(payload);
      toast.success(`Processo criado para "${selectedClient.name}"!`);
      handleClose();
      onSuccess?.();
    } catch (error) {
      console.error('Erro ao criar processo:', error);
      toast.error(error.response?.data?.detail || 'Erro ao criar processo');
    } finally {
      setIsCreating(false);
    }
  }, [selectedClient, formData, handleClose, onSuccess]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]" aria-describedby="create-client-description">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Novo Processo
          </DialogTitle>
          <DialogDescription id="create-client-description">
            Pesquise um cliente existente ou crie um novo. O processo será associado ao cliente selecionado.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4 py-4">
          <SmartClientSearch
            selectedClient={selectedClient}
            onClientSelect={setSelectedClient}
            onClearClient={() => setSelectedClient(null)}
          />
          
          <div className="space-y-2">
            <Label htmlFor="process_type">Tipo de Processo</Label>
            <Select 
              value={formData.process_type} 
              onValueChange={(v) => setFormData(prev => ({ ...prev, process_type: v }))}
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
            disabled={isCreating || !selectedClient}
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
                Criar Processo
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
