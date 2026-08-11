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
import { searchClients, updateProcess, createClient } from "../services/api";
import { queryKeys } from "../lib/queryClient";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import { useDebounce } from "../hooks/useDebounce";
import { Card, CardContent } from "./ui/card";
import { Input } from "./ui/input";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import {
  Users, Search, UserPlus, X, ExternalLink, Loader2,
  Mail, Phone, CreditCard, MapPin, Briefcase, Unlink
} from "lucide-react";
import { toast } from "sonner";
import { formatDate } from "../lib/utils";
import { safeString } from "../utils/safeString";
import { safeNumber } from "./dashboard/DashboardShared";

// PACOTE DD — Secção consolidada de Co-Buyers / Co-Applicants
// (movida do antigo cartão separado em PersonalInfoTab para dentro do SecondTitularCard).
// Usa apenas tokens semânticos do Shadcn (sem cores cruas).
function CoBuyersSection({ process: processData, financialData }) {
  const hasCoBuyers = Array.isArray(processData?.co_buyers) && processData.co_buyers.length > 0;
  const hasCoApplicants = Array.isArray(processData?.co_applicants) && processData.co_applicants.length > 0;

  if (!hasCoBuyers && !hasCoApplicants) return null;

  const totalPeople =
    (processData?.co_buyers?.length || 0) + (processData?.co_applicants?.length || 0);

  return (
    <div className="mt-4 pt-3 border-t border-border">
      <h5 className="font-semibold text-sm flex items-center gap-2 mb-3">
        <Users className="h-4 w-4 text-primary" />
        2º Titular / Fiador
        <Badge variant="secondary" className="ml-1">
          {totalPeople} pessoa(s)
        </Badge>
      </h5>
      <div className="space-y-3">
        {/* Co-Buyers (do CPCV) */}
        {hasCoBuyers && processData.co_buyers.map((buyer, index) => (
          <div key={`buyer-${index}`} className="p-3 bg-primary/5 rounded-lg border border-border">
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="outline" className="text-xs">
                Comprador {index + 1}
              </Badge>
              {buyer.estado_civil && (
                <Badge variant="secondary" className="text-xs">
                  {safeString(buyer.estado_civil)}
                </Badge>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
              {buyer.nome && (
                <div>
                  <span className="text-muted-foreground text-xs">Nome:</span>
                  <p className="font-medium">{safeString(buyer.nome)}</p>
                </div>
              )}
              {buyer.nif && (
                <div>
                  <span className="text-muted-foreground text-xs">NIF:</span>
                  <p className="font-medium">{safeString(buyer.nif)}</p>
                </div>
              )}
              {buyer.email && (
                <div>
                  <span className="text-muted-foreground text-xs">Email:</span>
                  <p className="font-medium">{safeString(buyer.email)}</p>
                </div>
              )}
              {buyer.telefone && (
                <div>
                  <span className="text-muted-foreground text-xs">Telefone:</span>
                  <p className="font-medium">{safeString(buyer.telefone)}</p>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Co-Applicants (do IRS/Simulação) */}
        {hasCoApplicants && processData.co_applicants.map((applicant, index) => (
          <div key={`applicant-${index}`} className="p-3 bg-muted rounded-lg border border-border">
            <div className="flex items-center gap-2 mb-2">
              <Badge variant="outline" className="text-xs">
                {index === 0 ? "Titular" : "Cônjuge/Proponente " + (index + 1)}
              </Badge>
              {applicant.rendimento_mensal && (
                <Badge variant="secondary" className="text-xs">
                  {safeNumber(applicant.rendimento_mensal).toLocaleString('pt-PT')}€/mês
                </Badge>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
              {applicant.nome && (
                <div>
                  <span className="text-muted-foreground text-xs">Nome:</span>
                  <p className="font-medium">{safeString(applicant.nome)}</p>
                </div>
              )}
              {applicant.nif && (
                <div>
                  <span className="text-muted-foreground text-xs">NIF:</span>
                  <p className="font-medium">{safeString(applicant.nif)}</p>
                </div>
              )}
              {applicant.data_nascimento && (
                <div>
                  <span className="text-muted-foreground text-xs">Data Nascimento:</span>
                  <p className="font-medium">{safeString(applicant.data_nascimento)}</p>
                </div>
              )}
              {applicant.entidade_patronal && (
                <div>
                  <span className="text-muted-foreground text-xs">Empresa:</span>
                  <p className="font-medium">{safeString(applicant.entidade_patronal)}</p>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Rendimento Agregado */}
        {financialData?.rendimento_agregado && (
          <div className="mt-3 p-2 bg-primary/5 rounded border border-border">
            <p className="text-sm font-medium text-foreground">
              Rendimento Agregado: {safeNumber(financialData.rendimento_agregado).toLocaleString('pt-PT')}€/mês
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

const SecondTitularCard = ({ process: processData, onUpdate, financialData }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [isSearching, setIsSearching] = useState(false);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [linking, setLinking] = useState(false);
  const containerRef = useRef(null);
  const debouncedQuery = useDebounce(query, 300);

  // ── Criação inline de novo cliente ──
  const [showNewClientForm, setShowNewClientForm] = useState(false);
  const [newClient, setNewClient] = useState({ nome: "", email: "", telefone: "", nif: "" });
  const [creating, setCreating] = useState(false);

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

  // Disparar pesquisa quando o valor com debounce mudar
  useEffect(() => {
    if (isSearching) search(debouncedQuery);
  }, [debouncedQuery, isSearching, search]);

  const handleInputChange = (e) => {
    setQuery(e.target.value);
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
      toast.error(extractErrorMessage(err.response?.data?.detail, "Erro ao ligar 2º titular"));
    } finally {
      setLinking(false);
    }
  };

  // Criar novo cliente e ligar automaticamente como 2º titular
  const handleCreateAndLink = async () => {
    if (!newClient.nome.trim()) return;
    setCreating(true);
    try {
      // 1. Criar o cliente na BD
      const res = await createClient({
        nome: newClient.nome.trim(),
        email: newClient.email.trim() || undefined,
        telefone: newClient.telefone.trim() || undefined,
        nif: newClient.nif.trim() || undefined,
        fonte: "staff_created",
      });
      const newClientId = res.data?.id || res.data?.client?.id;
      if (!newClientId) {
        toast.error("Erro ao criar cliente: resposta sem ID");
        return;
      }

      // 2. Ligar automaticamente como 2º titular do processo
      await updateProcess(processData.id, {
        second_client_id: newClientId,
      });
      toast.success(`${newClient.nome.trim()} criado(a) e ligado(a) como 2º Titular`);

      // 3. Limpar estado e atualizar
      setShowNewClientForm(false);
      setIsSearching(false);
      setQuery("");
      setResults([]);
      setNewClient({ nome: "", email: "", telefone: "", nif: "" });
      queryClient.invalidateQueries({ queryKey: queryKeys.processes.detail(processData.id) });
      if (onUpdate) onUpdate();
    } catch (err) {
      console.error("Erro ao criar e ligar 2º titular:", err);
      const detail = err.response?.data?.detail;
      toast.error(extractErrorMessage(detail, "Erro ao criar cliente"));
    } finally {
      setCreating(false);
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
                  {formatDate(secondClientData.birth_date)}
                </span>
              )}
              {secondClientData.nacionalidade && (
                <span>{secondClientData.nacionalidade}</span>
              )}
            </div>
          </div>

          {/* PACOTE DD — Secção consolidada de co-buyers / co-applicants */}
          <CoBuyersSection process={processData} financialData={financialData} />
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

            {/* Sem resultados → oferecer criação inline */}
            {query.length >= 2 && !loading && results.length === 0 && !showNewClientForm && (
              <div className="text-center py-2">
                <p className="text-sm text-muted-foreground mb-2">
                  Nenhum cliente encontrado.
                </p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="text-xs"
                  onClick={() => setShowNewClientForm(true)}
                >
                  <UserPlus className="h-3.5 w-3.5 mr-1.5 text-cyan-500" />
                  Criar Novo Cliente
                </Button>
              </div>
            )}

            {/* Formulário inline para criar novo cliente */}
            {showNewClientForm && (
              <div className="border rounded-lg p-3 bg-muted/20 space-y-3">
                <p className="text-sm font-medium flex items-center gap-2">
                  <UserPlus className="h-4 w-4 text-cyan-500" />
                  Criar Novo Cliente
                </p>
                <Input
                  placeholder="Nome completo *"
                  value={newClient.nome}
                  onChange={(e) => setNewClient({ ...newClient, nome: e.target.value })}
                  autoFocus
                  disabled={creating}
                />
                <div className="grid grid-cols-3 gap-2">
                  <Input
                    placeholder="NIF"
                    value={newClient.nif}
                    onChange={(e) => {
                      const v = e.target.value.replace(/[^\d]/g, "").slice(0, 9);
                      setNewClient({ ...newClient, nif: v });
                    }}
                    disabled={creating}
                  />
                  <Input
                    placeholder="Email"
                    type="email"
                    value={newClient.email}
                    onChange={(e) => setNewClient({ ...newClient, email: e.target.value })}
                    disabled={creating}
                  />
                  <Input
                    placeholder="Telefone"
                    value={newClient.telefone}
                    onChange={(e) => setNewClient({ ...newClient, telefone: e.target.value })}
                    disabled={creating}
                  />
                </div>
                <div className="flex gap-2">
                  <Button
                    type="button"
                    size="sm"
                    className="flex-1 text-xs"
                    onClick={handleCreateAndLink}
                    disabled={!newClient.nome.trim() || creating}
                  >
                    {creating ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                        A criar e ligar...
                      </>
                    ) : (
                      <>
                        <UserPlus className="h-3.5 w-3.5 mr-1.5" />
                        Criar e Ligar como 2º Titular
                      </>
                    )}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="text-xs"
                    onClick={() => {
                      setShowNewClientForm(false);
                      setNewClient({ nome: "", email: "", telefone: "", nif: "" });
                    }}
                    disabled={creating}
                  >
                    Cancelar
                  </Button>
                </div>
              </div>
            )}

            {/* Botão criar novo cliente (visível mesmo com resultados) */}
            {results.length > 0 && !showNewClientForm && (
              <div className="border-t pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="w-full text-xs text-primary hover:underline"
                  onClick={() => setShowNewClientForm(true)}
                >
                  <UserPlus className="h-3.5 w-3.5 mr-1.5" />
                  Criar Novo Cliente
                </Button>
              </div>
            )}
          </div>
        )}
        {/* PACOTE DD — Secção consolidada de co-buyers / co-applicants */}
        <CoBuyersSection process={processData} financialData={financialData} />
      </CardContent>
    </Card>
  );
};

export default SecondTitularCard;
