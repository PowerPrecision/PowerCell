import { useState, useEffect, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Calendar } from "../components/ui/calendar";
import { Textarea } from "../components/ui/textarea";
import { 
  Users, Settings, Plus, Edit, Trash2, Search, UserPlus, GitBranch, FolderOpen, 
  Loader2, CheckCircle, XCircle, FileText, Calendar as CalendarIcon, Filter, Eye, Sparkles,
  UserX, UserCheck, LayoutGrid
} from "lucide-react";
import { toast } from "sonner";
import { 
  getStats, getUsers, createUser, updateUser, deleteUser,
  getWorkflowStatuses, createWorkflowStatus, updateWorkflowStatus, deleteWorkflowStatus,
  getOneDriveStatus, getProcesses, getCalendarDeadlines, createDeadline, deleteDeadline,
  getUpcomingExpiries, analyzeDocument
} from "../services/api";

const roleLabels = { admin: "Administrador", ceo: "CEO", consultor: "Consultor", mediador: "Intermediário de Crédito", intermediario: "Intermediário de Crédito", consultor_mediador: "Consultor/Intermediário", consultor_intermediario: "Consultor/Intermediário", cliente: "Cliente" };
const roleColors = {
  admin: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400",
  consultor: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400",
  mediador: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400",
  cliente: "bg-gray-100 text-gray-800 dark:bg-gray-800/30 dark:text-gray-400",
};

const statusColorOptions = [
  { value: "yellow", label: "Amarelo", class: "bg-yellow-100 text-yellow-800" },
  { value: "blue", label: "Azul", class: "bg-blue-100 text-blue-800" },
  { value: "orange", label: "Laranja", class: "bg-orange-100 text-orange-800" },
  { value: "green", label: "Verde", class: "bg-green-100 text-green-800" },
  { value: "red", label: "Vermelho", class: "bg-red-100 text-red-800" },
  { value: "purple", label: "Roxo", class: "bg-purple-100 text-purple-800" },
];

