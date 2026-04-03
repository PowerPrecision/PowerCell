/**
 * EmailSearchPage - Página de Pesquisa Global de Emails
 * Permite pesquisar em todo o histórico de emails do sistema
 */
import { useState, useCallback } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { ScrollArea } from "../components/ui/scroll-area";
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
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
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
} from "lucide-react";
import { toast } from "sonner";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";
import { useNavigate } from "react-router-dom";

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
      navigate(`/processo/${processId}`);
    }
  };

  // Formatar data
  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    try {
      return format(parseISO(dateStr), "dd/MM/yyyy HH:mm", { locale: pt });
    } catch {
      return dateStr;
    }
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
                      className="cursor-pointer hover:bg-accent/50"
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

      {/* Email Detail Dialog */}
      <Dialog open={!!selectedEmail} onOpenChange={() => setSelectedEmail(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {selectedEmail?.direction === "sent" ? (
                <Send className="h-5 w-5 text-blue-500" />
              ) : (
                <Inbox className="h-5 w-5 text-green-500" />
              )}
              {selectedEmail?.subject || "(Sem assunto)"}
            </DialogTitle>
          </DialogHeader>

          {selectedEmail && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="flex items-center gap-2">
                  <User className="h-4 w-4 text-muted-foreground" />
                  <span className="text-muted-foreground">De:</span>
                  <span className="font-medium">{selectedEmail.from_email}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Data:</span>
                  <span>{formatDate(selectedEmail.sent_at)}</span>
                </div>
                <div className="flex items-center gap-2 col-span-2">
                  <Mail className="h-4 w-4 text-muted-foreground" />
                  <span className="text-muted-foreground">Para:</span>
                  <span>{selectedEmail.to_emails?.join(", ") || "-"}</span>
                </div>
                {selectedEmail.client_name && (
                  <div className="flex items-center gap-2 col-span-2">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    <span className="text-muted-foreground">Cliente:</span>
                    <Badge variant="outline">{selectedEmail.client_name}</Badge>
                    {selectedEmail.process_id && (
                      <Button
                        variant="link"
                        size="sm"
                        className="h-auto p-0"
                        onClick={() => {
                          setSelectedEmail(null);
                          goToProcess(selectedEmail.process_id);
                        }}
                      >
                        <LinkIcon className="h-3 w-3 mr-1" />
                        Ver processo
                      </Button>
                    )}
                  </div>
                )}
              </div>

              {selectedEmail.body && (
                <div className="border rounded-lg p-4 bg-muted/30 max-h-[300px] overflow-y-auto">
                  <pre className="text-sm whitespace-pre-wrap font-sans">
                    {selectedEmail.body}
                  </pre>
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
