/**
 * ClientPropertyMatch - Sugestões de imóveis compatíveis com o cliente
 */
import React, { useState, useEffect, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "./ui/card";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { ScrollArea } from "./ui/scroll-area";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "./ui/dialog";
import { toast } from "sonner";
import {
  Sparkles,
  Home,
  MapPin,
  Euro,
  ExternalLink,
  Loader2,
  Target,
  CheckCircle,
  TrendingUp,
  Eye,
} from "lucide-react";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Score badge
const ScoreBadge = ({ score }) => {
  let color = "bg-gray-100 text-gray-700";
  let label = "Baixo";
  
  if (score >= 80) {
    color = "bg-green-100 text-green-700 border-green-200";
    label = "Excelente";
  } else if (score >= 60) {
    color = "bg-blue-100 text-blue-700 border-blue-200";
    label = "Bom";
  } else if (score >= 40) {
    color = "bg-yellow-100 text-yellow-700 border-yellow-200";
    label = "Razoável";
  }

  return (
    <Badge variant="outline" className={`${color} text-xs`}>
      {score}% - {label}
    </Badge>
  );
};

// Card de match individual
const MatchCard = ({ match, onViewLead }) => {
  const { lead, score, match_reasons } = match;

  const formatPrice = (price) => {
    if (!price) return "N/D";
    return new Intl.NumberFormat("pt-PT", {
      style: "currency",
      currency: "EUR",
      maximumFractionDigits: 0,
    }).format(price);
  };

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            {/* Título e score */}
            <div className="flex items-center gap-2 mb-2">
              <h4 className="text-sm font-medium truncate" title={lead.title}>
                {lead.title || "Imóvel sem título"}
              </h4>
              <ScoreBadge score={score} />
            </div>

            {/* Detalhes */}
            <div className="flex flex-wrap gap-2 text-xs text-muted-foreground mb-2">
              <div className="flex items-center gap-1">
                <Euro className="h-3 w-3" />
                <span className="font-medium text-green-600">
                  {formatPrice(lead.price)}
                </span>
              </div>
              {lead.location && (
                <div className="flex items-center gap-1">
                  <MapPin className="h-3 w-3" />
                  <span>{lead.location}</span>
                </div>
              )}
              {lead.typology && (
                <Badge variant="secondary" className="text-xs">
                  {lead.typology}
                </Badge>
              )}
              {lead.area && (
                <span>{lead.area}m²</span>
              )}
            </div>

            {/* Razões do match */}
            <div className="space-y-1">
              {match_reasons.map((reason, idx) => (
                <div key={idx} className="flex items-center gap-1 text-xs text-green-600">
                  <CheckCircle className="h-3 w-3" />
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Foto */}
          {lead.photo_url && (
            <div className="w-20 h-20 rounded overflow-hidden bg-gray-100 flex-shrink-0">
              <img
                src={lead.photo_url}
                alt=""
                className="w-full h-full object-cover"
                onError={(e) => e.target.style.display = "none"}
              />
            </div>
          )}
        </div>

        {/* Acções */}
        <div className="flex items-center gap-2 mt-3 pt-3 border-t">
          <Button
            variant="outline"
            size="sm"
            className="text-xs"
            onClick={() => onViewLead(lead)}
          >
            <Eye className="h-3 w-3 mr-1" />
            Ver Detalhes
          </Button>
          {lead.url && (
            <a
              href={lead.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-500 hover:underline flex items-center gap-1"
            >
              <ExternalLink className="h-3 w-3" />
              Ver Anúncio
            </a>
          )}
        </div>
      </CardContent>
    </Card>
  );
};

const ClientPropertyMatch = ({ processId, clientName }) => {
  const { token } = useAuth();
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedLead, setSelectedLead] = useState(null);

  const fetchMatches = useCallback(async () => {
    try {
      const response = await fetch(
        `${API_URL}/api/match/client/${processId}/leads`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setMatches(data.matches || []);
      }
    } catch (error) {
      console.error("Erro ao carregar matches:", error);
    } finally {
      setLoading(false);
    }
  }, [processId, token]);

  useEffect(() => {
    fetchMatches();
  }, [fetchMatches]);

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  const topMatches = matches.filter(m => m.score >= 60);
  const otherMatches = matches.filter(m => m.score < 60);

  return (
    <>
      <Card data-testid="client-property-match">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Target className="h-4 w-4 text-purple-500" />
                Imóveis Compatíveis
              </CardTitle>
              <CardDescription>
                Sugestões baseadas no perfil de {clientName || "cliente"}
              </CardDescription>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={fetchMatches}
              title="Actualizar sugestões"
            >
              <TrendingUp className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>

        <CardContent>
          {matches.length === 0 ? (
            <div className="text-center py-6 text-muted-foreground">
              <Home className="h-10 w-10 mx-auto mb-2 opacity-50" />
              <p className="text-sm">Sem imóveis compatíveis encontrados</p>
              <p className="text-xs mt-1">
                Adicione leads de imóveis na tab "Leads" para ver sugestões
              </p>
            </div>
          ) : (
            <ScrollArea className="h-[350px]">
              <div className="space-y-3 pr-2">
                {/* Top matches */}
                {topMatches.length > 0 && (
                  <>
                    <div className="flex items-center gap-2 text-xs font-medium text-green-600 mb-2">
                      <Sparkles className="h-3 w-3" />
                      Melhores Correspondências ({topMatches.length})
                    </div>
                    {topMatches.map((match, idx) => (
                      <MatchCard
                        key={match.lead.id || idx}
                        match={match}
                        onViewLead={setSelectedLead}
                      />
                    ))}
                  </>
                )}

                {/* Other matches */}
                {otherMatches.length > 0 && (
                  <>
                    <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground mt-4 mb-2">
                      Outras Opções ({otherMatches.length})
                    </div>
                    {otherMatches.map((match, idx) => (
                      <MatchCard
                        key={match.lead.id || idx}
                        match={match}
                        onViewLead={setSelectedLead}
                      />
                    ))}
                  </>
                )}
              </div>
            </ScrollArea>
          )}
        </CardContent>
      </Card>

      {/* Dialog para ver detalhes do lead */}
      <Dialog open={!!selectedLead} onOpenChange={() => setSelectedLead(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{selectedLead?.title || "Detalhes do Imóvel"}</DialogTitle>
            <DialogDescription>
              {selectedLead?.location}
            </DialogDescription>
          </DialogHeader>

          {selectedLead && (
            <div className="space-y-4">
              {selectedLead.photo_url && (
                <img
                  src={selectedLead.photo_url}
                  alt=""
                  className="w-full h-48 object-cover rounded"
                />
              )}

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Preço:</span>
                  <p className="font-semibold text-green-600">
                    {selectedLead.price 
                      ? new Intl.NumberFormat("pt-PT", { style: "currency", currency: "EUR" }).format(selectedLead.price)
                      : "N/D"}
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Tipologia:</span>
                  <p className="font-medium">{selectedLead.typology || "N/D"}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Área:</span>
                  <p className="font-medium">{selectedLead.area ? `${selectedLead.area}m²` : "N/D"}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Estado:</span>
                  <Badge variant="outline">{selectedLead.status}</Badge>
                </div>
              </div>

              {selectedLead.consultant?.name && (
                <div className="border-t pt-4">
                  <p className="text-sm text-muted-foreground mb-1">Contacto:</p>
                  <p className="font-medium">{selectedLead.consultant.name}</p>
                  {selectedLead.consultant.phone && (
                    <p className="text-sm">{selectedLead.consultant.phone}</p>
                  )}
                </div>
              )}

              {selectedLead.url && (
                <a
                  href={selectedLead.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-blue-500 hover:underline"
                >
                  <ExternalLink className="h-4 w-4" />
                  Ver anúncio original
                </a>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
};

export default ClientPropertyMatch;
