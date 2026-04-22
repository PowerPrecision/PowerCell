/**
 * CreateProcessModal — Modal de criação de processo associado a um cliente.
 *
 * REGRAS DE NEGÓCIO:
 * - É PROIBIDO criar um processo sem associar a um cliente existente.
 * - O campo "Selecionar Cliente" é obrigatório e o botão de submeter
 *   permanece desativado até que um cliente seja selecionado.
 * - Quando chamado com `preSelectedClient`, o campo fica pré-preenchido
 *   e bloqueado (usado no atalho "Adicionar Processo" da ficha do cliente).
 *
 * @props {boolean} open          — Controla visibilidade do modal
 * @props {Function} onOpenChange — Callback ao fechar o modal
 * @props {Function} onSuccess    — Callback após criação bem-sucedida (recebe o processo criado)
 * @props {Object}  [preSelectedClient] — Cliente pré-preenchido { id, name, nif, email, phone }
 */
import React, { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Loader2, Search, FileText, X, UserPlus, CheckCircle } from "lucide-react";
import { createClientProcess, searchClients } from "../services/api";
import { toast } from "sonner";
import { PROCESS_TYPE_LABELS } from "../components/SmartClientSearch";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const CreateProcessModal = ({ open, onOpenChange, onSuccess, preSelectedClient }) => {
  const navigate = useNavigate();

  const [selectedClient, setSelectedClient] = useState(preSelectedClient || null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [processType, setProcessType] = useState("credito_habitacao");
  const [submitting, setSubmitting] = useState(false);

  const isClientLocked = !!preSelectedClient?.id;
  const canSubmit = selectedClient?.id && !submitting;

  // Reset state when modal opens/closes
  React.useEffect(() => {
    if (open) {
      setSelectedClient(preSelectedClient || null);
      setProcessType("credito_habitacao");
      setSearchQuery("");
      setSearchResults([]);
      setShowDropdown(false);
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
  };

  const handleClearClient = () => {
    setSelectedClient(null);
  };

  // ── Submit ─────────────────────────────────────────────────────────
  const handleSubmit = async () => {
    if (!selectedClient?.id || !processType) return;
    setSubmitting(true);
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(
        `${API_URL}/api/clients/${selectedClient.id}/create-process?process_type=${processType}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      if (res.ok) {
        const data = await res.json();
        toast.success(`Processo #${data.process_number} criado com sucesso`);
        onOpenChange(false);
        if (onSuccess) onSuccess(data);
        // Navegar para o novo processo
        if (data.process_id) {
          navigate(`/process/${data.process_id}`);
        }
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || "Erro ao criar processo");
      }
    } catch (err) {
      toast.error("Erro de ligação ao servidor");
    } finally {
      setSubmitting(false);
    }
  };

  // ── Dropdown click-outside ────────────────────────────────────────
  React.useEffect(() => {
    if (!showDropdown) return;
    const handler = (e) => {
      const container = document.getElementById("client-search-container");
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
            Crie um novo processo associado a um cliente existente.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* ── Client Selection (Obrigatório) ──────────────────── */}
          <div className="space-y-2" id="client-search-container" className="relative">
            <Label>
              Selecionar Cliente <span className="text-red-500 font-bold">*</span>
            </Label>

            {selectedClient ? (
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
                {!isClientLocked && (
                  <button
                    type="button"
                    onClick={handleClearClient}
                    className="p-1 hover:bg-muted rounded-md transition-colors"
                    title="Remover cliente"
                  >
                    <X className="h-4 w-4 text-muted-foreground" />
                  </button>
                )}
                {isClientLocked && (
                  <Badge variant="secondary" className="text-[10px] shrink-0">Bloqueado</Badge>
                )}
              </div>
            ) : (
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Pesquisar por nome, email ou NIF (mín. 2 chars)..."
                  value={searchQuery}
                  onChange={handleSearchChange}
                  onFocus={() => searchQuery.length >= 2 && setShowDropdown(true)}
                  className="pl-10 pr-10"
                  autoComplete="off"
                />
                {searchLoading && (
                  <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
                )}
              </div>
            )}

            {/* Search Dropdown */}
            {showDropdown && !selectedClient && (
              <div className="absolute z-50 w-full mt-1 bg-popover border rounded-lg shadow-lg max-h-56 overflow-y-auto">
                {searchResults.length > 0 ? (
                  searchResults.map((client) => (
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
                  ))
                ) : !searchLoading && searchQuery.length >= 2 ? (
                  <div className="px-3 py-4 text-center">
                    <p className="text-sm text-muted-foreground">
                      Nenhum cliente encontrado para "{searchQuery}"
                    </p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Crie o cliente primeiro na página de Clientes.
                    </p>
                  </div>
                ) : null}
              </div>
            )}
          </div>

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

          {/* ── Info ────────────────────────────────────────────── */}
          {!selectedClient?.id && (
            <div className="flex items-start gap-3 p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-lg">
              <UserPlus className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
              <div className="text-xs text-amber-700 dark:text-amber-300">
                <p className="font-medium">Regra de negócio</p>
                <p className="mt-0.5">
                  É obrigatório associar um cliente existente para criar um processo.
                  Se o cliente não existe, crie-o primeiro na secção "Clientes".
                </p>
              </div>
            </div>
          )}
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
