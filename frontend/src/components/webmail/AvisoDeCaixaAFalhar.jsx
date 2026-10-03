/**
 * O aviso de que uma caixa de correio deixou de receber email (Lote 7, ponto 4).
 *
 * PORQUE É QUE ISTO TEM DE EXISTIR
 * ================================
 * Quando a password do IMAP expira, a sincronização MANUAL falha o job e o
 * ecrã mostra um toast — que desaparece. A sincronização AUTOMÁTICA, de 10 em
 * 10 minutos, é a que mantém a caixa fresca e morria num `logger.warning` no
 * servidor: a caixa deixava de receber email e o ecrã mostrava **a lista
 * antiga, sem um único aviso**. O utilizador descobre dias depois, e o
 * diagnóstico natural («o servidor está em baixo») aponta para o sítio errado.
 *
 * Um toast informa quem está a olhar no momento exacto. Isto é um estado: fica
 * no ecrã enquanto o problema existir e desaparece quando a próxima
 * sincronização correr bem.
 *
 * DUAS DECISÕES
 * =============
 * 1. **Só aparece para a falha que a PESSOA tem de resolver** (credenciais
 *    recusadas). Um servidor inatingível passa sozinho, e avisar dos dois com
 *    a mesma força ensina a ignorar os dois.
 * 2. **Não é um `Alert` destrutivo com um ícone de erro vermelho** sobre a
 *    lista de emails: é uma faixa com a acção lá dentro. O objectivo é que a
 *    pessoa vá mudar a password, não que feche o aviso.
 */
import { AlertTriangle } from "lucide-react";
import { Link } from "react-router-dom";

import { contasComProblema, textoDoAviso } from "@/utils/saudeDaCaixa";

export default function AvisoDeCaixaAFalhar({ contas }) {
  const comProblema = contasComProblema(contas);
  if (comProblema.length === 0) return null;

  return (
    <div
      className="border-b border-destructive/40 bg-destructive/10 px-4 py-2.5"
      role="status"
      data-testid="aviso-caixa-a-falhar"
    >
      <div className="flex items-start gap-2.5">
        <AlertTriangle
          className="mt-0.5 h-4 w-4 flex-shrink-0 text-destructive"
          aria-hidden="true"
        />
        <div className="min-w-0 space-y-1">
          {comProblema.map((conta) => (
            <p key={conta.email_address || conta.id} className="text-xs">
              <span className="font-medium">
                {conta.label || conta.email_address}
              </span>
              {" — "}
              <span className="text-muted-foreground">
                {textoDoAviso(conta)}
              </span>
            </p>
          ))}
          <Link
            to="/perfil?tab=webmail"
            className="inline-block text-xs font-medium text-destructive hover:underline"
            data-testid="aviso-caixa-corrigir"
          >
            Corrigir as credenciais
          </Link>
        </div>
      </div>
    </div>
  );
}
