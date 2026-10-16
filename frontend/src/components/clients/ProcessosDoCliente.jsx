/**
 * «Processos do cliente» — navegação rápida a partir da modal de detalhes (Lote 7.3).
 *
 * Apresentação pura: a LISTA vem do servidor (`GET /clients/{id}` → `processes`), que já a recorta pela
 * empresa activa do cabeçalho e pelos processos partilhados com ela (`client_window`; a um visitante B2B
 * só chegam os partilhados). Este componente não filtra nem infere nada — um filtro do lado do ecrã seria
 * uma segunda fronteira, e a que divergir deixa ver o que não devia.
 */
import { ExternalLink, FolderOpen } from "lucide-react";
import { Badge } from "../ui/badge";

/** Só o que tem `id` pode ser aberto: uma linha sem destino é texto morto. */
export function processosAbriveis(processes) {
  return (Array.isArray(processes) ? processes : []).filter(
    (p) => p && typeof p === "object" && typeof p.id === "string" && p.id,
  );
}

export function rotaDoProcesso(id) {
  return `/processo/${encodeURIComponent(id)}`;
}

export default function ProcessosDoCliente({ processes, onAbrir }) {
  const lista = processosAbriveis(processes);

  return (
    <section aria-label="Processos do cliente" data-testid="processos-do-cliente">
      <h4 className="font-semibold text-sm text-muted-foreground uppercase tracking-wide flex items-center gap-2 mb-2">
        <FolderOpen className="h-4 w-4" />
        Processos ({lista.length})
      </h4>
      {lista.length === 0 ? (
        <p className="text-sm text-muted-foreground">Sem processos nesta empresa.</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {lista.map((p) => (
            <li key={p.id} className="flex items-center gap-3 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium truncate">
                  {p.process_number ? `Processo ${p.process_number}` : "Processo"}
                  {p.process_type ? <span className="text-muted-foreground font-normal"> · {String(p.process_type)}</span> : null}
                </p>
                <div className="flex items-center gap-2 mt-0.5">
                  {p.status_label || p.status ? (
                    <Badge variant="outline" style={p.status_color ? { borderColor: p.status_color } : undefined}>
                      {String(p.status_label || p.status)}
                    </Badge>
                  ) : null}
                  {p.client_role ? <span className="text-xs text-muted-foreground">{p.client_role}</span> : null}
                </div>
              </div>
              <a
                href={rotaDoProcesso(p.id)}
                className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline shrink-0"
                aria-label={`Abrir processo ${p.process_number || p.id}`}
                onClick={(e) => {
                  if (onAbrir) {
                    e.preventDefault();
                    onAbrir(p.id);
                  }
                }}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Abrir
              </a>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
