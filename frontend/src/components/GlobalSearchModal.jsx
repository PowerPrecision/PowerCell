/**
 * GlobalSearchModal - Modal de pesquisa global (Ctrl+K)
 * Pesquisa em processos, clientes e tarefas
 */
import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { 
  Search, FileText, User, CheckSquare, 
  Building2, Loader2, ArrowRight, Users, FolderOpen
} from "lucide-react";
import api from "../services/api";

const GlobalSearchModal = ({ open, onOpenChange }) => {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState({ processes: [], clients: [], tasks: [] });
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Debounced search
  useEffect(() => {
    if (!query.trim()) {
      setResults({ processes: [], clients: [], tasks: [] });
      return;
    }

    const timer = setTimeout(async () => {
      try {
        setLoading(true);
        const response = await api.get(`/search/global?q=${encodeURIComponent(query)}&limit=5`);
        setResults(response.data);
        setSelectedIndex(0);
      } catch (error) {
        console.error("Erro na pesquisa:", error);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [query]);

  // Flatten results for keyboard navigation
  const flatResults = [
    ...results.processes.map(p => ({ type: "process", data: p })),
    ...results.clients.map(c => ({ type: "client", data: c })),
    ...results.tasks.map(t => ({ type: "task", data: t })),
  ];

  // Keyboard navigation
  const handleKeyDown = useCallback((e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, flatResults.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && flatResults[selectedIndex]) {
      e.preventDefault();
      handleSelect(flatResults[selectedIndex]);
    }
  }, [flatResults, selectedIndex]);

  const handleSelect = (item) => {
    onOpenChange(false);
    setQuery("");
    
    switch (item.type) {
      case "process":
        navigate(`/processo/${item.data.id}`);
        break;
      case "client":
        // Se o cliente tem processo, navega para o primeiro processo
        if (item.data.first_process_id) {
          navigate(`/processo/${item.data.first_process_id}`);
        } else if (item.data.has_process && item.data.id) {
          // Fallback: navega para clientes com filtro
          navigate(`/clientes?cliente=${item.data.id}`);
        } else {
          // Cliente sem processo: navega para página de clientes
          navigate(`/clientes?cliente=${item.data.id}`);
        }
        break;
      case "task":
        navigate(`/pendentes`);
        break;
      default:
        break;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] p-0 gap-0">
        <DialogHeader className="px-4 pt-4 pb-2">
          <DialogTitle className="text-lg flex items-center gap-2">
            <Search className="h-5 w-5" />
            Pesquisa Rápida
          </DialogTitle>
          <DialogDescription className="sr-only">
            Pesquise por processos, clientes ou tarefas.
          </DialogDescription>
        </DialogHeader>
        
        <div className="px-4 pb-2">
          <div className="relative">
            <Input
              placeholder="Pesquisar processos, clientes, tarefas..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              className="pl-10"
              autoFocus
            />
            {loading ? (
              <Loader2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
            ) : (
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            )}
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            Use ↑↓ para navegar, Enter para seleccionar
          </p>
        </div>

        {flatResults.length > 0 && (
          <div className="border-t max-h-[300px] overflow-y-auto">
            {results.processes.length > 0 && (
              <div className="p-2">
                <p className="text-xs font-medium text-muted-foreground px-2 py-1 flex items-center gap-1">
                  <FileText className="h-3 w-3" />
                  Processos
                </p>
                {results.processes.map((process, idx) => (
                  <div
                    key={process.id}
                    className={`flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer ${
                      selectedIndex === idx ? "bg-accent" : "hover:bg-accent/50"
                    }`}
                    onClick={() => handleSelect({ type: "process", data: process })}
                  >
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{process.client_name}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {typeof process.process_type === 'string' ? process.process_type.replace(/_/g, ' ') : String(process.process_type || '')} • {typeof process.status === 'string' ? process.status.replace(/_/g, ' ') : String(process.status || '')}
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                ))}
              </div>
            )}

            {results.clients.length > 0 && (
              <div className="p-2 border-t">
                <p className="text-xs font-medium text-muted-foreground px-2 py-1 flex items-center gap-1">
                  <Users className="h-3 w-3" />
                  Clientes
                </p>
                {results.clients.map((client, idx) => (
                  <div
                    key={client.id}
                    className={`flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer ${
                      selectedIndex === results.processes.length + idx ? "bg-accent" : "hover:bg-accent/50"
                    }`}
                    onClick={() => handleSelect({ type: "client", data: client })}
                  >
                    <User className="h-4 w-4 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-medium truncate">{client.client_name}</p>
                        {client.has_process && (
                          <Badge variant="outline" className="text-[10px] h-4 px-1">
                            <FolderOpen className="h-2.5 w-2.5 mr-0.5" />
                            {client.process_count} processo{client.process_count !== 1 ? 's' : ''}
                          </Badge>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground truncate">
                        {client.personal_data?.nif || client.contacto?.email || "Sem dados"}
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                ))}
              </div>
            )}

            {results.tasks.length > 0 && (
              <div className="p-2 border-t">
                <p className="text-xs font-medium text-muted-foreground px-2 py-1 flex items-center gap-1">
                  <CheckSquare className="h-3 w-3" />
                  Tarefas
                </p>
                {results.tasks.map((task, idx) => (
                  <div
                    key={task.id}
                    className={`flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer ${
                      selectedIndex === results.processes.length + results.clients.length + idx ? "bg-accent" : "hover:bg-accent/50"
                    }`}
                    onClick={() => handleSelect({ type: "task", data: task })}
                  >
                    <CheckSquare className="h-4 w-4 text-muted-foreground" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">{task.title}</p>
                      <p className="text-xs text-muted-foreground truncate">
                        {typeof task.status === 'string' ? task.status.replace(/_/g, ' ') : String(task.status || '')}
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {query && !loading && flatResults.length === 0 && (
          <div className="border-t p-8 text-center text-muted-foreground">
            <Search className="h-8 w-8 mx-auto mb-2 opacity-20" />
            <p>Nenhum resultado para "{query}"</p>
          </div>
        )}

        <div className="border-t px-4 py-2 text-xs text-muted-foreground flex items-center justify-between">
          <span>
            <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px]">ESC</kbd> para fechar
          </span>
          <span>
            <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px]">Ctrl</kbd> + 
            <kbd className="px-1.5 py-0.5 bg-muted rounded text-[10px]">K</kbd> para abrir
          </span>
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default GlobalSearchModal;
