/**
 * ClientSearchTab - Componente de Pesquisa de Clientes para Admin Dashboard
 * 
 * FIX: Anteriormente fazia pesquisa client-side apenas nos processos já carregados.
 * Agora utiliza a API de pesquisa global do backend (/api/search/global) que faz
 * pesquisa accent-insensitive em processos E clientes registados.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Badge } from "../ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Search, Eye, Loader2 } from "lucide-react";
import { safeLabel } from "../dashboard/DashboardShared";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

/** Normaliza acentos para comparação local (fallback) */
function normalizeAccents(str) {
  return str
    ?.normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase() || "";
}

const ClientSearchTab = ({ workflowStatuses }) => {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState("");
  const [results, setResults] = useState({ processes: [], clients: [] });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);

  const fetchResults = useCallback(async (term) => {
    if (term.length < 2) {
      setResults({ processes: [], clients: [] });
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem("token");
      const response = await fetch(
        `${API_URL}/api/search/global?q=${encodeURIComponent(term)}&limit=20`,
        { headers: { Authorization: `Bearer ${token}` } }
      );

      if (response.ok) {
        const data = await response.json();
        setResults({
          processes: data.processes || [],
          clients: data.clients || [],
        });
      } else {
        setError("Erro ao pesquisar clientes");
      }
    } catch (err) {
      console.error("Erro na pesquisa:", err);
      setError("Erro de ligação ao servidor");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      fetchResults(searchTerm);
    }, 300);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchTerm, fetchResults]);

  const totalResults = results.processes.length + results.clients.length;

  return (
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg">Pesquisar Cliente</CardTitle>
        <CardDescription>
          Encontre e visualize informações de clientes (pesquisa global em processos e registos)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          <div className="relative">
            {loading ? (
              <Loader2 className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground animate-spin" />
            ) : (
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            )}
            <Input
              placeholder="Pesquisar por nome, NIF, email ou telefone..."
              className="pl-10"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>

          {error ? (
            <div className="text-center py-8 text-destructive text-sm">{error}</div>
          ) : searchTerm.length >= 2 ? (
            <div className="space-y-4">
              {/* Resultados de Processos */}
              {results.processes.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">
                    Processos ({results.processes.length})
                  </h4>
                  <div className="rounded-md border overflow-x-auto max-h-96 overflow-y-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Nome</TableHead>
                          <TableHead>Tipo</TableHead>
                          <TableHead>Fase</TableHead>
                          <TableHead>NIF</TableHead>
                          <TableHead className="text-right">Ações</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {results.processes.map((process) => {
                          const status = workflowStatuses?.find(s => s.name === process.status);
                          return (
                            <TableRow
                              key={process.id}
                              className="cursor-pointer hover:bg-muted/50"
                              onClick={() => navigate(`/processo/${process.id}`)}
                            >
                              <TableCell className="font-medium">{process.client_name}</TableCell>
                              <TableCell>
                                <Badge variant="outline" className="text-xs">
                                  {process.process_type || "—"}
                                </Badge>
                              </TableCell>
                              <TableCell>
                                <Badge className={`bg-${status?.color || 'gray'}-100 text-${status?.color || 'gray'}-800 border`}>
                                  {safeLabel(status?.label) || process.status}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-xs font-mono">
                                {process.personal_data?.nif || "—"}
                              </TableCell>
                              <TableCell className="text-right">
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={(e) => { e.stopPropagation(); navigate(`/processo/${process.id}`); }}
                                >
                                  <Eye className="h-4 w-4" />
                                </Button>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              )}

              {/* Resultados de Clientes Registados */}
              {results.clients.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">
                    Clientes Registados ({results.clients.length})
                  </h4>
                  <div className="rounded-md border overflow-x-auto max-h-96 overflow-y-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Nome</TableHead>
                          <TableHead>Email</TableHead>
                          <TableHead>Telefone</TableHead>
                          <TableHead>NIF</TableHead>
                          <TableHead className="text-right">Ações</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {results.clients.map((client) => {
                          const firstProcessId = client.process_ids?.[0];
                          return (
                            <TableRow
                              key={client.id}
                              className="cursor-pointer hover:bg-muted/50"
                              onClick={() => firstProcessId && navigate(`/processo/${firstProcessId}`)}
                            >
                              <TableCell className="font-medium">{client.nome}</TableCell>
                              <TableCell>{client.contacto?.email || "—"}</TableCell>
                              <TableCell>{client.contacto?.telefone || "—"}</TableCell>
                              <TableCell className="text-xs font-mono">
                                {client.dados_pessoais?.nif || "—"}
                              </TableCell>
                              <TableCell className="text-right">
                                <Button
                                  variant="ghost"
                                  size="icon"
                                  onClick={(e) => { e.stopPropagation(); firstProcessId && navigate(`/processo/${firstProcessId}`); }}
                                  disabled={!firstProcessId}
                                >
                                  <Eye className="h-4 w-4" />
                                </Button>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              )}

              {/* Sem resultados */}
              {!loading && totalResults === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  <Search className="h-8 w-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">
                    Nenhum cliente encontrado com &ldquo;{searchTerm}&rdquo;
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Tente pesquisar por nome, email, NIF ou telefone
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="text-sm">Digite pelo menos 2 caracteres para pesquisar</p>
              <p className="text-xs mt-1">Pesquisa global em processos e clientes registados</p>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

export default ClientSearchTab;
