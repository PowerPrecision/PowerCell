import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useAuth } from "../contexts/AuthContext";
import { useTheme } from "../contexts/ThemeContext";
import { useNavigate, Link, useLocation } from "react-router-dom";
import { Button } from "../components/ui/button";
import { ScrollArea } from "../components/ui/scroll-area";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../components/ui/collapsible";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "../components/ui/dialog";
import {
  LayoutDashboard,
  FileText,
  Users,
  Calendar,
  Settings,
  LogOut,
  Menu,
  X,
  User,
  Building2,
  CreditCard,
  BarChart3,
  Cog,
  Home,
  LayoutGrid,
  Search,
  Sparkles,
  AlertCircle,
  AlertTriangle,
  Database,
  FileArchive,
  Brain,
  ChevronDown,
  ChevronRight,
  Bell,
  Wrench,
  Sun,
  Moon,
  Keyboard,
  MessageSquare,
  Activity,
  FileSignature,
  Zap,
  Shield,
  ClipboardList,
  DollarSign,
  Lock,
  Mail,
  Eye,
} from "lucide-react";
import NotificationsDropdown from "../components/NotificationsDropdown";
import TasksDropdown from "../components/TasksDropdown";
import MobileBottomNav from "../components/layout/MobileBottomNav";
import ContextSwitcher from "../components/layout/ContextSwitcher";
import GlobalSearchModal from "../components/GlobalSearchModal";
import ChatPanel from "../components/ChatPanel";
import WelcomeConfigModal from "../components/WelcomeConfigModal";
import { useKeyboardShortcuts, KeyboardShortcutsHelp } from "../hooks/useKeyboardShortcuts";
import { useWebSocket } from "../hooks/useWebSocket";
import { hasRole, hasPermission, ROLE_LABELS, ROLE_SIDEBAR_COLORS, STAFF_ROLES, ADMIN_PANEL_ROLES, MANAGEMENT_ROLES } from "../utils/roleUtils";
import ErrorBoundary from "../components/ErrorBoundary";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Máximo de itens para o badge de mensagens não lidas
const MAX_UNREAD_DISPLAY = 99;

// Fonte única de verdade para rótulos e cores: roleUtils.js
const roleLabels = ROLE_LABELS;
// Cores para sidebar escura (fundo slate-900)
const roleColors = ROLE_SIDEBAR_COLORS;

// Stable empty object for useKeyboardShortcuts — prevents the hook's internal
// useCallback from recreating on every render (which would re-register the
// keydown listener on every render when AuthContext value changes).
const EMPTY_HANDLERS = {};

