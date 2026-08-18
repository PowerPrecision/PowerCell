/**
 * EmailAccountsCard — lista de contas IMAP/SMTP/OAuth do perfil (Pacote DN.4).
 *
 * Mostra as contas do UCR activo, permite adicionar, editar, definir
 * primária e remover. O formulário vive num Dialog (Progressive Disclosure).
 */
import { useEffect, useState } from "react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { extractErrorMessage } from "../utils/extractErrorMessage";
import api from "../services/api";
import EmailConfigForm from "./EmailConfigForm";
import { Mail, Plus, Pencil, Trash2, Star, Loader2 } from "lucide-react";
import { toast } from "sonner";

const authLabel = (account) => {
  if (account?.auth_method === "google_oauth" || account?.has_google_oauth) {
    return "OAuth";
  }
  if (account?.has_password || account?.auth_method === "imap_smtp") {
    return "IMAP/SMTP";
  }
  return "Pendente";
};

export default function EmailAccountsCard({
  companyId = "default",
  onUpdate,
}) {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAccount, setEditingAccount] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const companyHeaders = () => ({
    headers:
      companyId && companyId !== "default" ? { "X-Company-Id": companyId } : {},
    params: { company_id: companyId },
  });

  const loadAccounts = async () => {
    setLoading(true);
    try {
      const res = await api.get("/users/me/email-accounts", companyHeaders());
      setAccounts(res.data?.accounts || []);
    } catch {
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAccounts();
  }, [companyId]);

  const openAdd = () => {
    setEditingAccount(null);
    setDialogOpen(true);
  };

  const openEdit = (account) => {
    setEditingAccount(account);
    setDialogOpen(true);
  };

  const handleSaved = () => {
    setDialogOpen(false);
    setEditingAccount(null);
    loadAccounts();
    if (onUpdate) onUpdate();
  };

  const handleDelete = async (account) => {
    if (!window.confirm(`Remover a conta ${account.email_address}?`)) return;
    setBusyId(account.id);
    try {
      await api.delete(`/users/me/email-accounts/${account.id}`, companyHeaders());
      toast.success("Conta de email removida");
      loadAccounts();
      if (onUpdate) onUpdate();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao remover a conta"));
    } finally {
      setBusyId(null);
    }
  };

  const handleSetPrimary = async (account) => {
    setBusyId(account.id);
    try {
      await api.post(
        `/users/me/email-accounts/${account.id}/set-primary`,
        null,
        companyHeaders(),
      );
      toast.success("Conta principal actualizada");
      loadAccounts();
      if (onUpdate) onUpdate();
    } catch (error) {
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao definir conta principal"));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-4">
      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground py-4">
          <Loader2 className="h-4 w-4 animate-spin" />
          A carregar contas...
        </div>
      ) : accounts.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Ainda não tem contas de email neste perfil. Adicione IMAP/SMTP ou ligue o Google OAuth.
        </p>
      ) : (
        <ul className="space-y-2">
          {accounts.map((account) => (
            <li
              key={account.id}
              className="flex items-center gap-3 rounded-lg border border-border bg-muted/30 px-3 py-2"
            >
              <Mail className="h-4 w-4 text-muted-foreground shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">
                  {account.label && account.label !== account.email_address
                    ? account.label
                    : account.email_address || "Sem endereço"}
                </p>
                {account.label && account.label !== account.email_address && (
                  <p className="text-xs text-muted-foreground truncate">
                    {account.email_address}
                  </p>
                )}
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {account.is_primary && (
                  <Badge variant="secondary">Principal</Badge>
                )}
                <Badge variant="outline">{authLabel(account)}</Badge>
                {!account.is_primary && (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    title="Definir como principal"
                    disabled={busyId === account.id}
                    onClick={() => handleSetPrimary(account)}
                  >
                    <Star className="h-3.5 w-3.5" />
                  </Button>
                )}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8"
                  title="Editar"
                  onClick={() => openEdit(account)}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-destructive"
                  title="Remover"
                  disabled={busyId === account.id}
                  onClick={() => handleDelete(account)}
                >
                  {busyId === account.id ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Trash2 className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Button type="button" variant="outline" className="gap-2" onClick={openAdd}>
        <Plus className="h-4 w-4" />
        Adicionar Conta de Email
      </Button>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>
              {editingAccount ? "Editar conta de email" : "Adicionar conta de email"}
            </DialogTitle>
            <DialogDescription>
              Configure IMAP/SMTP ou ligue o Google OAuth para esta conta.
            </DialogDescription>
          </DialogHeader>
          <EmailConfigForm
            mode="self"
            companyId={companyId}
            createAdditional={!editingAccount}
            accountId={editingAccount?.id || null}
            onSuccess={handleSaved}
            onCancel={() => setDialogOpen(false)}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}
