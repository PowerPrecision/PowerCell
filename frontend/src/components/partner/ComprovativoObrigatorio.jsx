/**
 * O Comprovativo de Pagamento: a única coisa que liberta uma lead retida.
 *
 * Partilhado pelo detalhe do caso e pelo ecrã de sucesso do registo da lead,
 * para o envio ser o MESMO (mesma categoria, mesmo aviso) nos dois sítios.
 */
import React from "react";
import { Clock } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import PartnerUploadBox from "@/components/partner/PartnerUploadBox";
import { CATEGORIA_DO_COMPROVATIVO } from "@/utils/partnerPortal";

export default function ComprovativoObrigatorio({ caseId, descricao }) {
  return (
    <Card data-testid="comprovativo-obrigatorio" className="border-destructive/40">
      <CardContent className="space-y-3 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="font-medium">Comprovativo de Pagamento</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {descricao || "Obrigatório. Enquanto não o enviar, a lead fica retida e a nossa equipa não a vê."}
            </p>
          </div>
          <Badge variant="destructive" className="gap-1"><Clock className="h-3 w-3" aria-hidden="true" />Obrigatório</Badge>
        </div>
        <PartnerUploadBox
          caseId={caseId}
          categoria={CATEGORIA_DO_COMPROVATIVO}
          rotulo="Enviar comprovativo"
          testId="comprovativo"
        />
      </CardContent>
    </Card>
  );
}
