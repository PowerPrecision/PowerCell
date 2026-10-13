import { ArrowRight, Building2, UserRound } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  caminhosDaLinhagem,
  deveMostrarLinhagem,
  eOFimDoCaminho,
  textoDoCaminho,
} from "@/utils/linhagem";

/**
 * Linhagem do processo no cabeçalho do detalhe: Parceiro → Empresa Y → Empresa Z.
 *
 * A Empresa Y (destino) pode partilhar em cadeia com a Z sem aprovação do parceiro
 * angariador; quem VÊ o processo vê de onde veio e onde está. Um caminho por folha
 * (se a Y partilhou com duas empresas, são duas linhas); o último nó de cada caminho
 * é onde o processo está agora. Só leitura — retirar um elo faz-se no cartão
 * «Partilhado com».
 *
 * Não desenha nada quando não há mais do que a casa dona (a etiqueta da empresa já
 * diz tudo): ver `deveMostrarLinhagem`.
 *
 * @param {{linhagem?: object|null}} props `linhagem` tal como vem do servidor.
 */
export default function LinhagemDoProcesso({ linhagem }) {
  if (!deveMostrarLinhagem(linhagem)) return null;
  const caminhos = caminhosDaLinhagem(linhagem);

  return (
    <div className="basis-full space-y-1" data-testid="linhagem-do-processo">
      <span className="sr-only">Linhagem do processo</span>
      {caminhos.map((caminho, i) => (
        <ol
          key={i}
          className="flex flex-wrap items-center gap-1 text-xs"
          aria-label={`Linhagem: ${textoDoCaminho(caminho)}`}
          data-testid="linhagem-caminho"
        >
          {caminho.map((no, j) => {
            const agora = eOFimDoCaminho(caminho, j);
            const eParceiro = no.tipo === "parceiro";
            return (
              <li key={`${no.nome}-${j}`} className="flex items-center gap-1">
                {j > 0 && <ArrowRight className="h-3 w-3 text-muted-foreground" aria-hidden="true" />}
                <Badge
                  variant={agora ? "default" : eParceiro ? "outline" : "secondary"}
                  className="gap-1 font-medium"
                  title={
                    eParceiro
                      ? "Parceiro angariador"
                      : no.papel === "dona"
                        ? "Empresa dona do processo"
                        : no.partilhado_por
                          ? `Partilhado por ${no.partilhado_por}`
                          : "Empresa convidada"
                  }
                  data-testid={eParceiro ? "linhagem-parceiro" : "linhagem-empresa"}
                  aria-current={agora ? "true" : undefined}
                >
                  {eParceiro ? (
                    <UserRound className="h-3 w-3 shrink-0" aria-hidden="true" />
                  ) : (
                    <Building2 className="h-3 w-3 shrink-0" aria-hidden="true" />
                  )}
                  <span>{eParceiro ? `Parceiro ${no.nome}` : no.nome}</span>
                  {agora && !eParceiro && <span className="opacity-80">· aqui</span>}
                </Badge>
              </li>
            );
          })}
        </ol>
      ))}
    </div>
  );
}
