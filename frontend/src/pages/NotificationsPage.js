/**
 * ====================================================================
 * PÁGINA DE NOTIFICAÇÕES - POWERCELL
 * ====================================================================
 * Mostra todas as notificações do utilizador com filtros e ações.
 * ====================================================================
 */

import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { ScrollArea } from "../components/ui/scroll-area";
import { Checkbox } from "../components/ui/checkbox";
import { toast } from "sonner";
import {
  Bell,
  BellRing,
  UserPlus,
  Clock,
  FileText,
  Calendar,
  AlertTriangle,
  CheckCircle,
  ArrowRight,
  Mail,
  Inbox,
  Send,
  Search,
  Filter,
  Trash2,
  Check,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { getNotifications, markNotificationRead } from "../services/api";
import { safeDateStr } from "../lib/utils";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Ícones por tipo de notificação
const notificationIcons = {
  new_registration: UserPlus,
  age_under_35: AlertTriangle,
  pre_approval_countdown: Clock,
  document_expiry: FileText,
  document_expiry_watchdog: FileText,
  property_docs_check: FileText,
  deed_reminder: Calendar,
  process_status_change: ArrowRight,
  process_stale: AlertTriangle,
  process_urgent: Clock,
  clients_waiting: AlertTriangle,
  new_email: Mail,
  email_received: Inbox,
  email_sent: Send,
  default: Bell
};

// Cores por tipo de notificação
const notificationColors = {
  new_registration: "text-blue-500 bg-blue-50 dark:bg-blue-950",
  age_under_35: "text-amber-500 bg-amber-50 dark:bg-amber-950",
  pre_approval_countdown: "text-orange-500 bg-orange-50 dark:bg-orange-950",
  document_expiry: "text-red-500 bg-red-50 dark:bg-red-950",
  document_expiry_watchdog: "text-red-500 bg-red-50 dark:bg-red-950",
  property_docs_check: "text-purple-500 bg-purple-50 dark:bg-purple-950",
  deed_reminder: "text-green-500 bg-green-50 dark:bg-green-950",
  process_status_change: "text-indigo-500 bg-indigo-50 dark:bg-indigo-950",
  process_stale: "text-red-600 bg-red-50 dark:bg-red-950",
  process_urgent: "text-orange-500 bg-orange-50 dark:bg-orange-950",
  clients_waiting: "text-amber-600 bg-amber-50 dark:bg-amber-950",
  new_email: "text-amber-500 bg-amber-50 dark:bg-amber-950",
  email_received: "text-emerald-500 bg-emerald-50 dark:bg-emerald-950",
  email_sent: "text-blue-500 bg-blue-50 dark:bg-blue-950",
  default: "text-gray-500 bg-gray-50 dark:bg-gray-950"
};

// Labels por tipo de notificação
const notificationLabels = {
  new_registration: "Novo Registo",
  age_under_35: "Idade < 35",
  pre_approval_countdown: "Pré-aprovação",
  document_expiry: "Validade Documento",
  document_expiry_watchdog: "Validade Documento",
  property_docs_check: "Docs Imóvel",
  deed_reminder: "Escritura",
  process_status_change: "Mudança Status",
  process_stale: "Processo Parado",
  process_urgent: "Urgente",
  clients_waiting: "Clientes à Espera",
  new_email: "Novo Email",
  email_received: "Email Recebido",
  email_sent: "Email Enviado",
  default: "Notificação"
};

export default function NotificationsPage() {
  const { token, user } = useAuth();
  const navigate = useNavigate();
  
  const [loading, setLoading] = useState(true);
  const [notifications, setNotifications] = useState([]);
  const [filteredNotifications, setFilteredNotifications] = useState([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [activeTab, setActiveTab] = useState("all");
  const [selectedIds, setSelectedIds] = useState([]);
  const [processing, setProcessing] = useState(false);

  // Carregar notificações
  const loadNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const response = await getNotifications(false);
      const data = response.data.notifications || [];
      setNotifications(data);
      setFilteredNotifications(data);
    } catch (error) {
      console.error("Erro ao carregar notificações:", error);
      toast.error("Erro ao carregar notificações");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  // Filtrar notificações
  useEffect(() => {
    let filtered = [...notifications];
    
    // Filtrar por tab
    if (activeTab === "unread") {
      filtered = filtered.filter(n => !n.read);
    } else if (activeTab === "read") {
      filtered = filtered.filter(n => n.read);
    }
    
    // Filtrar por pesquisa
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(n => 
        n.message?.toLowerCase().includes(term) ||
        n.client_name?.toLowerCase().includes(term) ||
        n.type?.toLowerCase().includes(term)
      );
    }
    
    setFilteredNotifications(filtered);
  }, [notifications, activeTab, searchTerm]);

  // Contagem
  const unreadCount = notifications.filter(n => !n.read).length;
  const readCount = notifications.filter(n => n.read).length;

  // Marcar como lida
  const handleMarkAsRead = async (notification) => {
    try {
      await markNotificationRead(notification.id);
      setNotifications(prev => 
        prev.map(n => n.id === notification.id ? { ...n, read: true } : n)
      );
      
      // Se tiver process_id, navegar para o processo
      if (notification.process_id) {
        navigate(`/process/${notification.process_id}`);
      }
    } catch (error) {
      toast.error("Erro ao marcar notificação");
    }
  };

  // Marcar selecionadas como lidas
  const handleMarkSelectedAsRead = async () => {
    if (selectedIds.length === 0) return;
    
    setProcessing(true);
    try {
      await Promise.all(
        selectedIds.map(id => markNotificationRead(id))
      );
      setNotifications(prev => 
        prev.map(n => selectedIds.includes(n.id) ? { ...n, read: true } : n)
      );
      setSelectedIds([]);
      toast.success(`${selectedIds.length} notificações marcadas como lidas`);
    } catch (error) {
      toast.error("Erro ao marcar notificações");
    } finally {
      setProcessing(false);
    }
  };

  // Selecionar/desselecionar
  const toggleSelection = (id) => {
    setSelectedIds(prev => 
      prev.includes(id) 
        ? prev.filter(i => i !== id)
        : [...prev, id]
    );
  };

  // Selecionar todas as não lidas
  const selectAllUnread = () => {
    const unreadIds = filteredNotifications
      .filter(n => !n.read)
      .map(n => n.id);
    setSelectedIds(unreadIds);
  };

  // Formatar data
  const formatDate = (dateStr) => {
    const date = new Date(safeDateStr(dateStr));
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return "Agora mesmo";
    if (diff < 3600000) return `${Math.floor(diff / 60000)} min atrás`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} h atrás`;
    if (diff < 604800000) return `${Math.floor(diff / 86400000)} dias atrás`;
    
    return date.toLocaleDateString('pt-PT', { 
      day: 'numeric', 
      month: 'short',
      year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined
    });
  };

  // Obter ícone
  const getIcon = (type) => notificationIcons[type] || notificationIcons.default;
  
  // Obter cor
  const getColorClass = (type) => notificationColors[type] || notificationColors.default;
  
  // Obter label
  const getLabel = (type) => notificationLabels[type] || notificationLabels.default;

  if (loading) {
    return (
      <DashboardLayout>
        <div className="space-y-6">
          <div className="space-y-1.5">
            <div className="h-7 w-48 bg-muted animate-pulse rounded" />
            <div className="h-4 w-64 bg-muted animate-pulse rounded" />
          </div>
          <div className="space-y-3">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="h-20 bg-muted animate-pulse rounded-lg" />
            ))}
          </div>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="notifications-page">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              {unreadCount > 0 ? (
                <BellRing className="h-6 w-6 text-primary animate-pulse" />
              ) : (
                <Bell className="h-6 w-6 text-primary" />
              )}
              Notificações
            </h1>
            <p className="text-muted-foreground mt-1">
              {unreadCount > 0 
                ? `Tem ${unreadCount} notificação${unreadCount !== 1 ? 'ões' : ''} por ler`
                : "Todas as notificações foram lidas"
              }
            </p>
          </div>
          
          <div className="flex items-center gap-2">
            <Button 
              variant="outline" 
              size="sm"
              onClick={loadNotifications}
              disabled={loading}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
            
            {selectedIds.length > 0 && (
              <Button 
                size="sm"
                onClick={handleMarkSelectedAsRead}
                disabled={processing}
              >
                {processing ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Check className="h-4 w-4 mr-2" />
                )}
                Marcar {selectedIds.length} como lidas
              </Button>
            )}
          </div>
        </div>

        {/* Filtros e Pesquisa */}
        <Card>
          <CardContent className="pt-4">
            <div className="flex flex-col sm:flex-row gap-4">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Pesquisar notificações..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="pl-10"
                />
              </div>
              
              {unreadCount > 0 && (
                <Button variant="outline" size="sm" onClick={selectAllUnread}>
                  <Check className="h-4 w-4 mr-2" />
                  Selecionar não lidas
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Tabs */}
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="all">
              Todas
              <Badge variant="secondary" className="ml-2">
                {notifications.length}
              </Badge>
            </TabsTrigger>
            <TabsTrigger value="unread">
              Por Ler
              {unreadCount > 0 && (
                <Badge variant="default" className="ml-2 bg-red-500">
                  {unreadCount}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="read">
              Lidas
              <Badge variant="secondary" className="ml-2">
                {readCount}
              </Badge>
            </TabsTrigger>
          </TabsList>

          <TabsContent value={activeTab} className="mt-4">
            {filteredNotifications.length === 0 ? (
              <Card>
                <CardContent className="py-12">
                  <div className="flex flex-col items-center justify-center text-muted-foreground">
                    <CheckCircle className="h-12 w-12 mb-4 opacity-50" />
                    <p className="text-lg font-medium">
                      {activeTab === "unread" 
                        ? "Sem notificações por ler"
                        : activeTab === "read"
                        ? "Sem notificações lidas"
                        : "Sem notificações"
                      }
                    </p>
                    <p className="text-sm mt-1">
                      {activeTab === "all" && "Novas notificações aparecerão aqui"}
                    </p>
                  </div>
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-2">
                {filteredNotifications.map((notification) => {
                  const Icon = getIcon(notification.type);
                  const colorClass = getColorClass(notification.type);
                  const label = getLabel(notification.type);
                  
                  return (
                    <Card 
                      key={notification.id}
                      className={`cursor-pointer transition-all hover:shadow-md ${
                        !notification.read ? 'border-l-4 border-l-primary bg-primary/5' : ''
                      }`}
                      onClick={() => handleMarkAsRead(notification)}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start gap-4">
                          {/* Checkbox */}
                          <Checkbox
                            checked={selectedIds.includes(notification.id)}
                            onCheckedChange={() => toggleSelection(notification.id)}
                            onClick={(e) => e.stopPropagation()}
                            className="mt-1"
                          />
                          
                          {/* Ícone */}
                          <div className={`p-2.5 rounded-full ${colorClass} flex-shrink-0`}>
                            <Icon className="h-5 w-5" />
                          </div>
                          
                          {/* Conteúdo */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start justify-between gap-2">
                              <div>
                                <p className={`text-sm ${!notification.read ? 'font-semibold' : ''}`}>
                                  {notification.message}
                                </p>
                                {notification.client_name && (
                                  <p className="text-sm text-muted-foreground mt-0.5">
                                    {notification.client_name}
                                  </p>
                                )}
                              </div>
                              
                              <div className="flex items-center gap-2 flex-shrink-0">
                                <Badge variant="outline" className="text-xs">
                                  {label}
                                </Badge>
                                {!notification.read && (
                                  <div className="h-2 w-2 rounded-full bg-primary" />
                                )}
                              </div>
                            </div>
                            
                            <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
                              <span>{formatDate(notification.created_at)}</span>
                              {notification.process_id && (
                                <>
                                  <span>•</span>
                                  <span className="text-primary hover:underline">
                                    Ver processo
                                  </span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </TabsContent>
        </Tabs>

        {/* Info */}
        {notifications.length > 0 && (
          <Card className="bg-muted/50">
            <CardContent className="py-3">
              <p className="text-xs text-muted-foreground text-center">
                Clique numa notificação para a marcar como lida e ir para o processo relacionado
              </p>
            </CardContent>
          </Card>
        )}
      </div>
    </DashboardLayout>
  );
}
