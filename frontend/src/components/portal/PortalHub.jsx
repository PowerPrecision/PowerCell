import { ChevronRight, Loader2, LogOut } from "lucide-react";

import { detalheDoProcesso, listaDeProcessos, rotuloDoProcesso } from "../../utils/portalHub";

/**
 * O Hub do Portal (D-42): o cliente tem mais do que um processo activo — «Crédito Habitação ·
 * Power Real Estate», «Crédito Pessoal · Domus» — e escolhe qual consulta.
 *
 * Apresentação pura: não faz pedidos nem guarda nada (isso é do `PortalHubEcra`). Cada processo é
 * um botão com nome acessível «Tipo · Empresa», para o leitor de ecrã e para os testes.
 *
 * @param {object} props
 * @param {string} [props.nome] Nome do cliente.
 * @param {Array} props.processos Os processos activos (`utils/portalHub`).
 * @param {string|null} [props.aEscolher] id do processo cujo pedido está a decorrer.
 * @param {string|null} [props.erro] Mensagem a mostrar (escolha recusada, sessão…).
 * @param {(id: string) => void} props.onEscolher
 * @param {() => void} [props.onSair]
 */
export default function PortalHub({ nome, processos, aEscolher = null, erro = null, onEscolher, onSair }) {
  const lista = listaDeProcessos(processos);

  return (
    <div className="min-h-screen bg-background px-4 py-10" data-testid="portal-hub">
      <div className="mx-auto w-full max-w-xl">
        <header className="mb-6 text-center">
          <h1 className="text-xl font-semibold text-foreground">
            {nome ? `Olá, ${nome}` : "Os seus processos"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Tem {lista.length} processos activos. Escolha qual quer consultar.
          </p>
        </header>

        {erro && (
          <div
            role="alert"
            data-testid="portal-hub-erro"
            className="mb-4 rounded-lg border border-border bg-muted px-4 py-3 text-sm text-foreground"
          >
            {erro}
          </div>
        )}

        <ul className="space-y-3">
          {lista.map((processo) => {
            const ocupado = aEscolher === processo.id;
            const detalhe = detalheDoProcesso(processo);
            return (
              <li key={processo.id}>
                <button
                  type="button"
                  disabled={Boolean(aEscolher)}
                  onClick={() => onEscolher(processo.id)}
                  aria-label={rotuloDoProcesso(processo)}
                  data-testid={`portal-hub-processo-${processo.id}`}
                  className="flex w-full items-center gap-3 rounded-xl border border-border bg-card p-4 text-left shadow-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-70"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-base font-medium text-foreground">
                      {rotuloDoProcesso(processo)}
                    </span>
                    {detalhe && (
                      <span className="mt-0.5 block truncate text-sm text-muted-foreground">{detalhe}</span>
                    )}
                  </span>
                  {ocupado ? (
                    <Loader2 className="h-4 w-4 shrink-0 animate-spin text-muted-foreground" aria-hidden="true" />
                  ) : (
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  )}
                </button>
              </li>
            );
          })}
        </ul>

        {onSair && (
          <div className="mt-8 text-center">
            <button
              type="button"
              onClick={onSair}
              className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
              Sair
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
