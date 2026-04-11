/**
 * KanbanPage - Página dedicada ao Quadro Geral (Kanban)
 * 
 * Página principal após login - mostra o KanbanBoard com filtros por
 * consultor, intermediário e indexação. Filtros são persistidos na URL.
 */
import { useState, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import KanbanBoard from "../components/KanbanBoard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Label } from "../components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Loader2, LayoutGrid } from "lucide-react";
import { getUsers } from "../services/api";
import { toast } from "sonner";

const KanbanPage = () => {
  const { token, user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [users, setUsers] = useState([]);

  // Ler filtros da URL
  const consultorFilter = searchParams.get("consultor") || "all";
  const mediadorFilter = searchParams.get("mediador") || "all";
  const indexacaoFilter = searchParams.get("indexacao") || "all";

  const consultors = useMemo(() => users.filter(u => ["consultor", "diretor"].includes(u.role)), [users]);
  const intermediarios = useMemo(() => users.filter(u => ["mediador", "intermediario", "diretor"].includes(u.role)), [users]);
  const indexacaoUsers = useMemo(() => users.filter(u => u.role === "indexacao"), [users]);

  useEffect(() => {
    fetchUsers();
  }, []);

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
      <DashboardLayout>
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
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <LayoutGrid className="h-5 w-5 shrink-0" />
            Quadro Geral de Processos
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Filtre por consultor, intermediário ou indexação
          </p>
        </div>

        {/* Kanban Board */}
        <Card className="border-border">
          <CardHeader className="pb-3">
            <CardTitle className="text-base sm:text-lg flex items-center gap-2">
              <LayoutGrid className="h-5 w-5 shrink-0" />
              Quadro Geral de Processos
            </CardTitle>
            <CardDescription className="text-xs sm:text-sm">
              {user?.name?.split(' ')[0]} · {user?.role === "admin" ? "Administrador" : user?.role === "ceo" ? "CEO" : user?.role === "consultor" ? "Consultor" : user?.role === "mediador" || user?.role === "intermediario" ? "Intermediário" : user?.role === "indexacao" ? "Indexação" : user?.role === "diretor" ? "Diretor(a)" : user?.role === "administrativo" ? "Administrativo(a)" : user?.role}
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-0">
            {/* Filter Controls */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
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
            </div>

            {/* Kanban Board Component */}
            <KanbanBoard
              token={token}
              user={user}
              consultorFilter={consultorFilter}
              mediadorFilter={mediadorFilter}
              indexacaoFilter={indexacaoFilter}
            />
          </CardContent>
        </Card>
      </div>
    </DashboardLayout>
  );
};

export default KanbanPage;
