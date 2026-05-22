/**
 * KanbanPage - Página dedicada ao Quadro Geral (Kanban)
 * 
 * Página principal após login - mostra o KanbanBoard com filtros por
 * consultor, intermediário, indexação e parceiro. Filtros são persistidos na URL.
 */
import { useState, useEffect, useMemo } from "react";
import * as XLSX from 'xlsx';
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import KanbanBoard from "../components/KanbanBoard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Loader2, LayoutGrid, Plus, Download } from "lucide-react";
import { getUsers } from "../services/api";
import { toast } from "sonner";
import CreateClientModal from "../components/kanban/CreateClientModal";
import { filterByAnyRole, filterByRole, hasRole } from "../utils/roleUtils";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://powercell.onrender.com";
const API_URL = BACKEND_URL + "/api";

const KanbanPage = () => {
  const { token, user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState([]);
  const [showCreateProcess, setShowCreateProcess] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [allowExcelExport, setAllowExcelExport] = useState(true);

  // Admin/CEO sempre podem exportar, independentemente da config
  const canExportExcel = allowExcelExport || hasRole(user, 'admin') || hasRole(user, 'ceo');

  // Ler filtros da URL
  const consultorFilter = searchParams.get("consultor") || "all";
  const mediadorFilter = searchParams.get("mediador") || "all";
  const indexacaoFilter = searchParams.get("indexacao") || "all";
  const parceiroFilter = searchParams.get("parceiro") || "all";
  // Filtro de estado de indexação — 'pending' por omissão para role indexacao
  const indexStatusFilter = searchParams.get("indexStatus") ||
    (user?.role?.toLowerCase() === 'indexacao' ? 'pending' : 'all');

  const consultors = useMemo(() => filterByAnyRole(users, ["consultor", "diretor"]), [users]);
  const intermediarios = useMemo(() => filterByAnyRole(users, ["intermediario", "diretor"]), [users]);
  const indexacaoUsers = useMemo(() => filterByRole(users, "indexacao"), [users]);
  const parceiros = useMemo(() => filterByRole(users, "parceiro"), [users]);

  useEffect(() => {
    fetchUsers();
    checkExportPermission();
  }, []);

  const checkExportPermission = async () => {
    try {
      const res = await fetch(`${API_URL}/system-config/public/export-permission`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setAllowExcelExport(data.allow_excel_export !== false);
      }
    } catch {
      // Em caso de erro, manter default (true)
    }
  };

  const fetchUsers = async () => {
    try {
      setLoading(true);
      const usersRes = await getUsers().catch(() => ({ data: [] }));
      setUsers(usersRes.data);
    } catch (error) {
      console.error("Error fetching users:", error);
      toast.error("Erro ao carregar utilizadores");
    } finally {
      setLoading(false);
    }
  };

  const handleExportExcel = async () => {
    setExporting(true);
    try {
      // Construir query params com TODOS os filtros ativos
      const params = new URLSearchParams();
      if (consultorFilter !== 'all') params.set('consultor', consultorFilter);
      if (mediadorFilter !== 'all') params.set('mediador', mediadorFilter);
      if (indexacaoFilter !== 'all') params.set('indexacao', indexacaoFilter);
      if (parceiroFilter !== 'all') params.set('parceiro', parceiroFilter);

      const res = await fetch(`${API_URL}/processes/kanban?${params.toString()}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Erro ao obter dados');
      const data = await res.json();
      // Extract processes from columns
      let allProcesses = (data.columns || []).flatMap(col =>
        (col.processes || col.items || []).map(p => ({
          'Processo': p.process_number || '',
          'Cliente': p.client_name || '',
          'NIF': p.client_nif || '',
          'Telefone': p.client_phone || '',
          'Tipo de Processo': p.process_type ? String(p.process_type).replace(/_/g, ' ') : '',
          'Consultores': p.consultor_name || '',
          'Intermediários': p.mediador_name || '',
          'Indexação': p.indexacao_name || '',
          'Parceiro': p.parceiro_name || '',
          'Fase': (p.status || '').replace(/_/g, ' '),
          'Valor Imóvel': p.real_estate_data?.valor_imovel || p.property_value || '',
          'Morada do Imóvel': p.real_estate_data?.morada_imovel || p.real_estate_data?.morada || p.property_address || '',
          'Link Imóvel': p.real_estate_data?.link_imovel || '',
          'Notas/Descrição': p.description || '',
          'Previsão Escritura': p.deadlines?.escritura || '',
          'Data de Criação': p.created_at || '',
          'Indexado': p.is_indexed ? 'Sim' : 'Não',
        }))
      );
      // Aplicar filtro de estado de indexação no lado do cliente
      if (indexStatusFilter === 'completed') {
        allProcesses = allProcesses.filter(p => p['Indexado'] === 'Sim');
      } else if (indexStatusFilter === 'pending') {
        allProcesses = allProcesses.filter(p => p['Indexado'] === 'Não');
      }
      if (allProcesses.length === 0) {
        toast.error('Nenhum processo para exportar com os filtros selecionados');
        return;
      }
      const ws = XLSX.utils.json_to_sheet(allProcesses);
      // Ajustar larguras das colunas
      ws['!cols'] = [
        { wch: 10 }, // Processo
        { wch: 25 }, // Cliente
        { wch: 12 }, // NIF
        { wch: 15 }, // Telefone
        { wch: 18 }, // Tipo de Processo
        { wch: 25 }, // Consultores
        { wch: 25 }, // Intermediários
        { wch: 20 }, // Indexação
        { wch: 20 }, // Parceiro
        { wch: 18 }, // Fase
        { wch: 14 }, // Valor Imóvel
        { wch: 30 }, // Morada do Imóvel
        { wch: 35 }, // Link Imóvel
        { wch: 40 }, // Notas/Descrição
        { wch: 16 }, // Previsão Escritura
        { wch: 18 }, // Data de Criação
        { wch: 8 },  // Indexado
      ];
      const wb = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(wb, ws, 'Processos');
      XLSX.writeFile(wb, 'processos_powercell.xlsx');
      toast.success(`${allProcesses.length} processos exportados com sucesso!`);
    } catch (err) {
      toast.error('Erro ao exportar Excel');
    } finally {
      setExporting(false);
    }
  };

  // Actualizar filtros na URL
  const updateFilter = (key, value) => {
    setSearchParams(prev => {
      if (value === "all") {
        prev.delete(key);
      } else {
        prev.set(key, value);
      }
      return prev;
    }, { replace: true });
  };

  if (loading) {
    return (
      <DashboardLayout title="Quadro Geral">
        <div className="space-y-6">
          <div className="flex items-start justify-between">
            <div className="space-y-1.5">
              <div className="h-7 w-48 bg-muted animate-pulse rounded" />
              <div className="h-4 w-64 bg-muted animate-pulse rounded" />
            </div>
          </div>
          <div className="h-10 bg-muted animate-pulse rounded" />
          <div className="h-[600px] bg-muted animate-pulse rounded-lg" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout title="Quadro Geral">
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              <LayoutGrid className="h-5 w-5 shrink-0" />
              Quadro Geral de Processos
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Filtre por consultor, intermediário, indexação, parceiro ou estado de indexação
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {canExportExcel && (
              <Button
                variant="outline"
                className="gap-2"
                onClick={handleExportExcel}
                disabled={exporting}
              >
                {exporting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Download className="h-4 w-4" />
                )}
                Exportar Excel
              </Button>
            )}
            <Button
              className="gap-2"
              onClick={() => setShowCreateProcess(true)}
            >
              <Plus className="h-4 w-4" />
              Novo Processo
            </Button>
          </div>
        </div>

        {/* Kanban Board */}
        <Card className="border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-base sm:text-lg flex items-center gap-2">
              <LayoutGrid className="h-5 w-5 shrink-0" />
              Quadro Geral de Processos
            </CardTitle>
            <CardDescription className="text-xs sm:text-sm">
              {user?.name?.split(' ')[0]} · {hasRole(user, "admin") ? "Administrador" : hasRole(user, "ceo") ? "CEO" : hasRole(user, "consultor") ? "Consultor" : hasRole(user, "intermediario") ? "Intermediário" : hasRole(user, "indexacao") ? "Indexação" : hasRole(user, "diretor") ? "Diretor(a)" : hasRole(user, "administrativo") ? "Administrativo(a)" : user?.role}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            {/* Filter Controls */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
              <div className="space-y-2">
                <Label>Filtrar por Consultor</Label>
                <Select value={consultorFilter} onValueChange={(v) => updateFilter("consultor", v)}>
                  <SelectTrigger><SelectValue placeholder="Todos os consultores" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os consultores</SelectItem>
                    <SelectItem value="none">Nenhum (sem consultor)</SelectItem>
                    {consultors.map((c) => (<SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Filtrar por Intermediário</Label>
                <Select value={mediadorFilter} onValueChange={(v) => updateFilter("mediador", v)}>
                  <SelectTrigger><SelectValue placeholder="Todos os intermediários" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os intermediários</SelectItem>
                    <SelectItem value="none">Nenhum (sem intermediário)</SelectItem>
                    {intermediarios.map((m) => (<SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Filtrar por Indexação</Label>
                <Select value={indexacaoFilter} onValueChange={(v) => updateFilter("indexacao", v)}>
                  <SelectTrigger><SelectValue placeholder="Todos os indexação" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os Indexação</SelectItem>
                    <SelectItem value="none">Nenhum (sem indexação)</SelectItem>
                    {indexacaoUsers.map((u) => (<SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Filtrar por Parceiro</Label>
                <Select value={parceiroFilter} onValueChange={(v) => updateFilter("parceiro", v)}>
                  <SelectTrigger><SelectValue placeholder="Todos os parceiros" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos os Parceiros</SelectItem>
                    <SelectItem value="none">Nenhum (sem parceiro)</SelectItem>
                    {parceiros.map((p) => (<SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Estado de Indexação</Label>
                <Select value={indexStatusFilter} onValueChange={(v) => updateFilter("indexStatus", v)}>
                  <SelectTrigger><SelectValue placeholder="Todos os estados" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos</SelectItem>
                    <SelectItem value="pending">Pendentes (por indexar)</SelectItem>
                    <SelectItem value="completed">Concluídos (indexados)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Kanban Board Component */}
            <KanbanBoard
              token={token}
              user={user}
              consultorFilter={consultorFilter}
              mediadorFilter={mediadorFilter}
              indexacaoFilter={indexacaoFilter}
              parceiroFilter={parceiroFilter}
              indexStatusFilter={indexStatusFilter}
            />
          </CardContent>
        </Card>
      </div>

      {/* Create Process Modal — Fase 3: paradigma relacional */}
      <CreateClientModal
        open={showCreateProcess}
        onOpenChange={setShowCreateProcess}
        onSuccess={() => fetchUsers()}
      />
    </DashboardLayout>
  );
};

export default KanbanPage;
