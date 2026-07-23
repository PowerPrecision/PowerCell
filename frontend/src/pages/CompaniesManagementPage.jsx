/**
 * CompaniesManagementPage — Gestão de Empresas (Multi-Tenant).
 *
 * CRUD completo para empresas: listagem, criação, edição, eliminação e upload de logo.
 * Pode ser usado em modo `embedded={true}` (dentro de SystemAdminPanel) ou standalone.
 *
 * @prop {boolean} embedded — Se true, não renderiza wrapper de layout.
 */
import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getCompanies,
  createCompany,
  updateCompany,
  deleteCompany,
  uploadCompanyLogo,
  getCompanyEmailConfig,
  upsertCompanyEmailConfig,
} from "../services/api";
import { toast } from "sonner";
import {
  Building2,
  Plus,
  Search,
  Trash2,
  Upload,
  Mail,
  Save,
  Pencil,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Switch } from "../components/ui/switch";
import { Badge } from "../components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"];
const MAX_FILE_SIZE = 2 * 1024 * 1024; // 2 MB

const EMPTY_FORM = {
  name: "",
  nif: "",
  address: "",
  phone: "",
  contact_email: "",
  website: "",
  email_sync_enabled: false,
  logo_url: null,
  total_users: 0,
  // PACOTE BF: campos de email config unificados no form
  imap_server: "",
  imap_port: 993,
  smtp_server: "",
  smtp_port: 465,
};

/** Normaliza a resposta do endpoint de empresas para um array. */
function normalizeCompaniesPayload(payload) {
  // O endpoint pode devolver: Array puro, { data: [...] }, { items: [...] },
  // { companies: [...] }, ou { data: { companies: [...] } }.
  let rawData = payload?.data ?? payload;
  if (!Array.isArray(rawData)) {
    rawData = rawData?.items || rawData?.companies || rawData?.results || [];
  }
  return Array.isArray(rawData) ? rawData : [];
}

