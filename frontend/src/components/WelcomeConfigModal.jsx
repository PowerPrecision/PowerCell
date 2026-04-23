/**
 * WelcomeConfigModal — Pop-up de configuração de email no login.
 *
 * Quando um utilizador faz login e o seu perfil não tem email configurado
 * (email_configured = false no /auth/me), esta modal é exibida.
 *
 * COMPORTAMENTO:
 * - Mostra uma mensagem amigável a explicar a importância da configuração
 * - Botão principal: redireciona para "O Meu Perfil" (configurações de email)
 * - Botão secundário: "Lembrar-me mais tarde" — guarda flag em sessionStorage
 *   para não voltar a mostrar durante a sessão actual
 * - Não aparece se o utilizador está em modo de impersonate
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Button } from "./ui/button";
import { Mail, ExternalLink, X } from "lucide-react";
import { hasRole } from "../utils/roleUtils";

const DISMISSED_KEY = "email_config_dismissed";

const WelcomeConfigModal = () => {
  const { user, isImpersonating } = useAuth();
  const navigate = useNavigate();

  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!user) return;

    // Não mostrar se:
    // - Utilizador está em modo de impersonate
    // - Já tem email configurado
    // - Já dispensou nesta sessão
    // - Perfil de indexação (utilizam conta partilhada centralizada)
    if (isImpersonating) return;
    if (user.email_configured) return;
    if (hasRole(user, 'indexacao')) return;
    if (sessionStorage.getItem(DISMISSED_KEY)) return;

    // Pequeno delay para não colidir com a transição de login → dashboard
    const timer = setTimeout(() => setOpen(true), 1200);
    return () => clearTimeout(timer);
  }, [user, isImpersonating]);

  const handleGoToProfile = () => {
    setOpen(false);
    navigate("/meu-perfil");
  };

  const handleDismiss = () => {
    setOpen(false);
    sessionStorage.setItem(DISMISSED_KEY, "true");
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent className="sm:max-w-md" aria-describedby="email-config-description">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-lg">
            <Mail className="h-5 w-5 text-primary" />
            Configurar Email de Sincronização
          </DialogTitle>
          <DialogDescription id="email-config-description">
            Olá! Notámos que ainda não configurou o seu email para
            sincronização. Para tirar o máximo partido do CRM, por
            favor configure agora.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-lg border bg-muted/50 p-4 text-sm text-muted-foreground space-y-2">
          <p>
            Com o email configurado poderá:
          </p>
          <ul className="list-disc list-inside space-y-1 ml-1">
            <li>Receber notificações de novos processos</li>
            <li>Sincronizar emails automaticamente</li>
            <li>Enviar documentos diretamente do CRM</li>
            <li>Aceder ao webmail integrado</li>
          </ul>
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-row">
          <Button
            variant="outline"
            onClick={handleDismiss}
            className="gap-2"
          >
            <X className="h-4 w-4" />
            Lembrar-me mais tarde
          </Button>
          <Button
            onClick={handleGoToProfile}
            className="gap-2"
          >
            <ExternalLink className="h-4 w-4" />
            Configurar Agora
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default WelcomeConfigModal;
