/**
 * CreateProcessModal — Modal de criação de processo associado a um cliente.
 *
 * FASE 3 — Paradigma Relacional:
 * - Um processo NUNCA existe sem um client_id obrigatório.
 * - Se chamado com `preSelectedClient`, o campo fica pré-preenchido e bloqueado
 *   (usado no atalho "Adicionar Processo" da ficha do cliente).
 * - Se sem preSelectedClient, permite pesquisar/criar cliente via SmartClientSearch.
 * - Utiliza POST /processes/create-client com { client_id, process_type }.
 *
 * @props {boolean} open          — Controla visibilidade do modal
 * @props {Function} onOpenChange — Callback ao fechar o modal
 * @props {Function} onSuccess    — Callback após criação bem-sucedida (recebe o processo criado)
 * @props {Object}  [preSelectedClient] — Cliente pré-preenchido { id, name, nif, email, phone }
 */
import React, { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Badge } from "./ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import { Loader2, Search, FileText, X, UserPlus, CheckCircle, Users } from "lucide-react";
import { createClientProcess, createClient, searchClients } from "../services/api";
import { toast } from "sonner";
import { PROCESS_TYPE_LABELS } from "./SmartClientSearch";

const CreateProcessModal = ({ open, onOpenChange, onSuccess, preSelectedClient, isLead = false }) => {
  const navigate = useNavigate();

  const [selectedClient, setSelectedClient] = useState(preSelectedClient || null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [processType, setProcessType] = useState("credito_habitacao");
  const [submitting, setSubmitting] = useState(false);

  // ── Novo Cliente (quando não há preSelectedClient) ───────────────
  const [clientMode, setClientMode] = useState(null); // 'existing' | 'new' | null
  const [newClientData, setNewClientData] = useState({
    nome: '',
    email: '',
    telefone: '',
    nif: '',
  });

  const isClientLocked = !!preSelectedClient?.id;
  const canSubmit = (selectedClient?.id || (clientMode === 'new' && newClientData.nome.trim().length >= 2 && newClientData.email.trim().length >= 3)) && !submitting;

  // Reset state when modal opens/closes
  React.useEffect(() => {
    if (open) {
      setSelectedClient(preSelectedClient || null);
      setProcessType("credito_habitacao");
      setSearchQuery("");
      setSearchResults([]);
      setShowDropdown(false);
      setClientMode(preSelectedClient ? 'existing' : null);
      setNewClientData({ nome: '', email: '', telefone: '', nif: '' });
    }
  }, [open, preSelectedClient]);

  // ── Client Search ──────────────────────────────────────────────────
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

  const handleSelectClient = (client) => {
    setSelectedClient({
      id: client.id,
      name: client.nome,
      nif: client.nif || client.dados_pessoais?.nif || "",
      email: client.email || client.contacto?.email || "",
      phone: client.telefone || client.contacto?.telefone || "",
    });
    setSearchQuery("");
    setSearchResults([]);
    setShowDropdown(false);
    setClientMode('existing');
  };

  const handleClearClient = () => {
    setSelectedClient(null);
    setClientMode(null);
  };

  // ── Submit (Paradigma Relacional) ──────────────────────────────────
  const handleSubmit = async () => {
    if (!processType) return;

    let clientId = selectedClient?.id;

    // Se é novo cliente (sem ID), criar primeiro na BD
    if (clientMode === 'new' && !clientId) {
      setSubmitting(true);
      try {
        const newClientRes = await createClient({
          nome: newClientData.nome.trim(),
          email: newClientData.email.trim() || undefined,
          telefone: newClientData.telefone.trim() || undefined,
          nif: newClientData.nif.trim() || undefined,
          fonte: 'staff_created',
        });
        clientId = newClientRes.data?.id || newClientRes.data?.client?.id;
        if (!clientId) {
          toast.error('Erro ao criar cliente: resposta sem ID');
          setSubmitting(false);
          return;
        }
        toast.success(`Cliente "${newClientData.nome}" criado com sucesso!`);
      } catch (createErr) {
        console.error('Erro ao criar cliente:', createErr);
        toast.error(extractErrorMessage(createErr.response?.data?.detail, 'Erro ao criar cliente na base de dados'));
        setSubmitting(false);
        return;
      }
    }

    // Agora criar o processo com o client_id obrigatório
    if (!clientId) {
      toast.error('Selecione ou crie um cliente antes de criar o processo');
      return;
    }

    setSubmitting(true);
    try {
      // FASE 3: Enviar APENAS { client_id, process_type } — sem personal_data
      // PACOTE CY/DB: isLead=true → processo vai para Registos de Clientes (status vazio/Lead)
      const payload = {
        client_id: clientId,
        process_type: processType,
        ...(isLead ? { is_lead: true } : {}),
      };

      const res = await createClientProcess(payload);
      const data = res.data;
      toast.success(isLead
        ? `Registo #${data.process_number} criado em Registos de Clientes`
        : `Processo #${data.process_number} criado com sucesso`);
      onOpenChange(false);
      if (onSuccess) onSuccess(data);
      // Navegar para o novo processo
      if (data.id) {
        navigate(`/process/${data.id}`);
      }
    } catch (err) {
      const errMsg = extractErrorMessage(err.response?.data?.detail, err.message || 'Erro ao criar processo');
      toast.error(errMsg);
    } finally {
      setSubmitting(false);
    }
  };

  // ── Dropdown click-outside ────────────────────────────────────────
  React.useEffect(() => {
    if (!showDropdown) return;
    const handler = (e) => {
      const container = document.getElementById("cpm-client-search-container");
      if (container && !container.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showDropdown]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Novo Processo
          </DialogTitle>
          <DialogDescription>
            Crie um novo processo associado a um cliente.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* ── Cliente pré-selecionado (bloqueado) ─────────────────── */}
          {isClientLocked && selectedClient ? (
            <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg border">
              <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                <span className="text-sm font-medium text-primary">
                  {selectedClient.name?.charAt(0)?.toUpperCase() || "?"}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm truncate">{selectedClient.name}</p>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  {selectedClient.nif && <span>NIF: {selectedClient.nif}</span>}
                  {selectedClient.email && <span>· {selectedClient.email}</span>}
                </div>
              </div>
              <Badge className="bg-emerald-100 text-emerald-800 text-xs shrink-0">
                <CheckCircle className="h-3 w-3 mr-1" />
                Associado
              </Badge>
              <Badge variant="secondary" className="text-[10px] shrink-0">Bloqueado</Badge>
            </div>
          ) : (
            <>
              {/* ── Seleção de Modo ────────────────────────────────── */}
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

              {/* ── Modo: Cliente Existente (Autocomplete) ──────────── */}
              {clientMode === 'existing' && !selectedClient && (
                <div className="space-y-2" id="cpm-client-search-container">
                  <div className="flex items-center justify-between">
                    <Label>
                      Selecionar Cliente <span className="text-red-500 font-bold">*</span>
                    </Label>
                    <button
                      type="button"
                      onClick={() => { setClientMode(null); setSearchQuery(''); setSearchResults([]); }}
                      className="text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                      ← Voltar
                    </button>
                  </div>
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input
                      placeholder="Pesquisar por nome, email ou NIF (mín. 2 chars)..."
                      value={searchQuery}
                      onChange={handleSearchChange}
                      onFocus={() => searchQuery.length >= 2 && setShowDropdown(true)}
                      className="pl-10 pr-10"
                      autoComplete="off"
                      autoFocus
                    />
                    {searchLoading && (
                      <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
                    )}
                  </div>

                  {/* Search Dropdown */}
                  {showDropdown && (
                    <div className="absolute z-50 w-full mt-1 bg-popover border rounded-lg shadow-lg max-h-56 overflow-y-auto">
                      {searchResults.length > 0 ? (
                        <>
                          {searchResults.map((client) => (
                            <button
                              key={client.id}
                              type="button"
                              className="w-full text-left px-3 py-2.5 flex items-center gap-3 hover:bg-muted/50 transition-colors"
                              onClick={() => handleSelectClient(client)}
                            >
                              <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                                <span className="text-xs font-medium text-primary">
                                  {(client.nome || "?").charAt(0).toUpperCase()}
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
                          ))}
                          <div className="border-t px-3 py-2">
                            <button
                              type="button"
                              className="w-full text-left text-sm text-primary hover:underline flex items-center gap-2"
                              onClick={() => {
                                setClientMode('new');
                                setNewClientData(prev => ({ ...prev, nome: searchQuery }));
                                setSearchQuery('');
                                setSearchResults([]);
                                setShowDropdown(false);
                              }}
                            >
                              <UserPlus className="h-4 w-4" />
                              Criar novo cliente &quot;{searchQuery}&quot;
                            </button>
                          </div>
                        </>
                      ) : !searchLoading && searchQuery.length >= 2 ? (
                        <div className="px-3 py-4 text-center">
                          <p className="text-sm text-muted-foreground mb-2">
                            Nenhum cliente encontrado para &quot;{searchQuery}&quot;
                          </p>
                          <button
                            type="button"
                            className="text-sm text-primary hover:underline flex items-center gap-2 mx-auto"
                            onClick={() => {
                              setClientMode('new');
                              setNewClientData(prev => ({ ...prev, nome: searchQuery }));
                              setSearchQuery('');
                              setSearchResults([]);
                              setShowDropdown(false);
                            }}
                          >
                            <UserPlus className="h-4 w-4" />
                            Criar novo cliente &quot;{searchQuery}&quot;
                          </button>
                        </div>
                      ) : null}
                    </div>
                  )}
                </div>
              )}

              {/* ── Modo: Novo Cliente ──────────────────────────────── */}
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
                      Estes dados serão guardados na ficha do Cliente. O processo será criado automaticamente.
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

              {/* ── Cliente Selecionado (removível) ──────────────────── */}
              {selectedClient && !isClientLocked && (
                <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg border">
                  <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <span className="text-sm font-medium text-primary">
                      {selectedClient.name?.charAt(0)?.toUpperCase() || "?"}
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm truncate">{selectedClient.name}</p>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      {selectedClient.nif && <span>NIF: {selectedClient.nif}</span>}
                      {selectedClient.email && <span>· {selectedClient.email}</span>}
                    </div>
                  </div>
                  <Badge className="bg-emerald-100 text-emerald-800 text-xs shrink-0">
                    <CheckCircle className="h-3 w-3 mr-1" />
                    Associado
                  </Badge>
                  <button
                    type="button"
                    onClick={handleClearClient}
                    className="p-1 hover:bg-muted rounded-md transition-colors"
                    title="Remover cliente"
                  >
                    <X className="h-4 w-4 text-muted-foreground" />
                  </button>
                </div>
              )}

              {/* ── Info ────────────────────────────────────────────── */}
              {!selectedClient?.id && clientMode === null && (
                <div className="flex items-start gap-3 p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                  <UserPlus className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
                  <div className="text-xs text-amber-700 dark:text-amber-300">
                    <p className="font-medium">Regra de negócio</p>
                    <p className="mt-0.5">
                      É obrigatório associar um cliente para criar um processo.
                      Selecione um cliente existente ou crie um novo.
                    </p>
                  </div>
                </div>
              )}
            </>
          )}

          {/* ── Process Type ────────────────────────────────────── */}
          <div className="space-y-2">
            <Label>Tipo de Processo</Label>
            <Select value={processType} onValueChange={setProcessType}>
              <SelectTrigger>
                <SelectValue placeholder="Selecione o tipo de processo" />
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
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={submitting}>
            Cancelar
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 mr-1 animate-spin" />
                A criar...
              </>
            ) : (
              <>
                <FileText className="h-4 w-4 mr-1" />
                Criar Processo
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default CreateProcessModal;
