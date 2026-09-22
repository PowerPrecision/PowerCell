/**
 * EmpresaNifDialog — NIF da empresa antes do upload (Épico 8, Eixo 2).
 *
 * O perfil de indexação tem de identificar a empresa a que os documentos
 * pertencem antes de os carregar. Verificado o NIF, o diálogo mostra os
 * processos já existentes dessa empresa para o utilizador confirmar que
 * está no sítio certo.
 *
 * COMPONENTE DE APRESENTAÇÃO: não carrega nada. Cancelar devolve a
 * intenção; é o contentor que limpa os ficheiros pendentes e o campo de
 * ficheiro — se ele não o fizer, o mesmo ficheiro não volta a poder ser
 * escolhido (o `input` não dispara `change` para o mesmo valor).
 */
import { AlertTriangle, Building2, CheckCircle, Loader2, Search, Upload } from "lucide-react";

import { Badge } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Input } from "../../ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../ui/dialog";

/**
 * @param {Object} props
 * @param {boolean} props.open
 * @param {Array<File>} [props.files] - Ficheiros à espera do NIF.
 * @param {string} props.nif - NIF em edição (controlado, 9 dígitos).
 * @param {boolean} [props.checking] - Verificação em curso.
 * @param {Array<Object>|null} [props.existingProcesses] - Processos da empresa.
 * @param {(cor: string) => string} props.contrastColorOf - Contraste do texto
 *   sobre a cor do estado; vem do contentor por ser util partilhado.
 * @param {(nif: string) => void} props.onNifChange
 * @param {() => void} props.onVerify
 * @param {() => void} props.onConfirm
 * @param {() => void} props.onCancel
 */
export default function EmpresaNifDialog({
  open,
  files = [],
  nif = "",
  checking = false,
  existingProcesses,
  contrastColorOf,
  onNifChange,
  onVerify,
  onConfirm,
  onCancel,
}) {
  return (
  <Dialog open={open} onOpenChange={(aberto) => !aberto && onCancel()}>
    <DialogContent className="sm:max-w-lg">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-blue-600" />
          NIF da Empresa
        </DialogTitle>
        <DialogDescription>
          Para concluir o upload, é obrigatório indicar o NIF da empresa onde o cliente trabalha.
          <br />
          <span className="text-sm text-muted-foreground mt-1 block">
            {files?.length || 0} ficheiro(s) selecionado(s) para upload.
          </span>
        </DialogDescription>
      </DialogHeader>
      
      <div className="space-y-4 py-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">NIF da Empresa (9 dígitos)</label>
          <div className="flex gap-2">
            <Input
              placeholder="Ex: 509123456"
              value={nif}
              onChange={(evento) => onNifChange(evento.target.value.replace(/\D/g, "").slice(0, 9))}
              maxLength={9}
              className="flex-1"
            />
            <Button
              variant="outline"
              onClick={onVerify}
              disabled={nif.length !== 9 || checking}
              aria-label="Verificar NIF"
            >
              {checking ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Search className="h-4 w-4" />
              )}
              Verificar
            </Button>
          </div>
        </div>

        {/* Resultado da verificação */}
        {existingProcesses && (
          <div className={`rounded-lg border p-4 ${
            existingProcesses.exists 
              ? 'bg-amber-50 border-amber-200 dark:bg-amber-950/30 dark:border-amber-800' 
              : 'bg-green-50 border-green-200 dark:bg-green-950/30 dark:border-green-800'
          }`}>
            {existingProcesses.exists ? (
              <>
                <div className="flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-amber-800 dark:text-amber-200">
                      Este NIF já foi utilizado em {existingProcesses.total_count} processo(s)
                    </p>
                    <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                      Documentos desta empresa já foram enviados para os seguintes balcões:
                    </p>
                  </div>
                </div>
                
                <div className="mt-3 max-h-40 overflow-y-auto space-y-2">
                  {existingProcesses.processes.map((proc, idx) => (
                    <div 
                      key={idx}
                      className="flex items-center justify-between p-2 rounded bg-white/50 dark:bg-black/20 border border-amber-100 dark:border-amber-900"
                    >
                      <div>
                        <p className="font-medium text-sm">{proc.client_name}</p>
                        {proc.employer_name && (
                          <p className="text-xs text-muted-foreground">{proc.employer_name}</p>
                        )}
                      </div>
                      <div className="text-right">
                        <Badge 
                          style={{ 
                            backgroundColor: proc.status_color || '#6B7280',
                            color: contrastColorOf(proc.status_color),
                            fontSize: '10px'
                          }}
                        >
                          {proc.status_label}
                        </Badge>
                        {(proc.consultor_name || proc.mediador_name) && (
                          <p className="text-xs text-muted-foreground mt-1">
                            {proc.consultor_name || proc.mediador_name}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-3">
                  Pode prosseguir com o upload mesmo assim. Este aviso é apenas informativo.
                </p>
              </>
            ) : (
              <div className="flex items-center gap-3">
                <CheckCircle className="h-5 w-5 text-green-600" />
                <div>
                  <p className="font-medium text-green-800 dark:text-green-200">
                    NIF não registado anteriormente
                  </p>
                  <p className="text-sm text-green-700 dark:text-green-300">
                    Este NIF de empresa ainda não foi utilizado em nenhum processo.
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <DialogFooter className="flex gap-2">
        <Button
          variant="outline"
          onClick={onCancel}
        >
          Cancelar
        </Button>
        <Button
          onClick={onConfirm}
          disabled={nif.length !== 9}
          className="bg-teal-600 hover:bg-teal-700"
        >
          <Upload className="h-4 w-4 mr-2" />
          Confirmar Upload
        </Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
  );
}
