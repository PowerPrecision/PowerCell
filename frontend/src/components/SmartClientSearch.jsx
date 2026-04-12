/**
 * SmartClientSearch - Pesquisa inteligente de clientes com autocomplete
 * 
 * Pesquisa assíncrona por nome, email ou NIF.
 * Ao selecionar um cliente, lança onClientSelect com os dados do cliente.
 * Se não encontrar, permite criar um novo cliente no local.
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { searchClients } from "../services/api";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { Loader2, Search, UserPlus, X } from "lucide-react";

const PROCESS_TYPE_LABELS = {
  credito_habitacao: "Crédito Habitação",
  credito_pessoal: "Crédito Pessoal",
  credito_consolidado: "Crédito Consolidado",
  credito_automovel: "Crédito Automóvel",
  transferencia_credito: "Transferência de Crédito",
  imobiliario: "Imobiliário",
  compra_direta: "Compra Direta",
  arrendamento: "Arrendamento",
  consultoria: "Consultoria",
};

const SmartClientSearch = ({ onClientSelect, selectedClient, onClearClient }) => {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [showNewClientForm, setShowNewClientForm] = useState(false);
  const [newClient, setNewClient] = useState({ name: "", email: "", phone: "", nif: "" });
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const containerRef = useRef(null);
  const debounceRef = useRef(null);

  // Fechar dropdown ao clicar fora
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Se tem cliente selecionado, não mostrar pesquisa
  if (selectedClient) {
    return (
      <div className="space-y-2">
        <label className="text-sm font-medium">Cliente</label>
        <div className="flex items-center gap-2 p-3 bg-muted/50 rounded-lg border">
          <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
            <span className="text-xs font-medium text-primary">
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
          <Badge variant="outline" className="text-xs shrink-0">
            Associado
          </Badge>
          <button
            type="button"
            onClick={onClearClient}
            className="p-1 hover:bg-muted rounded-md transition-colors"
            title="Remover cliente"
          >
            <X className="h-4 w-4 text-muted-foreground" />
          </button>
        </div>
      </div>
    );
  }

  const search = useCallback(async (searchQuery) => {
    if (searchQuery.length < 2) {
      setResults([]);
      setShowDropdown(false);
      return;
    }
    setLoading(true);
    try {
      const response = await searchClients(searchQuery, 10);
      const items = response.data?.results || response.data || [];
      setResults(items);
      setShowDropdown(true);
      setSelectedIndex(-1);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleInputChange = (e) => {
    const value = e.target.value;
    setQuery(value);
    setShowNewClientForm(false);

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(value), 300);
  };

  const handleSelectClient = (client) => {
    onClientSelect({
      id: client.id,
      name: client.nome,
      nif: client.nif || client.dados_pessoais?.nif || "",
      email: client.email || client.contacto?.email || "",
      phone: client.telefone || client.contacto?.telefone || "",
    });
    setQuery("");
    setResults([]);
    setShowDropdown(false);
  };

  const handleKeyDown = (e) => {
    if (!showDropdown || results.length === 0) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, results.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (selectedIndex >= 0 && selectedIndex < results.length) {
        handleSelectClient(results[selectedIndex]);
      } else if (results.length === 0) {
        setShowNewClientForm(true);
      }
    } else if (e.key === "Escape") {
      setShowDropdown(false);
    }
  };

  const handleCreateNewClient = () => {
    if (!newClient.name.trim()) return;
    onClientSelect({
      id: null, // null = novo cliente
      name: newClient.name.trim(),
      nif: newClient.nif.trim(),
      email: newClient.email.trim(),
      phone: newClient.phone.trim(),
    });
    setShowNewClientForm(false);
    setNewClient({ name: "", email: "", phone: "", nif: "" });
    setQuery("");
  };

  return (
    <div className="space-y-2" ref={containerRef}>
      <label className="text-sm font-medium">Pesquisar Cliente</label>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Pesquisar por nome, email ou NIF..."
          value={showNewClientForm ? "" : query}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={() => query.length >= 2 && setShowDropdown(true)}
          className="pl-10 pr-10"
          autoComplete="off"
        />
        {loading && (
          <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
        )}
      </div>

      {/* Dropdown de resultados */}
      {showDropdown && !showNewClientForm && (
        <div className="absolute z-50 w-full mt-1 bg-popover border rounded-lg shadow-lg max-h-64 overflow-y-auto">
          {results.length > 0 ? (
            <>
              {results.map((client, idx) => (
                <button
                  key={client.id}
                  type="button"
                  className={`w-full text-left px-3 py-2.5 flex items-center gap-3 hover:bg-muted/50 transition-colors ${
                    idx === selectedIndex ? "bg-muted/50" : ""
                  }`}
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
                      {client.telefone && <span>· {client.telefone}</span>}
                    </div>
                  </div>
                </button>
              ))}
              <div className="border-t px-3 py-2">
                <button
                  type="button"
                  className="w-full text-left text-sm text-primary hover:underline flex items-center gap-2"
                  onClick={() => setShowNewClientForm(true)}
                >
                  <UserPlus className="h-4 w-4" />
                  Criar novo cliente "{query}"
                </button>
              </div>
            </>
          ) : !loading && query.length >= 2 ? (
            <div className="px-3 py-4 text-center">
              <p className="text-sm text-muted-foreground mb-2">Nenhum cliente encontrado</p>
              <button
                type="button"
                className="text-sm text-primary hover:underline flex items-center gap-2 mx-auto"
                onClick={() => setShowNewClientForm(true)}
              >
                <UserPlus className="h-4 w-4" />
                Criar novo cliente "{query}"
              </button>
            </div>
          ) : null}
        </div>
      )}

      {/* Formulário de novo cliente inline */}
      {showNewClientForm && (
        <div className="border rounded-lg p-3 bg-muted/20 space-y-3">
          <p className="text-sm font-medium flex items-center gap-2">
            <UserPlus className="h-4 w-4 text-primary" />
            Novo Cliente
          </p>
          <Input
            placeholder="Nome completo *"
            value={newClient.name}
            onChange={(e) => setNewClient({ ...newClient, name: e.target.value })}
            autoFocus
          />
          <div className="grid grid-cols-3 gap-2">
            <Input
              placeholder="NIF"
              value={newClient.nif}
              onChange={(e) => {
                const v = e.target.value.replace(/[^\d]/g, "").slice(0, 9);
                setNewClient({ ...newClient, nif: v });
              }}
            />
            <Input
              placeholder="Email"
              type="email"
              value={newClient.email}
              onChange={(e) => setNewClient({ ...newClient, email: e.target.value })}
            />
            <Input
              placeholder="Telefone"
              value={newClient.phone}
              onChange={(e) => setNewClient({ ...newClient, phone: e.target.value })}
            />
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className="flex-1 text-sm bg-primary text-primary-foreground px-3 py-1.5 rounded-md hover:bg-primary/90 transition-colors disabled:opacity-50"
              onClick={handleCreateNewClient}
              disabled={!newClient.name.trim()}
            >
              Selecionar Cliente
            </button>
            <button
              type="button"
              variant="outline"
              className="text-sm px-3 py-1.5 rounded-md border hover:bg-muted transition-colors"
              onClick={() => {
                setShowNewClientForm(false);
                setNewClient({ name: "", email: "", phone: "", nif: "" });
              }}
            >
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default SmartClientSearch;
export { PROCESS_TYPE_LABELS };
