/**
 * VisitsPage — Quadro de Visitas
 *
 * Página dedicada à gestão de Visitas a Imóveis.
 * Kanban Board com 3 colunas: Agendadas, Concluídas, Canceladas.
 * Cada cartão exibe: Data/Hora, Cliente, Imóvel, Consultor.
 *
 * Funcionalidades:
 * - Kanban Board com drag-and-drop visual (click para mover de coluna)
 * - Agendar nova visita (modal com seleção de imóvel, cliente, data/hora)
 * - Filtrar por consultor e data
 * - Alterar estado da visita (Agendada → Concluída/Cancelada)
 *
 * @route /visitas
 */
import { useState, useEffect, useCallback, useMemo } from "react";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Textarea } from "../components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import {
  Calendar as CalendarIcon,
  Clock,
  MapPin,
  User,
  Building2,
  Plus,
  CheckCircle2,
  XCircle,
  CalendarClock,
  Loader2,
  Search,
  Filter,
  ChevronRight,
  Users,
  ArrowRight,
  Inbox,
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO, isToday, isTomorrow, isPast } from "date-fns";
import { pt } from "date-fns/locale";
import { hasAnyRole, STAFF_ROLES } from "../utils/roleUtils";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

// ── Status config ──
const STATUS_CONFIG = {
  solicitada: {
    label: "Pedidos do Portal",
    color: "bg-violet-100 text-violet-800 border-violet-200",
    badge: "bg-violet-500 text-white",
    icon: Inbox,
    emptyText: "Nenhum pedido do portal",
  },
  agendada: {
    label: "Agendadas",
    color: "bg-amber-100 text-amber-800 border-amber-200",
    badge: "bg-amber-500 text-white",
    icon: CalendarClock,
    emptyText: "Nenhuma visita agendada",
  },
  concluida: {
    label: "Concluídas",
    color: "bg-emerald-100 text-emerald-800 border-emerald-200",
    badge: "bg-emerald-500 text-white",
    icon: CheckCircle2,
    emptyText: "Nenhuma visita concluída",
  },
  cancelada: {
    label: "Canceladas",
    color: "bg-red-100 text-red-800 border-red-200",
    badge: "bg-red-500 text-white",
    icon: XCircle,
    emptyText: "Nenhuma visita cancelada",
  },
};

// ── Format date helper ──
const formatVisitDate = (isoDate) => {
  if (!isoDate) return "—";
  try {
    const date = parseISO(isoDate);
    if (isToday(date)) return `Hoje, ${format(date, "HH:mm")}`;
    if (isTomorrow(date)) return `Amanhã, ${format(date, "HH:mm")}`;
    return format(date, "dd MMM yyyy, HH:mm", { locale: pt });
  } catch {
    return isoDate;
  }
};

const isVisitPast = (isoDate) => {
  if (!isoDate) return false;
  try {
    return isPast(parseISO(isoDate));
  } catch {
    return false;
  }
};

