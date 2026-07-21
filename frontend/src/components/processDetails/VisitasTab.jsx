/**
 * VisitasTab — Imóveis associados a um processo + diálogo de associação.
 *
 * Extraído de ProcessDetails.js para reduzir o mega-ficheiro.
 * Só é montado quando o tab "visitas" está activo, por isso carrega dados no mount.
 */
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../../contexts/AuthContext";
import { Card, CardContent } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Input } from "../ui/input";
import { ScrollArea } from "../ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import {
  Home,
  Building2,
  MapPin,
  ExternalLink,
  Link2,
  Search,
  Plus,
  Loader2,
  User,
} from "lucide-react";
import { toast } from "sonner";
import { safeString } from "../../utils/safeString";
import { extractErrorMessage } from "../../utils/extractErrorMessage";

const API_URL = process.env.REACT_APP_BACKEND_URL || "";

const propertyStatusColors = {
  disponivel: "bg-emerald-100 text-emerald-800 border-emerald-200",
  reservado: "bg-amber-100 text-amber-800 border-amber-200",
  vendido: "bg-red-100 text-red-800 border-red-200",
  suspenso: "bg-gray-100 text-gray-800 border-gray-200",
  em_analise: "bg-blue-100 text-blue-800 border-blue-200",
};

const propertyStatusLabels = {
  disponivel: "Disponível",
  reservado: "Reservado",
  vendido: "Vendido",
  suspenso: "Suspenso",
  em_analise: "Em Análise",
};

const propertyTypeLabels = {
  apartamento: "Apartamento",
  moradia: "Moradia",
  terreno: "Terreno",
  loja: "Loja",
  escritorio: "Escritório",
  armazem: "Armazém",
  garagem: "Garagem",
  outro: "Outro",
};

const formatPrice = (value) => {
  if (!value && value !== 0) return "—";
  return new Intl.NumberFormat("pt-PT", { style: "currency", currency: "EUR" }).format(value);
};

