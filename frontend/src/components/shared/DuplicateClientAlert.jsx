/**
 * DuplicateClientAlert — Banner BLOQUEANTE de cliente duplicado (PACOTE 10).
 *
 * PORQUÊ: antes do Pacote 10, tentar criar um cliente com um NIF/Email já
 * existente mostrava apenas um toast genérico que desaparecia sozinho — o
 * utilizador voltava a clicar "Criar" (submissões duplicadas acidentais)
 * sem perceber o problema. Este banner vermelho fica VISÍVEL dentro do
 * formulário, identifica o campo em conflito, nomeia o cliente existente
 * e oferece a acção "Usar cliente existente" quando aplicável.
 *
 * PROGRESSIVE DISCLOSURE: o banner resume o conflito em uma linha; o
 * detalhe (campo em conflito + acções) está expandido mas compacto.
 *
 * USO (CreateClientModal / CreateProcessModal / SecondTitularCard):
 *   const [duplicateError, setDuplicateError] = useState(null);
 *   // no catch do createClient:
 *   const dup = parseDuplicateClientError(createErr);
 *   if (dup) { setDuplicateError(dup); return; }
 *   // nos onChange dos campos NIF/Email: setDuplicateError(null)
 *   // render (dentro do formulário de novo cliente):
 *   <DuplicateClientAlert
 *     duplicate={duplicateError}
 *     onDismiss={() => setDuplicateError(null)}
 *     onUseExisting={dup ? () => handleSelectExistingClient({...}) : undefined}
 *   />
 *
 * @param {object|null} duplicate - Resultado de parseDuplicateClientError (null = escondido)
 * @param {function} [onDismiss] - Limpar o erro (botão ✕)
 * @param {function} [onUseExisting] - Acção "Usar cliente existente" (omitir em clientOnly)
 */
import { AlertTriangle, UserCheck, X } from "lucide-react";
import { Button } from "../ui/button";
import { duplicateFieldLabel } from "../../utils/duplicateClient";

const DuplicateClientAlert = ({ duplicate, onDismiss, onUseExisting }) => {
  if (!duplicate) return null;

  const fieldLabel = duplicateFieldLabel(duplicate.matched_fields);

  return (
    <div
      role="alert"
      data-testid="duplicate-client-alert"
      className="flex items-start gap-2.5 p-3 bg-red-50 dark:bg-red-950/30 border border-red-300 dark:border-red-800 rounded-lg"
    >
      <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
      <div className="flex-1 min-w-0 space-y-1.5">
        <p className="text-sm font-medium text-red-700 dark:text-red-300">
          {duplicate.message}
        </p>
        <p className="text-xs text-red-600/90 dark:text-red-400/90">
          {`O ${fieldLabel} introduzido já pertence a um cliente activo. `}
          {onUseExisting
            ? "Pode usar o cliente existente ou alterar os dados para continuar."
            : "Altere os dados para continuar."}
        </p>
        {onUseExisting && duplicate.existing_client_id && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs border-red-300 dark:border-red-800 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/40"
            onClick={onUseExisting}
            data-testid="duplicate-client-use-existing-btn"
          >
            <UserCheck className="h-3.5 w-3.5 mr-1" />
            Usar cliente existente
          </Button>
        )}
      </div>
      {onDismiss && (
        <button
          type="button"
          onClick={onDismiss}
          className="p-1 hover:bg-red-100 dark:hover:bg-red-900/40 rounded-md transition-colors shrink-0"
          title="Fechar aviso"
          aria-label="Fechar aviso de cliente duplicado"
        >
          <X className="h-3.5 w-3.5 text-red-600 dark:text-red-400" />
        </button>
      )}
    </div>
  );
};

export default DuplicateClientAlert;
