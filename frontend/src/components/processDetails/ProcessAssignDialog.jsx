/**
 * Dialog de atribuição multi-assignee (consultores / intermediários / indexação / parceiro).
 * Extraído de ProcessDetails.js.
 */
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Label } from "../ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { Users, Loader2, Lock } from "lucide-react";
import {
  filterByAnyRole,
  filterByRole,
  CONSULTOR_ASSIGNMENT_ROLES,
  DIRECAO_ASSIGNMENT_ROLES,
  INTERMEDIARIO_ASSIGNMENT_ROLES,
  INDEXACAO_ASSIGNMENT_ROLES,
} from "../../utils/roleUtils";
import { safeString } from "../dashboard/DashboardShared";
import EmpresaDoUtilizador from "../shared/EmpresaDoUtilizador";
import { textoDaOpcaoDeUtilizador } from "../../utils/empresaDoUtilizador";

/**
 * Uma secção de escolha múltipla. Quem a OUTRA empresa atribuiu (`so_leitura`, vem do servidor)
 * aparece com cadeado: vê-se, não se tira nem se põe (o servidor mantém-no na mesma).
 */
export function SeccaoDeEquipa({ titulo, vazio, papeis, appUsers, selected, setSelected, testId }) {
  const opcoes = filterByAnyRole(appUsers, papeis).filter((u) => !u.so_leitura);
  const porId = new Map((appUsers || []).map((u) => [u.id, u]));
  return (
    <div data-testid={`seccao-${testId}`}>
      <Label className="text-sm font-medium mb-2 block">{titulo}</Label>
      <div className="border rounded-lg p-3 max-h-48 overflow-y-auto">
        {opcoes.map((u) => (
          <label
            key={u.id}
            className="flex items-center gap-2 py-1.5 cursor-pointer hover:bg-muted px-2 rounded"
          >
            <input
              type="checkbox"
              checked={selected.includes(u.id)}
              onChange={(e) =>
                setSelected(
                  e.target.checked ? [...selected, u.id] : selected.filter((id) => id !== u.id),
                )
              }
              className="rounded border-input"
            />
            <span className="text-sm">{u.name}</span>
            <EmpresaDoUtilizador utilizador={u} />
            <Badge variant="outline" className="text-xs ml-auto">
              {u.role}
            </Badge>
          </label>
        ))}
        {opcoes.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-2">{vazio}</p>
        )}
      </div>
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-2">
          {selected.map((id) => {
            const u = porId.get(id);
            if (!u) return null;
            return (
              <Badge key={id} variant="secondary" className="flex items-center gap-1">
                {u.so_leitura && <Lock className="h-3 w-3" aria-label="Atribuído por outra empresa" />}
                {u.name}
                <EmpresaDoUtilizador utilizador={u} className="bg-transparent px-0" />
                {!u.so_leitura && (
                  <button
                    type="button"
                    onClick={() => setSelected(selected.filter((x) => x !== id))}
                    className="ml-1 hover:text-destructive"
                    aria-label={`Retirar ${u.name}`}
                  >
                    ×
                  </button>
                )}
              </Badge>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function ProcessAssignDialog({
  open,
  onOpenChange,
  clientName,
  processNumber,
  loadingUsers,
  appUsers,
  selectedConsultores,
  setSelectedConsultores,
  selectedMediadores,
  setSelectedMediadores,
  selectedIndexacao,
  setSelectedIndexacao,
  selectedDirecao = [],
  setSelectedDirecao = () => {},
  // Perfil Index activo: só o campo Index (regras do Flavio, Nov 2026).
  soIndex = false,
  selectedParceiro,
  setSelectedParceiro,
  savingAssignment,
  onSave,
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-purple-600" />
            Gerir Atribuições
          </DialogTitle>
          <DialogDescription>
            {soIndex
              ? "Como Index, pode alterar só o Index deste processo. A alteração fica no histórico."
              : "Só aparecem pessoas da empresa com que está a trabalhar. Quem foi atribuído por outra empresa (processo partilhado) aparece com cadeado e não se altera daqui."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          <div className="p-3 bg-gray-50 rounded-lg">
            <p className="font-medium">{safeString(clientName) || "Cliente"}</p>
            <p className="text-sm text-muted-foreground">
              #{safeString(processNumber, "—")}
            </p>
          </div>

          {loadingUsers ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-purple-600" />
              <span className="ml-2 text-sm text-muted-foreground">A carregar utilizadores...</span>
            </div>
          ) : (
            <div className="space-y-4">
              {!soIndex && (
                <>
                  <SeccaoDeEquipa
                    titulo="Consultores"
                    vazio="Nenhum consultor disponível"
                    papeis={CONSULTOR_ASSIGNMENT_ROLES}
                    appUsers={appUsers}
                    selected={selectedConsultores}
                    setSelected={setSelectedConsultores}
                    testId="consultores"
                  />
                  <SeccaoDeEquipa
                    titulo="Intermediários"
                    vazio="Nenhum intermediário disponível"
                    papeis={INTERMEDIARIO_ASSIGNMENT_ROLES}
                    appUsers={appUsers}
                    selected={selectedMediadores}
                    setSelected={setSelectedMediadores}
                    testId="intermediarios"
                  />
                  <SeccaoDeEquipa
                    titulo="Direção"
                    vazio="Nenhum diretor ou CEO disponível"
                    papeis={DIRECAO_ASSIGNMENT_ROLES}
                    appUsers={appUsers}
                    selected={selectedDirecao}
                    setSelected={setSelectedDirecao}
                    testId="direcao"
                  />
                </>
              )}

              <div>
                <Label className="text-sm font-medium">Indexação (Documentos)</Label>
                <Select
                  value={selectedIndexacao || "none"}
                  onValueChange={(v) => setSelectedIndexacao(v === "none" ? "" : v)}
                >
                  <SelectTrigger className="mt-1" data-testid="indexacao-select">
                    <SelectValue placeholder="Seleccionar indexação..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Nenhum</SelectItem>
                    {filterByAnyRole(appUsers, INDEXACAO_ASSIGNMENT_ROLES).map(
                      (u) => (
                        <SelectItem key={u.id} value={u.id}>
                          {textoDaOpcaoDeUtilizador(u)}
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>

              {!soIndex && (
              <div>
                <Label className="text-sm font-medium flex items-center gap-2">
                  Parceiro
                  <span className="text-xs text-muted-foreground font-normal">
                    (Utilizador fantasma - sem acesso)
                  </span>
                </Label>
                <Select
                  value={selectedParceiro || "none"}
                  onValueChange={(v) => setSelectedParceiro(v === "none" ? "" : v)}
                >
                  <SelectTrigger className="mt-1" data-testid="parceiro-select">
                    <SelectValue placeholder="Seleccionar parceiro..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">Nenhum</SelectItem>
                    {filterByRole(appUsers, "parceiro").map((u) => (
                      <SelectItem key={u.id} value={u.id}>
                        {textoDaOpcaoDeUtilizador(u, { comPapel: false })}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={onSave}
            disabled={savingAssignment}
            className="bg-purple-600 hover:bg-purple-700"
          >
            {savingAssignment ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                A guardar...
              </>
            ) : (
              "Guardar"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
