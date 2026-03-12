/**
 * DataConflictResolver - Resolução de Conflitos de Dados IA
 * 
 * TAREFA 2: Componente para mostrar e resolver conflitos entre
 * dados existentes e dados extraídos pela IA de documentos.
 */
import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Alert, AlertDescription, AlertTitle } from "./ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { 
  AlertTriangle, Check, X, FileText, ArrowRight, 
  Sparkles, Shield, Loader2, ChevronDown, ChevronUp
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Mapeamento de campos para labels legíveis
const FIELD_LABELS = {
  nif: "NIF",
  documento_id: "Nº Documento CC",
  naturalidade: "Naturalidade",
  nacionalidade: "Nacionalidade",
  morada_fiscal: "Morada Fiscal",
  birth_date: "Data de Nascimento",
  data_nascimento: "Data de Nascimento",
  estado_civil: "Estado Civil",
  data_validade_cc: "Validade CC",
  sexo: "Sexo",
  altura: "Altura",
  nome_pai: "Nome do Pai",
  nome_mae: "Nome da Mãe",
  salario_bruto: "Salário Bruto",
  salario_liquido: "Salário Líquido",
  rendimento_anual: "Rendimento Anual",
  renda_habitacao_atual: "Renda Habitação",
  capital_proprio: "Capital Próprio",
  valor_imovel: "Valor do Imóvel",
  localidade: "Localidade",
  tipologia: "Tipologia",
  client_name: "Nome do Cliente"
};

