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
import { Users, Loader2 } from "lucide-react";
import { filterByAnyRole, filterByRole } from "../../utils/roleUtils";
import { safeString } from "../dashboard/DashboardShared";

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
            Seleccione os utilizadores a atribuir a este processo.
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
              <div>
                <Label className="text-sm font-medium mb-2 block">Consultores</Label>
                <div className="border rounded-lg p-3 max-h-48 overflow-y-auto">
                  {filterByAnyRole(appUsers, ["consultor", "diretor", "admin", "ceo", "administrativo"]).map((u) => (
                    <label
                      key={u.id}
                      className="flex items-center gap-2 py-1.5 cursor-pointer hover:bg-gray-50 px-2 rounded"
                    >
                      <input
                        type="checkbox"
                        checked={selectedConsultores.includes(u.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedConsultores([...selectedConsultores, u.id]);
                          } else {
                            setSelectedConsultores(selectedConsultores.filter((id) => id !== u.id));
                          }
                        }}
                        className="rounded border-gray-300"
                      />
                      <span className="text-sm">{u.name}</span>
                      <Badge variant="outline" className="text-xs ml-auto">
                        {u.role}
                      </Badge>
                    </label>
                  ))}
                  {filterByAnyRole(appUsers, ["consultor", "diretor", "admin", "ceo", "administrativo"]).length ===
                    0 && (
                    <p className="text-sm text-muted-foreground text-center py-2">
                      Nenhum consultor disponível
                    </p>
                  )}
                </div>
                {selectedConsultores.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {selectedConsultores.map((cid) => {
                      const u = appUsers.find((x) => x.id === cid);
                      return u ? (
                        <Badge key={cid} variant="secondary" className="flex items-center gap-1">
                          {u.name}
                          <button
                            type="button"
                            onClick={() =>
                              setSelectedConsultores(selectedConsultores.filter((id) => id !== cid))
                            }
                            className="ml-1 hover:text-destructive"
                          >
                            ×
                          </button>
                        </Badge>
                      ) : null;
                    })}
                  </div>
                )}
              </div>

              <div>
                <Label className="text-sm font-medium mb-2 block">Intermediários</Label>
                <div className="border rounded-lg p-3 max-h-48 overflow-y-auto">
                  {filterByAnyRole(appUsers, [
                    "intermediario",
                    "intermediario_credito",
                    "diretor",
                  ]).map((u) => (
                    <label
                      key={u.id}
                      className="flex items-center gap-2 py-1.5 cursor-pointer hover:bg-gray-50 px-2 rounded"
                    >
                      <input
                        type="checkbox"
                        checked={selectedMediadores.includes(u.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedMediadores([...selectedMediadores, u.id]);
                          } else {
                            setSelectedMediadores(selectedMediadores.filter((id) => id !== u.id));
                          }
                        }}
                        className="rounded border-gray-300"
                      />
                      <span className="text-sm">{u.name}</span>
                      <Badge variant="outline" className="text-xs ml-auto">
                        {u.role}
                      </Badge>
                    </label>
                  ))}
                  {filterByAnyRole(appUsers, [
                    "intermediario",
                    "intermediario",
                    "intermediario_credito",
                    "diretor",
                  ]).length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-2">
                      Nenhum intermediário disponível
                    </p>
                  )}
                </div>
                {selectedMediadores.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {selectedMediadores.map((mid) => {
                      const u = appUsers.find((x) => x.id === mid);
                      return u ? (
                        <Badge key={mid} variant="secondary" className="flex items-center gap-1">
                          {u.name}
                          <button
                            type="button"
                            onClick={() =>
                              setSelectedMediadores(selectedMediadores.filter((id) => id !== mid))
                            }
                            className="ml-1 hover:text-destructive"
                          >
                            ×
                          </button>
                        </Badge>
                      ) : null;
                    })}
                  </div>
                )}
              </div>

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
                    {filterByAnyRole(appUsers, ["indexacao", "administrativo", "admin", "ceo"]).map(
                      (u) => (
                        <SelectItem key={u.id} value={u.id}>
                          {u.name} ({u.role})
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>

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
                        {u.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
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
