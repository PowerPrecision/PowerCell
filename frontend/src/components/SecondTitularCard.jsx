/**
 * SecondTitularCard — Pesquisa e ficha do 2º Titular ligado ao Processo
 *
 * Funcionalidades:
 * - Se não houver 2º titular: mostra botão "Adicionar / Ligar 2º Titular"
 *   com dropdown de pesquisa por Nome, Email ou NIF
 * - Se houver 2º titular ligado: mostra cartão com dados resumidos +
 *   link rápido para a ficha do cliente + botão para desligar
 * - Ao selecionar um cliente, guarda o ID dele no second_client_id do processo
 */
import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { searchClients, updateProcess } from "../services/api";
import { queryKeys } from "../lib/queryClient";
import { Card, CardContent } from "./ui/card";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import {
  Users, Search, UserPlus, X, ExternalLink, Loader2,
  Mail, Phone, CreditCard, MapPin, Briefcase, Unlink
} from "lucide-react";
import { toast } from "sonner";

const SecondTitularCard = ({ process: processData, onUpdate }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isSearching, setIsSearching] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [linking, setLinking] = useState(false);
  const containerRef = useRef(null);
  const debounceRef = useRef(null);

  const secondClientData = processData?.second_client_data;
  const secondClientId = processData?.second_client_id;
  const hasSecondTitular = !!(secondClientData && secondClientId);

  // Fechar dropdown ao clicar fora
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsSearching(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Pesquisa de clientes
  const search = useCallback(async (searchQuery) => {
    if (searchQuery.length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const response = await searchClients(searchQuery, 10);
      const items = response.data?.results || response.data || [];
      // Filtrar: não mostrar o titular principal
      const filtered = items.filter(
        (c) => c.id !== processData?.client_id
      );
      setResults(filtered);
    } catch (err) {
      console.error("Detalhe do Erro API [searchSecondClient]:", err);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, [processData?.client_id]);

  const handleInputChange = (e) => {
    const value = e.target.value;
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => search(value), 300);
  };

  // Ligar cliente como 2º titular
  const handleLinkClient = async (client) => {
    setLinking(true);
    try {
      await updateProcess(processData.id, {
        second_client_id: client.id,
      });
      toast.success(`${client.nome} ligado(a) como 2º Titular`);
      setIsSearching(false);
      setQuery("");
      setResults([]);
      // Invalidar cache React Query para forçar re-fetch dos dados do processo
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.detail(processData.id) });
      // Chamar callback do componente pai (fetchData) para atualizar o estado local
      if (onUpdate) onUpdate();
    } catch (err) {
      console.error("Detalhe do Erro API [linkSecondClient]:", err);
      toast.error(err.response?.data?.detail || "Erro ao ligar 2º titular");
    } finally {
      setLinking(false);
    }
  };

  // Desligar 2º titular
  const handleUnlinkClient = async () => {
    setLinking(true);
    try {
      await updateProcess(processData.id, {
        second_client_id: "",  // String vazia = remover
      });
      toast.success("2º Titular desligado do processo");
      // Invalidar cache React Query para forçar re-fetch dos dados do processo
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.detail(processData.id) });
      // Chamar callback do componente pai (fetchData) para atualizar o estado local
      if (onUpdate) onUpdate();
    } catch (err) {
      console.error("Detalhe do Erro API [unlinkSecondClient]:", err);
      toast.error("Erro ao desligar 2º titular");
    } finally {
      setLinking(false);
    }
  };

  // Navegar para ficha do cliente
  const goToClientPage = (clientId) => {
    navigate(`/cliente/${clientId}`);
  };

  // ── RENDER: Cartão com dados do 2º titular já ligado ──
  if (hasSecondTitular) {
    return (
      <Card className="border-l-4 border-l-cyan-500">
        <CardContent className="pt-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-semibold text-sm flex items-center gap-2">
              <Users className="h-4 w-4 text-cyan-500" />
              2º Titular
              <Badge variant="secondary" className="ml-1">
                Cliente Ligado
              </Badge>
            </h4>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={() => goToClientPage(secondClientId)}
                title="Abrir ficha do cliente"
              >
                <ExternalLink className="h-3.5 w-3.5 mr-1" />
                Ficha
              </Button>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs text-red-600 hover:text-red-700 hover:bg-red-50"
                onClick={handleUnlinkClient}
                disabled={linking}
                title="Desligar 2º titular deste processo"
              >
                <Unlink className="h-3.5 w-3.5 mr-1" />
                Desligar
              </Button>
            </div>
          </div>

          {/* Dados resumidos do 2º titular */}
          <div
            className="p-3 bg-muted/30 rounded-lg cursor-pointer hover:bg-muted/50 transition-colors"
            onClick={() => goToClientPage(secondClientId)}
          >
            <div className="flex items-center gap-3 mb-2">
              <div className="h-10 w-10 rounded-full bg-cyan-100 flex items-center justify-center shrink-0">
                <span className="text-sm font-semibold text-cyan-700">
                  {(secondClientData.nome || "?").charAt(0).toUpperCase()}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm truncate">{secondClientData.nome}</p>
                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground mt-0.5">
                  {secondClientData.nif && (
                    <span className="flex items-center gap-1">
                      <CreditCard className="h-3 w-3" />
                      NIF: {secondClientData.nif}
                    </span>
                  )}
                  {secondClientData.email && (
                    <span className="flex items-center gap-1">
                      <Mail className="h-3 w-3" />
                      {secondClientData.email}
                    </span>
                  )}
                  {secondClientData.telefone && (
                    <span className="flex items-center gap-1">
                      <Phone className="h-3 w-3" />
                      {secondClientData.telefone}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Linha extra com detalhes */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1 text-xs text-muted-foreground mt-2 pt-2 border-t">
              {secondClientData.profissao && (
                <span className="flex items-center gap-1">
                  <Briefcase className="h-3 w-3" />
                  {secondClientData.profissao}
                </span>
              )}
              {secondClientData.estado_civil && (
                <span className="capitalize">
                  {secondClientData.estado_civil.replace(/_/g, " ")}
                </span>
              )}
              {secondClientData.morada_fiscal && (
                <span className="flex items-center gap-1 truncate">
                  <MapPin className="h-3 w-3 shrink-0" />
                  {secondClientData.morada_fiscal}
                </span>
              )}
              {secondClientData.birth_date && (
                <span>
                  {new Date(secondClientData.birth_date).toLocaleDateString("pt-PT")}
                </span>
              )}
              {secondClientData.nacionalidade && (
                <span>{secondClientData.nacionalidade}</span>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  // ── RENDER: Botão de adicionar / Pesquisa ──
  return (
    <Card className="border-l-4 border-l-cyan-500/40 border-dashed">
      <CardContent className="pt-4">
        <h4 className="font-semibold text-sm flex items-center gap-2 mb-3">
          <Users className="h-4 w-4 text-cyan-500" />
          2º Titular
          <Badge variant="outline" className="ml-1 text-muted-foreground">
            Não definido
          </Badge>
        </h4>

        {!isSearching ? (
          <Button
            variant="outline"
            className="w-full border-dashed hover:border-cyan-500 hover:bg-cyan-50 dark:hover:bg-cyan-950/20"
            onClick={() => setIsSearching(true)}
          >
            <UserPlus className="h-4 w-4 mr-2 text-cyan-500" />
            Adicionar / Ligar 2º Titular
          </Button>
        ) : (
          <div className="space-y-2" ref={containerRef}>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Pesquisar por nome, email ou NIF..."
                value={query}
                onChange={handleInputChange}
                className="pl-10 pr-10"
                autoFocus
                autoComplete="off"
              />
              {loading && (
                <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 animate-spin text-muted-foreground" />
              )}
              <button
                type="button"
                onClick={() => {
                  setIsSearching(false);
                  setQuery("");
                  setResults([]);
                }}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {!loading && <X className="h-4 w-4" />}
              </button>
            </div>

            {/* Dropdown de resultados */}
            {results.length > 0 && (
              <div className="border rounded-lg shadow-lg max-h-64 overflow-y-auto bg-popover">
                {results.map((client) => (
                  <button
                    key={client.id}
                    type="button"
                    className="w-full text-left px-3 py-2.5 flex items-center gap-3 hover:bg-muted/50 transition-colors"
                    onClick={() => handleLinkClient(client)}
                    disabled={linking}
                  >
                    <div className="h-8 w-8 rounded-full bg-cyan-100 flex items-center justify-center shrink-0">
                      <span className="text-xs font-medium text-cyan-700">
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
                    <Badge variant="outline" className="text-xs shrink-0">
                      Ligar
                    </Badge>
                  </button>
                ))}
              </div>
            )}

            {/* Sem resultados */}
            {query.length >= 2 && !loading && results.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-2">
                Nenhum cliente encontrado. Crie o cliente primeiro na página de Clientes.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
};

export default SecondTitularCard;