const DataConflictResolver = ({ 
  processId, 
  suggestions = [], 
  isDataConfirmed = false,
  onResolve,
  onConfirmData,
  token 
}) => {
  const [resolving, setResolving] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);

  const handleResolve = async (suggestion, choice) => {
    setResolving(suggestion.id);
    try {
      const response = await fetch(`${API_URL}/api/processes/${processId}/resolve-conflict`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({
          field: suggestion.field,
          choice: choice,
          suggestion_id: suggestion.id
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Erro ao resolver conflito");
      }

      const result = await response.json();
      toast.success(result.message);
      
      if (onResolve) {
        onResolve(suggestion.id, choice);
      }
    } catch (error) {
      toast.error(error.message);
    } finally {
      setResolving(null);
    }
  };

  const handleConfirmData = async (confirmed) => {
    setConfirming(true);
    try {
      const response = await fetch(`${API_URL}/api/processes/${processId}/confirm-data`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ confirmed })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Erro ao confirmar dados");
      }

      const result = await response.json();
      toast.success(result.message);
      setShowConfirmDialog(false);
      
      if (onConfirmData) {
        onConfirmData(confirmed);
      }
    } catch (error) {
      toast.error(error.message);
    } finally {
      setConfirming(false);
    }
  };

  const formatValue = (value) => {
    if (value === null || value === undefined || value === "") {
      return <span className="text-muted-foreground italic">Vazio</span>;
    }
    if (typeof value === "number") {
      return new Intl.NumberFormat("pt-PT", {
        style: "currency",
        currency: "EUR"
      }).format(value);
    }
    return String(value);
  };

  // Se não há conflitos e dados não confirmados, não mostrar nada
  if (suggestions.length === 0 && !isDataConfirmed) {
    return null;
  }

  // Se dados confirmados, mostrar badge e botão para desbloquear
  if (isDataConfirmed) {
    return (
      <Alert className="border-green-200 bg-green-50 dark:bg-green-950/20 dark:border-green-800">
        <Shield className="h-4 w-4 text-green-600" />
        <AlertTitle className="text-green-800 dark:text-green-300">Dados Verificados</AlertTitle>
        <AlertDescription className="text-green-700 dark:text-green-400">
          Os dados deste cliente foram confirmados. A IA não irá sobrepor informações automaticamente.
          <Button 
            variant="outline" 
            size="sm" 
            className="ml-4"
            onClick={() => handleConfirmData(false)}
            disabled={confirming}
          >
            {confirming ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
            Desbloquear Dados
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <>
      <Card className="border-amber-200 bg-amber-50/50 dark:bg-amber-950/20 dark:border-amber-800">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-amber-600" />
              <CardTitle className="text-base text-amber-800 dark:text-amber-300">
                Conflitos de Dados ({suggestions.length})
              </CardTitle>
            </div>
            <div className="flex items-center gap-2">
              {suggestions.length === 0 && (
                <Button
                  size="sm"
                  variant="outline"
                  className="bg-green-100 hover:bg-green-200 text-green-700 border-green-300"
                  onClick={() => setShowConfirmDialog(true)}
                  data-testid="confirm-data-btn"
                >
                  <Check className="h-4 w-4 mr-1" />
                  Confirmar Dados
                </Button>
              )}
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setExpanded(!expanded)}
              >
                {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
              </Button>
            </div>
          </div>
          <CardDescription className="text-amber-700 dark:text-amber-400">
            A IA encontrou dados diferentes nos documentos. Escolha qual valor manter.
          </CardDescription>
        </CardHeader>
        
        {expanded && (
          <CardContent className="space-y-3">
            {suggestions.map((suggestion) => (
              <div 
                key={suggestion.id}
                className="p-3 bg-white dark:bg-gray-900 rounded-lg border border-amber-200 dark:border-amber-800"
                data-testid={`conflict-${suggestion.field}`}
              >
                {/* Header do conflito */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200">
                      {FIELD_LABELS[suggestion.field] || suggestion.field}
                    </Badge>
                    {suggestion.document && (
                      <span className="text-xs text-muted-foreground flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        {suggestion.document}
                      </span>
                    )}
                  </div>
                  {suggestion.detected_at && (
                    <span className="text-xs text-muted-foreground">
                      {format(parseISO(suggestion.detected_at), "dd/MM HH:mm", { locale: pt })}
                    </span>
                  )}
                </div>

                {/* Valores em conflito */}
                <div className="grid grid-cols-[1fr,auto,1fr] gap-2 items-center mb-3">
                  {/* Valor actual */}
                  <div className="p-2 bg-gray-50 dark:bg-gray-800 rounded border">
                    <p className="text-xs text-muted-foreground mb-1">Valor Actual</p>
                    <p className="font-medium text-sm">{formatValue(suggestion.current)}</p>
                  </div>
                  
                  <ArrowRight className="h-4 w-4 text-muted-foreground" />
                  
                  {/* Valor sugerido */}
                  <div className="p-2 bg-blue-50 dark:bg-blue-950 rounded border border-blue-200 dark:border-blue-800">
                    <p className="text-xs text-blue-600 dark:text-blue-400 mb-1 flex items-center gap-1">
                      <Sparkles className="h-3 w-3" />
                      Sugerido pela IA
                    </p>
                    <p className="font-medium text-sm text-blue-800 dark:text-blue-200">
                      {formatValue(suggestion.suggested)}
                    </p>
                  </div>
                </div>

                {/* Botões de acção */}
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => handleResolve(suggestion, "current")}
                    disabled={resolving === suggestion.id}
                    data-testid={`keep-current-${suggestion.field}`}
                  >
                    {resolving === suggestion.id ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    ) : (
                      <X className="h-4 w-4 mr-1" />
                    )}
                    Manter Actual
                  </Button>
                  <Button
                    size="sm"
                    className="flex-1 bg-blue-600 hover:bg-blue-700"
                    onClick={() => handleResolve(suggestion, "ai")}
                    disabled={resolving === suggestion.id}
                    data-testid={`accept-ai-${suggestion.field}`}
                  >
                    {resolving === suggestion.id ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-1" />
                    ) : (
                      <Check className="h-4 w-4 mr-1" />
                    )}
                    Aceitar IA
                  </Button>
                </div>
              </div>
            ))}

            {suggestions.length === 0 && (
              <div className="text-center py-4 text-muted-foreground">
                <Check className="h-8 w-8 mx-auto mb-2 text-green-500" />
                <p>Todos os conflitos foram resolvidos!</p>
                <p className="text-sm">Pode confirmar os dados do cliente para bloquear actualizações automáticas.</p>
              </div>
            )}
          </CardContent>
        )}
      </Card>

      {/* Dialog de confirmação */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-green-600" />
              Confirmar Dados do Cliente
            </DialogTitle>
            <DialogDescription>
              Ao confirmar os dados, a IA deixará de actualizar automaticamente os campos de perfil 
              quando novos documentos forem analisados. Os documentos continuarão a ser classificados 
              e armazenados normalmente.
            </DialogDescription>
          </DialogHeader>
          
          <div className="py-4">
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>Atenção</AlertTitle>
              <AlertDescription>
                Poderá desbloquear os dados a qualquer momento se precisar de fazer alterações.
              </AlertDescription>
            </Alert>
          </div>
          
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowConfirmDialog(false)}>
              Cancelar
            </Button>
            <Button 
              onClick={() => handleConfirmData(true)}
              disabled={confirming}
              className="bg-green-600 hover:bg-green-700"
            >
              {confirming ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Check className="h-4 w-4 mr-2" />}
              Confirmar Dados
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default DataConflictResolver;
