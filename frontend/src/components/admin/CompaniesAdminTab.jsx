/**
 * Tab Empresas — listagem + CRUD via Dialog (Pacote DW).
 *
 * Liga a GET/POST /admin/companies e PUT /admin/companies/{id}.
 */
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Loader2, Pencil, Plug, Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { createCompany, getCompanies, testCompanyEmailConnection, updateCompany } from "../../services/api";
import { queryKeys } from "../../lib/queryClient";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { validateNIF } from "../../utils/validateNIF";
import {
  isCompanyActive,
  normalizeCompaniesPayload,
} from "../../utils/organizationAdmin";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { ScrollArea } from "../ui/scroll-area";
import { Switch } from "../ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";
import EmptyState from "../ui/EmptyState";
import { TableSkeleton } from "../ui/skeletons";

const EMPTY_FORM = {
  name: "",
  nif: "",
  email: "",
  is_active: true,
  smtp_email: "",
  smtp_password: "",
  smtp_host: "",
  smtp_port: "",
  imap_email: "",
  imap_password: "",
  imap_host: "",
  imap_port: "",
};

function parseOptionalSmtpPort(value) {
  if (value === "" || value == null) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function smtpFieldsFromForm(form) {
  const smtp_email = form.smtp_email.trim() || null;
  const smtp_password = form.smtp_password || null;
  const smtp_host = form.smtp_host.trim() || null;
  const smtp_port = parseOptionalSmtpPort(form.smtp_port);
  return { smtp_email, smtp_password, smtp_host, smtp_port };
}

function imapFieldsFromForm(form) {
  const imap_email = form.imap_email.trim() || null;
  const imap_password = form.imap_password || null;
  const imap_host = form.imap_host.trim() || null;
  const imap_port = parseOptionalSmtpPort(form.imap_port);
  return { imap_email, imap_password, imap_host, imap_port };
}

export default function CompaniesAdminTab() {
  const queryClient = useQueryClient();
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);
  const [testingConnection, setTestingConnection] = useState(false);

  const {
    data: companies = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: queryKeys.orgAdmin.companies(debouncedSearch),
    queryFn: async () => {
      const res = await getCompanies(debouncedSearch || undefined);
      return normalizeCompaniesPayload(res.data);
    },
  });

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    if (isError) toast.error("Erro ao carregar empresas.");
  }, [isError]);

  const openCreate = () => {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setDialogOpen(true);
  };

  const openEdit = (company) => {
    setEditing(company);
    setForm({
      name: company.name || "",
      nif: company.nif || "",
      email: company.email || company.contact_email || "",
      is_active: isCompanyActive(company),
      smtp_email: company.smtp_email || "",
      smtp_password: "",
      smtp_host: company.smtp_host || "",
      smtp_port: company.smtp_port ?? "",
      imap_email: company.imap_email || "",
      imap_password: "",
      imap_host: company.imap_host || "",
      imap_port: company.imap_port ?? "",
    });
    setDialogOpen(true);
  };

  // Testa a ligação SMTP/IMAP com os valores atuais do formulário, sem gravar.
  // BUGFIX (Fev 2026): ao editar, a password fica vazia de propósito ("Deixe
  // em branco para manter") — nesse caso o backend usa a password já
  // guardada na Empresa, por isso o pedido de teste é válido mesmo sem
  // password explícita, desde que a empresa já exista (editing?.id).
  const handleTestConnection = async () => {
    const smtp = smtpFieldsFromForm(form);
    const imap = imapFieldsFromForm(form);
    const hasSmtp = Boolean(smtp.smtp_host && smtp.smtp_email && (smtp.smtp_password || editing?.id));
    const hasImap = Boolean(imap.imap_host && imap.imap_email && (imap.imap_password || editing?.id));
    if (!hasSmtp && !hasImap) {
      toast.error(
        "Preencha o email, a password e o servidor de SMTP e/ou IMAP para testar a ligação.",
      );
      return;
    }
    setTestingConnection(true);
    try {
      const res = await testCompanyEmailConnection({ ...smtp, ...imap, company_id: editing?.id || null });
      const messages = Object.values(res.data?.results || {}).map((r) => r.message);
      toast.success(messages.join(" | ") || "Ligação validada com sucesso.");
    } catch (err) {
      toast.error(
        extractErrorMessage(err.response?.data?.detail, "Falha ao testar a ligação."),
      );
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) {
      toast.error("O nome da empresa é obrigatório.");
      return;
    }
    if (form.nif.trim()) {
      const nifCheck = validateNIF(form.nif, { allowCompanyNIF: true });
      if (!nifCheck.valid) {
        toast.error(nifCheck.error || "NIF inválido.");
        return;
      }
    }

    setSaving(true);
    try {
      const payload = {
        name: form.name.trim(),
        nif: form.nif.trim() || null,
        email: form.email.trim() || null,
        is_active: form.is_active,
        ...smtpFieldsFromForm(form),
        ...imapFieldsFromForm(form),
      };
      if (editing?.id && !payload.smtp_password) {
        delete payload.smtp_password;
      }
      if (editing?.id && !payload.imap_password) {
        delete payload.imap_password;
      }
      if (editing?.id) {
        await updateCompany(editing.id, payload);
        toast.success("Empresa atualizada.");
      } else {
        await createCompany(payload);
        toast.success(`Empresa "${payload.name}" criada.`);
      }
      setDialogOpen(false);
      queryClient.invalidateQueries({ queryKey: queryKeys.orgAdmin.companiesAll() });
    } catch (err) {
      toast.error(
        extractErrorMessage(
          err.response?.data?.detail || err.response?.data?.error,
          "Erro ao guardar a empresa.",
        ),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="org-admin-companies-tab">
      <div className="flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Pesquisar por nome ou NIF..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-9"
            data-testid="org-admin-companies-search"
          />
        </div>
        <Button onClick={openCreate} className="gap-1.5" data-testid="btn-new-company">
          <Plus className="h-4 w-4" />
          Nova Empresa
        </Button>
      </div>

      {isLoading && companies.length === 0 ? (
        <TableSkeleton rows={5} />
      ) : companies.length === 0 ? (
        <EmptyState
          icon={Building2}
          title="Nenhuma empresa"
          message="Crie a primeira empresa do grupo para começar a atribuir acessos."
          action={
            <Button onClick={openCreate} className="gap-1.5">
              <Plus className="h-4 w-4" />
              Nova Empresa
            </Button>
          }
        />
      ) : (
        <ScrollArea className="h-fit max-h-[560px] rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>NIF</TableHead>
                <TableHead>Email Geral</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {companies.map((company) => {
                const active = isCompanyActive(company);
                return (
                  <TableRow
                    key={company.id}
                    data-testid={`company-row-${company.id}`}
                  >
                    <TableCell className="font-medium">{company.name}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {company.nif || "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {company.email || company.contact_email || "—"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={active ? "secondary" : "outline"}>
                        {active ? "Activa" : "Inactiva"}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="gap-1.5"
                        onClick={() => openEdit(company)}
                        data-testid={`btn-edit-company-${company.id}`}
                      >
                        <Pencil className="h-4 w-4" />
                        Editar
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </ScrollArea>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent data-testid="company-form-dialog">
          <form onSubmit={handleSave}>
            <DialogHeader>
              <DialogTitle>
                {editing ? "Editar Empresa" : "Nova Empresa"}
              </DialogTitle>
              <DialogDescription>
                {editing
                  ? "Atualize os dados da entidade do grupo."
                  : "Registe uma nova entidade do grupo."}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="company-name">
                  Nome <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="company-name"
                  value={form.name}
                  onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
                  placeholder="Nome da empresa"
                  data-testid="company-name-input"
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="company-nif">NIF</Label>
                <Input
                  id="company-nif"
                  value={form.nif}
                  onChange={(e) => setForm((p) => ({ ...p, nif: e.target.value }))}
                  placeholder="123456789"
                  data-testid="company-nif-input"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="company-email">Email Geral</Label>
                <Input
                  id="company-email"
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))}
                  placeholder="geral@empresa.pt"
                  data-testid="company-email-input"
                />
              </div>
              <div className="space-y-4 pt-2 border-t border-border">
                <p className="text-sm font-medium text-foreground">SMTP (opcional)</p>
                <div className="space-y-2">
                  <Label htmlFor="company-smtp-email">Email SMTP</Label>
                  <Input
                    id="company-smtp-email"
                    type="email"
                    value={form.smtp_email}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, smtp_email: e.target.value }))
                    }
                    placeholder="smtp@empresa.pt"
                    data-testid="company-smtp-email-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="company-smtp-password">Password SMTP</Label>
                  <Input
                    id="company-smtp-password"
                    type="password"
                    value={form.smtp_password}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, smtp_password: e.target.value }))
                    }
                    placeholder={
                      editing ? "Deixe em branco para manter" : "Password SMTP"
                    }
                    autoComplete="new-password"
                    data-testid="company-smtp-password-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="company-smtp-host">Host SMTP</Label>
                  <Input
                    id="company-smtp-host"
                    value={form.smtp_host}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, smtp_host: e.target.value }))
                    }
                    placeholder="smtp.empresa.pt"
                    data-testid="company-smtp-host-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="company-smtp-port">Porta SMTP</Label>
                  <Input
                    id="company-smtp-port"
                    type="number"
                    value={form.smtp_port}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, smtp_port: e.target.value }))
                    }
                    placeholder="465"
                    data-testid="company-smtp-port-input"
                  />
                </div>
              </div>
              <div className="space-y-4 pt-2 border-t border-border">
                <p className="text-sm font-medium text-foreground">IMAP (opcional — Webmail)</p>
                <div className="space-y-2">
                  <Label htmlFor="company-imap-email">Email IMAP</Label>
                  <Input
                    id="company-imap-email"
                    type="email"
                    value={form.imap_email}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, imap_email: e.target.value }))
                    }
                    placeholder="imap@empresa.pt"
                    data-testid="company-imap-email-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="company-imap-password">Password IMAP</Label>
                  <Input
                    id="company-imap-password"
                    type="password"
                    value={form.imap_password}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, imap_password: e.target.value }))
                    }
                    placeholder={
                      editing ? "Deixe em branco para manter" : "Password IMAP"
                    }
                    autoComplete="new-password"
                    data-testid="company-imap-password-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="company-imap-host">Host IMAP</Label>
                  <Input
                    id="company-imap-host"
                    value={form.imap_host}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, imap_host: e.target.value }))
                    }
                    placeholder="imap.empresa.pt"
                    data-testid="company-imap-host-input"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="company-imap-port">Porta IMAP</Label>
                  <Input
                    id="company-imap-port"
                    type="number"
                    value={form.imap_port}
                    onChange={(e) =>
                      setForm((p) => ({ ...p, imap_port: e.target.value }))
                    }
                    placeholder="993"
                    data-testid="company-imap-port-input"
                  />
                </div>
              </div>
              <div className="flex items-center justify-between rounded-md border border-border p-3">
                <div className="space-y-0.5">
                  <Label htmlFor="company-active">Estado</Label>
                  <p className="text-xs text-muted-foreground">
                    Empresas inactivas ficam visíveis mas não devem receber novos acessos.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">
                    {form.is_active ? "Activa" : "Inactiva"}
                  </span>
                  <Switch
                    id="company-active"
                    checked={form.is_active}
                    onCheckedChange={(checked) =>
                      setForm((p) => ({ ...p, is_active: checked }))
                    }
                    data-testid="company-active-switch"
                  />
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
              >
                Cancelar
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={handleTestConnection}
                disabled={testingConnection}
                className="gap-1.5"
                data-testid="btn-test-email-connection"
              >
                {testingConnection ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Plug className="h-4 w-4" />
                )}
                Testar Ligação
              </Button>
              <Button type="submit" disabled={saving} data-testid="btn-save-company">
                {saving ? "A guardar..." : editing ? "Guardar" : "Criar Empresa"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