const DashboardLayout = ({ children, title }) => {
  const { user, logout, effectiveRole, isImpersonating } = useAuth();
  const { theme, toggleTheme, isDark } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [headerCollapsed, setHeaderCollapsed] = useState(false);
  const [chatUnreadCount, setChatUnreadCount] = useState(0);
  const chatUnreadRef = useRef(0);
  const chatUnreadIntervalRef = useRef(null);
  
  // Atalhos de teclado — empty object is hoisted to module scope so the
  // reference is stable across renders (prevents useKeyboardShortcuts from
  // recreating its internal useCallback every render).
  const { showHelpModal, setShowHelpModal, showSearchModal, setShowSearchModal, shortcuts } = useKeyboardShortcuts(EMPTY_HANDLERS);

  // --- Contagem de mensagens não lidas (Chat Interno) ---
  const fetchChatUnreadCount = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      if (!token) return;
      if (hasRole(user, "parceiro")) return;
      const res = await fetch(`${API_URL}/api/chat/unread-count`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        const total = data.unread_count || data.total || 0;
        chatUnreadRef.current = total;
        setChatUnreadCount(total);
      }
    } catch {
      // Silently ignore fetch errors
    }
  }, []);

  useEffect(() => {
    fetchChatUnreadCount();
    // Poll every 30s for unread count
    chatUnreadIntervalRef.current = setInterval(fetchChatUnreadCount, 30000);
    return () => {
      if (chatUnreadIntervalRef.current) clearInterval(chatUnreadIntervalRef.current);
    };
  }, [fetchChatUnreadCount]);

  // Re-fetch unread badge when chat panel closes (not when it opens)
  useEffect(() => {
    if (!chatOpen) {
      fetchChatUnreadCount();
    }
  }, [chatOpen, fetchChatUnreadCount]);

  // --- WebSocket: incrementar badge de chat em tempo real ---
  useWebSocket({
    autoConnect: true,
    onChatMessage: useCallback((chatData) => {
      if (!chatData) return;
      // Incrementar badge de chat quando uma nova mensagem é recebida
      chatUnreadRef.current += 1;
      setChatUnreadCount(prev => prev + 1);
    }, []),
  });
  
  // Determinar quais secções devem estar abertas baseado na rota actual
  // Memoized to avoid creating new object references on every render
  const computedOpenSections = useMemo(() => {
    const path = location.pathname;
    
    // Rotas do grupo O Meu Negócio
    const meuNegocioRoutes = ["/registos-clientes", "/meus-clientes", "/processos", "/kanban", "/imoveis", "/financeiro"];
    // Rotas do grupo Visão Global
    const visaoGlobalRoutes = ["/clientes", "/lista-processos"];
    // Rotas do grupo Comunicações e Ficheiros
    const comunicacoesRoutes = ["/webmail", "/minutas", "/ficheiros"];
    // Rotas do grupo Gestão e Operações
    const gestaoRoutes = ["/estatisticas", "/rascunhos"];
    // Verificar se /rascunhos está acessível por capability
    const hasDraftAccess = hasPermission(user, "DRAFT_VIEW");
    
    return {
      "meu-negocio": meuNegocioRoutes.some(r => path.startsWith(r)),
      "visao-global": visaoGlobalRoutes.some(r => path.startsWith(r)),
      "comunicacoes": comunicacoesRoutes.some(r => path.startsWith(r)),
      "gestao-operacoes": gestaoRoutes.some(r => path.startsWith(r)),
    };
  }, [location.pathname, effectiveRole]);
  
  const [openSections, setOpenSections] = useState({});
  
  // Sync openSections with computed values when path or role changes
  useEffect(() => {
    setOpenSections(computedOpenSections);
  }, [computedOpenSections]);

  // Detectar scroll para minimizar header
  useEffect(() => {
    const handleScroll = () => {
      const scrollY = window.scrollY;
      const threshold = 100; // Pixels antes de minimizar
      setHeaderCollapsed(scrollY > threshold);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const toggleSection = (section) => {
    setOpenSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  const getNavItems = () => {
    const userRole = effectiveRole?.toLowerCase();
    const isAdmin = userRole === "admin";
    const isCeo = userRole === "ceo";
    const canSeeAdminPanel = isAdmin || isCeo; // Botão Painel de Administração
    const canSeeGestao = ["admin", "ceo", "diretor"].includes(userRole);

    // Permissões personalizadas (se definidas)
    const userPermissions = user?.permissions || {};
    const userPages = userPermissions?.pages || [];

    // Se o utilizador tem permissões definidas, verificar acesso
    const hasPageAccess = (page) => {
      if (userPages.length === 0) return true; // Sem permissões = acesso total
      return userPages.includes(page);
    };

    // ====================================================================
    // DASHBOARD
    // — admin e CEO: aponta para /admin (Painel de Administração)
    // — todos os outros: aponta para /staff
    // ====================================================================
    const dashboardHref = canSeeAdminPanel ? "/admin" : "/staff";
    const dashboardItem = {
      label: "Dashboard",
      icon: LayoutDashboard,
      href: dashboardHref,
    };

    // ====================================================================
    // O MEU NEGÓCIO (Visível para consultores, diretor, admin, CEO)
    // ====================================================================
    const meuNegocioGroup = {
      id: "meu-negocio",
      label: "O Meu Negócio",
      icon: Building2,
      items: [
        {
          label: "Registos de Clientes",
          icon: ClipboardList,
          href: "/registos-clientes",
        },
        {
          label: "Os Meus Clientes",
          icon: User,
          href: "/meus-clientes",
        },
        {
          label: "Os Meus Processos",
          icon: FileText,
          href: "/processos",
        },
        {
          label: "Quadro Geral",
          icon: LayoutGrid,
          href: "/kanban",
        },
        {
          label: "Imóveis e Visitas",
          icon: Search,
          href: "/imoveis",
        },
        {
          label: "Financeiro",
          icon: DollarSign,
          href: "/financeiro",
        },
      ],
    };

    // ====================================================================
    // VISÃO GLOBAL (admin, ceo, administrativo, diretor)
    // ====================================================================
    const visaoGlobalGroup = {
      id: "visao-global",
      label: "Visão Global",
      icon: Eye,
      items: [
        {
          label: "Todos os Clientes",
          icon: Users,
          href: "/clientes",
        },
        {
          label: "Todos os Processos",
          icon: FileText,
          href: "/lista-processos",
        },
      ],
    };

    // ====================================================================
    // COMUNICAÇÕES E FICHEIROS
    // ====================================================================
    const comunicacoesGroup = {
      id: "comunicacoes",
      label: "Comunicações e Ficheiros",
      icon: Mail,
      items: [
        {
          label: "Webmail",
          icon: Mail,
          href: "/webmail",
        },
        {
          label: "Minutas",
          icon: FileArchive,
          href: "/minutas",
        },
        {
          label: "Ficheiros",
          icon: Database,
          href: "/ficheiros",
        },
      ],
    };

    // ====================================================================
    // GESTÃO E OPERAÇÕES (admin, CEO, diretor)
    // — /templates e /rgpd-admin REMOVIDOS da Sidebar (obsoletos como
    //   links autónomos; acessíveis via Painel de Administração)
    // — Rascunhos filtrado por capability DRAFT_VIEW
    // ====================================================================
    const gestaoOperacoesItems = [
      {
        label: "Análise e Estatísticas",
        icon: BarChart3,
        href: "/estatisticas",
      },
      {
        label: "Rascunhos",
        icon: FileSignature,
        href: "/rascunhos",
        requiredCapability: "DRAFT_VIEW",
      },
    ].filter(item => !item.requiredCapability || hasPermission(user, item.requiredCapability));

    const gestaoOperacoesGroup = {
      id: "gestao-operacoes",
      label: "Gestão e Operações",
      icon: Settings,
      items: gestaoOperacoesItems,
    };

    // ====================================================================
    // INDEXAÇÃO — Sidebar minimalista com restrição máxima
    // Vê: Listas de Trabalho, Visão Global, Comunicações e Ficheiros
    // NÃO vê: Dashboard, Estatísticas, Gestão, Configuração
    // ====================================================================
    if (userRole === "indexacao") {
      return {
        main: [], // Sem Dashboard para indexação
        groups: [
          {
            id: "meu-negocio",
            label: "Listas de Trabalho",
            icon: ClipboardList,
            items: [
              { label: "Registos de Clientes", icon: ClipboardList, href: "/registos-clientes" },
              { label: "Os Meus Processos", icon: FileText, href: "/processos" },
              { label: "Documentos Pendentes", icon: FileText, href: "/validades" },
            ],
          },
          visaoGlobalGroup, // Indexação também tem acesso à Visão Global
          comunicacoesGroup, // Indexação também tem acesso a Comunicações e Ficheiros
        ],
        showAdminButton: false,
      };
    }

    // ====================================================================
    // MENU PARA CONSULTORES E INTERMEDIÁRIOS
    // ====================================================================
    if (["consultor", "intermediario"].includes(userRole)) {
      const consultorNegocioItems = [
        { label: "Registos de Clientes", icon: ClipboardList, href: "/registos-clientes" },
        { label: "Os Meus Clientes", icon: User, href: "/meus-clientes" },
        { label: "Os Meus Processos", icon: FileText, href: "/processos" },
        { label: "Quadro Geral", icon: LayoutGrid, href: "/kanban" },
        { label: "Gestor de Visitas", icon: Search, href: "/leads" },
        { label: "Financeiro", icon: DollarSign, href: "/financeiro" },
      ];

      return {
        main: [dashboardItem],
        groups: [
          { id: "meu-negocio", label: "O Meu Negócio", icon: Building2, items: consultorNegocioItems },
          visaoGlobalGroup,
          comunicacoesGroup,
        ],
        showAdminButton: false,
      };
    }

    // ====================================================================
    // MENU PARA DIRETOR
    // — Vê Gestão e Operações (Estatísticas, Rascunhos)
    // — Sem acesso ao Painel de Administração
    // ====================================================================
    if (userRole === "diretor") {
      const diretorGroups = [
        { ...meuNegocioGroup, items: meuNegocioGroup.items.filter(i => i.href !== "/financeiro") },
        visaoGlobalGroup,
        comunicacoesGroup,
      ];
      // Só mostrar "Gestão e Operações" se tiver items após filtrar capabilities
      if (gestaoOperacoesItems.length > 0) {
        diretorGroups.push(gestaoOperacoesGroup);
      }
      return {
        main: [dashboardItem],
        groups: diretorGroups,
        showAdminButton: false,
      };
    }

    // ====================================================================
    // MENU PARA ADMINISTRATIVO
    // — Sem Painel de Administração
    // — Rascunhos filtrado por capability DRAFT_VIEW
    // ====================================================================
    if (userRole === "administrativo") {
      const adminGestaoItems = [
        { label: "Análise e Estatísticas", icon: BarChart3, href: "/estatisticas" },
        { label: "Rascunhos", icon: FileSignature, href: "/rascunhos", requiredCapability: "DRAFT_VIEW" },
        { label: "RGPD", icon: Shield, href: "/rgpd-admin" },
      ].filter(item => !item.requiredCapability || hasPermission(user, item.requiredCapability));

      return {
        main: [dashboardItem],
        groups: [
          meuNegocioGroup,
          visaoGlobalGroup,
          comunicacoesGroup,
          {
            id: "gestao-operacoes",
            label: "Gestão e Operações",
            icon: Settings,
            items: adminGestaoItems,
          },
        ],
        showAdminButton: false,
      };
    }

    // ====================================================================
    // MENU PARA CEO e ADMIN
    // — Vêem Gestão e Operações
    // — Vêem o botão "Painel de Administração" no fundo
    // — SEM Configurações de Sistema espalhadas (tudo no Painel)
    // ====================================================================
    if (isAdmin || isCeo) {
      const adminGroups = [
        meuNegocioGroup,
        visaoGlobalGroup,
        comunicacoesGroup,
      ];
      // Só mostrar "Gestão e Operações" se tiver items após filtrar capabilities
      if (gestaoOperacoesItems.length > 0) {
        adminGroups.push(gestaoOperacoesGroup);
      }
      return {
        main: [dashboardItem],
        groups: adminGroups,
        showAdminButton: true,
      };
    }

    // Fallback
    return { main: [dashboardItem], groups: [], showAdminButton: false };
  };

  const navData = getNavItems();
  
  // Impersonate offset (isImpersonating already consumed above)
  const impersonateOffset = isImpersonating ? 'top-12' : 'top-0';
  const headerStyle = isImpersonating ? { top: '48px' } : {};

  return (
    <div className="min-h-screen bg-background">
      {/* Mobile sidebar backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-[45] lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed ${impersonateOffset} left-0 z-50 w-64 h-screen bg-slate-900 text-white border-r border-slate-800 transform transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={isImpersonating ? { height: 'calc(100vh - 48px)', top: '48px' } : {}}
      >
        <div className="flex flex-col h-full">
          {/* Logo — dinâmico consoante a empresa */}
          <div className="h-14 flex items-center justify-between px-4 lg:px-6 border-b border-slate-700 bg-slate-900">
            <div className="flex items-center gap-2">
              <img
                src={user?.company === 'power' ? '/PowerLogo-removebg-preview.png' : user?.company === 'precision' ? '/logoPrecision-removebg-preview.png' : '/PowerCell-default.png'}
                alt="Logo"
                className="h-7 w-auto object-contain"
              />
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="lg:hidden text-white hover:bg-slate-700 h-8 w-8"
              onClick={() => setSidebarOpen(false)}
              aria-label="Fechar menu"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          {/* Navigation */}
          <ScrollArea className="flex-1 py-4">
            <nav className="space-y-1 px-3">
              {/* Main items - always visible */}
              {navData.main.map((item) => {
                const isActive = location.pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    to={item.href}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                      isActive
                        ? "bg-brand text-white"
                        : "text-slate-300 hover:bg-slate-800 hover:text-white"
                    }`}
                    onClick={() => {
                      // Só fecha o sidebar no mobile
                      if (window.innerWidth < 1024) {
                        setSidebarOpen(false);
                      }
                    }}
                  >
                    <item.icon className="h-5 w-5" />
                    {item.label}
                  </Link>
                );
              })}
              
              {/* Collapsible groups */}
              {navData.groups.map((group) => (
                <Collapsible
                  key={group.id}
                  open={openSections[group.id]}
                  onOpenChange={(open) => {
                    // Only toggle if the CollapsibleTrigger itself was clicked
                    // Prevent items inside from collapsing the group
                    if (open !== openSections[group.id]) {
                      toggleSection(group.id);
                    }
                  }}
                  className="mt-2"
                >
                  <CollapsibleTrigger className="flex items-center justify-between w-full px-3 py-2.5 rounded-md text-sm font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors">
                    <div className="flex items-center gap-3">
                      <group.icon className="h-5 w-5" />
                      {group.label}
                    </div>
                    {openSections[group.id] ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </CollapsibleTrigger>
                  <CollapsibleContent className="pl-4 mt-1 space-y-1">
                    {group.items.map((item) => {
                      const isActive = location.pathname === item.href;
                      return (
                        <Link
                          key={item.href}
                          to={item.href}
                          className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                            isActive
                              ? "bg-brand/80 text-white"
                              : "text-slate-400 hover:bg-slate-800 hover:text-white"
                          }`}
                          onClick={(e) => {
                            e.stopPropagation(); // Prevent Collapsible onOpenChange from firing
                            // Só fecha o sidebar no mobile (quando está aberto como overlay)
                            if (window.innerWidth < 1024) {
                              setSidebarOpen(false);
                            }
                          }}
                        >
                          <item.icon className="h-4 w-4" />
                          {item.label}
                        </Link>
                      );
                    })}
                  </CollapsibleContent>
                </Collapsible>
              ))}
            </nav>
          </ScrollArea>

          {/* Painel de Administração do Sistema — apenas visível para admin e CEO */}
          {navData.showAdminButton && (
            <div className="px-3 pb-2">
              <Link
                to="/system-admin"
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-colors ${
                  location.pathname === "/system-admin"
                    ? "bg-amber-600 text-white"
                    : "text-amber-400 hover:bg-slate-800 hover:text-amber-300"
                }`}
                onClick={() => {
                  if (window.innerWidth < 1024) {
                    setSidebarOpen(false);
                  }
                }}
              >
                <Cog className="h-5 w-5" />
                Painel de Administração
              </Link>
            </div>
          )}

          {/* User section */}
          <div className="p-4 border-t border-slate-700">
            <div className="flex items-center gap-3 px-2">
              <div className="h-9 w-9 rounded-full bg-amber-500/20 flex items-center justify-center">
                <User className="h-5 w-5 text-amber-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate text-white">{user?.name}</p>
                <div className="flex items-center gap-1 flex-wrap">
                  <span
                    className={`inline-block px-2 py-0.5 text-xs font-semibold rounded-full ${
                      roleColors[user?.role]
                    }`}
                  >
                    {roleLabels[user?.role]}
                  </span>
                  {effectiveRole !== user?.role && (
                    <span className={`text-[10px] px-1.5 py-0.5 rounded ${roleColors[effectiveRole] || 'bg-gray-200'} ml-1`}>
                      {roleLabels[effectiveRole]}
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className={`lg:pl-64 ${isImpersonating ? 'pt-12' : ''}`}>
        {/* Top bar - Fixed height to prevent layout shift */}
        <header 
          className="border-b border-border bg-card sticky z-50 h-14"
          style={headerStyle}
        >
          <div className={`flex items-center justify-between h-full px-2 lg:px-6 gap-1 sm:gap-2`}>
            <div className="flex items-center gap-1 sm:gap-2 min-w-0 flex-1">
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden flex-shrink-0 h-9 w-9 sm:h-10 sm:w-10"
                onClick={() => setSidebarOpen(true)}
                aria-label="Abrir menu"
              >
                <Menu className="h-4 w-4" />
              </Button>
              <h1 className={`font-semibold tracking-tight transition-all duration-300 truncate text-sm ${headerCollapsed ? 'text-xs sm:text-sm lg:text-xl' : ''}`}>{title}</h1>
            </div>

            <div className="flex items-center gap-0.5 sm:gap-1 flex-shrink-0">
              {/* Search Button (Ctrl+K) */}
              <Button 
                variant="ghost" 
                size="icon"
                onClick={() => setShowSearchModal(true)}
                title="Pesquisar (Ctrl+K)"
                aria-label="Pesquisar"
                className="h-9 w-9 sm:h-10 sm:w-10"
              >
                <Search className="h-4 w-4" />
              </Button>
              
              {/* Dark Mode Toggle */}
              <Button
                variant="ghost"
                size="icon"
                onClick={toggleTheme}
                title={isDark ? "Modo Claro" : "Modo Escuro"}
                aria-label={isDark ? "Ativar modo claro" : "Ativar modo escuro"}
                className="h-9 w-9 sm:h-10 sm:w-10"
              >
                {isDark ? (
                  <Sun className="h-4 w-4" />
                ) : (
                  <Moon className="h-4 w-4" />
                )}
              </Button>
              
              {/* Keyboard Shortcuts Help - hide when collapsed */}
              {!headerCollapsed && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setShowHelpModal(true)}
                  title="Atalhos de Teclado (Ctrl+/)"
                  aria-label="Atalhos de teclado"
                  className="hidden sm:flex h-8 w-8"
                >
                  <Keyboard className="h-4 w-4" />
                </Button>
              )}
              
              {/* Home Button - hide when collapsed */}
              {!headerCollapsed && (
                <Button 
                  variant="ghost" 
                  size="sm"
                  onClick={() => {
                    const homePage = hasRole(user, "cliente") ? "/portal-cliente" : "/dashboard";
                    navigate(homePage);
                  }}
                  className="gap-2 hidden sm:flex h-8"
                >
                  <Home className="h-4 w-4" />
                  <span className="hidden md:inline">Página Inicial</span>
                </Button>
              )}
              
              {/* Context Switcher - Múltiplos Perfis */}
              <ContextSwitcher />

              {/* Notificações - só para utilizadores autenticados (não clientes/parceiros) */}
              {!hasRole(user, "cliente") && !hasRole(user, "parceiro") && (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setChatOpen(true)}
                    className="relative h-9 w-9 sm:h-10 sm:w-10"
                    title="Chat Interno"
                    aria-label={chatUnreadCount > 0 ? `Chat interno - ${chatUnreadCount} mensagens não lidas` : "Chat interno"}
                    data-testid="open-chat-btn"
                  >
                    <MessageSquare className="h-4 w-4" />
                    {chatUnreadCount > 0 && (
                      <span className="absolute -top-1 -right-2 z-10 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white shadow-sm">
                        {chatUnreadCount > MAX_UNREAD_DISPLAY ? `${MAX_UNREAD_DISPLAY}+` : chatUnreadCount}
                      </span>
                    )}
                  </Button>
                  {/* Centro de Operações - Tarefas Assíncronas */}
                  <TasksDropdown compact={headerCollapsed} />
                  <NotificationsDropdown compact={headerCollapsed} />
                </>
              )}
              
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="rounded-full h-9 w-9 sm:h-10 sm:w-10" aria-label="Menu do utilizador">
                    <User className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-56 max-w-[calc(100vw-2rem)]">
                  <div className="px-2 py-1.5">
                    <p className="text-sm font-medium">{user?.name}</p>
                    <p className="text-xs text-muted-foreground">{user?.email}</p>
                  </div>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={() => navigate("/perfil")}>
                    <User className="h-4 w-4 mr-2" />
                    Área Pessoal
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={handleLogout} className="text-destructive">
                    <LogOut className="h-4 w-4 mr-2" />
                    Terminar Sessão
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>
        </header>

        {/* Page content — ErrorBoundary isolates crashes here so sidebar stays alive */}
        <main className="p-4 lg:p-6 pb-24 md:pb-6 overflow-x-auto">
          <ErrorBoundary variant="page" moduleName={title || 'Conteúdo'} showRetry={true}>
            {children}
          </ErrorBoundary>
        </main>
      </div>
      
      {/* Mobile Bottom Navigation */}
      <MobileBottomNav />
      
      {/* Global Search Modal */}
      <GlobalSearchModal open={showSearchModal} onOpenChange={setShowSearchModal} />
      
      {/* Chat Panel */}
      <ChatPanel open={chatOpen} onOpenChange={setChatOpen} />
      
      {/* Email Config Reminder Modal */}
      <WelcomeConfigModal />

      {/* Keyboard Shortcuts Help Modal */}
      <Dialog open={showHelpModal} onOpenChange={setShowHelpModal}>
        <DialogContent className="sm:max-w-lg w-[calc(100vw-2rem)]">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Keyboard className="h-5 w-5" />
              Atalhos de Teclado
            </DialogTitle>
            <DialogDescription>
              Lista de atalhos de teclado disponíveis na aplicação.
            </DialogDescription>
          </DialogHeader>
          <KeyboardShortcutsHelp shortcuts={shortcuts} />
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default DashboardLayout;
