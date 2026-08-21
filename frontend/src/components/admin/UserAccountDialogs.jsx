/**
 * Dialogs de conta de utilizador (Pacote DY) — criar, editar dados e redefinir password.
 * Usados pela tab Utilizadores do painel de Administração.
 */
import { useEffect, useState } from "react";
import { Copy, Eye, EyeOff, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { generateTempPassword } from "../../utils/organizationAdmin";
import { PRIMARY_ROLE_OPTIONS, ROLE_LABELS } from "../../utils/roleUtils";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";

export const EMPTY_USER_FORM = {
  name: "",
  email: "",
  phone: "",
  password: "",
  role: "consultor",
};

function PasswordField({
  value,
  onChange,
  required = false,
  placeholder = "",
  testId,
}) {
  const [visible, setVisible] = useState(false);

  const fillGenerated = () => {
    const next = generateTempPassword();
    onChange(next);
    setVisible(true);
  };

  const copyValue = () => {
    if (!value) return;
    navigator.clipboard.writeText(value);
    toast.success("Password copiada para o clipboard");
  };

  return (
    <div className="space-y-2">
      <Label>Password</Label>
      <div className="flex gap-2">
        <div className="relative flex-1">
          <Input
            type={visible ? "text" : "password"}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            required={required}
            placeholder={placeholder}
            className="pr-20"
            data-testid={testId}
          />
          <div className="absolute right-1 top-1/2 -translate-y-1/2 flex">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setVisible((v) => !v)}
              title={visible ? "Ocultar password" : "Mostrar password"}
            >
              {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </Button>
            {value ? (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={copyValue}
                title="Copiar password"
              >
                <Copy className="h-4 w-4" />
              </Button>
            ) : null}
          </div>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={fillGenerated}
          title="Gerar password aleatória"
          data-testid={`${testId || "password"}-generate`}
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export function UserCreateDialog({ open, onOpenChange, onSubmit, saving }) {
  const [form, setForm] = useState({ ...EMPTY_USER_FORM });
  const isParceiro = form.role === "parceiro";

  const handleOpenChange = (next) => {
    if (!next) setForm({ ...EMPTY_USER_FORM });
    onOpenChange(next);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const payload = {
      name: form.name.trim(),
      email: form.email.trim(),
      phone: form.phone.trim(),
      role: form.role,
    };
    if (!isParceiro) payload.password = form.password;
    const ok = await onSubmit(payload);
    if (ok) {
      setForm({ ...EMPTY_USER_FORM });
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto" data-testid="user-create-dialog">
        <DialogHeader>
          <DialogTitle>Novo utilizador</DialogTitle>
          <DialogDescription>
            Crie a conta. Os acessos por empresa (UCR) definem-se depois em Gerir Acessos.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>Nome</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              data-testid="user-create-name"
            />
          </div>
          <div className="space-y-2">
            <Label>
              Email
              {isParceiro ? (
                <span className="text-xs text-muted-foreground ml-1">(opcional)</span>
              ) : null}
            </Label>
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required={!isParceiro}
              data-testid="user-create-email"
            />
          </div>
          <div className="space-y-2">
            <Label>
              Telefone
              <span className="text-xs text-muted-foreground ml-1">(opcional)</span>
            </Label>
            <Input
              type="tel"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              data-testid="user-create-phone"
            />
          </div>
          <div className="space-y-2">
            <Label>Perfil principal</Label>
            <Select
              value={form.role}
              onValueChange={(role) => setForm({ ...form, role })}
            >
              <SelectTrigger data-testid="user-create-role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PRIMARY_ROLE_OPTIONS.map((role) => (
                  <SelectItem key={role} value={role}>
                    {ROLE_LABELS[role]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {isParceiro ? (
              <p className="text-xs text-muted-foreground">
                Parceiros são contas fantasma sem acesso à plataforma.
              </p>
            ) : null}
          </div>
          {!isParceiro ? (
            <PasswordField
              value={form.password}
              onChange={(password) => setForm({ ...form, password })}
              required
              testId="user-create-password"
            />
          ) : null}
          <DialogFooter>
            <Button type="submit" disabled={saving} data-testid="user-create-submit">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Criar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function UserEditDialog({ open, onOpenChange, user, onSubmit, saving }) {
  const [form, setForm] = useState({ name: "", email: "", phone: "" });

  useEffect(() => {
    if (!open) return;
    setForm({
      name: user?.name || "",
      email: user?.email || "",
      phone: user?.phone || "",
    });
  }, [open, user]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    const ok = await onSubmit({
      name: form.name.trim(),
      email: form.email.trim(),
      phone: form.phone.trim(),
    });
    if (ok) onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg" data-testid="user-edit-dialog">
        <DialogHeader>
          <DialogTitle>Editar dados</DialogTitle>
          <DialogDescription>
            Actualize o nome, email e telefone de {user?.name || "utilizador"}.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>Nome</Label>
            <Input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              data-testid="user-edit-name"
            />
          </div>
          <div className="space-y-2">
            <Label>Email</Label>
            <Input
              type="email"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              required={user?.role !== "parceiro"}
              data-testid="user-edit-email"
            />
          </div>
          <div className="space-y-2">
            <Label>
              Telefone
              <span className="text-xs text-muted-foreground ml-1">(opcional)</span>
            </Label>
            <Input
              type="tel"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              data-testid="user-edit-phone"
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={saving} data-testid="user-edit-submit">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Guardar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function UserPasswordDialog({ open, onOpenChange, user, onSubmit, saving }) {
  const [password, setPassword] = useState("");

  const handleOpenChange = (next) => {
    if (!next) setPassword("");
    onOpenChange(next);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!password.trim()) {
      toast.error("Indique a nova password.");
      return;
    }
    const ok = await onSubmit(password);
    if (ok) {
      setPassword("");
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid="user-password-dialog">
        <DialogHeader>
          <DialogTitle>Redefinir password</DialogTitle>
          <DialogDescription>
            Defina uma nova password para {user?.name || "o utilizador"}.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <PasswordField
            value={password}
            onChange={setPassword}
            required
            placeholder="Nova password"
            testId="user-reset-password"
          />
          <DialogFooter>
            <Button type="submit" disabled={saving} data-testid="user-password-submit">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Redefinir"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