// ════════════════════════════════════════════════════════════════
// VISIT CARD — Cartão individual de visita
// ════════════════════════════════════════════════════════════════
function VisitCard({ visit, onStatusChange, onEdit, onSchedule }) {
  const status = visit.status || "agendada";
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.agendada;
  const past = isVisitPast(visit.scheduled_date) && status === "agendada";

  return (
    <Card className={`group hover:shadow-md transition-all ${past ? "border-amber-300 border-dashed" : ""}`}>
      <CardContent className="p-3 space-y-2">
        {/* Date & Time */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
            <Clock className="h-3.5 w-3.5 text-amber-600" />
            {formatVisitDate(visit.scheduled_date)}
          </div>
          <Badge className={`text-[9px] px-1.5 py-0 ${config.badge}`}>
            {config.label.slice(0, -1)}
          </Badge>
          {visit.source === 'portal_client' && (
            <span className="text-[9px] px-1.5 py-0 rounded-full bg-emerald-100 text-emerald-700 border border-emerald-200">
              Sugerido pelo Cliente
            </span>
          )}
        </div>

        {/* Property */}
        <div className="flex items-start gap-2">
          {visit.property_photo ? (
            <img src={visit.property_photo} alt="" className="h-10 w-10 rounded-lg object-cover shrink-0" onError={(e) => { e.target.style.display = 'none'; }} />
          ) : (
            <Building2 className="h-4 w-4 text-teal-600 mt-0.5 shrink-0" />
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium truncate">{visit.property_title || "Imóvel"}</p>
            {visit.property_address && (
              <p className="text-[11px] text-muted-foreground truncate">
                <MapPin className="h-3 w-3 inline mr-0.5" />
                {[visit.property_address?.municipality, visit.property_address?.district]
                  .filter(Boolean)
                  .join(", ")}
              </p>
            )}
            {visit.scraped_data?.price && (
              <p className="text-[11px] font-semibold text-amber-700 truncate">
                {typeof visit.scraped_data.price === 'number' 
                  ? new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(visit.scraped_data.price)
                  : visit.scraped_data.price}
              </p>
            )}
            {visit.scraped_data?.typology && (
              <p className="text-[10px] text-muted-foreground">{visit.scraped_data.typology}</p>
            )}
          </div>
        </div>

        {/* Client */}
        <div className="flex items-center gap-2">
          <User className="h-4 w-4 text-purple-500 shrink-0" />
          <span className="text-xs text-muted-foreground truncate">{visit.client_name || "Cliente"}</span>
        </div>

        {/* Consultor */}
        <div className="flex items-center gap-2">
          <Users className="h-4 w-4 text-blue-500 shrink-0" />
          <span className="text-xs text-muted-foreground truncate">{visit.consultor_name || "Consultor"}</span>
        </div>

        {/* Notes */}
        {visit.notes && (
          <p className="text-[11px] text-muted-foreground italic truncate mt-1">{visit.notes}</p>
        )}

        {/* Past warning */}
        {past && (
          <div className="flex items-center gap-1 text-[10px] text-amber-600 bg-amber-50 rounded px-1.5 py-0.5">
            <Clock className="h-3 w-3" />
            Data passada — marque como concluída ou reagende
          </div>
        )}

        {/* Actions */}
        {status === "solicitada" && (
          <div className="flex gap-1.5 pt-1 border-t border-border/50">
            <Button
              size="sm"
              className="flex-1 h-7 text-[11px] gap-1 bg-amber-600 hover:bg-amber-700 text-white"
              onClick={() => onSchedule && onSchedule(visit)}
            >
              <CalendarClock className="h-3 w-3" />
              Agendar
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="flex-1 h-7 text-[11px] gap-1 text-red-700 border-red-300 hover:bg-red-50"
              onClick={() => onStatusChange(visit.id, "cancelada")}
            >
              <XCircle className="h-3 w-3" />
              Recusar
            </Button>
          </div>
        )}
        {status === "agendada" && (
          <div className="flex gap-1.5 pt-1 border-t border-border/50">
            <Button
              size="sm"
              variant="outline"
              className="flex-1 h-7 text-[11px] gap-1 text-emerald-700 border-emerald-300 hover:bg-emerald-50"
              onClick={() => onStatusChange(visit.id, "concluida")}
            >
              <CheckCircle2 className="h-3 w-3" />
              Concluída
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="flex-1 h-7 text-[11px] gap-1 text-red-700 border-red-300 hover:bg-red-50"
              onClick={() => onStatusChange(visit.id, "cancelada")}
            >
              <XCircle className="h-3 w-3" />
              Cancelar
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ════════════════════════════════════════════════════════════════
// KANBAN COLUMN — Coluna do Quadro
// ════════════════════════════════════════════════════════════════
function KanbanColumn({ status, visits, onStatusChange, onEdit, onSchedule }) {
  const config = STATUS_CONFIG[status];
  const Icon = config.icon;

  return (
    <div className="flex-1 min-w-[300px]">
      {/* Column header */}
      <div className={`rounded-t-xl p-3 border ${config.color} flex items-center justify-between`}>
        <div className="flex items-center gap-2">
          <Icon className="h-4 w-4" />
          <h3 className="font-bold text-sm">{config.label}</h3>
        </div>
        <Badge variant="outline" className="text-xs bg-white/60">
          {visits.length}
        </Badge>
      </div>

      {/* Cards area */}
      <div className="bg-gray-50/50 dark:bg-gray-900/20 border border-t-0 rounded-b-xl p-2 space-y-2 min-h-[200px] max-h-[calc(100vh-320px)] overflow-y-auto">
        {visits.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <Icon className="h-8 w-8 text-muted-foreground/30 mb-2" />
            <p className="text-xs text-muted-foreground">{config.emptyText}</p>
          </div>
        ) : (
          visits.map((visit) => (
            <VisitCard
              key={visit.id}
              visit={visit}
              onStatusChange={onStatusChange}
              onEdit={onEdit}
              onSchedule={onSchedule}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════
// SCHEDULE VISIT DIALOG — Modal para agendar visita
// ════════════════════════════════════════════════════════════════
function ScheduleVisitDialog({ open, onOpenChange, onSuccess, properties, processes, users }) {
  const { user, token } = useAuth();
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    property_id: "",
    client_id: "",
    scheduled_date: "",
    consultor_id: "",
    notes: "",
  });

  const handleSubmit = async () => {
    if (!form.property_id || !form.client_id || !form.scheduled_date) {
      toast.error("Preencha imóvel, cliente e data/hora");
      return;
    }
    setSaving(true);
    try {
      const response = await fetch(`${API_URL}/api/visits`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          ...form,
          consultor_id: form.consultor_id || user?.id,
        }),
      });
      if (response.ok) {
        toast.success("Visita agendada com sucesso!");
        setForm({ property_id: "", client_id: "", scheduled_date: "", consultor_id: "", notes: "" });
        onOpenChange(false);
        if (onSuccess) onSuccess();
      } else {
        const err = await response.json();
        toast.error(err.detail || "Erro ao agendar visita");
      }
    } catch {
      toast.error("Erro de ligação ao servidor");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarClock className="h-5 w-5 text-amber-600" />
            Agendar Visita
          </DialogTitle>
          <DialogDescription>
            Agende uma visita a um imóvel para um cliente.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Property select */}
          <div>
            <Label className="text-sm font-medium">Imóvel *</Label>
            <Select
              value={form.property_id}
              onValueChange={(v) => setForm((f) => ({ ...f, property_id: v }))}
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Selecionar imóvel..." />
              </SelectTrigger>
              <SelectContent className="max-h-64">
                {properties.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    <span className="truncate">{p.title || "Sem título"}</span>
                    {p.financials?.asking_price && (
                      <span className="ml-2 text-muted-foreground text-xs">
                        {new Intl.NumberFormat("pt-PT", { style: "currency", currency: "EUR" }).format(p.financials.asking_price)}
                      </span>
                    )}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Client select */}
          <div>
            <Label className="text-sm font-medium">Cliente (Processo) *</Label>
            <Select
              value={form.client_id}
              onValueChange={(v) => setForm((f) => ({ ...f, client_id: v }))}
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Selecionar cliente..." />
              </SelectTrigger>
              <SelectContent className="max-h-64">
                {processes.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.client_name || "Sem nome"} — {p.process_type || "Processo"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Date/Time */}
          <div>
            <Label className="text-sm font-medium">Data e Hora *</Label>
            <Input
              type="datetime-local"
              className="mt-1"
              value={form.scheduled_date}
              onChange={(e) => setForm((f) => ({ ...f, scheduled_date: e.target.value }))}
            />
          </div>

          {/* Consultor (optional) */}
          <div>
            <Label className="text-sm font-medium">Consultor</Label>
            <Select
              value={form.consultor_id}
              onValueChange={(v) => setForm((f) => ({ ...f, consultor_id: v }))}
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Eu próprio (padrão)" />
              </SelectTrigger>
              <SelectContent className="max-h-48">
                {users.map((u) => (
                  <SelectItem key={u.id} value={u.id}>
                    {u.name || "Utilizador"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Notes */}
          <div>
            <Label className="text-sm font-medium">Notas</Label>
            <Textarea
              className="mt-1"
              rows={2}
              placeholder="Notas adicionais..."
              value={form.notes}
              onChange={(e) => setForm((f) => ({ ...f, notes: e.target.value }))}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={saving || !form.property_id || !form.client_id || !form.scheduled_date}
            className="gap-1.5 bg-amber-600 hover:bg-amber-700 text-white"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarClock className="h-4 w-4" />}
            Agendar Visita
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ════════════════════════════════════════════════════════════════
// VISITS PAGE — Página Principal
// ════════════════════════════════════════════════════════════════
function ScheduleFromPortalDialog({ open, onOpenChange, visit, onSuccess }) {
  const { user, token } = useAuth();
  const [saving, setSaving] = useState(false);
  const [scheduledDate, setScheduledDate] = useState("");
  const [consultorNotes, setConsultorNotes] = useState("");

  const handleSubmit = async () => {
    if (!scheduledDate) {
      toast.error("Escolha a data e hora da visita");
      return;
    }
    setSaving(true);
    try {
      const response = await fetch(`${API_URL}/api/visits/${visit.id}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          status: "agendada",
          scheduled_date: scheduledDate,
          notes: visit.notes ? `${visit.notes}\n[Consultor]: ${consultorNotes}` : consultorNotes,
          consultor_id: user?.id,
        }),
      });
      if (response.ok) {
        toast.success("Visita agendada com sucesso!");
        setScheduledDate("");
        setConsultorNotes("");
        onOpenChange(false);
        if (onSuccess) onSuccess();
      } else {
        const err = await response.json();
        toast.error(err.detail || "Erro ao agendar visita");
      }
    } catch {
      toast.error("Erro de ligação ao servidor");
    } finally {
      setSaving(false);
    }
  };

  if (!visit) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarClock className="h-5 w-5 text-amber-600" />
            Agendar Visita Pedida pelo Cliente
          </DialogTitle>
          <DialogDescription>
            O cliente pediu uma visita a este imóvel. Escolha a data e hora.
          </DialogDescription>
        </DialogHeader>

        {/* Property preview */}
        <div className="flex gap-3 p-3 bg-violet-50 rounded-xl border border-violet-100">
          {visit.property_photo && (
            <img src={visit.property_photo} alt="" className="h-16 w-16 rounded-lg object-cover shrink-0" />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold truncate">{visit.property_title || "Imóvel"}</p>
            {visit.scraped_data?.price && (
              <p className="text-xs font-semibold text-amber-700">
                {typeof visit.scraped_data.price === 'number'
                  ? new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(visit.scraped_data.price)
                  : visit.scraped_data.price}
              </p>
            )}
            {visit.scraped_data?.typology && (
              <p className="text-xs text-muted-foreground">{visit.scraped_data.typology}</p>
            )}
            {visit.client_name && (
              <p className="text-xs text-muted-foreground mt-1">
                <User className="h-3 w-3 inline mr-0.5" />
                {visit.client_name}
              </p>
            )}
          </div>
        </div>

        <div className="space-y-4">
          <div>
            <Label className="text-sm font-medium">Data e Hora *</Label>
            <Input
              type="datetime-local"
              className="mt-1"
              value={scheduledDate}
              onChange={(e) => setScheduledDate(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-sm font-medium">Notas do Consultor</Label>
            <Textarea
              className="mt-1"
              rows={2}
              placeholder="Notas adicionais para o cliente..."
              value={consultorNotes}
              onChange={(e) => setConsultorNotes(e.target.value)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={saving || !scheduledDate}
            className="gap-1.5 bg-amber-600 hover:bg-amber-700 text-white"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <CalendarClock className="h-4 w-4" />}
            Confirmar Agendamento
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const VisitsPage = () => {
  const { user, token } = useAuth();
  const [visits, setVisits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showScheduleDialog, setShowScheduleDialog] = useState(false);
  const [properties, setProperties] = useState([]);
  const [processes, setProcesses] = useState([]);
  const [users, setUsers] = useState([]);
  const [filterConsultor, setFilterConsultor] = useState("");
  const [searchTerm, setSearchTerm] = useState("");
  const [schedulingVisit, setSchedulingVisit] = useState(null);

  // Fetch visits kanban
  const fetchVisits = useCallback(async () => {
    try {
      let url = `${API_URL}/api/visits/kanban`;
      const params = new URLSearchParams();
      if (filterConsultor) params.append("consultor_id", filterConsultor);
      if (params.toString()) url += `?${params.toString()}`;

      const response = await fetch(url, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        // Flatten for search, keep kanban structure
        setVisits(data);
      }
    } catch (error) {
      console.error("Erro ao carregar visitas:", error);
    } finally {
      setLoading(false);
    }
  }, [token, filterConsultor]);

  // Fetch properties, processes, users for the schedule dialog
  const fetchFormData = useCallback(async () => {
    try {
      const [propsRes, procsRes, usersRes] = await Promise.all([
        fetch(`${API_URL}/api/properties?status=disponivel`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API_URL}/api/processes`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API_URL}/api/admin/users`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ]);

      if (propsRes.ok) {
        const data = await propsRes.json();
        setProperties(Array.isArray(data) ? data : []);
      }
      if (procsRes.ok) {
        const data = await procsRes.json();
        setProcesses(Array.isArray(data) ? data : data.processes || []);
      }
      if (usersRes.ok) {
        const data = await usersRes.json();
        setUsers(Array.isArray(data) ? data.filter((u) => u.is_active !== false) : []);
      }
    } catch (error) {
      console.error("Erro ao carregar dados do formulário:", error);
    }
  }, [token]);

  useEffect(() => {
    fetchVisits();
    fetchFormData();
  }, [fetchVisits, fetchFormData]);

  const handleSchedule = useCallback((visit) => {
    setSchedulingVisit(visit);
  }, []);

  // Status change handler
  const handleStatusChange = async (visitId, newStatus) => {
    try {
      const response = await fetch(`${API_URL}/api/visits/${visitId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ status: newStatus }),
      });
      if (response.ok) {
        const statusLabels = { concluida: "concluída", cancelada: "cancelada", agendada: "agendada" };
        toast.success(`Visita marcada como ${statusLabels[newStatus] || newStatus}`);
        fetchVisits();
      } else {
        toast.error("Erro ao alterar estado da visita");
      }
    } catch {
      toast.error("Erro de ligação ao servidor");
    }
  };

  // Filter visits by search term
  const filteredKanban = useMemo(() => {
    if (!searchTerm) return visits;

    const term = searchTerm.toLowerCase();
    const filterList = (list) =>
      (list || []).filter(
        (v) =>
          (v.property_title || "").toLowerCase().includes(term) ||
          (v.client_name || "").toLowerCase().includes(term) ||
          (v.consultor_name || "").toLowerCase().includes(term) ||
          (v.notes || "").toLowerCase().includes(term)
      );

    return {
      solicitadas: filterList(visits.solicitadas),
      agendadas: filterList(visits.agendadas),
      concluidas: filterList(visits.concluidas),
      canceladas: filterList(visits.canceladas),
      total: visits.total,
    };
  }, [visits, searchTerm]);

  // Stats
  const stats = useMemo(() => ({
    total: filteredKanban.total || 0,
    solicitadas: (filteredKanban.solicitadas || []).length,
    agendadas: (filteredKanban.agendadas || []).length,
    concluidas: (filteredKanban.concluidas || []).length,
    canceladas: (filteredKanban.canceladas || []).length,
  }), [filteredKanban]);

  return (
    <DashboardLayout title="Quadro de Visitas">
      <div className="space-y-6">
        {/* ── Header ── */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <CalendarClock className="h-7 w-7 text-amber-600" />
              Quadro de Visitas
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Gerir e acompanhar visitas a imóveis
            </p>
          </div>
          <Button
            className="gap-1.5 bg-amber-600 hover:bg-amber-700 text-white"
            onClick={() => setShowScheduleDialog(true)}
          >
            <Plus className="h-4 w-4" />
            Agendar Visita
          </Button>
        </div>

        {/* ── Stats Cards ── */}
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <Card className="border-l-4 border-l-gray-400">
            <CardContent className="p-3">
              <p className="text-xs text-muted-foreground">Total</p>
              <p className="text-2xl font-bold">{stats.total}</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-violet-500">
            <CardContent className="p-3">
              <p className="text-xs text-muted-foreground">Pedidos Portal</p>
              <p className="text-2xl font-bold text-violet-600">{stats.solicitadas}</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-amber-500">
            <CardContent className="p-3">
              <p className="text-xs text-muted-foreground">Agendadas</p>
              <p className="text-2xl font-bold text-amber-600">{stats.agendadas}</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-emerald-500">
            <CardContent className="p-3">
              <p className="text-xs text-muted-foreground">Concluídas</p>
              <p className="text-2xl font-bold text-emerald-600">{stats.concluidas}</p>
            </CardContent>
          </Card>
          <Card className="border-l-4 border-l-red-500">
            <CardContent className="p-3">
              <p className="text-xs text-muted-foreground">Canceladas</p>
              <p className="text-2xl font-bold text-red-600">{stats.canceladas}</p>
            </CardContent>
          </Card>
        </div>

        {/* ── Filters ── */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Pesquisar por imóvel, cliente ou consultor..."
              className="pl-9"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
          </div>
          <Select value={filterConsultor} onValueChange={setFilterConsultor}>
            <SelectTrigger className="w-[200px]">
              <Filter className="h-4 w-4 mr-2 text-muted-foreground" />
              <SelectValue placeholder="Todos os consultores" />
            </SelectTrigger>
            <SelectContent className="max-h-48">
              <SelectItem value="all">Todos</SelectItem>
              {users.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.name || "Utilizador"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* ── Kanban Board ── */}
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Loader2 className="h-10 w-10 animate-spin text-amber-500" />
            <span className="ml-3 text-muted-foreground">A carregar visitas...</span>
          </div>
        ) : (
          <div className="flex gap-4 overflow-x-auto pb-4" style={{ scrollbarWidth: "thin" }}>
            <KanbanColumn
              status="solicitada"
              visits={filteredKanban.solicitadas || []}
              onStatusChange={handleStatusChange}
              onSchedule={handleSchedule}
            />
            <KanbanColumn
              status="agendada"
              visits={filteredKanban.agendadas || []}
              onStatusChange={handleStatusChange}
            />
            <KanbanColumn
              status="concluida"
              visits={filteredKanban.concluidas || []}
              onStatusChange={handleStatusChange}
            />
            <KanbanColumn
              status="cancelada"
              visits={filteredKanban.canceladas || []}
              onStatusChange={handleStatusChange}
            />
          </div>
        )}
      </div>

      {/* Schedule Visit Dialog */}
      <ScheduleVisitDialog
        open={showScheduleDialog}
        onOpenChange={setShowScheduleDialog}
        onSuccess={fetchVisits}
        properties={properties}
        processes={processes}
        users={users}
      />

      {/* Schedule from Portal Dialog */}
      <ScheduleFromPortalDialog
        open={!!schedulingVisit}
        onOpenChange={(v) => { if (!v) setSchedulingVisit(null); }}
        visit={schedulingVisit}
        onSuccess={fetchVisits}
      />
    </DashboardLayout>
  );
};

export default VisitsPage;
