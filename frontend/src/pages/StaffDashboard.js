import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import KanbanBoard from "../components/KanbanBoard";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Badge } from "../components/ui/badge";
import { Loader2, LayoutGrid, Calendar, Users, FileText, CheckCircle, XCircle, TrendingUp, ClipboardList } from "lucide-react";
import TasksPanel from "../components/TasksPanel";
import { toast } from "sonner";
import { getStats, getUsers, getUpcomingExpiries, getCalendarDeadlines } from "../services/api";

const roleLabels = {
  admin: "Administrador",
  ceo: "CEO",
  consultor: "Consultor",
  intermediario: "Intermediário de Crédito",
  mediador: "Intermediário de Crédito",
  diretor: "Diretor(a)",
  administrativo: "Administrativo(a)",
  cliente: "Cliente"
};

const StaffDashboard = () => {
  const navigate = useNavigate();
  const { user, token } = useAuth();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [users, setUsers] = useState([]);
  const [expiries, setExpiries] = useState([]);
  const [deadlines, setDeadlines] = useState([]);
  const [activeTab, setActiveTab] = useState("kanban");

  const isAdmin = user?.role === "admin";
  const isCeo = user?.role === "ceo";
  const canManageUsers = isAdmin;
  const canSeeAllStats = isAdmin || isCeo;

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [statsRes, usersRes, expiriesRes, deadlinesRes] = await Promise.all([
        getStats().catch(() => ({ data: {} })),
        canSeeAllStats ? getUsers().catch(() => ({ data: [] })) : Promise.resolve({ data: [] }),
        getUpcomingExpiries(60).catch(() => ({ data: [] })),
        getCalendarDeadlines().catch(() => ({ data: [] })),
      ]);
      setStats(statsRes.data);
      setUsers(usersRes.data);
      setExpiries(expiriesRes.data);
      setDeadlines(deadlinesRes.data);
    } catch (error) {
      console.error("Error fetching data:", error);
      toast.error("Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  };

  // Navegação para lista filtrada
  const goToFilteredList = (filter) => {
    navigate(`/processos-filtrados?filter=${filter}`);
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="staff-dashboard">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Olá, {user?.name?.split(' ')[0]}</h1>
            <div className="text-muted-foreground flex items-center gap-2">
              <Badge variant="outline">{roleLabels[user?.role] || user?.role}</Badge>
              <span>{canSeeAllStats ? `${stats.total_processes || 0} processos no sistema` : "Os seus processos atribuídos"}</span>
            </div>
          </div>
        </div>

        {/* Quick Stats - Clickable cards */}
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card 
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate('/processos')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-3xl font-bold text-primary">{stats.total_processes || 0}</p>
                <p className="text-sm text-muted-foreground">Total</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className="bg-blue-50 dark:bg-blue-950/30 border-blue-200 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => goToFilteredList('active')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <TrendingUp className="h-5 w-5 text-blue-600" />
                  <p className="text-3xl font-bold text-blue-600">{stats.active_processes || 0}</p>
                </div>
                <p className="text-sm text-blue-600/80">Ativos</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className="bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => goToFilteredList('concluded')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <CheckCircle className="h-5 w-5 text-emerald-600" />
                  <p className="text-3xl font-bold text-emerald-600">{stats.concluded_processes || 0}</p>
                </div>
                <p className="text-sm text-emerald-600/80">Concluídos</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className="bg-red-50 dark:bg-red-950/30 border-red-200 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => goToFilteredList('dropped')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <div className="flex items-center justify-center gap-1">
                  <XCircle className="h-5 w-5 text-red-600" />
                  <p className="text-3xl font-bold text-red-600">{stats.dropped_processes || 0}</p>
                </div>
                <p className="text-sm text-red-600/80">Desistências</p>
              </div>
            </CardContent>
          </Card>
          <Card 
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate('/pendentes')}
          >
            <CardContent className="pt-6">
              <div className="text-center">
                <p className="text-3xl font-bold text-orange-500">{stats.total_pending || stats.pending_deadlines || 0}</p>
                <p className="text-sm text-muted-foreground">Pendentes</p>
                {(stats.pending_tasks > 0 || stats.pending_deadlines > 0) && (
                  <p className="text-xs text-muted-foreground mt-1">
                    {stats.pending_tasks || 0} tarefas • {stats.pending_deadlines || 0} prazos
                  </p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Main Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="flex-wrap">
            <TabsTrigger value="kanban" className="gap-2">
              <LayoutGrid className="h-4 w-4" />
              <span className="hidden sm:inline">Quadro Geral</span>
              <span className="sm:hidden">Quadro</span>
            </TabsTrigger>
            <TabsTrigger value="tasks" className="gap-2">
              <ClipboardList className="h-4 w-4" />
              <span className="hidden sm:inline">Minhas Tarefas</span>
              <span className="sm:hidden">Tarefas</span>
            </TabsTrigger>
            <TabsTrigger value="calendar" className="gap-2">
              <Calendar className="h-4 w-4" />
              <span className="hidden sm:inline">Calendário</span>
              <span className="sm:hidden">Cal.</span>
            </TabsTrigger>
            <TabsTrigger value="documents" className="gap-2">
              <FileText className="h-4 w-4" />
              <span className="hidden sm:inline">Documentos</span>
              <span className="sm:hidden">Docs</span>
            </TabsTrigger>
            {canManageUsers && (
              <TabsTrigger value="users" className="gap-2">
                <Users className="h-4 w-4" />
                <span className="hidden sm:inline">Utilizadores</span>
                <span className="sm:hidden">Users</span>
              </TabsTrigger>
            )}
          </TabsList>

          {/* Kanban Tab */}
          <TabsContent value="kanban" className="mt-6">
            <KanbanBoard token={token} user={user} />
          </TabsContent>

          {/* Tasks Tab - Minhas Tarefas */}
          <TabsContent value="tasks" className="mt-6">
            <TasksPanel 
              showCreateButton={true}
              compact={false}
              maxHeight="600px"
              showOnlyMyTasks={true}
            />
          </TabsContent>

          {/* Calendar Tab */}
          <TabsContent value="calendar" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Próximos Prazos</CardTitle>
                <CardDescription>Prazos e eventos agendados</CardDescription>
              </CardHeader>
              <CardContent>
                {deadlines.length === 0 ? (
                  <p className="text-muted-foreground text-center py-8">Nenhum prazo agendado</p>
                ) : (
                  <div className="space-y-3">
                    {[...deadlines]
                      .sort((a, b) => new Date(a.due_date) - new Date(b.due_date))
                      .slice(0, 10)
                      .map((deadline) => (
                      <div key={deadline.id} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
                        <div>
                          <p className="font-medium">{deadline.title}</p>
                          <p className="text-sm text-muted-foreground">{deadline.client_name}</p>
                        </div>
                        <div className="text-right">
                          <p className="text-sm font-medium">{new Date(deadline.due_date).toLocaleDateString('pt-PT')}</p>
                          <Badge variant={deadline.priority === "high" ? "destructive" : "outline"}>
                            {deadline.priority === "high" ? "Alta" : deadline.priority === "medium" ? "Média" : "Baixa"}
                          </Badge>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Documents Tab */}
          <TabsContent value="documents" className="mt-6">
            <Card>
              <CardHeader>
                <CardTitle>Documentos a Expirar</CardTitle>
                <CardDescription>Documentos dos seus clientes próximos da data de validade (60 dias), ordenados por data</CardDescription>
              </CardHeader>
              <CardContent>
                {expiries.length === 0 ? (
                  <p className="text-muted-foreground text-center py-8">Nenhum documento a expirar nos próximos 60 dias</p>
                ) : (
                  <div className="space-y-4">
                    {/* Ordenar documentos por data de expiração e agrupar por cliente */}
                    {(() => {
                      // Ordenar todos os documentos por data de expiração (crescente)
                      const sortedDocs = [...expiries].sort((a, b) => 
                        new Date(a.expiry_date) - new Date(b.expiry_date)
                      );
                      
                      // Agrupar por cliente mantendo a ordem
                      const grouped = sortedDocs.reduce((acc, doc) => {
                        const clientKey = doc.client_name || 'Sem Cliente';
                        if (!acc[clientKey]) {
                          acc[clientKey] = {
                            client_name: doc.client_name,
                            process_id: doc.process_id,
                            documents: [],
                            earliestExpiry: doc.expiry_date
                          };
                        }
                        acc[clientKey].documents.push(doc);
                        return acc;
                      }, {});
                      
                      // Ordenar grupos pelo documento mais próximo a expirar
                      const sortedGroups = Object.entries(grouped).sort((a, b) => 
                        new Date(a[1].earliestExpiry) - new Date(b[1].earliestExpiry)
                      );
                      
                      return sortedGroups.map(([clientName, clientData]) => {
                        const earliestDays = Math.ceil((new Date(clientData.earliestExpiry) - new Date()) / (1000 * 60 * 60 * 24));
                        const borderColor = earliestDays <= 7 ? 'border-l-red-500' : earliestDays <= 30 ? 'border-l-amber-500' : 'border-l-blue-500';
                        
                        return (
                          <div key={clientName} className={`border-l-4 ${borderColor} rounded-lg bg-muted/20 overflow-hidden`}>
                            <div className="py-2 px-4 bg-muted/40 flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                <Users className="h-4 w-4 text-blue-900" />
                                {clientData.process_id ? (
                                  <span 
                                    className="font-semibold text-blue-900 hover:text-blue-700 cursor-pointer hover:underline"
                                    onClick={() => navigate(`/process/${clientData.process_id}`)}
                                  >
                                    {clientName}
                                  </span>
                                ) : (
                                  <span className="font-semibold">{clientName}</span>
                                )}
                                <Badge variant="outline">{clientData.documents.length} doc(s)</Badge>
                              </div>
                            </div>
                            <div className="p-3 space-y-2">
                              {clientData.documents.map((doc) => {
                                const daysUntil = Math.ceil((new Date(doc.expiry_date) - new Date()) / (1000 * 60 * 60 * 24));
                                const urgencyClass = daysUntil <= 7 ? 'bg-red-50 border-red-200 text-red-800' : 
                                                     daysUntil <= 30 ? 'bg-amber-50 border-amber-200 text-amber-800' : 
                                                     'bg-blue-50 border-blue-200 text-blue-800';
                                return (
                                  <div key={doc.id} className={`flex items-center justify-between p-2 rounded border ${urgencyClass}`}>
                                    <div className="flex items-center gap-2">
                                      <FileText className="h-4 w-4" />
                                      <span className="font-medium text-sm">{doc.document_name}</span>
                                      <Badge variant="outline" className="text-xs">{doc.document_type}</Badge>
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <span className="text-xs">{new Date(doc.expiry_date).toLocaleDateString('pt-PT')}</span>
                                      <Badge className={daysUntil <= 7 ? 'bg-red-500' : daysUntil <= 30 ? 'bg-amber-500' : 'bg-blue-500'}>
                                        {daysUntil}d
                                      </Badge>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      });
                    })()}
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Users Tab (Admin only) */}
          {canManageUsers && (
            <TabsContent value="users" className="mt-6">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle>Gestão de Utilizadores</CardTitle>
                      <CardDescription>
                        {stats.active_users || 0} ativos • {stats.inactive_users || 0} inativos
                      </CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {users.map((u) => (
                      <div key={u.id} className={`flex items-center justify-between p-3 rounded-lg ${u.is_active === false ? 'bg-red-50 dark:bg-red-950/20' : 'bg-muted/30'}`}>
                        <div className="flex items-center gap-3">
                          <div className={`w-2 h-2 rounded-full ${u.is_active === false ? 'bg-red-500' : 'bg-emerald-500'}`} />
                          <div>
                            <p className={`font-medium ${u.is_active === false ? 'text-muted-foreground' : ''}`}>
                              {u.name}
                              {u.is_active === false && <span className="text-xs text-red-500 ml-2">(Inativo)</span>}
                            </p>
                            <p className="text-sm text-muted-foreground">{u.email}</p>
                          </div>
                        </div>
                        <Badge variant={u.is_active === false ? "secondary" : "default"}>
                          {roleLabels[u.role] || u.role}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>
          )}

        </Tabs>
      </div>
    </DashboardLayout>
  );
};

export default StaffDashboard;
