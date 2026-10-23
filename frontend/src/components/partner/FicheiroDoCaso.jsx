/**
 * Uma linha de ficheiro: nome, quem enviou, tamanho e descarga.
 *
 * O parceiro nunca nomeia uma chave S3: pede a descarga por `file_id` e o
 * servidor resolve-o entre os ficheiros que ele pode ver.
 */
import React, { useState } from "react";
import { Download, File as FicheiroGenerico, FileImage, FileText, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { obterUrlDeDescarga } from "@/services/partnerApi";
import { etiquetaDoTitular, formatarData, mensagemDeErro, podeDescarregar, rotuloDeAutoria, tamanhoLegivel, tipoDeFicheiro } from "@/utils/partnerPortal";

/** O estado de cada ficheiro, na linguagem do parceiro. «Recebido» é o de todos; o comprovativo de
 *  pagamento segue a validação financeira da equipa. Um estado que o servidor não conheça cai em
 *  «Recebido» em vez de inventar um rótulo. */
export const ROTULO_DO_ESTADO = {
  recebido: "Recebido",
  em_validacao: "Em validação",
  validado: "Validado",
  rejeitado: "Rejeitado",
};

const ICONE_POR_TIPO = { pdf: FileText, imagem: FileImage, documento: FileText, outro: FicheiroGenerico };

export default function FicheiroDoCaso({ caseId, ficheiro, dentroDoPedido = false, titulares = [] }) {
  const [aObter, setAObter] = useState(false);
  const [erro, setErro] = useState("");

  const descarregar = async () => {
    setAObter(true);
    setErro("");
    try {
      const r = await obterUrlDeDescarga(caseId, ficheiro.id);
      // Noutro separador, sem `opener`: o URL é do S3, não é nosso.
      window.open(r.url, "_blank", "noopener,noreferrer");
    } catch (e) {
      setErro(mensagemDeErro(e, "Não foi possível obter o ficheiro."));
    } finally {
      setAObter(false);
    }
  };

  const detalhe = [
    ficheiro.category_label,
    rotuloDeAutoria(ficheiro.by),
    tamanhoLegivel(ficheiro.file_size),
    formatarData(ficheiro.uploaded_at),
  ]
    .filter(Boolean)
    .join(" · ");
  // O que o próprio parceiro submeteu não se descarrega de volta (o servidor
  // também o recusa; esconder o botão é só a cortesia).
  const comDescarga = podeDescarregar(ficheiro);

  const estado = ROTULO_DO_ESTADO[ficheiro.estado] ? ficheiro.estado : "recebido";
  // Dentro de um pedido o cartão já diz «Recebido»: repetir o mesmo rótulo em cada ficheiro era
  // ruído. Só se acrescenta quando o ficheiro tem um estado PRÓPRIO (o comprovativo).
  const mostrarEstado = !dentroDoPedido || estado !== "recebido";
  const { tipo, extensao } = tipoDeFicheiro(ficheiro.filename);
  const Icone = ICONE_POR_TIPO[tipo];
  const doTitular = etiquetaDoTitular(ficheiro, titulares);

  return (
    <li
      data-tipo={tipo}
      className="flex items-center justify-between gap-3 rounded-md border-2 border-border bg-secondary/40 px-3 py-2"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 flex-col items-center justify-center rounded-md border border-border bg-background">
          <Icone className="h-4 w-4 text-foreground" aria-hidden="true" />
          {extensao ? <span className="text-[9px] font-bold leading-none text-muted-foreground">{extensao}</span> : null}
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{ficheiro.filename || "Ficheiro"}</p>
          {doTitular && (
            <Badge variant="secondary" data-testid="titular-do-ficheiro" data-titular={ficheiro.titular} className="mt-0.5">
              {doTitular}
            </Badge>
          )}
          <p className="text-xs text-muted-foreground">{detalhe}</p>
          {erro && <p role="alert" className="text-xs text-destructive">{erro}</p>}
        </div>
      </div>
      {mostrarEstado && (
        <Badge
          variant={estado === "rejeitado" ? "destructive" : "outline"}
          data-testid="estado-do-ficheiro"
          data-estado={estado}
          className="shrink-0"
        >
          {ROTULO_DO_ESTADO[estado]}
        </Badge>
      )}
      {comDescarga && (
        <Button type="button" size="sm" variant="ghost" onClick={descarregar} disabled={aObter} aria-label={`Descarregar ${ficheiro.filename || "ficheiro"}`}>
          {aObter ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
        </Button>
      )}
    </li>
  );
}
