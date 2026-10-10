/**
 * PasswordInput — campo de palavra-passe com o «olho» que mostra/oculta o texto.
 *
 * É um `Input` normal: recebe as mesmas props (id, value, onChange,
 * autoComplete…), por isso o `<Label htmlFor>` continua a associar-se ao CAMPO
 * e não ao botão. O botão tem nome acessível próprio («Mostrar palavra-passe» /
 * «Ocultar palavra-passe») e `aria-pressed`, e nunca é alcançado pela tecla
 * Tab antes do campo seguinte do formulário (`tabIndex={-1}` seria um defeito
 * de acessibilidade: o utilizador de teclado também quer o olho).
 */
import { forwardRef, useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { Input } from "../ui/input";
import { cn } from "../../lib/utils";

const PasswordInput = forwardRef(function PasswordInput({ className, disabled, ...props }, ref) {
  const [visivel, setVisivel] = useState(false);
  const rotulo = visivel ? "Ocultar palavra-passe" : "Mostrar palavra-passe";

  return (
    <div className="relative">
      <Input
        ref={ref}
        {...props}
        disabled={disabled}
        type={visivel ? "text" : "password"}
        className={cn("pr-10", className)}
      />
      <button
        type="button"
        onClick={() => setVisivel((v) => !v)}
        disabled={disabled}
        aria-label={rotulo}
        aria-pressed={visivel}
        title={rotulo}
        data-testid="alternar-palavra-passe"
        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-md text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
      >
        {visivel ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
      </button>
    </div>
  );
});

export default PasswordInput;