const AdminDashboard = () => {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({});
  const [users, setUsers] = useState([]);
  const [processes, setProcesses] = useState([]);
  const [workflowStatuses, setWorkflowStatuses] = useState([]);
  const [oneDriveStatus, setOneDriveStatus] = useState(null);
  const [calendarDeadlines, setCalendarDeadlines] = useState([]);
  const [upcomingExpiries, setUpcomingExpiries] = useState([]);
  
  const [activeTab, setActiveTab] = useState("overview");
  const [searchTerm, setSearchTerm] = useState("");
  const [userSearchTerm, setUserSearchTerm] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [consultorFilter, setConsultorFilter] = useState("all");
  const [mediadorFilter, setMediadorFilter] = useState("all");
  const [selectedDate, setSelectedDate] = useState(new Date());
  
  // Dialogs
  const [isCreateUserDialogOpen, setIsCreateUserDialogOpen] = useState(false);
  const [isEditUserDialogOpen, setIsEditUserDialogOpen] = useState(false);
  const [isCreateStatusDialogOpen, setIsCreateStatusDialogOpen] = useState(false);
  const [isEditStatusDialogOpen, setIsEditStatusDialogOpen] = useState(false);
  const [isCreateEventDialogOpen, setIsCreateEventDialogOpen] = useState(false);
  const [formLoading, setFormLoading] = useState(false);
  
  // Form data
  const [userFormData, setUserFormData] = useState({ name: "", email: "", password: "", phone: "", role: "cliente", onedrive_folder: "" });
  const [statusFormData, setStatusFormData] = useState({ name: "", label: "", order: 1, color: "blue", description: "" });
  const [eventFormData, setEventFormData] = useState({ 
    title: "", 
    description: "", 
    due_date: "", 
    priority: "medium",
    process_id: "",
    assigned_consultor_id: "",
    assigned_mediador_id: ""
  });
  const [editingUserId, setEditingUserId] = useState(null);
  const [editingStatusId, setEditingStatusId] = useState(null);

  // Get consultors and intermediários for filters
  const consultors = useMemo(() => users.filter(u => u.role === "consultor" || u.role === "consultor_mediador" || u.role === "consultor_intermediario" || u.role === "ceo"), [users]);
  const intermediarios = useMemo(() => users.filter(u => u.role === "mediador" || u.role === "intermediario" || u.role === "consultor_mediador" || u.role === "consultor_intermediario"), [users]);

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    fetchCalendarData();
  }, [consultorFilter, mediadorFilter]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [statsRes, usersRes, processesRes, statusesRes, oneDriveRes, expiriesRes] = await Promise.all([
        getStats(),
        getUsers(),
        getProcesses(),
        getWorkflowStatuses(),
        getOneDriveStatus().catch(() => ({ data: { configured: false } })),
        getUpcomingExpiries(60).catch(() => ({ data: [] })),
      ]);
      setStats(statsRes.data);
      setUsers(usersRes.data);
      setProcesses(processesRes.data);
      setWorkflowStatuses(statusesRes.data);
      setOneDriveStatus(oneDriveRes.data);
      setUpcomingExpiries(expiriesRes.data);
    } catch (error) {
      console.error("Error fetching data:", error);
      toast.error("Erro ao carregar dados");
    } finally {
      setLoading(false);
    }
  };

  const fetchCalendarData = async () => {
    try {
      const res = await getCalendarDeadlines(
        consultorFilter !== "all" ? consultorFilter : null,
        mediadorFilter !== "all" ? mediadorFilter : null
      );
      setCalendarDeadlines(res.data);
    } catch (error) {
      console.error("Error fetching calendar data:", error);
    }
  };

  const filteredUsers = useMemo(() => {
    return users.filter(user => {
      const matchesSearch = user.name.toLowerCase().includes(userSearchTerm.toLowerCase()) ||
                           user.email.toLowerCase().includes(userSearchTerm.toLowerCase());
      const matchesRole = roleFilter === "all" || user.role === roleFilter;
      return matchesSearch && matchesRole;
    });
  }, [users, userSearchTerm, roleFilter]);

  const filteredProcesses = useMemo(() => {
    return processes.filter(process => {
      const matchesConsultor = consultorFilter === "all" || process.assigned_consultor_id === consultorFilter;
      const matchesMediador = mediadorFilter === "all" || process.assigned_mediador_id === mediadorFilter;
      return matchesConsultor && matchesMediador;
    });
  }, [processes, consultorFilter, mediadorFilter]);

  // Get deadlines for selected date
  const deadlinesForDate = useMemo(() => {
    const dateStr = selectedDate.toISOString().split('T')[0];
    return calendarDeadlines.filter(d => d.due_date === dateStr);
  }, [calendarDeadlines, selectedDate]);

  // Get dates with deadlines for calendar highlighting
  const datesWithDeadlines = useMemo(() => {
    return calendarDeadlines.map(d => new Date(d.due_date));
  }, [calendarDeadlines]);

  const getColorClass = (color) => {
    const colorOption = statusColorOptions.find(c => c.value === color);
    return colorOption ? colorOption.class : "bg-gray-100 text-gray-800";
  };

  // User handlers
  const handleCreateUser = async (e) => {
    e.preventDefault();
    setFormLoading(true);
    try {
      await createUser(userFormData);
      toast.success("Utilizador criado com sucesso");
      setIsCreateUserDialogOpen(false);
      setUserFormData({ name: "", email: "", password: "", phone: "", role: "cliente", onedrive_folder: "" });
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao criar utilizador");
    } finally {
      setFormLoading(false);
    }
  };

  const openEditUserDialog = (user) => {
    setEditingUserId(user.id);
    setUserFormData({ name: user.name, email: user.email, phone: user.phone || "", role: user.role, onedrive_folder: user.onedrive_folder || "" });
    setIsEditUserDialogOpen(true);
  };

  const handleEditUser = async (e) => {
    e.preventDefault();
    setFormLoading(true);
    try {
      await updateUser(editingUserId, { name: userFormData.name, phone: userFormData.phone, role: userFormData.role, onedrive_folder: userFormData.onedrive_folder });
      toast.success("Utilizador atualizado");
      setIsEditUserDialogOpen(false);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao atualizar utilizador");
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeleteUser = async (userId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar este utilizador?")) return;
    try {
      await deleteUser(userId);
      toast.success("Utilizador eliminado");
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao eliminar utilizador");
    }
  };

  const handleToggleUserStatus = async (userId, currentStatus) => {
    try {
      await updateUser(userId, { is_active: !currentStatus });
      toast.success(`Utilizador ${!currentStatus ? 'ativado' : 'desativado'} com sucesso`);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao atualizar utilizador");
    }
  };


  // Status handlers
  const handleCreateStatus = async (e) => {
    e.preventDefault();
    setFormLoading(true);
    try {
      await createWorkflowStatus(statusFormData);
      toast.success("Estado criado com sucesso");
      setIsCreateStatusDialogOpen(false);
      setStatusFormData({ name: "", label: "", order: 1, color: "blue", description: "" });
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao criar estado");
    } finally {
      setFormLoading(false);
    }
  };

  const openEditStatusDialog = (status) => {
    setEditingStatusId(status.id);
    setStatusFormData({ name: status.name, label: status.label, order: status.order, color: status.color, description: status.description || "" });
    setIsEditStatusDialogOpen(true);
  };

  const handleEditStatus = async (e) => {
    e.preventDefault();
    setFormLoading(true);
    try {
      await updateWorkflowStatus(editingStatusId, { label: statusFormData.label, order: statusFormData.order, color: statusFormData.color, description: statusFormData.description });
      toast.success("Estado atualizado");
      setIsEditStatusDialogOpen(false);
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao atualizar estado");
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeleteStatus = async (statusId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar este estado?")) return;
    try {
      await deleteWorkflowStatus(statusId);
      toast.success("Estado eliminado");
      fetchData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao eliminar estado");
    }
  };

  // Event/Deadline handlers
  const openCreateEventDialog = (date) => {
    setEventFormData({
      title: "",
      description: "",
      due_date: date ? date.toISOString().split('T')[0] : selectedDate.toISOString().split('T')[0],
      priority: "medium",
      process_id: "",
      assigned_consultor_id: "",
      assigned_mediador_id: ""
    });
    setIsCreateEventDialogOpen(true);
  };

  const handleCreateEvent = async (e) => {
    e.preventDefault();
    setFormLoading(true);
    try {
      const data = {
        title: eventFormData.title,
        description: eventFormData.description || null,
        due_date: eventFormData.due_date,
        priority: eventFormData.priority,
        process_id: eventFormData.process_id || null,
        assigned_consultor_id: eventFormData.assigned_consultor_id || null,
        assigned_mediador_id: eventFormData.assigned_mediador_id || null
      };
      await createDeadline(data);
      toast.success("Evento criado com sucesso");
      setIsCreateEventDialogOpen(false);
      fetchCalendarData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao criar evento");
    } finally {
      setFormLoading(false);
    }
  };

  const handleDeleteEvent = async (eventId) => {
    if (!window.confirm("Tem a certeza que deseja eliminar este evento?")) return;
    try {
      await deleteDeadline(eventId);
      toast.success("Evento eliminado");
      fetchCalendarData();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Erro ao eliminar evento");
    }
  };

  const getUserName = (userId) => {
    const user = users.find(u => u.id === userId);
    return user ? user.name : "-";
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
      <div className="space-y-6" data-testid="admin-dashboard">
        <div>
          <h1 className="text-2xl font-bold">Painel de Administração</h1>
          <p className="text-muted-foreground">Gestão completa do sistema</p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="border-border">
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                  <FileText className="h-6 w-6 text-blue-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{stats.total_processes || 0}</p>
                  <p className="text-sm text-muted-foreground">Total Processos</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-border">
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-emerald-100 dark:bg-emerald-900/30 rounded-lg">
                  <Users className="h-6 w-6 text-emerald-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{stats.total_users || 0}</p>
                  <p className="text-sm text-muted-foreground">Utilizadores</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-border">
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-orange-100 dark:bg-orange-900/30 rounded-lg">
                  <CalendarIcon className="h-6 w-6 text-orange-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{stats.pending_deadlines || 0}</p>
                  <p className="text-sm text-muted-foreground">Prazos Pendentes</p>
                </div>
              </div>
            </CardContent>
          </Card>
          <Card className="border-border">
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
                  <GitBranch className="h-6 w-6 text-purple-600" />
                </div>
                <div>
                  <p className="text-2xl font-bold">{workflowStatuses.length}</p>
                  <p className="text-sm text-muted-foreground">Estados</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Main Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList className="flex-wrap">
            <TabsTrigger value="overview" className="gap-2">
              <Eye className="h-4 w-4" />
              Visão Geral
            </TabsTrigger>
            <TabsTrigger value="calendar" className="gap-2">
              <CalendarIcon className="h-4 w-4" />
              Calendário
            </TabsTrigger>
            <TabsTrigger value="documents" className="gap-2">
              <FileText className="h-4 w-4" />
              Documentos
            </TabsTrigger>
            <TabsTrigger value="ai" className="gap-2">
              <Sparkles className="h-4 w-4" />
              Análise IA
            </TabsTrigger>
            <TabsTrigger value="clients" className="gap-2">
              <Search className="h-4 w-4" />
              Pesquisar Cliente
            </TabsTrigger>
          </TabsList>

          {/* Overview Tab */}
          <TabsContent value="overview" className="mt-6 space-y-6">
            <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Filter className="h-5 w-5" />
                  Filtros de Visualização
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Consultor</Label>
                    <Select value={consultorFilter} onValueChange={setConsultorFilter}>
                      <SelectTrigger><SelectValue placeholder="Todos os consultores" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos os consultores</SelectItem>
                        {consultors.map((c) => (<SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Intermediário</Label>
                    <Select value={mediadorFilter} onValueChange={setMediadorFilter}>
                      <SelectTrigger><SelectValue placeholder="Todos os intermediários" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos os intermediários</SelectItem>
                        {intermediarios.map((m) => (<SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg">Processos ({filteredProcesses.length})</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Cliente</TableHead>
                        <TableHead>Email</TableHead>
                        <TableHead>Estado</TableHead>
                        <TableHead>Consultor</TableHead>
                        <TableHead>Intermediário</TableHead>
                        <TableHead className="text-right">Ações</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredProcesses.length === 0 ? (
                        <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Nenhum processo encontrado</TableCell></TableRow>
                      ) : (
                        filteredProcesses.map((process) => (
                          <TableRow key={process.id}>
                            <TableCell className="font-medium">{process.client_name}</TableCell>
                            <TableCell>{process.client_email}</TableCell>
                            <TableCell>
                              <Badge className={`${getColorClass(workflowStatuses.find(s => s.name === process.status)?.color || "gray")} border`}>
                                {workflowStatuses.find(s => s.name === process.status)?.label || process.status}
                              </Badge>
                            </TableCell>
                            <TableCell>{getUserName(process.assigned_consultor_id)}</TableCell>
                            <TableCell>{getUserName(process.assigned_mediador_id)}</TableCell>
                            <TableCell className="text-right">
                              <Button variant="ghost" size="icon" onClick={() => navigate(`/process/${process.id}`)}><Eye className="h-4 w-4" /></Button>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Calendar Tab */}
          <TabsContent value="calendar" className="mt-6">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              <Card className="border-border lg:col-span-1">
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-lg">Filtros & Calendário</CardTitle>
                    <Button size="sm" onClick={() => openCreateEventDialog()}>
                      <Plus className="h-4 w-4 mr-1" />Evento
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label>Consultor</Label>
                    <Select value={consultorFilter} onValueChange={setConsultorFilter}>
                      <SelectTrigger><SelectValue placeholder="Todos" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos</SelectItem>
                        {consultors.map((c) => (<SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label>Intermediário</Label>
                    <Select value={mediadorFilter} onValueChange={setMediadorFilter}>
                      <SelectTrigger><SelectValue placeholder="Todos" /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">Todos</SelectItem>
                        {intermediarios.map((m) => (<SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="pt-4 border-t">
                    <Calendar
                      mode="single"
                      selected={selectedDate}
                      onSelect={(date) => date && setSelectedDate(date)}
                      className="rounded-md border"
                      modifiers={{ hasDeadline: datesWithDeadlines }}
                      modifiersStyles={{ hasDeadline: { backgroundColor: "rgb(254 202 202)", fontWeight: "bold" } }}
                    />
                  </div>
                </CardContent>
              </Card>

              <Card className="border-border lg:col-span-2">
                <CardHeader>
                  <CardTitle className="text-lg">
                    Prazos - {selectedDate.toLocaleDateString('pt-PT', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })}
                  </CardTitle>
                  <CardDescription>{deadlinesForDate.length} prazo(s) nesta data</CardDescription>
                </CardHeader>
                <CardContent>
                  {deadlinesForDate.length === 0 ? (
                    <div className="text-center py-8 text-muted-foreground">
                      <p>Nenhum prazo para esta data</p>
                      <Button variant="outline" className="mt-4" onClick={() => openCreateEventDialog(selectedDate)}>
                        <Plus className="h-4 w-4 mr-2" />Criar Evento
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {deadlinesForDate.map((deadline) => (
                        <div key={deadline.id} className="flex items-center justify-between p-4 bg-muted/30 rounded-lg">
                          <div className="space-y-1">
                            <p className="font-medium">{deadline.title}</p>
                            <p className="text-sm text-muted-foreground">
                              {deadline.client_name !== "Evento Geral" ? `Cliente: ${deadline.client_name}` : "Evento Geral"}
                            </p>
                            <div className="flex gap-2 mt-2 flex-wrap">
                              {deadline.assigned_consultor_id && (
                                <Badge variant="outline" className="text-xs bg-blue-50">Consultor: {getUserName(deadline.assigned_consultor_id)}</Badge>
                              )}
                              {deadline.assigned_mediador_id && (
                                <Badge variant="outline" className="text-xs bg-emerald-50">Mediador: {getUserName(deadline.assigned_mediador_id)}</Badge>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <Badge className={deadline.priority === "high" ? "bg-red-100 text-red-800" : deadline.priority === "medium" ? "bg-yellow-100 text-yellow-800" : "bg-green-100 text-green-800"}>
                              {deadline.priority === "high" ? "Alta" : deadline.priority === "medium" ? "Média" : "Baixa"}
                            </Badge>
                            {deadline.process_id && (
                              <Button variant="ghost" size="icon" onClick={() => navigate(`/process/${deadline.process_id}`)}>
                                <Eye className="h-4 w-4" />
                              </Button>
                            )}
                            <Button variant="ghost" size="icon" onClick={() => handleDeleteEvent(deadline.id)}>
                              <Trash2 className="h-4 w-4 text-destructive" />
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Documents Tab - Admin can see all document expiries */}
          <TabsContent value="documents" className="mt-6">
            <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg">Documentos a Expirar (Próximos 60 dias)</CardTitle>
                <CardDescription>Documentos de todos os clientes próximos da data de validade</CardDescription>
              </CardHeader>
              <CardContent>
                {upcomingExpiries.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
                    <p>Nenhum documento a expirar</p>
                  </div>
                ) : (
                  <div className="rounded-md border">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Documento</TableHead>
                          <TableHead>Cliente</TableHead>
                          <TableHead>Tipo</TableHead>
                          <TableHead>Data Expiração</TableHead>
                          <TableHead className="text-right">Ações</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {upcomingExpiries.map((doc) => (
                          <TableRow key={doc.id}>
                            <TableCell className="font-medium">{doc.document_name}</TableCell>
                            <TableCell>{doc.client_name}</TableCell>
                            <TableCell><Badge variant="outline">{doc.document_type}</Badge></TableCell>
                            <TableCell>{new Date(doc.expiry_date).toLocaleDateString('pt-PT')}</TableCell>
                            <TableCell className="text-right">
                              <Button variant="ghost" size="icon" onClick={() => navigate(`/process/${doc.process_id}`)}>
                                <Eye className="h-4 w-4" />
                              </Button>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* AI Tab - Admin can use AI analysis */}
          <TabsContent value="ai" className="mt-6">
            <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Sparkles className="h-5 w-5 text-purple-500" />
                  Análise de Documentos com IA
                </CardTitle>
                <CardDescription>
                  Use a IA para extrair dados de documentos automaticamente
                </CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  A funcionalidade de análise IA está disponível nos dashboards de Consultor e Mediador.
                  Como admin, pode aceder a todas as funcionalidades através da visualização de processos individuais.
                </p>
                <Button className="mt-4" onClick={() => setActiveTab("overview")}>
                  Ver Processos
                </Button>
              </CardContent>
            </Card>
          </TabsContent>


          {/* Clients Search Tab */}
          <TabsContent value="clients" className="mt-6">
            <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg">Pesquisar Cliente</CardTitle>
                <CardDescription>Encontre e visualize informações de clientes</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input 
                      placeholder="Pesquisar por nome, email ou telefone..." 
                      className="pl-10" 
                      value={searchTerm} 
                      onChange={(e) => setSearchTerm(e.target.value)} 
                    />
                  </div>

                  {searchTerm.length >= 2 ? (
                    <div className="rounded-md border">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Nome</TableHead>
                            <TableHead>Email</TableHead>
                            <TableHead>Telefone</TableHead>
                            <TableHead>Fase</TableHead>
                            <TableHead>Valor</TableHead>
                            <TableHead className="text-right">Ações</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {processes.filter(p => 
                            p.client_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            p.client_email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            p.client_phone?.includes(searchTerm)
                          ).map((process) => {
                            const status = workflowStatuses.find(s => s.name === process.status);
                            return (
                              <TableRow key={process.id} className="cursor-pointer hover:bg-muted/50" onClick={() => navigate(`/process/${process.id}`)}>
                                <TableCell className="font-medium">{process.client_name}</TableCell>
                                <TableCell>{process.client_email}</TableCell>
                                <TableCell>{process.client_phone || "-"}</TableCell>
                                <TableCell>
                                  <Badge className={`bg-${status?.color || 'gray'}-100 text-${status?.color || 'gray'}-800 border`}>
                                    {status?.label || process.status}
                                  </Badge>
                                </TableCell>
                                <TableCell>{process.property_value ? `€${process.property_value.toLocaleString('pt-PT')}` : "-"}</TableCell>
                                <TableCell className="text-right">
                                  <Button variant="ghost" size="icon" onClick={(e) => { e.stopPropagation(); navigate(`/process/${process.id}`); }}>
                                    <Eye className="h-4 w-4" />
                                  </Button>
                                </TableCell>
                              </TableRow>
                            );
                          })}
                          {processes.filter(p => 
                            p.client_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            p.client_email?.toLowerCase().includes(searchTerm.toLowerCase()) ||
                            p.client_phone?.includes(searchTerm)
                          ).length === 0 && (
                            <TableRow>
                              <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">
                                Nenhum cliente encontrado com "{searchTerm}"
                              </TableCell>
                            </TableRow>
                          )}
                        </TableBody>
                      </Table>
                    </div>
                  ) : (
                    <div className="text-center py-12 text-muted-foreground">
                      <Search className="h-12 w-12 mx-auto mb-4 opacity-50" />
                      <p>Digite pelo menos 2 caracteres para pesquisar</p>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Users Tab */}
          <TabsContent value="users" className="mt-6">
            <Card className="border-border">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-lg">Gestão de Utilizadores</CardTitle>
                    <CardDescription>Criar, editar e eliminar utilizadores</CardDescription>
                  </div>
                  <Dialog open={isCreateUserDialogOpen} onOpenChange={setIsCreateUserDialogOpen}>
                    <DialogTrigger asChild>
                      <Button data-testid="create-user-btn"><UserPlus className="h-4 w-4 mr-2" />Novo Utilizador</Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader><DialogTitle>Criar Novo Utilizador</DialogTitle></DialogHeader>
                      <form onSubmit={handleCreateUser} className="space-y-4">
                        <div className="space-y-2"><Label>Nome</Label><Input value={userFormData.name} onChange={(e) => setUserFormData({ ...userFormData, name: e.target.value })} required /></div>
                        <div className="space-y-2"><Label>Email</Label><Input type="email" value={userFormData.email} onChange={(e) => setUserFormData({ ...userFormData, email: e.target.value })} required /></div>
                        <div className="space-y-2"><Label>Password</Label><Input type="password" value={userFormData.password} onChange={(e) => setUserFormData({ ...userFormData, password: e.target.value })} required /></div>
                        <div className="space-y-2"><Label>Telefone</Label><Input value={userFormData.phone} onChange={(e) => setUserFormData({ ...userFormData, phone: e.target.value })} /></div>
                        <div className="space-y-2">
                          <Label>Perfil</Label>
                          <Select value={userFormData.role} onValueChange={(value) => setUserFormData({ ...userFormData, role: value })}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              <SelectItem value="cliente">Cliente</SelectItem>
                              <SelectItem value="consultor">Consultor</SelectItem>
                              <SelectItem value="mediador">Mediador</SelectItem>
                              <SelectItem value="admin">Administrador</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-2"><Label>Pasta OneDrive</Label><Input value={userFormData.onedrive_folder} onChange={(e) => setUserFormData({ ...userFormData, onedrive_folder: e.target.value })} placeholder="Nome da pasta no OneDrive" /></div>
                        <DialogFooter><Button type="submit" disabled={formLoading}>{formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar"}</Button></DialogFooter>
                      </form>
                    </DialogContent>
                  </Dialog>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col sm:flex-row gap-4 mb-4">
                  <div className="relative flex-1">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                    <Input placeholder="Pesquisar utilizador..." className="pl-10" value={userSearchTerm} onChange={(e) => setUserSearchTerm(e.target.value)} />
                  </div>
                  <Select value={roleFilter} onValueChange={setRoleFilter}>
                    <SelectTrigger className="w-full sm:w-48"><SelectValue placeholder="Filtrar por perfil" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Todos os perfis</SelectItem>
                      <SelectItem value="cliente">Cliente</SelectItem>
                      <SelectItem value="consultor">Consultor</SelectItem>
                      <SelectItem value="mediador">Mediador</SelectItem>
                      <SelectItem value="admin">Administrador</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div className="rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Nome</TableHead>
                        <TableHead>Email</TableHead>
                        <TableHead>Perfil</TableHead>
                        <TableHead>Status</TableHead>
                        <TableHead>Pasta OneDrive</TableHead>
                        <TableHead className="text-right">Ações</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {filteredUsers.length === 0 ? (
                        <TableRow><TableCell colSpan={6} className="text-center py-8 text-muted-foreground">Nenhum utilizador encontrado</TableCell></TableRow>
                      ) : (
                        filteredUsers.map((user) => (
                          <TableRow key={user.id}>
                            <TableCell className="font-medium">{user.name}</TableCell>
                            <TableCell>{user.email}</TableCell>
                            <TableCell><Badge className={`${roleColors[user.role]} border`}>{roleLabels[user.role]}</Badge></TableCell>
                            <TableCell>
                              <Badge variant={user.is_active ? "success" : "destructive"} className={user.is_active ? "bg-green-100 text-green-800" : "bg-red-100 text-red-800"}>
                                {user.is_active ? "Ativo" : "Inativo"}
                              </Badge>
                            </TableCell>
                            <TableCell className="font-mono text-sm">{user.onedrive_folder || "-"}</TableCell>
                            <TableCell className="text-right">
                              <Button 
                                variant="ghost" 
                                size="icon" 
                                onClick={() => handleToggleUserStatus(user.id, user.is_active)}
                                title={user.is_active ? "Desativar utilizador" : "Ativar utilizador"}
                              >
                                {user.is_active ? <UserX className="h-4 w-4 text-orange-600" /> : <UserCheck className="h-4 w-4 text-green-600" />}
                              </Button>
                              <Button variant="ghost" size="icon" onClick={() => openEditUserDialog(user)}><Edit className="h-4 w-4" /></Button>
                              <Button variant="ghost" size="icon" onClick={() => handleDeleteUser(user.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                            </TableCell>
                          </TableRow>
                        ))
                      )}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Workflow Tab */}
          <TabsContent value="workflow" className="mt-6">
            <Card className="border-border">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle className="text-lg">Estados do Fluxo de Processos</CardTitle>
                    <CardDescription>Configurar as fases dos processos</CardDescription>
                  </div>
                  <Dialog open={isCreateStatusDialogOpen} onOpenChange={setIsCreateStatusDialogOpen}>
                    <DialogTrigger asChild>
                      <Button data-testid="create-status-btn"><Plus className="h-4 w-4 mr-2" />Novo Estado</Button>
                    </DialogTrigger>
                    <DialogContent>
                      <DialogHeader><DialogTitle>Criar Novo Estado</DialogTitle></DialogHeader>
                      <form onSubmit={handleCreateStatus} className="space-y-4">
                        <div className="space-y-2"><Label>Nome (identificador)</Label><Input value={statusFormData.name} onChange={(e) => setStatusFormData({ ...statusFormData, name: e.target.value.toLowerCase().replace(/\s+/g, "_") })} placeholder="ex: documentos_pendentes" required /></div>
                        <div className="space-y-2"><Label>Label (exibição)</Label><Input value={statusFormData.label} onChange={(e) => setStatusFormData({ ...statusFormData, label: e.target.value })} placeholder="ex: Documentos Pendentes" required /></div>
                        <div className="space-y-2"><Label>Ordem</Label><Input type="number" value={statusFormData.order} onChange={(e) => setStatusFormData({ ...statusFormData, order: parseInt(e.target.value) || 1 })} min={1} required /></div>
                        <div className="space-y-2">
                          <Label>Cor</Label>
                          <Select value={statusFormData.color} onValueChange={(value) => setStatusFormData({ ...statusFormData, color: value })}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                              {statusColorOptions.map((color) => (
                                <SelectItem key={color.value} value={color.value}>
                                  <div className="flex items-center gap-2"><span className={`w-3 h-3 rounded-full ${color.class.split(" ")[0]}`} />{color.label}</div>
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        </div>
                        <div className="space-y-2"><Label>Descrição</Label><Input value={statusFormData.description} onChange={(e) => setStatusFormData({ ...statusFormData, description: e.target.value })} /></div>
                        <DialogFooter><Button type="submit" disabled={formLoading}>{formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar"}</Button></DialogFooter>
                      </form>
                    </DialogContent>
                  </Dialog>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {workflowStatuses.map((status) => (
                    <div key={status.id} className="flex items-center justify-between p-4 bg-muted/30 rounded-md">
                      <div className="flex items-center gap-4">
                        <span className="text-2xl font-bold text-muted-foreground font-mono w-8">{status.order}</span>
                        <div>
                          <div className="flex items-center gap-2">
                            <Badge className={`${getColorClass(status.color)} border`}>{status.label}</Badge>
                            {status.is_default && <Badge variant="outline" className="text-xs">Padrão</Badge>}
                          </div>
                          <p className="text-xs text-muted-foreground font-mono mt-1">{status.name}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon" onClick={() => openEditStatusDialog(status)}><Edit className="h-4 w-4" /></Button>
                        {!status.is_default && <Button variant="ghost" size="icon" onClick={() => handleDeleteStatus(status.id)}><Trash2 className="h-4 w-4 text-destructive" /></Button>}
                      </div>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Settings Tab */}
          <TabsContent value="settings" className="mt-6">
            <Card className="border-border">
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2"><FolderOpen className="h-5 w-5" />Integração OneDrive</CardTitle>
                <CardDescription>Configuração de acesso aos documentos</CardDescription>
              </CardHeader>
              <CardContent>
                {oneDriveStatus?.configured ? (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-emerald-600"><CheckCircle className="h-5 w-5" /><span className="font-medium">OneDrive configurado</span></div>
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div><p className="text-muted-foreground">Tenant ID</p><p className="font-mono">{oneDriveStatus.tenant_id}</p></div>
                      <div><p className="text-muted-foreground">Client ID</p><p className="font-mono">{oneDriveStatus.client_id}</p></div>
                    </div>
                  </div>
                ) : (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 text-red-600"><XCircle className="h-5 w-5" /><span className="font-medium">OneDrive não configurado</span></div>
                    <p className="text-sm text-muted-foreground">Para configurar o OneDrive, adicione as variáveis de ambiente no backend.</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>

        {/* Create Event Dialog */}
        <Dialog open={isCreateEventDialogOpen} onOpenChange={setIsCreateEventDialogOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader><DialogTitle>Criar Novo Evento/Prazo</DialogTitle></DialogHeader>
            <form onSubmit={handleCreateEvent} className="space-y-4">
              <div className="space-y-2">
                <Label>Título *</Label>
                <Input value={eventFormData.title} onChange={(e) => setEventFormData({ ...eventFormData, title: e.target.value })} placeholder="Ex: Reunião com cliente" required />
              </div>
              <div className="space-y-2">
                <Label>Descrição</Label>
                <Textarea value={eventFormData.description} onChange={(e) => setEventFormData({ ...eventFormData, description: e.target.value })} placeholder="Detalhes do evento..." rows={2} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Data *</Label>
                  <Input type="date" value={eventFormData.due_date} onChange={(e) => setEventFormData({ ...eventFormData, due_date: e.target.value })} />
                </div>
                <div className="space-y-2">
                  <Label>Prioridade</Label>
                  <Select value={eventFormData.priority} onValueChange={(v) => setEventFormData({ ...eventFormData, priority: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="low">Baixa</SelectItem>
                      <SelectItem value="medium">Média</SelectItem>
                      <SelectItem value="high">Alta</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="space-y-2">
                <Label>Processo (opcional)</Label>
                <Select value={eventFormData.process_id || "none"} onValueChange={(v) => setEventFormData({ ...eventFormData, process_id: v === "none" ? "" : v })}>
                  <SelectTrigger><SelectValue placeholder="Selecione um processo" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Nenhum (evento geral)</SelectItem>
                    {processes.map((p) => (<SelectItem key={p.id} value={p.id}>{p.client_name}</SelectItem>))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label>Atribuir Consultor</Label>
                  <Select value={eventFormData.assigned_consultor_id || "none"} onValueChange={(v) => setEventFormData({ ...eventFormData, assigned_consultor_id: v === "none" ? "" : v })}>
                    <SelectTrigger><SelectValue placeholder="Nenhum" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Nenhum</SelectItem>
                      {consultors.map((c) => (<SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Atribuir Intermediário</Label>
                  <Select value={eventFormData.assigned_mediador_id || "none"} onValueChange={(v) => setEventFormData({ ...eventFormData, assigned_mediador_id: v === "none" ? "" : v })}>
                    <SelectTrigger><SelectValue placeholder="Nenhum" /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">Nenhum</SelectItem>
                      {intermediarios.map((m) => (<SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <DialogFooter>
                <Button type="submit" disabled={formLoading}>
                  {formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar Evento"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        {/* Edit User Dialog */}
        <Dialog open={isEditUserDialogOpen} onOpenChange={setIsEditUserDialogOpen}>
          <DialogContent>
            <DialogHeader><DialogTitle>Editar Utilizador</DialogTitle></DialogHeader>
            <form onSubmit={handleEditUser} className="space-y-4">
              <div className="space-y-2"><Label>Nome</Label><Input value={userFormData.name} onChange={(e) => setUserFormData({ ...userFormData, name: e.target.value })} required /></div>
              <div className="space-y-2"><Label>Email</Label><Input type="email" value={userFormData.email} disabled className="bg-muted" /></div>
              <div className="space-y-2"><Label>Telefone</Label><Input value={userFormData.phone} onChange={(e) => setUserFormData({ ...userFormData, phone: e.target.value })} /></div>
              <div className="space-y-2">
                <Label>Perfil</Label>
                <Select value={userFormData.role} onValueChange={(value) => setUserFormData({ ...userFormData, role: value })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="cliente">Cliente</SelectItem>
                    <SelectItem value="consultor">Consultor</SelectItem>
                    <SelectItem value="mediador">Mediador</SelectItem>
                    <SelectItem value="admin">Administrador</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Pasta OneDrive</Label><Input value={userFormData.onedrive_folder} onChange={(e) => setUserFormData({ ...userFormData, onedrive_folder: e.target.value })} /></div>
              <DialogFooter><Button type="submit" disabled={formLoading}>{formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Guardar"}</Button></DialogFooter>
            </form>
          </DialogContent>
        </Dialog>

        {/* Edit Status Dialog */}
        <Dialog open={isEditStatusDialogOpen} onOpenChange={setIsEditStatusDialogOpen}>
          <DialogContent>
            <DialogHeader><DialogTitle>Editar Estado</DialogTitle></DialogHeader>
            <form onSubmit={handleEditStatus} className="space-y-4">
              <div className="space-y-2"><Label>Nome (identificador)</Label><Input value={statusFormData.name} disabled className="bg-muted font-mono" /></div>
              <div className="space-y-2"><Label>Label (exibição)</Label><Input value={statusFormData.label} onChange={(e) => setStatusFormData({ ...statusFormData, label: e.target.value })} required /></div>
              <div className="space-y-2"><Label>Ordem</Label><Input type="number" value={statusFormData.order} onChange={(e) => setStatusFormData({ ...statusFormData, order: parseInt(e.target.value) || 1 })} min={1} required /></div>
              <div className="space-y-2">
                <Label>Cor</Label>
                <Select value={statusFormData.color} onValueChange={(value) => setStatusFormData({ ...statusFormData, color: value })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {statusColorOptions.map((color) => (
                      <SelectItem key={color.value} value={color.value}>
                        <div className="flex items-center gap-2"><span className={`w-3 h-3 rounded-full ${color.class.split(" ")[0]}`} />{color.label}</div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label>Descrição</Label><Input value={statusFormData.description} onChange={(e) => setStatusFormData({ ...statusFormData, description: e.target.value })} /></div>
              <DialogFooter><Button type="submit" disabled={formLoading}>{formLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Guardar"}</Button></DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </DashboardLayout>
  );
};

export default AdminDashboard;
