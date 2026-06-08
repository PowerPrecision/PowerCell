/**
 * CreateClientModal Component
 * 
 * Modal para criação de novo processo com pesquisa inteligente de clientes.
 * 
 * FASE 3 — Paradigma Relacional (Cliente ↔ Processo):
 * - Um processo NUNCA existe sem um cliente associado (client_id obrigatório).
 * - Se o cliente já existe: selecionar via autocomplete → criar processo com client_id.
 * - Se é um cliente novo: recolher dados básicos → POST /clients → obter client_id → POST /processes/create-client.
 * - Dados pessoais (Nome, Email, Telefone, NIF) pertencem ao Cliente, NÃO ao Processo.
 * - Quando um cliente existente é selecionado, os campos pessoais ficam ocultos/bloqueados.
 * 
 * FLUXO SEQUENCIAL:
 * 1. Utilizador escolhe: "Cliente Existente" ou "Novo Cliente"
 * 2. Se existente → autocomplete → seleciona → client_id obtido
 * 3. Se novo → preenche Nome/Email/Telefone/NIF → cria cliente → obtém client_id
 * 4. Com client_id em mãos → cria processo passando apenas { client_id, process_type }
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
import { Input } from '../ui/input';
import { 
  Select, 
  SelectContent, 
  SelectItem, 
  SelectTrigger, 
  SelectValue 
} from '../ui/select';
import { Loader2, Plus, UserPlus, Users, CheckCircle } from 'lucide-react';
import { toast } from 'sonner';
import { createClientProcess, createClient, searchClients } from '../../services/api';
import { PROCESS_TYPE_LABELS } from '../SmartClientSearch';

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

  // ── Novo Cliente ──────────────────────────────────────────────────
  const [clientMode, setClientMode] = useState(null); // 'existing' | 'new' | null
  const [newClientData, setNewClientData] = useState({
    nome: '',
    email: '',
    telefone: '',
    nif: '',
  });

  // ── Pesquisa de Clientes Existente ────────────────────────────────
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);

  const handleClose = useCallback(() => {
    onOpenChange?.(false);
    setFormData(INITIAL_FORM_STATE);
    setSelectedClient(null);
    setClientMode(null);
    setNewClientData({ nome: '', email: '', telefone: '', nif: '' });
    setSearchQuery('');
    setSearchResults([]);
    setShowDropdown(false);
  }, [onOpenChange]);

  // ── Pesquisa de Clientes ──────────────────────────────────────────
  const searchForClients = useCallback(async (query) => {
    if (query.length < 2) {
      setSearchResults([]);
      setShowDropdown(false);
      return;
    }
    setSearchLoading(true);
    try {
      const res = await searchClients(query, 10);
      const items = res.data?.results || res.data || [];
      setSearchResults(items);
      setShowDropdown(true);
    } catch {
      setSearchResults([]);
    } finally {
      setSearchLoading(false);
    }
  }, []);

  const handleSearchChange = (e) => {
    const val = e.target.value;
    setSearchQuery(val);
    if (val.length >= 2) {
      const timer = setTimeout(() => searchForClients(val), 300);
      return () => clearTimeout(timer);
    } else {
      setSearchResults([]);
      setShowDropdown(false);
    }
  };

  const handleSelectExistingClient = (client) => {
    setSelectedClient({
      id: client.id,
      name: client.nome,
      nif: client.nif || client.dados_pessoais?.nif || '',
      email: client.email || client.contacto?.email || '',
      phone: client.telefone || client.contacto?.telefone || '',
    });
    setSearchQuery('');
    setSearchResults([]);
    setShowDropdown(false);
  };

  const handleClearClient = () => {
    setSelectedClient(null);
    setClientMode(null);
  };

  // ── Click-outside dropdown ────────────────────────────────────────
  React.useEffect(() => {
    if (!showDropdown) return;
    const handler = (e) => {
      const container = document.getElementById('client-search-dropdown');
      if (container && !container.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [showDropdown]);

  // ── Reset ao abrir/fechar ─────────────────────────────────────────
  React.useEffect(() => {
    if (!open) {
      setFormData(INITIAL_FORM_STATE);
      setSelectedClient(null);
      setClientMode(null);
      setNewClientData({ nome: '', email: '', telefone: '', nif: '' });
      setSearchQuery('');
      setSearchResults([]);
      setShowDropdown(false);
    }
  }, [open]);

  // ── Validação do formulário ───────────────────────────────────────
  const isExistingClientReady = clientMode === 'existing' && selectedClient?.id;
  const isNewClientReady = clientMode === 'new' && newClientData.nome.trim().length >= 2 && newClientData.email.trim().length >= 3;
  const canSubmit = (isExistingClientReady || isNewClientReady) && formData.process_type && !isCreating;

  // ── Submissão ─────────────────────────────────────────────────────
  const handleCreate = useCallback(async () => {
    if (!canSubmit) return;

    setIsCreating(true);
    try {
      let clientId = selectedClient?.id;

      // ── PASSO 1: Se é novo cliente, criar primeiro na BD ──────────
      if (clientMode === 'new' && !clientId) {
        try {
          const newClientRes = await createClient({
            nome: newClientData.nome.trim(),
            email: newClientData.email.trim() || undefined,
            telefone: newClientData.telefone.trim() || undefined,
            nif: newClientData.nif.trim() || undefined,
            fonte: 'staff_created',
          });
          // Extrair client_id da resposta do backend
          clientId = newClientRes.data?.id || newClientRes.data?.client?.id;
          if (!clientId) {
            toast.error('Erro ao criar cliente: resposta sem ID');
            return;
          }
          toast.success(`Cliente "${newClientData.nome}" criado com sucesso!`);
        } catch (createErr) {
          console.error('Erro ao criar cliente:', createErr);
          const errMsg = createErr.response?.data?.detail || createErr.message || 'Erro ao criar cliente na base de dados';
          toast.error(errMsg);
          return;
        }
      }

      // ── PASSO 2: Criar o processo com o client_id obrigatório ─────
      // NOTA: NÃO enviamos personal_data — os dados pessoais pertencem ao Cliente.
      // O backend obtém os dados do cliente via client_id.
      const payload = {
        client_id: clientId,
        process_type: formData.process_type,
      };

      const processRes = await createClientProcess(payload);
      const processNumber = processRes.data?.process_number;
      const displayName = selectedClient?.name || newClientData.nome;

      toast.success(`Processo${processNumber ? ` #${processNumber}` : ''} criado para "${displayName}"!`);
      handleClose();
      onSuccess?.(processRes.data);
    } catch (error) {
      console.error('Erro ao criar processo:', error);
      toast.error(error.response?.data?.detail || 'Erro ao criar processo');
    } finally {
      setIsCreating(false);
    }
  }, [canSubmit, clientMode, selectedClient, newClientData, formData, handleClose, onSuccess]);

  // ── Render ────────────────────────────────────────────────────────
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]" aria-describedby="create-client-description">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Plus className="h-5 w-5" />
            Novo Processo
          </DialogTitle>
          <DialogDescription id="create-client-description">
            Associe um cliente existente ou crie um novo. O processo será vinculado ao cliente selecionado.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4 py-4">
          {/* ── Seleção de Modo: Cliente Existente vs Novo ──────────── */}
          {!selectedClient && clientMode === null && (
            <div className="space-y-2">
              <Label className="text-sm font-medium">Associar a:</Label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setClientMode('existing')}
                  className="flex flex-col items-center gap-2 p-4 rounded-lg border-2 border-muted hover:border-teal-500/50 hover:bg-teal-50 dark:hover:bg-teal-950/20 transition-all"
                >
                  <Users className="h-6 w-6 text-teal-600" />
                  <span className="text-sm font-medium">Cliente Existente</span>
                  <span className="text-xs text-muted-foreground">Pesquisar e selecionar</span>
                </button>
                <button
                  type="button"
                  onClick={() => setClientMode('new')}
                  className="flex flex-col items-center gap-2 p-4 rounded-lg border-2 border-muted hover:border-teal-500/50 hover:bg-teal-50 dark:hover:bg-teal-950/20 transition-all"
                >
                  <UserPlus className="h-6 w-6 text-teal-600" />
                  <span className="text-sm font-medium">Novo Cliente</span>
                  <span className="text-xs text-muted-foreground">Criar e associar</span>
                </button>
              </div>
            </div>
          )}

          {/* ── Modo: Cliente Existente (Autocomplete) ──────────────── */}
          {clientMode === 'existing' && !selectedClient && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium">Pesquisar Cliente Existente</Label>
                <button
                  type="button"
                  onClick={() => { setClientMode(null); setSearchQuery(''); setSearchResults([]); }}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  ← Voltar
                </button>
              </div>
              <div className="relative" id="client-search-dropdown">
                <Input
                  placeholder="Pesquisar por nome, email ou NIF (mín. 2 chars)..."
                  value={searchQuery}
                  onChange={handleSearchChange}
                  onFocus={() => searchQuery.length >= 2 && setShowDropdown(true)}
                  className="pr-10"
                  autoComplete="off"
                  autoFocus
                />
                {searchLoading && (
                  <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
                )}

                {/* Dropdown de resultados */}
                {showDropdown && (
                  <div className="absolute z-50 w-full mt-1 bg-popover border rounded-lg shadow-lg max-h-56 overflow-y-auto">
                    {searchResults.length > 0 ? (
                      searchResults.map((client) => (
                        <button
                          key={client.id}
                          type="button"
                          className="w-full text-left px-3 py-2.5 flex items-center gap-3 hover:bg-muted/50 transition-colors"
                          onClick={() => handleSelectExistingClient(client)}
                        >
                          <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                            <span className="text-xs font-medium text-primary">
                              {(client.nome || '?').charAt(0).toUpperCase()}
                            </span>
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-sm truncate">{client.nome}</p>
                            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                              {client.nif && <span>NIF: {client.nif}</span>}
                              {client.email && <span>· {client.email}</span>}
                            </div>
                          </div>
                        </button>
                      ))
                    ) : !searchLoading && searchQuery.length >= 2 ? (
                      <div className="px-3 py-4 text-center">
                        <p className="text-sm text-muted-foreground">
                          Nenhum cliente encontrado para &quot;{searchQuery}&quot;
                        </p>
                        <button
                          type="button"
                          className="mt-2 text-sm text-primary hover:underline flex items-center gap-1 mx-auto"
                          onClick={() => {
                            setClientMode('new');
                            setNewClientData(prev => ({ ...prev, nome: searchQuery }));
                            setSearchQuery('');
                            setSearchResults([]);
                            setShowDropdown(false);
                          }}
                        >
                          <UserPlus className="h-3.5 w-3.5" />
                          Criar novo cliente &quot;{searchQuery}&quot;
                        </button>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── Modo: Novo Cliente (Formulário) ─────────────────────── */}
          {clientMode === 'new' && !selectedClient && (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-sm font-medium flex items-center gap-2">
                  <UserPlus className="h-4 w-4 text-teal-600" />
                  Dados do Novo Cliente
                </Label>
                <button
                  type="button"
                  onClick={() => { setClientMode(null); setNewClientData({ nome: '', email: '', telefone: '', nif: '' }); }}
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                >
                  ← Voltar
                </button>
              </div>
              <div className="border rounded-lg p-3 bg-muted/20 space-y-3">
                <p className="text-xs text-muted-foreground">
                  Estes dados serão guardados na ficha do Cliente. O processo será criado automaticamente após guardar o cliente.
                </p>
                <Input
                  placeholder="Nome completo *"
                  value={newClientData.nome}
                  onChange={(e) => setNewClientData(prev => ({ ...prev, nome: e.target.value }))}
                  autoFocus
                />
                <Input
                  placeholder="Email * (obrigatório para o Portal do Cliente)"
                  type="email"
                  value={newClientData.email}
                  onChange={(e) => setNewClientData(prev => ({ ...prev, email: e.target.value }))}
                  required
                />
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="NIF"
                    value={newClientData.nif}
                    onChange={(e) => {
                      const v = e.target.value.replace(/[^\d]/g, '').slice(0, 9);
                      setNewClientData(prev => ({ ...prev, nif: v }));
                    }}
                  />
                  <Input
                    placeholder="Telefone"
                    value={newClientData.telefone}
                    onChange={(e) => setNewClientData(prev => ({ ...prev, telefone: e.target.value }))}
                  />
                </div>
              </div>
            </div>
          )}

          {/* ── Cliente Selecionado (Existente ou Novo preenchido) ─── */}
          {selectedClient && (
            <div className="space-y-2">
              <Label className="text-sm font-medium">Cliente Associado</Label>
              <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg border">
                <div className="h-9 w-9 rounded-full bg-teal-100 dark:bg-teal-900/30 flex items-center justify-center shrink-0">
                  <span className="text-sm font-medium text-teal-700 dark:text-teal-300">
                    {selectedClient.name?.charAt(0)?.toUpperCase() || '?'}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-sm truncate">{selectedClient.name}</p>
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    {selectedClient.nif && <span>NIF: {selectedClient.nif}</span>}
                    {selectedClient.email && <span>· {selectedClient.email}</span>}
                    {selectedClient.phone && <span>· {selectedClient.phone}</span>}
                  </div>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <span className="inline-flex items-center gap-1 text-xs bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300 px-2 py-0.5 rounded-full">
                    <CheckCircle className="h-3 w-3" />
                    Associado
                  </span>
                  <button
                    type="button"
                    onClick={handleClearClient}
                    className="p-1 hover:bg-muted rounded-md transition-colors"
                    title="Remover cliente"
                  >
                    ✕
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* ── Info: Dados pessoais pertencem ao cliente ──────────── */}
          {clientMode === 'new' && !selectedClient && (
            <div className="flex items-start gap-2 p-2.5 bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-800 rounded-lg">
              <Users className="h-4 w-4 text-blue-600 mt-0.5 shrink-0" />
              <p className="text-xs text-blue-700 dark:text-blue-300">
                Os dados pessoais são guardados na ficha do Cliente. O Processo fica automaticamente associado via <code className="font-mono text-[10px] bg-blue-100 dark:bg-blue-900/40 px-1 rounded">client_id</code>.
              </p>
            </div>
          )}

          {/* ── Tipo de Processo ────────────────────────────────────── */}
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
                {Object.entries(PROCESS_TYPE_LABELS).map(([key, label]) => (
                  <SelectItem key={key} value={key}>
                    {label}
                  </SelectItem>
                ))}
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
            disabled={!canSubmit}
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
