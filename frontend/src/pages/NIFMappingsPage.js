/**
 * NIFMappingsPage - Gestão de Mapeamentos NIF
 * Permite visualizar e gerir os mapeamentos pasta -> cliente baseados em NIF
 */
import { useState, useEffect } from "react";
import DashboardLayout from "../layouts/DashboardLayout";
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
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "../components/ui/alert-dialog";
import { 
  Database, Plus, Trash2, RefreshCw, Search, 
  FolderOpen, User, Hash, Clock, AlertTriangle
} from "lucide-react";
import { toast } from "sonner";
import api from "../services/api";

const NIFMappingsPage = () => {
  const [mappings, setMappings] = useState([]);
  const [stats, setStats] = useState({ total_entries_memory: 0, total_entries_db: 0, ttl_days: 30 });
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  
  // Dialogs
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [isClearDialogOpen, setIsClearDialogOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [clearing, setClearing] = useState(false);
  
  // Form state
  const [newMapping, setNewMapping] = useState({
    folder_name: "",
    nif: ""
  });

  useEffect(() => {
    fetchMappings();
  }, []);

  const fetchMappings = async () => {
    try {
      setLoading(true);
      const response = await api.get("/ai/bulk/nif-cache/stats");
      setStats({
        total_entries_memory: response.data.total_entries_memory || 0,
        total_entries_db: response.data.total_entries_db || 0,
        ttl_days: response.data.ttl_days || 30
      });
      setMappings(response.data.entries || []);
    } catch (error) {
      console.error("Erro ao carregar mapeamentos:", error);
      toast.error("Erro ao carregar mapeamentos NIF");
    } finally {
      setLoading(false);
    }
  };

  const handleAddMapping = async () => {
    if (!newMapping.folder_name.trim() || !newMapping.nif.trim()) {
      toast.error("Preencha todos os campos");
      return;
    }

    if (newMapping.nif.replace(/\D/g, "").length !== 9) {
      toast.error("NIF deve ter 9 dígitos");
      return;
    }

    try {
      setAdding(true);
      const response = await api.post(
        `/ai/bulk/nif-cache/add-mapping?folder_name=${encodeURIComponent(newMapping.folder_name)}&nif=${newMapping.nif}`
      );
      
      if (response.data.success) {
        toast.success(response.data.message);
        setIsAddDialogOpen(false);
        setNewMapping({ folder_name: "", nif: "" });
        fetchMappings();
      } else {
        toast.error(response.data.error || "Erro ao adicionar mapeamento");
      }
    } catch (error) {
      console.error("Erro ao adicionar mapeamento:", error);
      toast.error(error.response?.data?.detail || "Erro ao adicionar mapeamento");
    } finally {
      setAdding(false);
    }
  };

  const handleClearAll = async () => {
    try {
      setClearing(true);
      const response = await api.post("/ai/bulk/nif-cache/clear");
      toast.success(response.data.message);
      setIsClearDialogOpen(false);
      fetchMappings();
    } catch (error) {
      console.error("Erro ao limpar cache:", error);
      toast.error("Erro ao limpar cache NIF");
    } finally {
      setClearing(false);
    }
  };

  // Filtrar mapeamentos
  const filteredMappings = mappings.filter(m => 
    m.folder?.toLowerCase().includes(searchTerm.toLowerCase()) ||
    m.nif?.includes(searchTerm) ||
    m.client_name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <DashboardLayout title="Mapeamentos NIF">
    <div className="space-y-6" data-testid="nif-mappings-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Database className="h-6 w-6" />
            Mapeamentos NIF
          </h1>
          <p className="text-muted-foreground">
            Gestão de mapeamentos pasta → cliente baseados em NIF
          </p>
        </div>
        <div className="flex gap-2">
          <Button 
            variant="outline" 
            onClick={fetchMappings}
            disabled={loading}
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
            Actualizar
          </Button>
          <Button 
            onClick={() => setIsAddDialogOpen(true)}
            className="bg-teal-600 hover:bg-teal-700"
          >
            <Plus className="h-4 w-4 mr-2" />
            Novo Mapeamento
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Mapeamentos em Memória
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total_entries_memory}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Mapeamentos na Base de Dados
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.total_entries_db}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Validade do Cache
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats.ttl_days} dias</div>
          </CardContent>
        </Card>
      </div>

      {/* Main Card */}
      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div>
              <CardTitle>Lista de Mapeamentos</CardTitle>
              <CardDescription>
                Mapeamentos pasta → cliente para upload massivo de documentos
              </CardDescription>
            </div>
            <div className="flex gap-2 w-full sm:w-auto">
              <div className="relative flex-1 sm:flex-initial">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Pesquisar..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-9 w-full sm:w-64"
                />
              </div>
              {mappings.length > 0 && (
                <Button 
                  variant="destructive" 
                  size="sm"
                  onClick={() => setIsClearDialogOpen(true)}
                >
                  <Trash2 className="h-4 w-4 mr-1" />
                  Limpar
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredMappings.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <Database className="h-12 w-12 mx-auto mb-2 opacity-20" />
              <p>Nenhum mapeamento encontrado</p>
              <p className="text-sm">
                Os mapeamentos são criados automaticamente quando um CC é analisado
              </p>
            </div>
          ) : (
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>
                      <div className="flex items-center gap-1">
                        <FolderOpen className="h-4 w-4" />
                        Pasta
                      </div>
                    </TableHead>
                    <TableHead>
                      <div className="flex items-center gap-1">
                        <Hash className="h-4 w-4" />
                        NIF
                      </div>
                    </TableHead>
                    <TableHead>
                      <div className="flex items-center gap-1">
                        <User className="h-4 w-4" />
                        Cliente
                      </div>
                    </TableHead>
                    <TableHead>
                      <div className="flex items-center gap-1">
                        <Clock className="h-4 w-4" />
                        Idade / Expira
                      </div>
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredMappings.map((mapping, index) => (
                    <TableRow key={index}>
                      <TableCell className="font-medium">
                        {mapping.folder}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className="font-mono">
                          {mapping.nif}
                        </Badge>
                      </TableCell>
                      <TableCell>{mapping.client_name}</TableCell>
                      <TableCell>
                        <div className="flex flex-col text-sm">
                          <span className="text-muted-foreground">
                            Há {mapping.age_days} dias
                          </span>
                          <span className={mapping.expires_in_days < 7 ? "text-amber-600" : "text-green-600"}>
                            Expira em {mapping.expires_in_days} dias
                          </span>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Add Mapping Dialog */}
      <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Adicionar Mapeamento Manual</DialogTitle>
            <DialogDescription>
              Associe uma pasta de documentos a um cliente através do NIF.
              O sistema irá encontrar o cliente correspondente na base de dados.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="folder_name">Nome da Pasta</Label>
              <Input
                id="folder_name"
                placeholder="Ex: João Silva"
                value={newMapping.folder_name}
                onChange={(e) => setNewMapping({ ...newMapping, folder_name: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                Nome da pasta onde estão os documentos do cliente
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="nif">NIF do Cliente</Label>
              <Input
                id="nif"
                placeholder="123456789"
                maxLength={9}
                value={newMapping.nif}
                onChange={(e) => setNewMapping({ ...newMapping, nif: e.target.value.replace(/\D/g, "") })}
              />
              <p className="text-xs text-muted-foreground">
                O NIF será usado para encontrar o cliente na base de dados
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsAddDialogOpen(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={handleAddMapping} 
              disabled={adding}
              className="bg-teal-600 hover:bg-teal-700"
            >
              {adding ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  A adicionar...
                </>
              ) : (
                <>
                  <Plus className="h-4 w-4 mr-2" />
                  Adicionar
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Clear All Confirmation */}
      <AlertDialog open={isClearDialogOpen} onOpenChange={setIsClearDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Limpar Todos os Mapeamentos?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Esta acção irá remover todos os {stats.total_entries_db} mapeamentos da memória e da base de dados.
              Os mapeamentos serão recriados automaticamente quando novos CCs forem analisados.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleClearAll}
              disabled={clearing}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {clearing ? "A limpar..." : "Sim, Limpar Tudo"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
    </DashboardLayout>
  );
};

export default NIFMappingsPage;
