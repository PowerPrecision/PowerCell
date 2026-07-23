/**
 * EmailSearchPage - Página de Pesquisa Global de Emails
 * Permite pesquisar em todo o histórico de emails do sistema
 * 
 * MELHORIAS:
 * - Barra de navegação com prev/next entre emails
 * - Breadcrumb de contexto
 * - Atalhos de teclado
 */
import { useState, useCallback, useEffect, useMemo } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
import { Separator } from "../components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "../components/ui/dialog";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
import {
  Search,
  Mail,
  MailOpen,
  Send,
  Inbox,
  Loader2,
  Link as LinkIcon,
  ExternalLink,
  Calendar,
  User,
  FileText,
  ChevronLeft,
  ChevronRight,
  X,
  Copy,
} from "lucide-react";
import { toast } from "sonner";
import { pt } from "date-fns/locale";
import { useNavigate } from "react-router-dom";
import { sanitizeEmailHtml } from "../utils/sanitize";
import { safeFormat } from "../lib/utils";

const API_URL = process.env.REACT_APP_BACKEND_URL;

const EmailSearchPage = () => {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchType, setSearchType] = useState("all"); // all, subject, sender, recipient
  const [dateRange, setDateRange] = useState("all"); // all, week, month, year
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [totalResults, setTotalResults] = useState(0);

  // Pesquisar emails
  const handleSearch = useCallback(async () => {
    if (!searchQuery.trim() || searchQuery.length < 3) {
      toast.error("Introduza pelo menos 3 caracteres para pesquisar");
      return;
    }

    setLoading(true);
    try {
      const params = new URLSearchParams({
        q: searchQuery,
        limit: "50",
      });
      
      if (searchType !== "all") {
        params.append("search_type", searchType);
      }
      if (dateRange !== "all") {
        params.append("date_range", dateRange);
      }

      const response = await fetch(
        `${API_URL}/api/emails/search?${params.toString()}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (!response.ok) throw new Error("Erro na pesquisa");
      const data = await response.json();
      setResults(data.emails || []);
      setTotalResults(data.total || 0);
      
      if (data.emails?.length === 0) {
        toast.info("Nenhum email encontrado com esses critérios");
      }
    } catch (error) {
      console.error("Erro:", error);
      toast.error("Erro ao pesquisar emails");
    } finally {
      setLoading(false);
    }
  }, [searchQuery, searchType, dateRange, token]);

  // Pesquisar ao pressionar Enter
  const handleKeyPress = (e) => {
    if (e.key === "Enter") {
      handleSearch();
    }
  };

  // Navegar para o processo associado
  const goToProcess = (processId) => {
    if (processId) {
      setSelectedEmail(null);
      navigate(`/processo/${processId}`);
    }
  };

  // Formatar data
  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    return safeFormat(dateStr, "dd/MM/yyyy HH:mm", { locale: pt });
  };

  // Índice do email selecionado nos resultados
  const selectedIndex = useMemo(() => {
    if (!selectedEmail || results.length === 0) return -1;
    return results.findIndex(e => e.id === selectedEmail.id);
  }, [selectedEmail, results]);

  // Navegação prev/next
  const handlePrevEmail = () => {
    if (selectedIndex > 0) {
      setSelectedEmail(results[selectedIndex - 1]);
    }
  };

  const handleNextEmail = () => {
    if (selectedIndex >= 0 && selectedIndex < results.length - 1) {
      setSelectedEmail(results[selectedIndex + 1]);
    }
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!selectedEmail) return;
      if (e.key === 'ArrowLeft') {
        handlePrevEmail();
      } else if (e.key === 'ArrowRight') {
        handleNextEmail();
      } else if (e.key === 'Escape') {
        setSelectedEmail(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedEmail, selectedIndex, results]);

  // Memorizar o HTML sanitizado
  const sanitizedBodyHtml = useMemo(() => {
    if (selectedEmail?.body_html) {
      return sanitizeEmailHtml(selectedEmail.body_html);
    }
    return '';
  }, [selectedEmail?.body_html]);

  // Copiar email
  const copyEmail = (text) => {
    navigator.clipboard.writeText(text).then(() => {
      toast.success("Copiado para o clipboard");
    }).catch(() => {
      toast.error("Erro ao copiar");
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Mail className="h-6 w-6 text-primary" />
          Pesquisa de Emails
        </h1>
        <p className="text-muted-foreground mt-1">
          Pesquise em todo o histórico de emails do sistema
        </p>
      </div>

      {/* Search Card */}
      <Card>
        <CardHeader className="pb-4">
          <CardTitle className="text-lg">Filtros de Pesquisa</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Search Input */}
            <div className="md:col-span-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Pesquisar por assunto, remetente ou conteúdo..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyPress={handleKeyPress}
                  className="pl-9"
                  data-testid="email-search-input"
                />
              </div>
            </div>

            {/* Search Type */}
            <Select value={searchType} onValueChange={setSearchType}>
              <SelectTrigger data-testid="search-type-select">
                <SelectValue placeholder="Tipo de pesquisa" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os campos</SelectItem>
                <SelectItem value="subject">Apenas assunto</SelectItem>
                <SelectItem value="sender">Apenas remetente</SelectItem>
                <SelectItem value="recipient">Apenas destinatário</SelectItem>
              </SelectContent>
            </Select>

            {/* Date Range */}
            <Select value={dateRange} onValueChange={setDateRange}>
              <SelectTrigger data-testid="date-range-select">
                <SelectValue placeholder="Período" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os períodos</SelectItem>
                <SelectItem value="week">Última semana</SelectItem>
                <SelectItem value="month">Último mês</SelectItem>
                <SelectItem value="year">Último ano</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex justify-end mt-4">
            <Button
              onClick={handleSearch}
              disabled={loading || searchQuery.length < 3}
              data-testid="search-emails-btn"
            >
              {loading ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Search className="h-4 w-4 mr-2" />
              )}
              Pesquisar
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {results.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-lg flex items-center justify-between">
              <span>Resultados</span>
              <Badge variant="secondary">{totalResults} encontrados</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[500px] overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[40px]"></TableHead>
                    <TableHead>Assunto</TableHead>
                    <TableHead>De / Para</TableHead>
                    <TableHead>Data</TableHead>
                    <TableHead>Cliente</TableHead>
                    <TableHead className="w-[80px]">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {results.map((email) => (
                    <TableRow
                      key={email.id}
                      className={`cursor-pointer hover:bg-accent/50 ${selectedEmail?.id === email.id ? "bg-accent" : ""}`}
                      onClick={() => setSelectedEmail(email)}
                      data-testid={`email-row-${email.id}`}
                    >
                      <TableCell>
                        {email.direction === "sent" ? (
                          <Send className="h-4 w-4 text-blue-500" />
                        ) : (
                          <Inbox className="h-4 w-4 text-green-500" />
                        )}
                      </TableCell>
                      <TableCell className="font-medium max-w-[300px] truncate">
                        {email.subject || "(Sem assunto)"}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {email.direction === "sent" ? (
                          <span>Para: {email.to_emails?.[0] || "-"}</span>
                        ) : (
                          <span>De: {email.from_email || "-"}</span>
                        )}
                      </TableCell>
                      <TableCell className="text-sm">
                        {formatDate(email.sent_at)}
                      </TableCell>
                      <TableCell>
                        {email.client_name ? (
                          <Badge variant="outline" className="text-xs">
                            {email.client_name}
                          </Badge>
                        ) : (
                          <span className="text-xs text-muted-foreground">
                            Não associado
                          </span>
                        )}
                      </TableCell>
                      <TableCell>
                        {email.process_id && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              goToProcess(email.process_id);
                            }}
                            title="Ver processo"
                          >
                            <ExternalLink className="h-4 w-4" />
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </ScrollArea>
          </CardContent>
        </Card>
      )}

      {/* Empty State */}
      {!loading && results.length === 0 && searchQuery.length >= 3 && (
        <Card>
          <CardContent className="py-12 text-center">
            <MailOpen className="h-12 w-12 mx-auto mb-4 text-muted-foreground opacity-50" />
            <p className="text-muted-foreground">Nenhum email encontrado</p>
            <p className="text-sm text-muted-foreground mt-1">
              Tente ajustar os filtros de pesquisa
            </p>
          </CardContent>
        </Card>
      )}

      {/* Email Detail Dialog with Navigation */}
      <Dialog open={!!selectedEmail} onOpenChange={() => setSelectedEmail(null)}>
        <DialogContent className="max-w-3xl h-[90vh] sm:h-[85vh] p-0 gap-0 overflow-hidden flex flex-col">
          <VisuallyHidden>
            <DialogTitle>Visualização de Email</DialogTitle>
            <DialogDescription>{selectedEmail?.subject || "Email"}</DialogDescription>
          </VisuallyHidden>

          {/* Barra de Navegação Superior */}
          <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/30 shrink-0">
            {/* Breadcrumb de contexto */}
            <div className="flex items-center gap-1.5 text-sm text-muted-foreground min-w-0">
              <Mail className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">Pesquisa: &quot;{searchQuery}&quot;</span>
              <ChevronLeft className="h-3 w-3 shrink-0 rotate-180" />
              <span className="text-foreground font-medium truncate">
                {selectedIndex >= 0 ? results[selectedIndex]?.subject || "(Sem assunto)" : ""}
              </span>
            </div>

            {/* Navegação Prev/Next + Contador */}
            <div className="flex items-center gap-1.5 shrink-0">
              <Button
                variant="outline"
                size="sm"
                onClick={(e) => { e.stopPropagation(); handlePrevEmail(); }}
                disabled={selectedIndex <= 0}
                className="h-7 px-2"
                title="Email anterior (←)"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-xs text-muted-foreground px-1.5 whitespace-nowrap">
                {selectedIndex >= 0 ? `${selectedIndex + 1} / ${results.length}` : "-"}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={(e) => { e.stopPropagation(); handleNextEmail(); }}
                disabled={selectedIndex < 0 || selectedIndex >= results.length - 1}
                className="h-7 px-2"
                title="Email seguinte (→)"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
              <Separator orientation="vertical" className="h-5 mx-1" />
              <Button
                variant="ghost"
                size="icon"
                className="h-7 w-7"
                onClick={() => setSelectedEmail(null)}
                title="Fechar (Esc)"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Conteúdo do Email */}
          {selectedEmail && (
            <div className="flex-1 overflow-hidden flex flex-col">
              {/* Cabeçalho do Email */}
              <div className="px-5 py-4 border-b bg-background shrink-0">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0 space-y-2">
                    <h2 className="font-semibold text-lg break-words">
                      {selectedEmail.direction === "sent" ? (
                        <Send className="h-4 w-4 text-blue-500 inline mr-2" />
                      ) : (
                        <Inbox className="h-4 w-4 text-green-500 inline mr-2" />
                      )}
                      {selectedEmail.subject || "(Sem assunto)"}
                    </h2>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 text-sm">
                      <div className="flex items-center gap-2 min-w-0">
                        <User className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="text-muted-foreground shrink-0">De:</span>
                        <span className="font-medium truncate" title={selectedEmail.from_email}>
                          {selectedEmail.from_email || "-"}
                        </span>
                        <button
                          onClick={() => copyEmail(selectedEmail.from_email || "")}
                          className="text-muted-foreground hover:text-foreground shrink-0"
                          title="Copiar email"
                        >
                          <Copy className="h-3 w-3" />
                        </button>
                      </div>
                      <div className="flex items-center gap-2">
                        <Calendar className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="text-muted-foreground shrink-0">Data:</span>
                        <span>{formatDate(selectedEmail.sent_at)}</span>
                      </div>
                      <div className="flex items-center gap-2 min-w-0 sm:col-span-2">
                        <Mail className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="text-muted-foreground shrink-0">Para:</span>
                        <span className="truncate" title={selectedEmail.to_emails?.join(", ")}>
                          {selectedEmail.to_emails?.join(", ") || "-"}
                        </span>
                      </div>
                      {selectedEmail.cc_emails?.length > 0 && (
                        <div className="flex items-center gap-2 min-w-0 sm:col-span-2 text-amber-600 dark:text-amber-400">
                          <Copy className="h-3.5 w-3.5 shrink-0" />
                          <span className="font-medium shrink-0">CC:</span>
                          <span className="truncate">{selectedEmail.cc_emails.join(", ")}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Badge direção + link processo */}
                  <div className="flex flex-col items-end gap-2 shrink-0">
                    <Badge variant={selectedEmail.direction === "sent" ? "default" : "secondary"}>
                      {selectedEmail.direction === "sent" ? "Enviado" : "Recebido"}
                    </Badge>
                    {selectedEmail.client_name && (
                      <Badge variant="outline" className="text-xs">
                        {selectedEmail.client_name}
                      </Badge>
                    )}
                    {selectedEmail.process_id && (
                      <Button
                        variant="outline"
                        size="sm"
                        className="text-xs h-7"
                        onClick={() => goToProcess(selectedEmail.process_id)}
                      >
                        <LinkIcon className="h-3 w-3 mr-1" />
                        Ver Processo
                      </Button>
                    )}
                  </div>
                </div>
              </div>

              {/* Corpo do Email */}
              <ScrollArea className="flex-1">
                <div className="p-5">
                  <div className="prose prose-sm max-w-none dark:prose-invert">
                    {sanitizedBodyHtml ? (
                      <div
                        dangerouslySetInnerHTML={{ __html: sanitizedBodyHtml }}
                        className="email-content"
                      />
                    ) : (
                      <pre className="whitespace-pre-wrap font-sans text-sm">
                        {selectedEmail.body}
                      </pre>
                    )}
                  </div>

                  {/* Anexos */}
                  {selectedEmail.attachments?.length > 0 && (
                    <div className="mt-6 pt-4 border-t">
                      <h4 className="font-medium text-sm flex items-center gap-2 mb-3">
                        <FileText className="h-4 w-4" />
                        Anexos ({selectedEmail.attachments.length})
                      </h4>
                      <div className="space-y-1">
                        {selectedEmail.attachments.map((attachment, idx) => (
                          <div
                            key={attachment.id || idx}
                            className="flex items-center gap-2 p-2 rounded border bg-muted/30 text-sm"
                          >
                            <FileText className="h-4 w-4 text-muted-foreground" />
                            <span className="flex-1 truncate">{attachment.filename}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Notas */}
                  {selectedEmail.notes && (
                    <div className="mt-4 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                      <p className="text-xs font-medium text-amber-700 dark:text-amber-400">Notas:</p>
                      <p className="text-sm text-amber-600 dark:text-amber-300 mt-1">{selectedEmail.notes}</p>
                    </div>
                  )}
                </div>
              </ScrollArea>

              {/* Barra inferior com info de conta */}
              {selectedEmail.account && (
                <div className="px-5 py-2 border-t bg-muted/20 text-xs text-muted-foreground flex items-center gap-2 shrink-0">
                  <Mail className="h-3 w-3" />
                  <span>
                    {selectedEmail.account === "precision" ? "Precision Crédito" : "Power Real Estate"}
                  </span>
                  {selectedEmail.matched_by && (
                    <>
                      <span>•</span>
                      <span>Associado por: {selectedEmail.matched_by}</span>
                    </>
                  )}
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default EmailSearchPage;
