/**
 * Tab Empresas — listagem + CRUD via Dialog (Pacote DW).
 *
 * Liga a GET/POST /admin/companies e PUT /admin/companies/{id}.
 */
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Pencil, Plus, Search } from "lucide-react";
import { toast } from "sonner";
import { createCompany, getCompanies, updateCompany } from "../../services/api";
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
};

export default function CompaniesAdminTab() {
  const queryClient = useQueryClient();
  const [searchInput, setSearchInput] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);

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
    });
    setDialogOpen(true);
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
      };
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
