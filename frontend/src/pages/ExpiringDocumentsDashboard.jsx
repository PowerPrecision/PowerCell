import React, { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  AlertCircle,
  FileText,
  Search,
  Calendar,
  User,
  ExternalLink,
  RefreshCw,
  AlertTriangle,
  Clock,
  Filter,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const ExpiringDocumentsDashboard = () => {
  const { user, token } = useAuth();
  const navigate = useNavigate();
  
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  
  // Filtros
  const [searchTerm, setSearchTerm] = useState("");
  const [urgencyFilter, setUrgencyFilter] = useState("all");
  const [consultorFilter, setConsultorFilter] = useState("all");
  const [daysAhead, setDaysAhead] = useState(60);

  const fetchData = useCallback(async (showRefreshing = false) => {
    if (showRefreshing) setRefreshing(true);
    else setLoading(true);
    
    try {
      const params = new URLSearchParams();
      params.append("days_ahead", daysAhead);
      if (urgencyFilter !== "all") params.append("urgency", urgencyFilter);
      if (consultorFilter !== "all") params.append("consultor_id", consultorFilter);
      if (searchTerm.trim()) params.append("search", searchTerm.trim());
      
      const response = await fetch(
        `${API_URL}/api/documents/expiring-dashboard?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );
      
      if (!response.ok) throw new Error("Erro ao carregar dados");
      
      const result = await response.json();
      setData(result);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token, daysAhead, urgencyFilter, consultorFilter, searchTerm]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchData();
  };

  const getUrgencyBadge = (urgency, daysUntil) => {
    const config = {
      critical: { 
        class: "bg-red-500 text-white border-red-500", 
        icon: AlertCircle,
        label: daysUntil === 0 ? "Expira Hoje" : daysUntil === 1 ? "1 dia" : `${daysUntil} dias`
      },
      high: { 
        class: "bg-orange-500 text-white border-orange-500", 
        icon: AlertTriangle,
        label: `${daysUntil} dias`
      },
      medium: { 
        class: "bg-yellow-500 text-white border-yellow-500", 
        icon: Clock,
        label: `${daysUntil} dias`
      },
    };
    
    const { class: badgeClass, icon: Icon, label } = config[urgency] || config.medium;
    
    return (
      <Badge variant="outline" className={`text-xs ${badgeClass}`}>
        <Icon className="h-3 w-3 mr-1" />
        {label}
      </Badge>
    );
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "N/D";
    try {
      return new Date(dateStr).toLocaleDateString("pt-PT");
    } catch {
      return dateStr;
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <RefreshCw className="h-8 w-8 animate-spin text-primary" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="expiring-docs-dashboard">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Dashboard de Validades</h1>
            <p className="text-muted-foreground">
              Documentos a expirar nos próximos {daysAhead} dias
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => fetchData(true)}
            disabled={refreshing}
            data-testid="refresh-btn"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
            Actualizar
          </Button>
        </div>

        {/* Estatísticas */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card className="border-l-4 border-l-gray-500">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground">
                Total a Expirar
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold">{data?.stats?.total || 0}</div>
            </CardContent>
          </Card>
          
          <Card className="border-l-4 border-l-red-500">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-red-500" />
                Crítico (&lt;7 dias)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-red-600">{data?.stats?.critical || 0}</div>
            </CardContent>
          </Card>
          
          <Card className="border-l-4 border-l-orange-500">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-orange-500" />
                Alto (7-29 dias)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-orange-600">{data?.stats?.high || 0}</div>
            </CardContent>
          </Card>
          
          <Card className="border-l-4 border-l-yellow-500">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                <Clock className="h-4 w-4 text-yellow-500" />
                Médio (30-60 dias)
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-yellow-600">{data?.stats?.medium || 0}</div>
            </CardContent>
          </Card>
        </div>

        {/* Filtros */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Filter className="h-4 w-4" />
              Filtros
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSearch} className="flex flex-wrap gap-4">
              <div className="flex-1 min-w-[200px]">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Pesquisar por cliente..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="pl-10"
                    data-testid="search-input"
                  />
                </div>
              </div>
              
              <Select value={urgencyFilter} onValueChange={setUrgencyFilter}>
                <SelectTrigger className="w-[180px]" data-testid="urgency-filter">
                  <SelectValue placeholder="Urgência" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todas Urgências</SelectItem>
                  <SelectItem value="critical">Crítico (&lt;7 dias)</SelectItem>
                  <SelectItem value="high">Alto (7-29 dias)</SelectItem>
                  <SelectItem value="medium">Médio (30-60 dias)</SelectItem>
                </SelectContent>
              </Select>
              
              {data?.is_management && data?.consultors_filter?.length > 0 && (
                <Select value={consultorFilter} onValueChange={setConsultorFilter}>
                  <SelectTrigger className="w-[200px]" data-testid="consultor-filter">
                    <SelectValue placeholder="Consultor" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos Consultores</SelectItem>
                    {data.consultors_filter.map((c) => (
                      <SelectItem key={c.id} value={c.id}>
                        {c.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              
              <Select value={String(daysAhead)} onValueChange={(v) => setDaysAhead(Number(v))}>
                <SelectTrigger className="w-[150px]" data-testid="days-filter">
                  <SelectValue placeholder="Período" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="7">7 dias</SelectItem>
                  <SelectItem value="30">30 dias</SelectItem>
                  <SelectItem value="60">60 dias</SelectItem>
                  <SelectItem value="90">90 dias</SelectItem>
                </SelectContent>
              </Select>
              
              <Button type="submit" data-testid="apply-filters-btn">
                Aplicar
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Lista de Clientes */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Clientes com Documentos a Expirar</span>
              <Badge variant="secondary">{data?.total_clients || 0} clientes</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {error ? (
              <div className="text-center py-8 text-red-500">
                <AlertCircle className="h-8 w-8 mx-auto mb-2" />
                <p>{error}</p>
              </div>
            ) : data?.clients?.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>Nenhum documento a expirar encontrado</p>
                <p className="text-sm">Todos os documentos estão em dia!</p>
              </div>
            ) : (
              <ScrollArea className="h-[500px]">
                <div className="space-y-4">
                  {data?.clients?.map((client) => (
                    <div
                      key={client.process_id}
                      className={`p-4 rounded-lg border transition-colors ${
                        client.critical_count > 0
                          ? "border-red-300 bg-red-50/50 dark:bg-red-900/10"
                          : client.high_count > 0
                          ? "border-orange-300 bg-orange-50/50 dark:bg-orange-900/10"
                          : "border-yellow-300 bg-yellow-50/50 dark:bg-yellow-900/10"
                      }`}
                      data-testid={`client-card-${client.process_id}`}
                    >
                      {/* Header do Cliente */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div>
                            <h3 className="font-semibold text-lg">{client.client_name}</h3>
                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                              <User className="h-3 w-3" />
                              <span>{client.consultor_name}</span>
                            </div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          {client.critical_count > 0 && (
                            <Badge variant="destructive" className="bg-red-500">
                              {client.critical_count} crítico{client.critical_count > 1 ? "s" : ""}
                            </Badge>
                          )}
                          {client.high_count > 0 && (
                            <Badge className="bg-orange-500 text-white">
                              {client.high_count} alto{client.high_count > 1 ? "s" : ""}
                            </Badge>
                          )}
                          {client.medium_count > 0 && (
                            <Badge className="bg-yellow-500 text-white">
                              {client.medium_count} médio{client.medium_count > 1 ? "s" : ""}
                            </Badge>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => navigate(`/process/${client.process_id}`)}
                            data-testid={`view-client-${client.process_id}`}
                          >
                            <ExternalLink className="h-4 w-4 mr-1" />
                            Ver Ficha
                          </Button>
                        </div>
                      </div>

                      {/* Lista de Documentos */}
                      <div className="space-y-2">
                        {client.documents.map((doc, idx) => (
                          <div
                            key={doc.id || idx}
                            className="flex items-center justify-between p-2 bg-white/60 dark:bg-gray-800/60 rounded border"
                          >
                            <div className="flex items-center gap-3">
                              <FileText className="h-4 w-4 text-red-500" />
                              <div>
                                <span className="font-medium text-sm">
                                  {doc.subcategory || doc.category || doc.filename}
                                </span>
                                <div className="text-xs text-muted-foreground">
                                  {doc.filename}
                                </div>
                              </div>
                            </div>
                            <div className="flex items-center gap-3">
                              <div className="text-right text-sm">
                                <div className="flex items-center gap-1 text-muted-foreground">
                                  <Calendar className="h-3 w-3" />
                                  {formatDate(doc.expiry_date)}
                                </div>
                              </div>
                              {getUrgencyBadge(doc.urgency, doc.days_until)}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default ExpiringDocumentsDashboard;
