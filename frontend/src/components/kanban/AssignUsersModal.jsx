/**
 * AssignUsersModal Component
 * 
 * Modal para atribuir consultores e mediadores a um processo.
 * 
 * RESPONSABILIDADE ÚNICA:
 * - Gerir estado de seleção de utilizadores
 * - Carregar lista de utilizadores
 * - Submeter atribuições
 * 
 * PERFORMANCE:
 * - Estado local isolado
 * - Não causa re-renders no KanbanBoard
 */
import { memo, useState, useCallback, useEffect } from 'react';
import { extractErrorMessage } from '../../utils/extractErrorMessage';
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
import { Loader2, Users } from 'lucide-react';
import { toast } from 'sonner';
import { filterByAnyRole, CONSULTOR_ASSIGNMENT_ROLES, INTERMEDIARIO_ASSIGNMENT_ROLES } from '../../utils/roleUtils';
import { safeString } from '../../utils/safeString';

const API_URL = process.env.REACT_APP_BACKEND_URL;

const AssignUsersModal = memo(({
  open,
  onOpenChange,
  process,
  token,
  onSuccess,
}) => {
  // Estado LOCAL - isolado do componente pai
  const [selectedConsultor, setSelectedConsultor] = useState('');
  const [selectedMediador, setSelectedMediador] = useState('');
  const [appUsers, setAppUsers] = useState([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Carregar utilizadores quando o modal abre
  useEffect(() => {
    if (open && process) {
      setSelectedConsultor(process.assigned_consultor_id || '');
      setSelectedMediador(process.assigned_mediador_id || '');
      
      if (appUsers.length === 0) {
        fetchUsers();
      }
    }
  }, [open, process]);

  const fetchUsers = useCallback(async () => {
    setIsLoadingUsers(true);
    try {
      const response = await fetch(`${API_URL}/api/users/staff`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const users = await response.json();
        setAppUsers((Array.isArray(users) ? users : []).filter(u => u.is_active !== false));
      }
    } catch (error) {
      console.error('Erro ao buscar utilizadores:', error);
    } finally {
      setIsLoadingUsers(false);
    }
  }, [token]);

  const handleSave = useCallback(async () => {
    if (!process) return;

    setIsSaving(true);
    try {
      const params = new URLSearchParams();
      params.append('consultor_id', selectedConsultor || '');
      params.append('mediador_id', selectedMediador || '');

      const response = await fetch(`${API_URL}/api/processes/${process.id}/assign?${params.toString()}`, {
        method: 'POST',
        headers: { 
          Authorization: `Bearer ${token}`
        }
      });

      if (response.ok) {
        toast.success('Atribuições actualizadas com sucesso');
        onOpenChange?.(false);
        onSuccess?.();
      } else {
        const data = await response.json();
        toast.error(extractErrorMessage(data.detail, 'Erro ao actualizar atribuições'));
      }
    } catch (error) {
      console.error('Erro ao guardar atribuições:', error);
      toast.error('Erro ao guardar atribuições');
    } finally {
      setIsSaving(false);
    }
  }, [process, selectedConsultor, selectedMediador, token, onOpenChange, onSuccess]);

  const handleClose = useCallback(() => {
    onOpenChange?.(false);
  }, [onOpenChange]);

  if (!process) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]" aria-describedby="assign-users-description">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-purple-600" />
            Gerir Atribuições
          </DialogTitle>
          <DialogDescription id="assign-users-description">
            Atribua consultores e mediadores a este processo.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4">
          <div className="p-3 bg-gray-50 rounded-lg">
            <p className="font-medium">{safeString(process.client_name)}</p>
            <p className="text-sm text-muted-foreground">
              #{process.process_number || '—'}
            </p>
          </div>
          
          {isLoadingUsers ? (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <Label className="text-sm font-medium">Consultor</Label>
                <Select 
                  value={selectedConsultor || 'none'} 
                  onValueChange={(v) => setSelectedConsultor(v === 'none' ? '' : v)}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Seleccionar consultor..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Nenhum</SelectItem>
                    {appUsers
                      .filter(u => filterByAnyRole(u, CONSULTOR_ASSIGNMENT_ROLES))
                      .map(u => (
                        <SelectItem key={u.id} value={u.id}>
                          {u.name} ({u.role})
                        </SelectItem>
                      ))
                    }
                  </SelectContent>
                </Select>
              </div>
              
              <div>
                <Label className="text-sm font-medium">Intermediário</Label>
                <Select 
                  value={selectedMediador || 'none'} 
                  onValueChange={(v) => setSelectedMediador(v === 'none' ? '' : v)}
                >
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Seleccionar intermediário..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Nenhum</SelectItem>
                    {appUsers
                      .filter(u => filterByAnyRole(u, INTERMEDIARIO_ASSIGNMENT_ROLES))
                      .map(u => (
                        <SelectItem key={u.id} value={u.id}>
                          {u.name} ({u.role})
                        </SelectItem>
                      ))
                    }
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}
        </div>
        
        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={handleClose}>
            Cancelar
          </Button>
          <Button 
            onClick={handleSave}
            disabled={isSaving || isLoadingUsers}
            className="bg-purple-600 hover:bg-purple-700"
          >
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                A guardar...
              </>
            ) : (
              'Guardar'
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
});

AssignUsersModal.displayName = 'AssignUsersModal';

export default AssignUsersModal;
