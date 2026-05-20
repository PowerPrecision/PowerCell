/**
 * VisitsPage — Quadro de Visitas
 *
 * Página dedicada à gestão de Visitas a Imóveis.
 * Kanban Board com 4 colunas: Pedidos Portal, Agendadas, Concluídas, Canceladas.
 *
 * v2 — Enriquecido com dados do Scraper:
 * - Cartões mostram: Nome, Preço, Morada, Tipologia, Foto, Link fonte
 * - Botão 'Criar Visita' (renomeado de 'Agendar') com campo URL opcional
 * - Scraper invocado em background quando URL é preenchida
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
  ExternalLink,
  Home,
  Euro,
  Link2,
  Sparkles,
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

// ── Format price helper ──
const formatPrice = (price) => {
  if (!price) return null;
  if (typeof price === 'number') {
    return new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(price);
  }
  return String(price);
};

// ════════════════════════════════════════════════════════════════
// VISIT CARD — Cartão individual de visita (v2 com dados do scraper)
// ════════════════════════════════════════════════════════════════
function VisitCard({ visit, onStatusChange, onEdit, onSchedule }) {
  const status = visit.status || "agendada";
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.agendada;
  const past = isVisitPast(visit.scheduled_date) && status === "agendada";

  // Dados do scraper (para visitas do portal ou criadas com URL)
  const scraped = visit.scraped_data || {};
  const scrapedUrl = visit.scraped_url;
  const propertyTitle = visit.property_title || scraped.title || "Imóvel";
  const propertyPhoto = visit.property_photo || scraped.photo_url;
  const propertyPrice = visit.scraped_price || scraped.price;
  const propertyTypology = visit.scraped_typology || scraped.typology;
  const propertyLocation = visit.property_address?.municipality || scraped.location || "";
  const propertyAddress = [
    visit.property_address?.street,
    visit.property_address?.municipality || scraped.location,
    visit.property_address?.district,
  ].filter(Boolean).join(", ") || scraped.location || "";
  const sourceName = scraped.source;
  const sourceUrl = scrapedUrl || scraped.url;

  return (
    <Card className={`group hover:shadow-md transition-all ${past ? "border-amber-300 border-dashed" : ""}`}>
      <CardContent className="p-3 space-y-2">
        {/* Date & Time + Source Badge */}
        <div className="flex items-center justify-between gap-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground min-w-0">
            <Clock className="h-3.5 w-3.5 text-amber-600 shrink-0" />
            <span className="truncate">{formatVisitDate(visit.scheduled_date)}</span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {visit.source === 'portal_client' && (
              <span className="text-[9px] px-1.5 py-0 rounded-full bg-emerald-100 text-emerald-700 border border-emerald-200">
                Cliente
              </span>
            )}
            <Badge className={`text-[9px] px-1.5 py-0 ${config.badge}`}>
              {config.label.slice(0, -1)}
            </Badge>
          </div>
        </div>

        {/* Property Info — Enriquecido com dados do scraper */}
        <div className="flex items-start gap-2">
          {propertyPhoto ? (
            <img
              src={propertyPhoto}
              alt={propertyTitle}
              className="h-12 w-12 rounded-lg object-cover shrink-0 border border-gray-100"
              onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling && (e.target.nextSibling.style.display = 'flex'); }}
            />
          ) : (
            <div className="h-12 w-12 rounded-lg bg-teal-50 flex items-center justify-center shrink-0">
              <Building2 className="h-5 w-5 text-teal-500" />
            </div>
          )}
          <div className="min-w-0 flex-1">
            {/* Nome do Imóvel */}
            <p className="text-sm font-medium truncate">{propertyTitle}</p>

            {/* Preço */}
            {propertyPrice && (
              <p className="text-[11px] font-semibold text-amber-700">
                <Euro className="h-3 w-3 inline mr-0.5" />
                {formatPrice(propertyPrice)}
              </p>
            )}

            {/* Tipologia */}
            {propertyTypology && (
              <p className="text-[10px] text-muted-foreground">
                <Home className="h-3 w-3 inline mr-0.5" />
                {propertyTypology}
              </p>
            )}

            {/* Morada */}
            {propertyAddress && (
              <p className="text-[10px] text-muted-foreground truncate">
                <MapPin className="h-3 w-3 inline mr-0.5" />
                {propertyAddress}
              </p>
            )}

            {/* Link para fonte original */}
            {sourceUrl && (
              <a
                href={sourceUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[10px] text-teal-600 hover:text-teal-800 hover:underline inline-flex items-center gap-0.5 mt-0.5"
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLink className="h-2.5 w-2.5" />
                {sourceName || 'Ver fonte'}
              </a>
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

        {/* Scraper pending indicator */}
        {visit.scraper_status === "pending" && (
          <div className="flex items-center gap-1 text-[10px] text-amber-600 bg-amber-50 rounded px-1.5 py-0.5">
            <Loader2 className="h-3 w-3 animate-spin" />
            A extrair dados do imóvel...
          </div>
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
              onClick={() => onStatusChange(visit.id, "recusada")}
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
// CREATE VISIT DIALOG — Modal para criar visita (v2 com URL do imóvel)
// ════════════════════════════════════════════════════════════════
function CreateVisitDialog({ open, onOpenChange, onSuccess, properties, processes, users }) {
  const { user, token } = useAuth();
  const [saving, setSaving] = useState(false);
  const [scrapingUrl, setScrapingUrl] = useState(false);
  const [scrapePreview, setScrapePreview] = useState(null);
  const [form, setForm] = useState({
    property_id: "",
    client_id: "",
    scheduled_date: "",
    consultor_id: "",
    notes: "",
    property_url: "",  // v2: URL do imóvel (Idealista/Imovirtual)
  });

  // Verificar se a URL parece ser de um portal de imóveis
  const isPropertyUrl = form.property_url && (
    form.property_url.includes("idealista") ||
    form.property_url.includes("imovirtual") ||
    form.property_url.includes("remax") ||
    form.property_url.includes("era") ||
    form.property_url.includes("supercasa") ||
    form.property_url.includes("olx") ||
    form.property_url.includes("casa.sapo") ||
    form.property_url.startsWith("http")
  );

  // Debounced scrape preview quando URL é colada
  useEffect(() => {
    if (!isPropertyUrl || !token) {
      setScrapePreview(null);
      return;
    }
    const timeout = setTimeout(async () => {
      setScrapingUrl(true);
      try {
        const res = await fetch(
          `${API_URL}/api/scraper/single`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ url: form.property_url.trim() }),
          }
        );
        if (res.ok) {
          const data = await res.json();
          if (data.success && data.data) {
            setScrapePreview(data.data);
          } else {
            setScrapePreview(null);
          }
        } else {
          setScrapePreview(null);
        }
      } catch {
        setScrapePreview(null);
      } finally {
        setScrapingUrl(false);
      }
    }, 1500);
    return () => clearTimeout(timeout);
  }, [form.property_url, token, isPropertyUrl]);

  const handleSubmit = async () => {
    // Se tem URL, property_id não é obrigatório
    if (!form.property_id && !form.property_url) {
      toast.error("Selecione um imóvel ou insira um URL de imóvel");
      return;
    }
    if (!form.client_id) {
      toast.error("Selecione um cliente");
      return;
    }
    if (!form.scheduled_date) {
      toast.error("Escolha a data e hora da visita");
      return;
    }

    setSaving(true);
    try {
      const body = {
        client_id: form.client_id,
        scheduled_date: form.scheduled_date,
        consultor_id: form.consultor_id || user?.id,
        notes: form.notes,
      };

      // Se tem property_id, enviar
      if (form.property_id) {
        body.property_id = form.property_id;
      }

      // Se tem URL do imóvel, enviar para o backend invocar o scraper
      if (form.property_url) {
        body.property_url = form.property_url.trim();
      }

      const response = await fetch(`${API_URL}/api/visits`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
      });
      if (response.ok) {
        toast.success(
          form.property_url
            ? "Visita criada! Os dados do imóvel estão a ser extraídos..."
            : "Visita criada com sucesso!"
        );
        setForm({ property_id: "", client_id: "", scheduled_date: "", consultor_id: "", notes: "", property_url: "" });
        setScrapePreview(null);
        onOpenChange(false);
        if (onSuccess) onSuccess();
      } else {
        const err = await response.json();
        toast.error(err.detail || "Erro ao criar visita");
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
            <Plus className="h-5 w-5 text-amber-600" />
            Criar Visita
          </DialogTitle>
          <DialogDescription>
            Crie uma visita a um imóvel para um cliente. Pode selecionar um imóvel existente ou colar um URL.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* URL do Imóvel (opcional) — v2 */}
          <div>
            <Label className="text-sm font-medium flex items-center gap-1">
              <Link2 className="h-3.5 w-3.5 text-teal-500" />
              URL do Imóvel (Idealista/Imovirtual)
              <span className="text-muted-foreground font-normal">— opcional</span>
            </Label>
            <div className="relative mt-1">
              <Input
                type="url"
                placeholder="https://www.idealista.pt/imovel/..."
                value={form.property_url}
                onChange={(e) => setForm((f) => ({ ...f, property_url: e.target.value }))}
                className={isPropertyUrl ? "border-teal-300 focus-visible:ring-teal-400" : ""}
              />
              {isPropertyUrl && (
                <Sparkles className="absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-teal-500" />
              )}
            </div>
            <p className="text-[10px] text-muted-foreground mt-1">
              Se preencher, o sistema extrai automaticamente os dados do imóvel (nome, preço, morada, foto).
            </p>
            {/* Scrape preview inline */}
            {scrapingUrl && (
              <div className="flex items-center gap-2 mt-2 p-2 bg-teal-50 rounded-lg border border-teal-100">
                <Loader2 className="h-4 w-4 animate-spin text-teal-600" />
                <span className="text-xs text-teal-700">A extrair dados do imóvel...</span>
              </div>
            )}
            {scrapePreview && !scrapingUrl && (
              <div className="mt-2 p-2 bg-teal-50 rounded-lg border border-teal-100 space-y-1">
                <p className="text-xs font-semibold text-teal-800 flex items-center gap-1">
                  <Sparkles className="h-3 w-3" />
                  Dados extraídos
                </p>
                <div className="flex gap-2">
                  {scrapePreview.photo_url && (
                    <img src={scrapePreview.photo_url} alt="" className="h-10 w-10 rounded object-cover shrink-0" onError={(e) => { e.target.style.display = 'none'; }} />
                  )}
                  <div className="min-w-0 text-[11px]">
                    {scrapePreview.title && <p className="font-medium truncate">{scrapePreview.title}</p>}
                    {scrapePreview.price && <p className="text-amber-700 font-semibold">{formatPrice(scrapePreview.price)}</p>}
                    {scrapePreview.location && <p className="text-muted-foreground"><MapPin className="h-3 w-3 inline mr-0.5" />{scrapePreview.location}</p>}
                    {scrapePreview.typology && <p className="text-muted-foreground"><Home className="h-3 w-3 inline mr-0.5" />{scrapePreview.typology}</p>}
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Divider */}
          {form.property_url && (
            <div className="flex items-center gap-2">
              <div className="h-px flex-1 bg-border" />
              <span className="text-[10px] text-muted-foreground">ou selecione um imóvel existente</span>
              <div className="h-px flex-1 bg-border" />
            </div>
          )}

          {/* Property select (opcional se tem URL) */}
          <div>
            <Label className="text-sm font-medium">
              Imóvel {form.property_url ? "" : "*"}
            </Label>
            <Select
              value={form.property_id}
              onValueChange={(v) => setForm((f) => ({ ...f, property_id: v }))}
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder={form.property_url ? "Opcional — dados virão do URL" : "Selecionar imóvel..."} />
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
            disabled={saving || (!form.property_id && !form.property_url) || !form.client_id || !form.scheduled_date}
            className="gap-1.5 bg-amber-600 hover:bg-amber-700 text-white"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            Criar Visita
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ════════════════════════════════════════════════════════════════
// SCHEDULE FROM PORTAL DIALOG — Modal para agendar visita pedida pelo cliente
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

  // Dados do scraper
  const scraped = visit.scraped_data || {};
  const scrapedUrl = visit.scraped_url || scraped.url;
  const propertyTitle = visit.property_title || scraped.title || "Imóvel";
  const propertyPhoto = visit.property_photo || scraped.photo_url;
  const propertyPrice = scraped.price;
  const propertyTypology = scraped.typology;
  const propertyLocation = scraped.location || visit.property_address?.municipality;

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

        {/* Property preview — Enriquecido com dados do scraper */}
        <div className="flex gap-3 p-3 bg-violet-50 rounded-xl border border-violet-100">
          {propertyPhoto && (
            <img src={propertyPhoto} alt="" className="h-16 w-16 rounded-lg object-cover shrink-0" />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold truncate">{propertyTitle}</p>
            {propertyPrice && (
              <p className="text-xs font-semibold text-amber-700">
                <Euro className="h-3 w-3 inline mr-0.5" />
                {formatPrice(propertyPrice)}
              </p>
            )}
            {propertyTypology && (
              <p className="text-xs text-muted-foreground">
                <Home className="h-3 w-3 inline mr-0.5" />
                {propertyTypology}
              </p>
            )}
            {propertyLocation && (
              <p className="text-xs text-muted-foreground">
                <MapPin className="h-3 w-3 inline mr-0.5" />
                {propertyLocation}
              </p>
            )}
            {scrapedUrl && (
              <a
                href={scrapedUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[10px] text-teal-600 hover:text-teal-800 hover:underline inline-flex items-center gap-0.5 mt-0.5"
              >
                <ExternalLink className="h-2.5 w-2.5" />
                Ver anúncio original
              </a>
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

// ════════════════════════════════════════════════════════════════
// VISITS PAGE — Página Principal
// ════════════════════════════════════════════════════════════════
const VisitsPage = () => {
  const { user, token } = useAuth();
  const [visits, setVisits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
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
        const statusLabels = { concluida: "concluída", cancelada: "cancelada", agendada: "agendada", recusada: "recusada" };
        toast.success(`Visita marcada como ${statusLabels[newStatus] || newStatus}`);
        fetchVisits();
      } else {
        toast.error("Erro ao alterar estado da visita");
      }
    } catch {
      toast.error("Erro de ligação ao servidor");
    }
  };

  // Filter visits by search term (inclui campos do scraper)
  const filteredKanban = useMemo(() => {
    if (!searchTerm) return visits;

    const term = searchTerm.toLowerCase();
    const filterList = (list) =>
      (list || []).filter(
        (v) =>
          (v.property_title || "").toLowerCase().includes(term) ||
          (v.client_name || "").toLowerCase().includes(term) ||
          (v.consultor_name || "").toLowerCase().includes(term) ||
          (v.notes || "").toLowerCase().includes(term) ||
          (v.scraped_data?.title || "").toLowerCase().includes(term) ||
          (v.scraped_data?.location || "").toLowerCase().includes(term) ||
          (v.scraped_url || "").toLowerCase().includes(term) ||
          (v.scraped_data?.typology || "").toLowerCase().includes(term)
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
            onClick={() => setShowCreateDialog(true)}
          >
            <Plus className="h-4 w-4" />
            Criar Visita
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
              placeholder="Pesquisar por imóvel, cliente, morada..."
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

      {/* Create Visit Dialog */}
      <CreateVisitDialog
        open={showCreateDialog}
        onOpenChange={setShowCreateDialog}
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
