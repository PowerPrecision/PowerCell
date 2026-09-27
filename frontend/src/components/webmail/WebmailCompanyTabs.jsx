/**
 * WebmailCompanyTabs — a barra de Empresas do Webmail (Ponto 8, Fase 3).
 *
 * PORQUÊ: a empresa era um estado escondido no Context Switcher do
 * cabeçalho do CRM, e o utilizador multi-perfil tinha de trocar de
 * perfil para ver a caixa certa. Aqui a empresa é o sítio ONDE SE ESTÁ:
 * clica-se no separador e a caixa é aquela. O `company_id` viaja com
 * cada pedido (Fase 1), e o backend recusa com 404 qualquer empresa fora
 * dos UCRs do utilizador.
 *
 * ZERO RUÍDO: com uma empresa só, este componente não desenha nada — a
 * decisão vive em `deveMostrarSeparadores`, não num `length > 1` solto
 * no meio do JSX.
 *
 * O indicador de sincronização vive AQUI, e não na barra lateral, onde
 * era um botão de largura total. A sincronização é uma operação de
 * fundo: o que interessa é saber se a caixa está actualizada, e isso
 * cabe numa linha ao lado do nome da empresa.
 *
 * Componente de APRESENTAÇÃO: diz o que aconteceu
 * (`onSelectCompany(id)`, `onSync()`) e não sabe pedir nada.
 */
import { Tabs, TabsList, TabsTrigger } from "../ui/tabs";
import { Button } from "../ui/button";
import { Building2, RefreshCw, Loader2 } from "lucide-react";
import {
  deveMostrarSeparadores,
  rotuloDaEmpresa,
  estadoDaSincronizacao,
} from "../../utils/webmailEmpresas";

const TOM_DO_ESTADO = {
  "a-sincronizar": "text-primary",
  actualizado: "text-muted-foreground",
  desactualizado: "text-muted-foreground",
  "por-sincronizar": "text-muted-foreground",
};

/**
 * @param {object} props
 * @param {Array<{company_id: string, company_name: string}>} props.empresas
 * @param {string} props.empresaActivaId
 * @param {(companyId: string) => void} props.onSelectCompany
 * @param {boolean} [props.syncing]
 * @param {Date|null} [props.ultimaSinc]
 * @param {() => void} props.onSync
 */
export default function WebmailCompanyTabs({
  empresas,
  empresaActivaId,
  onSelectCompany,
  syncing = false,
  ultimaSinc = null,
  onSync,
}) {
  const sinc = estadoDaSincronizacao({ syncing, ultimaSinc });
  const mostrarSeparadores = deveMostrarSeparadores(empresas);

  return (
    <div
      className="flex items-center justify-between gap-3 px-3 py-1.5 border-b bg-muted/30"
      data-testid="webmail-company-bar"
    >
      {mostrarSeparadores ? (
        <Tabs
          value={empresaActivaId || ""}
          onValueChange={onSelectCompany}
          className="min-w-0"
        >
          <TabsList className="h-8 bg-transparent p-0 gap-1">
            {empresas.map((empresa) => (
              <TabsTrigger
                key={empresa.company_id}
                value={empresa.company_id}
                className="h-7 gap-1.5 text-xs data-[state=active]:bg-background
                           data-[state=active]:shadow-sm"
              >
                <Building2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                <span className="truncate max-w-[160px]">
                  {rotuloDaEmpresa(empresa)}
                </span>
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      ) : (
        // Uma empresa só: sem separador solitário. O nome fica como
        // rótulo discreto — o utilizador continua a saber em que caixa
        // está, sem lhe dar uma escolha que não existe.
        <span
          className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground
                     truncate min-w-0"
          data-testid="webmail-empresa-unica"
        >
          <Building2 className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {rotuloDaEmpresa(empresas?.[0])}
        </span>
      )}

      <div className="flex items-center gap-2 shrink-0">
        <span
          className={`text-[11px] tabular-nums ${TOM_DO_ESTADO[sinc.estado] || ""}`}
          data-testid="webmail-estado-sinc"
        >
          {sinc.texto}
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={onSync}
          disabled={sinc.emCurso}
          aria-label="Sincronizar caixa de correio"
          title="Sincronizar caixa de correio"
        >
          {sinc.emCurso ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>
    </div>
  );
}