const CompaniesManagementPage = ({ embedded = false }) => {
  // ── State ──────────────────────────────────────────────────────
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [saving, setSaving] = useState(false);
  const [selectedId, setSelectedId] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  // PACOTE BF: config IMAP/SMTP unificada no form (estados de loading removidos)
  const [emailConfigSaving, setEmailConfigSaving] = useState(false);

  const fileInputRef = useRef(null);

  // Server state via TanStack Query (substitui useState + useEffect + fetch manual).
  const {
    data: companies = [],
    isLoading: loading,
    isError: companiesError,
    refetch: refetchCompanies,
  } = useQuery({
    queryKey: ["companies", debouncedSearch],
    queryFn: async () => {
      const res = await getCompanies(debouncedSearch || undefined);
      return normalizeCompaniesPayload(res.data);
    },
  });

  useEffect(() => {
    if (companiesError) {
      toast.error("Erro ao carregar a lista de empresas.");
    }
  }, [companiesError]);

  // Compat: call-sites antigos usavam fetchCompanies(search).
  const search = debouncedSearch;
  const fetchCompanies = useCallback(
    async (_searchTerm) => {
      await refetchCompanies();
    },
    [refetchCompanies]
  );

  // ── Search debounce ────────────────────────────────────────────
  const handleSearchChange = (e) => {
    const value = e.target.value;
    setSearchInput(value);
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // ── Select company ─────────────────────────────────────────────
  const handleSelectCompany = (company) => {
    setSelectedId(company.id);
    setIsCreating(false);
    setForm({
      name: company.name || "",
      nif: company.nif || "",
      address: company.address || "",
      phone: company.phone || "",
      contact_email: company.contact_email || "",
      website: company.website || "",
      email_sync_enabled: company.email_sync_enabled ?? false,
      logo_url: company.logo_url || null,
      total_users: company.total_users ?? 0,
      imap_server: "",
      imap_port: 993,
      smtp_server: "",
      smtp_port: 465,
    });
    // PACOTE BF: carregar config de email em paralelo
    if (company.email_sync_enabled && company.name) {
      fetchEmailConfig(company.name);
    }
  };

  // ── New company ────────────────────────────────────────────────
  const handleNewCompany = () => {
    setSelectedId(null);
    setIsCreating(true);
    setForm({ ...EMPTY_FORM });
  };

  // ── Form helpers ───────────────────────────────────────────────
  const updateField = (field, value) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  // ── Save (create or update) ────────────────────────────────────
  // PACOTE BF: guarda empresa + config de email em paralelo (Promise.all)
  const handleSave = async () => {
    if (!form.name.trim()) {
      toast.error("O nome da empresa é obrigatório.");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        name: form.name,
        nif: form.nif || null,
        address: form.address || null,
        phone: form.phone || null,
        contact_email: form.contact_email || null,
        website: form.website || null,
        email_sync_enabled: form.email_sync_enabled,
      };

      // Promise array: company save + email config save (se sync ativado)
      const promises = [];

      if (isCreating) {
        promises.push(createCompany(payload));
      } else {
        promises.push(updateCompany(selectedId, payload));
      }

      // Se sync ativado e tem smtp_server, guardar config de email
      if (form.email_sync_enabled && form.smtp_server && form.name) {
        promises.push(upsertCompanyEmailConfig({
          company_name: form.name,
          imap_server: form.imap_server || "",
          imap_port: parseInt(form.imap_port) || 993,
          smtp_server: form.smtp_server,
          smtp_port: parseInt(form.smtp_port) || 465,
        }));
      }

      const results = await Promise.all(promises);
      const companyResult = results[0];
      const savedCompany = companyResult.data?.data ?? companyResult.data;

      if (isCreating) {
        toast.success(`Empresa "${savedCompany.name}" criada com sucesso.`);
        setIsCreating(false);
        setSelectedId(savedCompany.id);
      } else {
        toast.success("Empresa atualizada com sucesso.");
      }
      setForm((prev) => ({ ...prev, ...savedCompany }));
      fetchCompanies(search);
    } catch (err) {
      console.error("Erro ao guardar empresa:", err);
      toast.error(err.response?.data?.error || "Erro ao guardar a empresa.");
    } finally {
      setSaving(false);
    }
  };

  // ── Delete ─────────────────────────────────────────────────────
  const handleDelete = async () => {
    if (!selectedId) return;
    try {
      await deleteCompany(selectedId);
      toast.success("Empresa eliminada com sucesso.");
      setDeleteDialogOpen(false);
      setSelectedId(null);
      setForm({ ...EMPTY_FORM });
      fetchCompanies(search);
    } catch (err) {
      console.error("Erro ao eliminar empresa:", err);
      toast.error(err.response?.data?.error || "Erro ao eliminar a empresa.");
    }
  };

  // ── Logo upload ────────────────────────────────────────────────
  const handleLogoClick = () => {
    fileInputRef.current?.click();
  };

  const handleLogoFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!ACCEPTED_TYPES.includes(file.type)) {
      toast.error("Formato inválido. Use PNG, JPEG, GIF, WebP ou SVG.");
      e.target.value = "";
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      toast.error("Ficheiro demasiado grande. Máximo 2 MB.");
      e.target.value = "";
      return;
    }

    // If creating a new company, we can't upload a logo yet — save first
    if (isCreating || !selectedId) {
      toast.error("Guarde a empresa primeiro antes de carregar um logo.");
      e.target.value = "";
      return;
    }

    setUploadingLogo(true);
    try {
      const res = await uploadCompanyLogo(selectedId, file);
      const data = res.data?.data ?? res.data;
      toast.success("Logo carregado com sucesso.");
      updateField("logo_url", data?.logo_url ?? data?.logo ?? form.logo_url);
      fetchCompanies(search);
    } catch (err) {
      console.error("Erro ao carregar logo:", err);
      toast.error("Erro ao carregar o logo.");
    } finally {
      setUploadingLogo(false);
      e.target.value = "";
    }
  };

  // ── Email sync toggle ──────────────────────────────────────────
  const handleEmailSyncToggle = async (checked) => {
    updateField("email_sync_enabled", checked);
    if (!isCreating && selectedId) {
      try {
        await updateCompany(selectedId, { email_sync_enabled: checked });
        toast.success(checked ? "Sincronização de e-mail ativada." : "Sincronização de e-mail desativada.");
        fetchCompanies(search);
      } catch (err) {
        console.error("Erro ao atualizar sincronização de e-mail:", err);
        toast.error("Erro ao atualizar a sincronização de e-mail.");
        updateField("email_sync_enabled", !checked);
      }
    }
  };

  // ── Fetch email config (IMAP/SMTP) — preenche o form ────────
  const fetchEmailConfig = useCallback(async (companyName) => {
    try {
      const res = await getCompanyEmailConfig(companyName);
      const cfg = res.data?.data ?? res.data;
      if (cfg) {
        setForm(prev => ({
          ...prev,
          imap_server: cfg.imap_server || "",
          imap_port: cfg.imap_port || 993,
          smtp_server: cfg.smtp_server || "",
          smtp_port: cfg.smtp_port || 465,
        }));
      }
    } catch (err) {
      // 404 = sem config, normal
      if (err?.response?.status !== 404) {
        console.error("Erro ao carregar config de email:", err);
      }
    }
  }, []);

  // ── Selected company (derived) ─────────────────────────────────
  // Guard defensivo: se companies não for array (edge case), usar [] para
  // evitar "t.find is not a function".
  const selectedCompany = (Array.isArray(companies) ? companies : []).find((c) => c.id === selectedId);
  const showRightPanel = isCreating || selectedId;

  // ── Render ─────────────────────────────────────────────────────
  const pageContent = (
    <div className="flex flex-col lg:flex-row gap-6 h-full" data-testid="companies-management">
      {/* ── Left panel: Company list ─────────────────────────────── */}
      <div className="w-full lg:w-[380px] xl:w-[420px] shrink-0 flex flex-col gap-4">
        {/* Header row */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Pesquisar por nome ou NIF..."
              value={searchInput}
              onChange={handleSearchChange}
              className="pl-9"
            />
          </div>
          <Button
            onClick={handleNewCompany}
            className="gap-1.5 bg-amber-600 hover:bg-amber-700 text-white shrink-0"
            data-testid="btn-new-company"
          >
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">Nova Empresa</span>
            <span className="sm:hidden">Nova</span>
          </Button>
        </div>

        {/* Company list */}
        <div className="flex-1 overflow-y-auto space-y-2 min-h-0 max-h-[calc(100vh-260px)] lg:max-h-none">
          {loading && companies.length === 0 ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Building2 className="h-6 w-6 mr-2 animate-pulse" />
              A carregar empresas...
            </div>
          ) : companies.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground text-sm">
              <Building2 className="h-10 w-10 mb-3 opacity-30" />
              <p>Nenhuma empresa encontrada.</p>
            </div>
          ) : (
            companies.map((company) => (
              <Card
                key={company.id}
                className={`cursor-pointer transition-colors hover:bg-amber-50 dark:hover:bg-amber-950/30 border ${
                  selectedId === company.id
                    ? "border-amber-500 bg-amber-50 dark:bg-amber-950/30 ring-1 ring-amber-500/40"
                    : ""
                }`}
                onClick={() => handleSelectCompany(company)}
                data-testid={`company-card-${company.id}`}
              >
                <CardContent className="p-3 flex items-center gap-3">
                  {/* Logo thumbnail or placeholder */}
                  <div className="h-10 w-10 rounded-md bg-muted flex items-center justify-center shrink-0 overflow-hidden">
                    {company.logo_url ? (
                      <img
                        src={company.logo_url}
                        alt={company.name}
                        className="h-full w-full object-contain"
                      />
                    ) : (
                      <Building2 className="h-5 w-5 text-muted-foreground" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-sm truncate">{company.name}</p>
                    {company.nif && (
                      <p className="text-xs text-muted-foreground">NIF: {company.nif}</p>
                    )}
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    {company.total_users != null && company.total_users > 0 && (
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                        {company.total_users} {company.total_users === 1 ? "utilizador" : "utilizadores"}
                      </Badge>
                    )}
                    {company.email_sync_enabled && (
                      <Badge className="text-[10px] px-1.5 py-0 bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400 hover:bg-emerald-100">
                        <Mail className="h-2.5 w-2.5 mr-0.5" />
                        E-mail
                      </Badge>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </div>

      {/* ── Right panel: Detail / Edit form ─────────────────────── */}
      {showRightPanel ? (
        <div className="flex-1 min-w-0">
          <Card className="h-full">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-2 text-lg">
                {isCreating ? (
                  <>
                    <Plus className="h-5 w-5 text-amber-600" />
                    Nova Empresa
                  </>
                ) : (
                  <>
                    <Pencil className="h-5 w-5 text-amber-600" />
                    Editar Empresa
                  </>
                )}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* ── a) Dados Base ─────────────────────────────────── */}
              <div>
                <h3 className="text-sm font-semibold text-amber-700 dark:text-amber-400 mb-3 flex items-center gap-1.5">
                  <Building2 className="h-4 w-4" />
                  Dados Base
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium">
                      Nome <span className="text-red-500">*</span>
                    </label>
                    <Input
                      value={form.name}
                      onChange={(e) => updateField("name", e.target.value)}
                      placeholder="Nome da empresa"
                      data-testid="company-name-input"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium">NIF</label>
                    <Input
                      value={form.nif}
                      onChange={(e) => updateField("nif", e.target.value)}
                      placeholder="123456789"
                      data-testid="company-nif-input"
                    />
                  </div>
                  <div className="space-y-1.5 md:col-span-2">
                    <label className="text-sm font-medium">Morada</label>
                    <Textarea
                      value={form.address}
                      onChange={(e) => updateField("address", e.target.value)}
                      placeholder="Morada da empresa"
                      rows={2}
                      data-testid="company-address-input"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium">Telefone</label>
                    <Input
                      value={form.phone}
                      onChange={(e) => updateField("phone", e.target.value)}
                      placeholder="+351 000 000 000"
                      data-testid="company-phone-input"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-sm font-medium">Email de Contacto</label>
                    <Input
                      type="email"
                      value={form.contact_email}
                      onChange={(e) => updateField("contact_email", e.target.value)}
                      placeholder="geral@empresa.pt"
                      data-testid="company-email-input"
                    />
                  </div>
                  <div className="space-y-1.5 md:col-span-2">
                    <label className="text-sm font-medium">Website</label>
                    <Input
                      value={form.website}
                      onChange={(e) => updateField("website", e.target.value)}
                      placeholder="https://www.empresa.pt"
                      data-testid="company-website-input"
                    />
                  </div>
                </div>
              </div>

              {/* ── b) Branding ───────────────────────────────────── */}
              <div>
                <h3 className="text-sm font-semibold text-amber-700 dark:text-amber-400 mb-3 flex items-center gap-1.5">
                  <Upload className="h-4 w-4" />
                  Branding
                </h3>
                <div
                  className="border-2 border-dashed rounded-lg p-6 flex flex-col items-center justify-center gap-3 cursor-pointer hover:border-amber-400 hover:bg-amber-50/50 dark:hover:bg-amber-950/20 transition-colors min-h-[140px]"
                  onClick={handleLogoClick}
                  data-testid="logo-upload-area"
                >
                  {form.logo_url ? (
                    <div className="flex flex-col items-center gap-2">
                      <img
                        src={form.logo_url}
                        alt="Logo"
                        className="h-16 w-16 object-contain rounded"
                      />
                      <p className="text-xs text-muted-foreground">
                        Clique para substituir o logo
                      </p>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-2 text-muted-foreground">
                      <Upload className="h-8 w-8 opacity-40" />
                      <p className="text-sm">
                        Arraste ou clique para carregar o logo
                      </p>
                      <p className="text-xs text-muted-foreground">
                        PNG, JPEG, GIF, WebP, SVG — Máx. 2 MB
                      </p>
                    </div>
                  )}
                  {uploadingLogo && (
                    <p className="text-xs text-amber-600 font-medium animate-pulse">
                      A carregar...
                    </p>
                  )}
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".png,.jpg,.jpeg,.gif,.webp,.svg"
                  className="hidden"
                  onChange={handleLogoFile}
                  data-testid="logo-file-input"
                />
              </div>

              {/* ── c) Motor de E-mail ────────────────────────────── */}
              <div>
                <h3 className="text-sm font-semibold text-amber-700 dark:text-amber-400 mb-3 flex items-center gap-1.5">
                  <Mail className="h-4 w-4" />
                  Motor de E-mail
                </h3>
                <div className="flex items-center justify-between rounded-lg border p-4">
                  <div className="space-y-0.5">
                    <label className="text-sm font-medium">
                      Ativar Sincronização de E-mail para esta Empresa
                    </label>
                    <p className="text-xs text-muted-foreground">
                      Permite a sincronização automática de e-mails associados a esta empresa.
                    </p>
                  </div>
                  <Switch
                    checked={form.email_sync_enabled}
                    onCheckedChange={handleEmailSyncToggle}
                    data-testid="email-sync-switch"
                  />
                </div>

                {/* PACOTE BF: Campos IMAP/SMTP unificados no form, visíveis quando sync ativo */}
                {form.email_sync_enabled && (
                  <div className="mt-4 space-y-3 rounded-lg border border-amber-200 dark:border-amber-900 p-4 bg-amber-50/30 dark:bg-amber-950/10">
                    <p className="text-xs font-medium text-amber-700 dark:text-amber-400">
                      Configuração de Servidores (IMAP/SMTP)
                    </p>
                    <p className="text-[11px] text-muted-foreground">
                      Estes servidores são usados como padrão para os utilizadores desta empresa que não tenham configuração individual. Guardados juntamente com a empresa.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <label className="text-xs text-muted-foreground">Servidor IMAP</label>
                        <Input
                          value={form.imap_server}
                          onChange={(e) => updateField("imap_server", e.target.value)}
                          placeholder="imap.exemplo.pt"
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs text-muted-foreground">Porta IMAP</label>
                        <Input
                          type="number"
                          value={form.imap_port}
                          onChange={(e) => updateField("imap_port", e.target.value)}
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs text-muted-foreground">Servidor SMTP</label>
                        <Input
                          value={form.smtp_server}
                          onChange={(e) => updateField("smtp_server", e.target.value)}
                          placeholder="smtp.exemplo.pt"
                          className="h-8 text-sm"
                        />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs text-muted-foreground">Porta SMTP</label>
                        <Input
                          type="number"
                          value={form.smtp_port}
                          onChange={(e) => updateField("smtp_port", e.target.value)}
                          className="h-8 text-sm"
                        />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* ── Footer actions ────────────────────────────────── */}
              <div className="flex items-center justify-end gap-3 pt-4 border-t">
                {!isCreating && selectedId && (
                  <Button
                    variant="destructive"
                    className="gap-1.5"
                    onClick={() => setDeleteDialogOpen(true)}
                    data-testid="btn-delete-company"
                  >
                    <Trash2 className="h-4 w-4" />
                    Eliminar
                  </Button>
                )}
                <Button
                  onClick={handleSave}
                  disabled={saving}
                  className="gap-1.5 bg-amber-600 hover:bg-amber-700 text-white"
                  data-testid="btn-save-company"
                >
                  <Save className="h-4 w-4" />
                  {saving ? "A guardar..." : "Guardar"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      ) : (
        /* ── Empty state ─────────────────────────────────────────── */
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center text-muted-foreground space-y-3">
            <Building2 className="h-16 w-16 mx-auto opacity-20" />
            <p className="text-lg font-medium">Selecione uma empresa</p>
            <p className="text-sm">
              Escolha uma empresa da lista ou crie uma nova para começar.
            </p>
          </div>
        </div>
      )}
    </div>
  );

  // ── Delete confirmation dialog ─────────────────────────────────
  const deleteDialog = (
    <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-red-600">
            <Trash2 className="h-5 w-5" />
            Eliminar Empresa
          </DialogTitle>
          <DialogDescription>
            Tem a certeza que pretende eliminar a empresa{" "}
            <span className="font-semibold text-foreground">"{form.name}"</span>?
            {selectedCompany?.total_users > 0 && (
              <span className="block mt-2 text-amber-600 dark:text-amber-400 font-medium">
                ⚠️ Esta empresa tem {selectedCompany.total_users} utilizador(es) associado(s).
                A eliminação pode ter impacto nesses utilizadores.
              </span>
            )}
            Esta ação não pode ser revertida.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => setDeleteDialogOpen(false)}
          >
            Cancelar
          </Button>
          <Button
            variant="destructive"
            onClick={handleDelete}
            className="gap-1.5"
          >
            <Trash2 className="h-4 w-4" />
            Confirmar Eliminação
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );

  // ── Standalone wrapper vs embedded ─────────────────────────────
  if (embedded) {
    return (
      <>
        {pageContent}
        {deleteDialog}
      </>
    );
  }

  return (
    <div className="container mx-auto py-6 px-4 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
          <Building2 className="h-6 w-6 text-amber-600" />
          Gestão de Empresas
        </h1>
        <p className="text-muted-foreground mt-1">
          Crie e gerencie as empresas do sistema PowerCell.
        </p>
      </div>
      {pageContent}
      {deleteDialog}
    </div>
  );
};

export default CompaniesManagementPage;