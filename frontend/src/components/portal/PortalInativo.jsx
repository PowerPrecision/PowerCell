import { Lock } from "lucide-react";

/**
 * Ecrã completo do Portal bloqueado (processo inativo).
 *
 * Apresentação pura: a mensagem vem de quem decidiu o bloqueio (o servidor).
 * Não há botão de "tentar de novo": se o processo voltar a uma fase activa o
 * cliente entra pelo login normal, e um botão que não resolve nada convida a
 * insistir.
 *
 * @param {object} props
 * @param {string} props.mensagem Texto do servidor.
 */
export default function PortalInativo({ mensagem }) {
  return (
    <div
      className="min-h-screen flex items-center justify-center bg-background px-4"
      data-testid="portal-inativo"
    >
      <div
        role="alert"
        className="max-w-md w-full rounded-2xl border border-border bg-card p-8 text-center shadow-sm"
      >
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
          <Lock className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
        </div>
        <h1 className="text-lg font-semibold text-foreground">Acesso suspenso</h1>
        <p className="mt-2 text-sm text-muted-foreground">{mensagem}</p>
      </div>
    </div>
  );
}
