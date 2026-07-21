/**
 * MandatoryDocumentsSection — documentos obrigatórios.
 */
import React, { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Badge } from "../../components/ui/badge";
import { Switch } from "../../components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { extractErrorMessage } from "../../utils/extractErrorMessage";
import { toast } from "sonner";
import {
  Save,
  Loader2,
  FileEdit,
  Plus,
  X,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;



// =====================================================================
// PACOTE G — SECÇÃO: Documentos Obrigatórios (mandatory_documents)
// Permite ao CEO/Diretor gerir a checklist de documentos que são pedidos
// automaticamente a cada novo processo (pre_registo ou criação interna).
// =====================================================================
export default function MandatoryDocumentsSection({ token }) {
  const [enabled, setEnabled] = useState(true);
  const [documents, setDocuments] = useState([]);
  const [newName, setNewName] = useState("");
  const [newCategory, setNewCategory] = useState("outros");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const CATEGORIES = [
    { value: "identificacao", label: "Identificação" },
    { value: "irs", label: "IRS" },
    { value: "recibo_vencimento", label: "Recibo de Vencimento" },
    { value: "comprovativo_morada", label: "Comprovativo de Morada" },
    { value: "extrato_bancario", label: "Extrato Bancário" },
    { value: "mapa_responsabilidades", label: "Mapa de Responsabilidades" },
    { value: "caderneta_predial", label: "Caderneta Predial" },
    { value: "certidao_teor", label: "Certidão de Teor" },
    { value: "outros", label: "Outros" },
  ];

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/system-config`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        // PACOTE CY — fix read path: data.config.mandatory_documents (não data.mandatory_documents)
        const md = (data.config && data.config.mandatory_documents) || data.mandatory_documents || {};
        setEnabled(md.enabled !== false);
        setDocuments(Array.isArray(md.documents) ? md.documents : []);
      } else {
        toast.error("Erro ao carregar documentos obrigatórios");
      }
    } catch {
      toast.error("Erro de ligação");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchConfig();
  }, [fetchConfig]);

  const handleAdd = () => {
    const name = newName.trim();
    if (!name) {
      toast.error("Indique um nome para o documento");
      return;
    }
    // Evitar duplicados (case-insensitive)
    if (documents.some((d) => (d.name || "").toLowerCase() === name.toLowerCase())) {
      toast.error("Este documento já está na lista");
      return;
    }
    setDocuments([...documents, { name, category: newCategory }]);
    setNewName("");
  };

  const handleRemove = (idx) => {
    setDocuments(documents.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/system-config/mandatory_documents`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ enabled, documents }),
      });
      if (res.ok) {
        toast.success("Checklist de documentos obrigatórios guardada");
        fetchConfig();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(extractErrorMessage(err.detail, "Erro ao guardar"));
      }
    } catch {
      toast.error("Erro de ligação");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileEdit className="h-5 w-5 text-primary" />
            Documentos Obrigatórios por Defeito
          </CardTitle>
          <CardDescription>
            Lista gerida pelo CEO/Diretor. Quando um processo é criado (via formulário público
            ou criação interna), estes pedidos são gerados automaticamente. Assim que o cliente
            submeter todos, o sistema envia um email de confirmação em nome do intermediário.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between rounded-lg border p-3">
            <div>
              <Label className="font-medium">Ativar checklist automática</Label>
              <p className="text-xs text-muted-foreground mt-0.5">
                Se inativo, novos processos não geram pedidos automáticos.
              </p>
            </div>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </div>

          <div className="rounded-lg border p-3 space-y-3">
            <Label className="font-medium">Adicionar documento</Label>
            <div className="flex flex-col sm:flex-row gap-2">
              <Input
                placeholder="Ex: Bilhete de Identidade / Cartão de Cidadão"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAdd();
                  }
                }}
                className="flex-1"
              />
              <Select value={newCategory} onValueChange={setNewCategory}>
                <SelectTrigger className="w-full sm:w-56">
                  <SelectValue placeholder="Categoria" />
                </SelectTrigger>
                <SelectContent>
                  {CATEGORIES.map((c) => (
                    <SelectItem key={c.value} value={c.value}>
                      {c.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button type="button" onClick={handleAdd} variant="secondary">
                <Plus className="h-4 w-4 mr-1" /> Adicionar
              </Button>
            </div>
          </div>

          {/* PACOTE I — Lista de Etiquetas (Tags): badges com ícone X.
              Layout flex-wrap para os badges fluírem em múltiplas linhas.
              Cada badge mostra o nome do documento + categoria (se não for
              "outros") + botão X para remover. */}
          <div className="flex flex-wrap gap-2 min-h-[3rem] p-3 rounded-lg border bg-muted/30 items-center">
            {documents.length === 0 ? (
              <span className="text-sm text-muted-foreground italic">
                Sem documentos na checklist. Adicione acima para começar.
              </span>
            ) : (
              documents.map((doc, idx) => {
                const cat = CATEGORIES.find((c) => c.value === doc.category);
                const hasCat = doc.category && doc.category !== "outros";
                return (
                  <Badge
                    key={`${doc.name}-${idx}`}
                    variant="secondary"
                    className="pl-3 pr-1 py-1 text-sm gap-1.5"
                  >
                    <span className="truncate max-w-[16rem]">{doc.name}</span>
                    {hasCat && (
                      <Badge variant="outline" className="px-1 py-0 text-[10px] font-normal">
                        {cat?.label || doc.category}
                      </Badge>
                    )}
                    <button
                      type="button"
                      onClick={() => handleRemove(idx)}
                      className="ml-0.5 rounded-full hover:bg-destructive/20 hover:text-destructive p-0.5 transition-colors"
                      aria-label={`Remover ${doc.name}`}
                    >
                      <X className="h-3.5 w-3.5" />
                    </button>
                  </Badge>
                );
              })
            )}
          </div>

          <div className="flex items-center justify-between pt-2 border-t">
            <p className="text-xs text-muted-foreground">
              {documents.length} documento{documents.length !== 1 ? "s" : ""} na checklist
            </p>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Save className="h-4 w-4 mr-2" />}
              Guardar Checklist
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

