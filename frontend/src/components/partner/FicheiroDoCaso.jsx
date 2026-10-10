/**
 * Uma linha de ficheiro: nome, quem enviou, tamanho e descarga.
 *
 * O parceiro nunca nomeia uma chave S3: pede a descarga por `file_id` e o
 * servidor resolve-o entre os ficheiros que ele pode ver.
 */
import React, { useState } from "react";
import { Download, FileText, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { obterUrlDeDescarga } from "@/services/partnerApi";
import { formatarData, mensagemDeErro, rotuloDeAutoria, tamanhoLegivel } from "@/utils/partnerPortal";

export default function FicheiroDoCaso({ caseId, ficheiro }) {
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

  const detalhe = [rotuloDeAutoria(ficheiro.by), tamanhoLegivel(ficheiro.file_size), formatarData(ficheiro.uploaded_at)]
    .filter(Boolean)
    .join(" · ");

  return (
    <li className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2">
      <div className="flex min-w-0 items-center gap-2">
        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <div className="min-w-0">
          <p className="truncate text-sm">{ficheiro.filename || "Ficheiro"}</p>
          <p className="text-xs text-muted-foreground">{detalhe}</p>
          {erro && <p role="alert" className="text-xs text-destructive">{erro}</p>}
        </div>
      </div>
      <Button type="button" size="sm" variant="ghost" onClick={descarregar} disabled={aObter} aria-label={`Descarregar ${ficheiro.filename || "ficheiro"}`}>
        {aObter ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Download className="h-4 w-4" aria-hidden="true" />}
      </Button>
    </li>
  );
}
