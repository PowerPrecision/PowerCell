/**
 * GlobalSearchModal - Modal de pesquisa global (Ctrl+K)
 * Pesquisa em processos, clientes e tarefas.
 * Resultados são separados em duas secções: "Resultados Ativos" e "Arquivo / Inativos".
 */
import { useState, useEffect, useCallback, useMemo } from "react";
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
  Building2, Loader2, ArrowRight, Users, FolderOpen,
  Archive, AlertCircle
} from "lucide-react";
import api from "../services/api";

// Status values that represent inactive/archived records
const INACTIVE_STATUS_RE = /concluido|concluidos|desistencia|desistencias|eliminado|eliminados|cancelado|arquivo|perdido|inativo/i;

const isItemInactive = (item) => {
  const status = item.status || "";
  return INACTIVE_STATUS_RE.test(status);
};

const GlobalSearchModal = ({ open, onOpenChange }) => {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState({ processes: [], clients: [], tasks: [] });
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Build flat result items with type information
  const flatResults = useMemo(() => [
    ...results.processes.map(p => ({ type: "process", data: p })),
    ...results.clients.map(c => ({ type: "client", data: c })),
    ...results.tasks.map(t => ({ type: "task", data: t })),
  ], [results]);

  // Split into active and inactive
  const { activeItems, inactiveItems } = useMemo(() => {
    const active = [];
    const inactive = [];
    flatResults.forEach((item, idx) => {
      if (isItemInactive(item.data)) {
        inactive.push({ ...item, _flatIdx: idx });
      } else {
        active.push({ ...item, _flatIdx: idx });
      }
    });
    return { activeItems: active, inactiveItems: inactive };
  }, [flatResults]);

  // For keyboard navigation, active items come first, then inactive
  const orderedForNav = useMemo(() => [...activeItems, ...inactiveItems], [activeItems, inactiveItems]);

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

  // Keyboard navigation
  const handleKeyDown = useCallback((e) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, orderedForNav.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, 0));
    } else if (e.key === "Enter" && orderedForNav[selectedIndex]) {
      e.preventDefault();
      handleSelect(orderedForNav[selectedIndex]);
    }
  }, [orderedForNav, selectedIndex]);

  const handleSelect = (item) => {
    onOpenChange(false);
    setQuery("");
    
    switch (item.type) {
      case "process":
        navigate(`/processo/${item.data.id}`);
        break;
      case "client":
        if (item.data.first_process_id) {
          navigate(`/processo/${item.data.first_process_id}`);
        } else if (item.data.has_process && item.data.id) {
          navigate(`/clientes?cliente=${item.data.id}`);
        } else {
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

  // Render a single result row
  const ResultRow = ({ item, navIdx }) => {
    const { type, data } = item;
    const inactive = isItemInactive(data);
    const isSelected = selectedIndex === navIdx;

    return (
      <div
        className={`flex items-center gap-3 px-3 py-2 rounded-md cursor-pointer transition-colors ${
          isSelected ? "bg-accent" : "hover:bg-accent/50"
        } ${inactive ? "opacity-70" : ""}`}
        onClick={() => handleSelect(item)}
      >
        {type === "process" && <FileText className={`h-4 w-4 shrink-0 ${inactive ? "text-muted-foreground/60" : "text-muted-foreground"}`} />}
        {type === "client" && <User className={`h-4 w-4 shrink-0 ${inactive ? "text-muted-foreground/60" : "text-muted-foreground"}`} />}
        {type === "task" && <CheckSquare className={`h-4 w-4 shrink-0 ${inactive ? "text-muted-foreground/60" : "text-muted-foreground"}`} />}
        <div className="flex-1 min-w-0">
          {type === "process" && (
            <>
              <p className="font-medium truncate">{data.client_name}</p>
              <p className="text-xs text-muted-foreground truncate">
                {typeof data.process_type === 'string' ? data.process_type.replace(/_/g, ' ') : String(data.process_type || '')} • {typeof data.status === 'string' ? data.status.replace(/_/g, ' ') : String(data.status || '')}
              </p>
            </>
          )}
          {type === "client" && (
            <>
              <div className="flex items-center gap-2">
                <p className="font-medium truncate">{data.client_name}</p>
                {data.has_process && (
                  <Badge variant="outline" className="text-[10px] h-4 px-1 shrink-0">
                    <FolderOpen className="h-2.5 w-2.5 mr-0.5" />
                    {data.process_count} processo{data.process_count !== 1 ? 's' : ''}
                  </Badge>
                )}
                {inactive && (
                  <Badge variant="secondary" className="text-[10px] h-4 px-1 shrink-0 text-muted-foreground">
                    Inativo
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground truncate">
                {data.personal_data?.nif || data.contacto?.email || "Sem dados"}
              </p>
            </>
          )}
          {type === "task" && (
            <>
              <p className="font-medium truncate">{data.title}</p>
              <p className="text-xs text-muted-foreground truncate">
                {typeof data.status === 'string' ? data.status.replace(/_/g, ' ') : String(data.status || '')}
              </p>
            </>
          )}
        </div>
        <ArrowRight className={`h-4 w-4 shrink-0 ${inactive ? "text-muted-foreground/40" : "text-muted-foreground"}`} />
      </div>
    );
  };

  // Build nav index mapping: active items get sequential indices starting from 0,
  // inactive items continue after
  const getNavIdx = (section, localIdx) => {
    if (section === "active") return localIdx;
    return activeItems.length + localIdx;
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
          <div className="border-t max-h-[350px] overflow-y-auto">
            {/* Section 1: Active Results */}
            {activeItems.length > 0 && (
              <div className="p-2">
                <p className="text-xs font-semibold text-foreground/70 px-2 py-1 flex items-center gap-1.5 uppercase tracking-wide">
                  <Search className="h-3 w-3" />
                  Resultados Ativos
                </p>
                {activeItems.map((item, idx) => (
                  <ResultRow key={`active-${item.type}-${item.data.id}`} item={item} navIdx={getNavIdx("active", idx)} />
                ))}
              </div>
            )}

            {/* Section 2: Inactive / Archived Results */}
            {inactiveItems.length > 0 && (
              <div className={`p-2 ${activeItems.length > 0 ? "border-t" : ""}`}>
                <p className="text-xs font-semibold text-muted-foreground px-2 py-1 flex items-center gap-1.5 uppercase tracking-wide">
                  <Archive className="h-3 w-3" />
                  Arquivo / Inativos
                </p>
                {inactiveItems.map((item, idx) => (
                  <ResultRow key={`inactive-${item.type}-${item.data.id}`} item={item} navIdx={getNavIdx("inactive", idx)} />
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
