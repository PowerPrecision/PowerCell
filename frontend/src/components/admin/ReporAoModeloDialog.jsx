/**
 * ReporAoModeloDialog — confirmação com PASSWORD de uma acção destrutiva.
 *
 * «Repor ao Modelo» descarta a configuração própria da rede (workflow ou formulário) e
 * volta ao modelo. Não se desfaz, por isso o ecrã pede a password ACTUAL de quem está
 * ligado — e é o SERVIDOR que a valida: este diálogo só a recolhe e a envia.
 *
 * Regras:
 *  - o botão de confirmar só se activa com a password escrita e nunca duas vezes em voo;
 *  - password errada: o campo limpa-se, o foco volta a ele e o erro diz-se no diálogo (não num toast);
 *  - o diálogo NÃO fecha com um erro — fecha só com sucesso ou quando o utilizador cancela;
 *  - a password sai do estado ao fechar (nunca fica em memória à espera do próximo abrir);
 *  - `autoComplete="current-password"`: o gestor de passwords do browser reconhece o campo.
 *
 * @param {boolean}  open
 * @param {function} onOpenChange
 * @param {string}   titulo
 * @param {React.ReactNode} descricao   o que se perde (dito em claro)
 * @param {function} onConfirmar        async (password) => resposta do servidor (lança em erro)
 * @param {function} [onSucesso]        chamada com a resposta depois de repor
 */
import { useEffect, useRef, useState } from "react";
import { AlertTriangle, Loader2, RotateCcw } from "lucide-react";

import { Button } from "../ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "../ui/dialog";
import { Label } from "../ui/label";
import PasswordInput from "../shared/PasswordInput";
import { lerErroDeReposicao } from "../../utils/reporAoModelo";

export default function ReporAoModeloDialog({ open, onOpenChange, titulo, descricao, onConfirmar, onSucesso }) {
  const [password, setPassword] = useState("");
  const [erro, setErro] = useState(null);
  const [aEnviar, setAEnviar] = useState(false);
  const campo = useRef(null);

  // A password não sobrevive ao diálogo.
  useEffect(() => {
    if (!open) {
      setPassword("");
      setErro(null);
      setAEnviar(false);
    }
  }, [open]);

  const confirmar = async (e) => {
    e?.preventDefault?.();
    if (!password || aEnviar) return;
    setAEnviar(true);
    setErro(null);
    try {
      const resposta = await onConfirmar(password);
      setPassword("");
      onOpenChange(false);
      onSucesso?.(resposta?.data ?? resposta);
    } catch (err) {
      const lido = lerErroDeReposicao(err);
      setErro(lido);
      if (lido.tipo === "password_errada") {
        setPassword("");
        campo.current?.focus?.();
      }
    } finally {
      setAEnviar(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(valor) => !aEnviar && onOpenChange(valor)}>
      <DialogContent className="max-w-md" data-testid="repor-modelo-dialog">
        <form onSubmit={confirmar} className="space-y-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
              {titulo}
            </DialogTitle>
            <DialogDescription asChild>
              <div className="space-y-2 text-sm text-muted-foreground">{descricao}</div>
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2">
            <Label htmlFor="repor-modelo-password">A sua password actual</Label>
            <PasswordInput
              id="repor-modelo-password"
              ref={campo}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              autoFocus
              disabled={aEnviar}
              aria-invalid={erro?.tipo === "password_errada" || undefined}
              aria-describedby={erro ? "repor-modelo-erro" : undefined}
              data-testid="repor-modelo-password"
            />
          </div>

          {erro && (
            <div
              id="repor-modelo-erro"
              role="alert"
              data-testid="repor-modelo-erro"
              data-tipo={erro.tipo}
              className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
            >
              <p className="font-medium">{erro.mensagem}</p>
              {erro.fases.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs" data-testid="repor-modelo-fases">
                  {erro.fases.map((f) => (
                    <li key={f.name}>
                      {f.name}: {f.total} processo{f.total === 1 ? "" : "s"}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={aEnviar}>
              Cancelar
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={!password || aEnviar}
              data-testid="repor-modelo-confirmar"
            >
              {aEnviar ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
              ) : (
                <RotateCcw className="mr-2 h-4 w-4" aria-hidden="true" />
              )}
              Repor ao Modelo
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
