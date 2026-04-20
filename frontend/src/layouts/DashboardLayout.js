import React, { useState, useEffect } from "react";
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

const roleLabels = {
  cliente: "Cliente",
  consultor: "Consultor",
  mediador: "Mediador",
  intermediario: "Intermediário de Crédito",
  consultor_intermediario: "Consultor/Intermediário",
  indexacao: "Indexação",
  administrativo: "Administrativo",
  diretor: "Diretor",
  ceo: "CEO",
  admin: "Administrador",
};

// Cores dos badges de papel - Azul PowerCell, Dourado Precision
const roleColors = {
  cliente: "bg-blue-100 text-blue-800",
  consultor: "bg-teal-600 text-white",                    // PowerCell
  mediador: "bg-amber-500 text-white",                    // PowerCell
  intermediario: "bg-amber-500 text-white",               // PowerCell
  consultor_intermediario: "bg-gradient-to-r from-blue-900 to-amber-500 text-white",
  ceo: "bg-blue-800 text-white",                          // PowerCell
  indexacao: "bg-indigo-500 text-white",
  administrativo: "bg-slate-500 text-white",
  diretor: "bg-purple-600 text-white",
  admin: "bg-slate-800 text-white",
};

const DashboardLayout = ({ children, title }) => {
  const { user, logout, effectiveRole } = useAuth();
  const { theme, toggleTheme, isDark } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [headerCollapsed, setHeaderCollapsed] = useState(false);
  
  // Atalhos de teclado
  const { showHelpModal, setShowHelpModal, showSearchModal, setShowSearchModal, shortcuts } = useKeyboardShortcuts({});
  
  // Determinar quais secções devem estar abertas baseado na rota actual
  const getInitialOpenSections = () => {
    const path = location.pathname;
    
    // Rotas do grupo O Meu Negócio
    const meuNegocioRoutes = ["/registos-clientes", "/meus-clientes", "/processos", "/kanban", "/imoveis", "/financeiro"];
    // Rotas do grupo Visão Global
    const visaoGlobalRoutes = ["/clientes", "/lista-processos"];
    // Rotas do grupo Comunicações e Ficheiros
    const comunicacoesRoutes = ["/webmail", "/minutas", "/leads"];
    // Rotas do grupo Gestão e Operações
    const gestaoRoutes = ["/templates", "/estatisticas", "/rascunhos", "/rgpd-admin"];
    // Rotas do grupo Configurações de Sistema
    const configRoutes = ["/configuracoes", "/definicoes", "/automation", "/configuracoes/ia", "/admin/backups", "/admin/logs", "/validades", "/workflow-estados", "/configuracoes-perfis", "/admin/migracao-rgpd", "/diagnosticos", "/admin/processos-background"];
    
    return {
      "meu-negocio": meuNegocioRoutes.some(r => path.startsWith(r)),
      "visao-global": visaoGlobalRoutes.some(r => path.startsWith(r)),
      "comunicacoes": comunicacoesRoutes.some(r => path.startsWith(r)),
      "gestao-operacoes": gestaoRoutes.some(r => path.startsWith(r)),
      "config-sistema": configRoutes.some(r => path.startsWith(r)),
    };
  };
  
  const [openSections, setOpenSections] = useState(getInitialOpenSections);
  
  // Actualizar secções abertas quando a rota muda
  useEffect(() => {
    setOpenSections(getInitialOpenSections());
  }, [location.pathname]);

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
    const isGlobalOps = ["admin", "ceo", "administrativo"].includes(userRole);
    const isStaff = ["consultor", "mediador", "intermediario", "consultor_intermediario", "indexacao", "diretor", "administrativo", "ceo", "admin"].includes(userRole);

    // Permissões personalizadas (se definidas)
    const userPermissions = user?.permissions || {};
    const userPages = userPermissions?.pages || [];

    // Se o utilizador tem permissões definidas, verificar acesso
    const hasPageAccess = (page) => {
      if (userPages.length === 0) return true; // Sem permissões = acesso total
      return userPages.includes(page);
    };

    // ====================================================================
    // DASHBOARD (Visível para todos)
    // ====================================================================
    const dashboardHref = isAdmin ? "/admin" : "/kanban";
    const dashboardItem = {
      label: "Dashboard",
      icon: LayoutDashboard,
      href: dashboardHref,
    };

    // ====================================================================
    // O MEU NEGÓCIO (Visível para todos)
    // ====================================================================
    const meuNegocioGroup = {
      id: "meu-negocio",
      label: "O Meu Negócio",
      icon: Building2,
      items: [
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
    // VISÃO GLOBAL (Apenas admin, ceo, administrativo)
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
    // COMUNICAÇÕES E FICHEIROS (Visível para todos)
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
          icon: FileText,
          href: "/leads",
        },
      ],
    };

    // ====================================================================
    // GESTÃO E OPERAÇÕES (Apenas admin, ceo, administrativo)
    // ====================================================================
    const gestaoOperacoesGroup = {
      id: "gestao-operacoes",
      label: "Gestão e Operações",
      icon: Settings,
      items: [
        {
          label: "Destinatários",
          icon: Users,
          href: "/templates",
        },
        {
          label: "Análise e Estatísticas",
          icon: BarChart3,
          href: "/estatisticas",
        },
        {
          label: "Rascunhos",
          icon: FileSignature,
          href: "/rascunhos",
        },
        {
          label: "RGPD",
          icon: Shield,
          href: "/rgpd-admin",
        },
      ],
    };

    // ====================================================================
    // CONFIGURAÇÕES DE SISTEMA (Apenas admin)
    // ====================================================================
    const configSistemaGroup = {
      id: "config-sistema",
      label: "Configurações de Sistema",
      icon: Cog,
      items: [
        {
          label: "Definições Gerais",
          icon: Settings,
          href: "/configuracoes",
        },
        {
          label: "Utilizadores e Equipas",
          icon: Users,
          href: "/utilizadores",
        },
        {
          label: "Integrações",
          icon: Zap,
          href: "/automation",
        },
        {
          label: "Gestão de Formulários",
          icon: FileSignature,
          href: "/gestao-formulario",
        },
      ],
    };

    // ====================================================================
    // MENU PARA INDEXAÇÃO (simplificado)
    // ====================================================================
    if (userRole === "indexacao") {
      const indexacaoGroups = [];
      if (hasPageAccess("kanban")) {
        indexacaoGroups.push({
          id: "meu-negocio",
          label: "O Meu Negócio",
          icon: Building2,
          items: [
            { label: "Os Meus Processos", icon: FileText, href: "/processos" },
            { label: "Quadro Geral", icon: LayoutGrid, href: "/kanban" },
          ],
        });
      }
      if (hasPageAccess("webmail")) {
        indexacaoGroups.push({
          id: "comunicacoes",
          label: "Comunicações e Ficheiros",
          icon: Mail,
          items: [
            { label: "Webmail", icon: Mail, href: "/webmail" },
            { label: "Minutas", icon: FileArchive, href: "/minutas" },
            { label: "Ficheiros", icon: FileText, href: "/leads" },
          ],
        });
      }

      return {
        main: [dashboardItem],
        groups: indexacaoGroups,
      };
    }

    // ====================================================================
    // MENU PARA CONSULTORES, INTERMEDIÁRIOS, MEDIADORES
    // ====================================================================
    if (["consultor", "mediador", "intermediario", "consultor_intermediario"].includes(userRole)) {
      const consultorNegocioItems = [
        { label: "Os Meus Clientes", icon: User, href: "/meus-clientes" },
        { label: "Os Meus Processos", icon: FileText, href: "/processos" },
        { label: "Quadro Geral", icon: LayoutGrid, href: "/kanban" },
        { label: "Imóveis e Visitas", icon: Search, href: "/imoveis" },
      ];

      return {
        main: [dashboardItem],
        groups: [
          { id: "meu-negocio", label: "O Meu Negócio", icon: Building2, items: consultorNegocioItems },
          comunicacoesGroup,
        ],
      };
    }

    // ====================================================================
    // MENU PARA DIRETOR
    // ====================================================================
    if (userRole === "diretor") {
      return {
        main: [dashboardItem],
        groups: [
          { ...meuNegocioGroup, items: meuNegocioGroup.items.filter(i => i.href !== "/financeiro") },
          comunicacoesGroup,
        ],
      };
    }

    // ====================================================================
    // MENU PARA ADMINISTRATIVA, CEO e ADMIN
    // ====================================================================
    if (["administrativo", "ceo", "admin"].includes(userRole)) {
      const allGroups = [
        meuNegocioGroup,
        visaoGlobalGroup,
        comunicacoesGroup,
      ];

      // Gestão e Operações — para admin, remover itens redundantes
      // (acessíveis via Definições Gerais > Destinatários, RGPD)
      if (isAdmin) {
        // Admin só vê "Análise e Estatísticas" neste grupo
        allGroups.push({
          id: "gestao-operacoes",
          label: "Gestão e Operações",
          icon: Settings,
          items: gestaoOperacoesGroup.items.filter(
            (item) => item.href === "/estatisticas"
          ),
        });
      } else {
        // CEO e Administrativo vêem todos os itens
        allGroups.push(gestaoOperacoesGroup);
      }

      // Configurações de Sistema apenas para admin
      if (isAdmin) {
        allGroups.push(configSistemaGroup);
      }

      return {
        main: [dashboardItem],
        groups: allGroups,
      };
    }

    // Fallback
    return { main: [dashboardItem], groups: [] };
  };

  const navData = getNavItems();
  
  // Verificar se está em modo de impersonate para ajustar o layout
  const { isImpersonating } = useAuth();
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
          {/* Logo - PowerCell */}
          <div className="h-14 flex items-center justify-between px-4 lg:px-6 border-b border-slate-700 bg-slate-900">
            <div className="flex items-center gap-2">
              <Building2 className="h-5 w-5 text-amber-400" />
              <span className="font-bold text-sm tracking-tight text-white">PowerCell</span>
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
                        ? "bg-teal-600 text-white"
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
                              ? "bg-teal-600/80 text-white"
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
                    const homePage = user?.role === "cliente" ? "/portal-cliente" : "/dashboard";
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

              {/* Notificações - só para utilizadores autenticados (não clientes) */}
              {user?.role !== "cliente" && (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setChatOpen(true)}
                    className="relative h-9 w-9 sm:h-10 sm:w-10"
                    title="Chat Interno"
                    aria-label="Chat interno"
                    data-testid="open-chat-btn"
                  >
                    <MessageSquare className="h-4 w-4" />
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

        {/* Page content */}
        <main className="p-4 lg:p-6 pb-24 md:pb-6 overflow-x-auto">{children}</main>
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
