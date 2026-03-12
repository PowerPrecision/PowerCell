/**
 * ImportErrorsPage - Dashboard de Erros de Importação
 * Visualiza erros de upload massivo e permite resolver associações
 */
import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { Label } from "../components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { 
  AlertTriangle, RefreshCw, Search, Download, 
  FolderOpen, FileText, Clock, CheckCircle, XCircle,
  Filter, Link2
} from "lucide-react";
import { toast } from "sonner";
import api from "../services/api";

const ImportErrorsPage = () => {
  const [errors, setErrors] = useState([]);
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [filterType, setFilterType] = useState("all");
  const [stats, setStats] = useState({
    total: 0,
    client_not_found: 0,
    ai_failed: 0,
    invalid_file: 0,
    resolved: 0
  });
  
  // Resolve dialog
  const [isResolveDialogOpen, setIsResolveDialogOpen] = useState(false);
  const [selectedError, setSelectedError] = useState(null);
  const [selectedClientId, setSelectedClientId] = useState("");
  const [resolving, setResolving] = useState(false);

  useEffect(() => {
    fetchErrors();
    fetchClients();
  }, []);

  const fetchErrors = async () => {
    try {
      setLoading(true);
      const response = await api.get("/api/ai/bulk/import-errors");
      const errorList = response.data.errors || [];
      setErrors(errorList);
      
      // Calculate stats
      const newStats = {
        total: errorList.length,
        client_not_found: errorList.filter(e => e.error_type === "client_not_found").length,
        ai_failed: errorList.filter(e => e.error_type === "ai_failed").length,
        invalid_file: errorList.filter(e => e.error_type === "invalid_file").length,
        resolved: errorList.filter(e => e.resolved).length
      };
      setStats(newStats);
    } catch (error) {
      console.error("Erro ao carregar erros:", error);
      toast.error("Erro ao carregar lista de erros");
    } finally {
      setLoading(false);
    }
  };

  const fetchClients = async () => {
    try {
      const response = await api.get("/api/clients?limit=500");
      setClients(response.data.clients || response.data || []);
    } catch (error) {
      console.error("Erro ao carregar clientes:", error);
    }
  };

  const handleResolve = async () => {
    if (!selectedClientId || !selectedError) {
      toast.error("Seleccione um cliente");
      return;
    }

    try {
      setResolving(true);
      
      // Add NIF mapping for this folder -> client
      const client = clients.find(c => c.id === selectedClientId);
      if (client && client.personal_data?.nif) {
        await api.post(
          `/api/ai/bulk/nif-cache/add-mapping?folder_name=${encodeURIComponent(selectedError.folder_name)}&nif=${client.personal_data.nif}`
        );
      }
      
      // Mark error as resolved
      await api.post(`/api/ai/bulk/import-errors/${selectedError.id}/resolve`, {
        resolved_client_id: selectedClientId
      });
      
      toast.success(`Pasta "${selectedError.folder_name}" associada a "${client?.client_name}"`);
      setIsResolveDialogOpen(false);
      setSelectedError(null);
      setSelectedClientId("");
      fetchErrors();
    } catch (error) {
      console.error("Erro ao resolver:", error);
      toast.error(error.response?.data?.detail || "Erro ao resolver associação");
    } finally {
      setResolving(false);
    }
  };

  const openResolveDialog = (error) => {
    setSelectedError(error);
    setSelectedClientId("");
    setIsResolveDialogOpen(true);
  };

  const exportToCSV = useCallback(() => {
    const headers = ["Data", "Pasta", "Ficheiro", "Tipo Erro", "Mensagem", "Resolvido"];
    const rows = errors.map(e => [
      new Date(e.created_at).toLocaleString("pt-PT"),
      e.folder_name || "",
      e.filename || "",
      e.error_type || "",
      e.error_message || "",
      e.resolved ? "Sim" : "Não"
    ]);
    
    const csvContent = [
      headers.join(";"),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(";"))
    ].join("\n");
    
    const blob = new Blob(["\ufeff" + csvContent], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `erros_importacao_${new Date().toISOString().split("T")[0]}.csv`;
    link.click();
    
    toast.success("CSV exportado com sucesso");
  }, [errors]);

  // Filter errors
  const filteredErrors = errors.filter(e => {
    const matchesSearch = 
      e.folder_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      e.filename?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      e.error_message?.toLowerCase().includes(searchTerm.toLowerCase());
    
    const matchesType = filterType === "all" || e.error_type === filterType;
    
    return matchesSearch && matchesType;
  });

  const getErrorTypeBadge = (type) => {
    const types = {
      client_not_found: { label: "Cliente não encontrado", variant: "destructive" },
      ai_failed: { label: "Falha IA", variant: "warning" },
      invalid_file: { label: "Ficheiro inválido", variant: "secondary" },
      duplicate: { label: "Duplicado", variant: "outline" },
      unknown: { label: "Desconhecido", variant: "secondary" }
    };
    const config = types[type] || types.unknown;
    return <Badge variant={config.variant}>{config.label}</Badge>;
  };

  return (
    <div className="space-y-6" data-testid="import-errors-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <AlertTriangle className="h-6 w-6 text-amber-500" />
            Erros de Importação
          </h1>
          <p className="text-muted-foreground">
            Dashboard de erros do upload massivo de documentos
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={fetchErrors} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
            Actualizar
          </Button>
          <Button variant="outline" onClick={exportToCSV} disabled={errors.length === 0}>
            <Download className="h-4 w-4 mr-2" />
            Exportar CSV
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">Total</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total}</div>
          </CardContent>
        </Card>
        <Card className="border-red-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-red-600">Cliente Não Encontrado</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-red-600">{stats.client_not_found}</div>
          </CardContent>
        </Card>
        <Card className="border-amber-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-amber-600">Falha IA</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-amber-600">{stats.ai_failed}</div>
          </CardContent>
        </Card>
        <Card className="border-gray-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600">Ficheiro Inválido</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-gray-600">{stats.invalid_file}</div>
          </CardContent>
        </Card>
        <Card className="border-green-200">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-green-600">Resolvidos</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{stats.resolved}</div>
          </CardContent>
        </Card>
      </div>

      {/* Main Card */}
      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div>
              <CardTitle>Lista de Erros</CardTitle>
              <CardDescription>
                Erros ocorridos durante o upload massivo de documentos
              </CardDescription>
            </div>
            <div className="flex gap-2 w-full sm:w-auto">
              <div className="relative flex-1 sm:flex-initial">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Pesquisar..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9 w-full sm:w-48"
                />
              </div>
              <Select value={filterType} onValueChange={setFilterType}>
                <SelectTrigger className="w-[180px]">
                  <Filter className="h-4 w-4 mr-2" />
                  <SelectValue placeholder="Filtrar por tipo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="client_not_found">Cliente não encontrado</SelectItem>
                  <SelectItem value="ai_failed">Falha IA</SelectItem>
                  <SelectItem value="invalid_file">Ficheiro inválido</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredErrors.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <CheckCircle className="h-12 w-12 mx-auto mb-2 text-green-500 opacity-50" />
              <p>Nenhum erro de importação encontrado</p>
              <p className="text-sm">
                Os erros aparecerão aqui quando ocorrerem durante o upload massivo
              </p>
            </div>
          ) : (
            <div className="rounded-md border overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[140px]">
                      <div className="flex items-center gap-1">
                        <Clock className="h-4 w-4" />
                        Data
                      </div>
                    </TableHead>
                    <TableHead>
                      <div className="flex items-center gap-1">
                        <FolderOpen className="h-4 w-4" />
                        Pasta
                      </div>
                    </TableHead>
                    <TableHead>
                      <div className="flex items-center gap-1">
                        <FileText className="h-4 w-4" />
                        Ficheiro
                      </div>
                    </TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Mensagem</TableHead>
                    <TableHead className="text-right">Acções</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredErrors.slice(0, 100).map((error, index) => (
                    <TableRow key={error.id || index} className={error.resolved ? "opacity-50" : ""}>
                      <TableCell className="text-sm text-muted-foreground">
                        {new Date(error.created_at).toLocaleString("pt-PT", {
                          day: "2-digit",
                          month: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit"
                        })}
                      </TableCell>
                      <TableCell className="font-medium max-w-[150px] truncate" title={error.folder_name}>
                        {error.folder_name || "-"}
                      </TableCell>
                      <TableCell className="max-w-[150px] truncate" title={error.filename}>
                        {error.filename || "-"}
                      </TableCell>
                      <TableCell>{getErrorTypeBadge(error.error_type)}</TableCell>
                      <TableCell className="max-w-[200px] truncate text-sm" title={error.error_message}>
                        {error.error_message}
                      </TableCell>
                      <TableCell className="text-right">
                        {error.resolved ? (
                          <Badge variant="outline" className="text-green-600">
                            <CheckCircle className="h-3 w-3 mr-1" />
                            Resolvido
                          </Badge>
                        ) : error.error_type === "client_not_found" ? (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => openResolveDialog(error)}
                          >
                            <Link2 className="h-4 w-4 mr-1" />
                            Resolver
                          </Button>
                        ) : (
                          <Badge variant="outline" className="text-muted-foreground">
                            <XCircle className="h-3 w-3 mr-1" />
                            Manual
                          </Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {filteredErrors.length > 100 && (
                <div className="text-center py-2 text-sm text-muted-foreground border-t">
                  A mostrar 100 de {filteredErrors.length} erros
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Resolve Dialog */}
      <Dialog open={isResolveDialogOpen} onOpenChange={setIsResolveDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Resolver Associação</DialogTitle>
            <DialogDescription>
              Associe a pasta "{selectedError?.folder_name}" a um cliente existente.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Pasta</Label>
              <div className="flex items-center gap-2 p-2 bg-muted rounded">
                <FolderOpen className="h-4 w-4" />
                <span className="font-medium">{selectedError?.folder_name}</span>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Seleccionar Cliente</Label>
              <Select value={selectedClientId} onValueChange={setSelectedClientId}>
                <SelectTrigger>
                  <SelectValue placeholder="Escolha um cliente..." />
                </SelectTrigger>
                <SelectContent className="max-h-[300px]">
                  {clients.map(client => (
                    <SelectItem key={client.id} value={client.id}>
                      <div className="flex flex-col">
                        <span>{client.client_name}</span>
                        {client.personal_data?.nif && (
                          <span className="text-xs text-muted-foreground">
                            NIF: {client.personal_data.nif}
                          </span>
                        )}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                O mapeamento será guardado para futuros uploads
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsResolveDialogOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleResolve}
              disabled={resolving || !selectedClientId}
              className="bg-teal-600 hover:bg-teal-700"
            >
              {resolving ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  A associar...
                </>
              ) : (
                <>
                  <Link2 className="h-4 w-4 mr-2" />
                  Associar
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default ImportErrorsPage;