export default function VisitasTab({ processId }) {
  const { token } = useAuth();
  const [visitasProperties, setVisitasProperties] = useState([]);
  const [visitasLoading, setVisitasLoading] = useState(false);
  const [showAssociatePropertyDialog, setShowAssociatePropertyDialog] = useState(false);
  const [propertySearch, setPropertySearch] = useState("");
  const [propertySearchResults, setPropertySearchResults] = useState([]);
  const [propertySearchLoading, setPropertySearchLoading] = useState(false);
  const [associatingProperty, setAssociatingProperty] = useState(false);

  const fetchVisitasProperties = useCallback(async () => {
    if (!processId) return;
    setVisitasLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/properties/by-process/${processId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setVisitasProperties(Array.isArray(data) ? data : []);
      }
    } catch (error) {
      console.error("Erro ao carregar imóveis:", error);
    } finally {
      setVisitasLoading(false);
    }
  }, [processId, token]);

  const searchProperties = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setPropertySearchResults([]);
      return;
    }
    setPropertySearchLoading(true);
    try {
      const response = await fetch(
        `${API_URL}/api/properties?search=${encodeURIComponent(query)}`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (response.ok) {
        const data = await response.json();
        const associatedIds = visitasProperties.map((p) => p.id);
        setPropertySearchResults(data.filter((p) => !associatedIds.includes(p.id)));
      }
    } catch (error) {
      console.error("Erro ao pesquisar imóveis:", error);
    } finally {
      setPropertySearchLoading(false);
    }
  }, [token, visitasProperties]);

  const handleAssociateProperty = useCallback(async (propertyId) => {
    setAssociatingProperty(true);
    try {
      const response = await fetch(
        `${API_URL}/api/properties/${propertyId}/interested-client?client_id=${processId}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        },
      );
      if (response.ok) {
        toast.success("Imóvel associado ao processo com sucesso");
        setShowAssociatePropertyDialog(false);
        setPropertySearch("");
        setPropertySearchResults([]);
        fetchVisitasProperties();
      } else {
        const data = await response.json();
        toast.error(extractErrorMessage(data.detail, "Erro ao associar imóvel"));
      }
    } catch (error) {
      console.error("Erro ao associar imóvel:", error);
      toast.error("Erro ao associar imóvel ao processo");
    } finally {
      setAssociatingProperty(false);
    }
  }, [processId, token, fetchVisitasProperties]);

  useEffect(() => {
    fetchVisitasProperties();
  }, [fetchVisitasProperties]);

  useEffect(() => {
    const timeout = setTimeout(() => {
      if (propertySearch.length >= 2) {
        searchProperties(propertySearch);
      } else {
        setPropertySearchResults([]);
      }
    }, 400);
    return () => clearTimeout(timeout);
  }, [propertySearch, searchProperties]);

  return (
    <div className="space-y-4">
      <div className="bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800 rounded-lg p-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-emerald-100 dark:bg-emerald-900/40 rounded-lg">
              <Home className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
            </div>
            <div>
              <h3 className="font-semibold text-emerald-800 dark:text-emerald-200">Visitas / Imóveis</h3>
              <p className="text-sm text-emerald-600 dark:text-emerald-400">
                Imóveis associados a este processo
              </p>
            </div>
          </div>
          <Button
            size="sm"
            className="gap-1.5 bg-emerald-600 hover:bg-emerald-700"
            onClick={() => {
              setPropertySearch("");
              setPropertySearchResults([]);
              setShowAssociatePropertyDialog(true);
            }}
          >
            <Plus className="h-4 w-4" />
            Associar Imóvel
          </Button>
        </div>
      </div>

      {visitasLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-emerald-500" />
          <span className="ml-3 text-muted-foreground">A carregar imóveis...</span>
        </div>
      )}

      {!visitasLoading && visitasProperties.length === 0 && (
        <Card className="border-dashed">
          <CardContent className="py-12 flex flex-col items-center text-center">
            <div className="p-3 bg-muted rounded-full mb-4">
              <Building2 className="h-8 w-8 text-muted-foreground" />
            </div>
            <h4 className="font-semibold text-lg mb-1">Nenhum imóvel associado</h4>
            <p className="text-sm text-muted-foreground max-w-md">
              Nenhum imóvel associado a este processo. Clique em &quot;Associar Imóvel&quot; para ligar um imóvel existente a este processo.
            </p>
          </CardContent>
        </Card>
      )}

      {!visitasLoading && visitasProperties.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {visitasProperties.map((prop) => (
            <Card key={prop.id} className="overflow-hidden hover:shadow-md transition-shadow">
              <CardContent className="p-4">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs text-muted-foreground font-mono">
                        {safeString(prop.internal_reference)}
                      </span>
                      <Badge
                        className={`text-[10px] px-1.5 py-0 ${propertyStatusColors[prop.status] || "bg-gray-100 text-gray-800"}`}
                        variant="outline"
                      >
                        {propertyStatusLabels[prop.status] || prop.status}
                      </Badge>
                    </div>
                    <h5 className="font-semibold text-sm truncate">
                      {safeString(prop.title)}
                    </h5>
                  </div>
                  <Badge variant="outline" className="text-xs ml-2 shrink-0">
                    {propertyTypeLabels[prop.property_type] || prop.property_type}
                  </Badge>
                </div>

                <div className="text-lg font-bold text-emerald-700 dark:text-emerald-400 mb-2">
                  {formatPrice(prop.asking_price)}
                </div>

                <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2">
                  <MapPin className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">
                    {[prop.municipality, prop.district].filter(Boolean).join(", ")}
                  </span>
                </div>

                {(prop.bedrooms != null || prop.useful_area != null) && (
                  <div className="flex items-center gap-3 text-xs text-muted-foreground mb-2">
                    {prop.bedrooms != null && <span>T{prop.bedrooms}</span>}
                    {prop.useful_area != null && <span>{prop.useful_area} m²</span>}
                  </div>
                )}

                {prop.client_name && (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-2">
                    <User className="h-3.5 w-3.5 shrink-0" />
                    <span className="truncate">{prop.client_name}</span>
                  </div>
                )}

                {prop.source_url && (
                  <div className="flex items-center gap-1.5 text-xs mt-2 pt-2 border-t">
                    <ExternalLink className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <a
                      href={prop.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-600 hover:text-blue-800 hover:underline truncate"
                    >
                      Ver origem
                    </a>
                  </div>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={showAssociatePropertyDialog} onOpenChange={setShowAssociatePropertyDialog}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Link2 className="h-5 w-5 text-emerald-600" />
              Associar Imóvel
            </DialogTitle>
            <DialogDescription>
              Pesquise e selecione um imóvel existente para associar a este processo.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Pesquisar imóveis por título, referência ou localidade..."
                value={propertySearch}
                onChange={(e) => setPropertySearch(e.target.value)}
                className="pl-9"
              />
            </div>

            {propertySearchLoading && (
              <div className="flex items-center justify-center py-6">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                <span className="ml-2 text-sm text-muted-foreground">A pesquisar...</span>
              </div>
            )}

            {!propertySearchLoading && propertySearch.length >= 2 && propertySearchResults.length === 0 && (
              <div className="text-center py-6 text-sm text-muted-foreground">
                Nenhum imóvel encontrado para &quot;{propertySearch}&quot;
              </div>
            )}

            {!propertySearchLoading && propertySearchResults.length > 0 && (
              <ScrollArea className="max-h-72">
                <div className="space-y-2 pr-3">
                  {propertySearchResults.map((prop) => (
                    <div
                      key={prop.id}
                      className="flex items-center justify-between p-3 rounded-lg border hover:bg-muted/50 cursor-pointer transition-colors"
                    >
                      <div className="flex-1 min-w-0 mr-3">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span className="text-xs text-muted-foreground font-mono">
                            {safeString(prop.internal_reference)}
                          </span>
                          <Badge
                            className={`text-[9px] px-1 py-0 ${propertyStatusColors[prop.status] || "bg-gray-100 text-gray-800"}`}
                            variant="outline"
                          >
                            {propertyStatusLabels[prop.status] || prop.status}
                          </Badge>
                        </div>
                        <p className="text-sm font-medium truncate">{prop.title}</p>
                        <p className="text-xs text-muted-foreground">
                          {[prop.municipality, prop.district].filter(Boolean).join(", ")}
                          {" · "}
                          {formatPrice(prop.asking_price)}
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        className="shrink-0 gap-1 text-emerald-700 border-emerald-300 hover:bg-emerald-50"
                        onClick={() => handleAssociateProperty(prop.id)}
                        disabled={associatingProperty}
                      >
                        {associatingProperty ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Link2 className="h-3.5 w-3.5" />
                        )}
                        Associar
                      </Button>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            )}

            {propertySearch.length < 2 && (
              <p className="text-xs text-center text-muted-foreground py-4">
                Escreva pelo menos 2 caracteres para pesquisar
              </p>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setShowAssociatePropertyDialog(false);
                setPropertySearch("");
                setPropertySearchResults([]);
              }}
            >
              Cancelar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
