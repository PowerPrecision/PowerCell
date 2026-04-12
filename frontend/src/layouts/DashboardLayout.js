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
} from "lucide-react";
import NotificationsDropdown from "../components/NotificationsDropdown";
import TasksDropdown from "../components/TasksDropdown";
import MobileBottomNav from "../components/layout/MobileBottomNav";
import GlobalSearchModal from "../components/GlobalSearchModal";
import ChatPanel from "../components/ChatPanel";
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
  const { user, logout } = useAuth();
  const { theme, toggleTheme, isDark } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [headerCollapsed, setHeaderCollapsed] = useState(false);
  
  // Atalhos de teclado
  const { showHelpModal, setShowHelpModal, showSearchModal, setShowSearchModal, shortcuts } = useKeyboardShortcuts({
    onNew: () => navigate("/processos/novo"),
  });
  
  // Determinar quais secções devem estar abertas baseado na rota actual
  const getInitialOpenSections = () => {
    const path = location.pathname;
    
    // Rotas do grupo Negócio
    const negocioRoutes = ["/utilizadores", "/processos", "/clientes", "/leads", "/imoveis", "/minutas", "/meus-clientes", "/registos-clientes", "/financeiro"];
    // Rotas do grupo IA
    const iaRoutes = ["/configuracoes/ia", "/ai-insights", "/revisao-dados-ia", "/configuracoes/treino-ia"];
    // Rotas do grupo Configurações (unificado com Sistema)
    const configuracoesRoutes = ["/configuracoes", "/definicoes", "/configuracoes/notificacoes", "/admin/backups", "/admin/logs", "/admin/mapeamentos-nif", "/admin/processos-background", "/validades", "/auditoria", "/workflow-estados", "/automation", "/configuracoes-perfis", "/gestao-formulario", "/admin/migracao-rgpd", "/diagnosticos"];
    
    return {
      negocio: negocioRoutes.some(r => path.startsWith(r)),
      ia: iaRoutes.some(r => path.startsWith(r)),
      configuracoes: configuracoesRoutes.some(r => path.startsWith(r)),
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
    // Admin vai para /admin, CEO e outros staff vão para /processos
    const dashboardHref = user?.role?.toLowerCase() === "admin" ? "/admin" : "/processos";
    
    const baseItems = [
      {
        label: "Dashboard",
        icon: LayoutDashboard,
        href: dashboardHref,
      },
    ];

    // Estatísticas para todos os utilizadores autenticados
    const statsItem = {
      label: "Estatísticas",
      icon: BarChart3,
      href: "/estatisticas",
    };

    // Definições para admin e ceo
    const settingsItem = {
      label: "Definições",
      icon: Settings,
      href: "/definicoes",
    };

    if (user?.role === "cliente") {
      return [
        ...baseItems,
        statsItem,
      ];
    }

    // CEO tem menu limitado
    if (user?.role?.toLowerCase() === "ceo") {
      return {
        main: [
          ...baseItems,
          statsItem,
          {
            label: "Quadro Geral",
            icon: LayoutGrid,
            href: "/staff",
          },
        ],
        groups: [
          {
            id: "negocio",
            label: "Negócio",
            icon: Building2,
            items: [
              {
                label: "Utilizadores",
                icon: Users,
                href: "/utilizadores",
              },
              {
                label: "Registo de Clientes",
                icon: Users,
                href: "/registos-clientes",
              },
              {
                label: "Processos",
                icon: User,
                href: "/clientes",
              },
              {
                label: "Gestor de Visitas",
                icon: Search,
                href: "/leads",
              },
              {
                label: "Imóveis",
                icon: Building2,
                href: "/imoveis",
              },
              {
                label: "Minutas",
                icon: FileArchive,
                href: "/minutas",
              },
              {
                label: "Validades Docs",
                icon: AlertCircle,
                href: "/validades",
              },
              {
                label: "Financeiro",
                icon: DollarSign,
                href: "/financeiro",
              },
            ],
          },
          {
            id: "configuracoes",
            label: "Configurações",
            icon: Cog,
            items: [
              {
                label: "Sistema",
                icon: Cog,
                href: "/configuracoes",
              },
              {
                label: "Estados do Workflow",
                icon: Settings,
                href: "/workflow-estados",
              },
              {
                label: "Automacoes",
                icon: Zap,
                href: "/automation",
              },
              {
                label: "Perfis e Permissoes",
                icon: Shield,
                href: "/configuracoes-perfis",
              },
              {
                label: "Gestao do Formulario",
                icon: FileSignature,
                href: "/gestao-formulario",
              },
              {
                label: "Auditoria",
                icon: ClipboardList,
                href: "/auditoria",
              },
            ],
          },
        ],
      };
    }

    // Admin tem menu completo
    if (user?.role?.toLowerCase() === "admin") {
      return {
        main: [
          ...baseItems,
          statsItem,
          {
            label: "Quadro Geral",
            icon: LayoutGrid,
            href: "/staff",
          },
        ],
        groups: [
          {
            id: "negocio",
            label: "Negócio",
            icon: Building2,
            items: [
              {
                label: "Utilizadores",
                icon: Users,
                href: "/utilizadores",
              },
              {
                label: "Registo de Clientes",
                icon: Users,
                href: "/registos-clientes",
              },
              {
                label: "Processos",
                icon: User,
                href: "/clientes",
              },
              {
                label: "Gestor de Visitas",
                icon: Search,
                href: "/leads",
              },
              {
                label: "Imóveis",
                icon: Building2,
                href: "/imoveis",
              },
              {
                label: "Minutas",
                icon: FileArchive,
                href: "/minutas",
              },
              {
                label: "Financeiro",
                icon: DollarSign,
                href: "/financeiro",
              },
            ],
          },
          {
            id: "ia",
            label: "Ferramentas IA",
            icon: Brain,
            items: [
              {
                label: "Configuração de IA",
                icon: Sparkles,
                href: "/configuracoes/ia",
              },
              {
                label: "Treino do Agente",
                icon: Brain,
                href: "/configuracoes/treino-ia",
              },
              {
                label: "Agente IA",
                icon: Brain,
                href: "/ai-insights",
              },
              {
                label: "Revisão Dados IA",
                icon: FileText,
                href: "/revisao-dados-ia",
              },
            ],
          },
          {
            id: "configuracoes",
            label: "Configurações",
            icon: Cog,
            items: [
              {
                label: "Definições",
                icon: Settings,
                href: "/definicoes",
              },
              {
                label: "Sistema",
                icon: Cog,
                href: "/configuracoes",
              },
              {
                label: "Validades Docs",
                icon: AlertCircle,
                href: "/validades",
              },
              {
                label: "Processos Background",
                icon: LayoutGrid,
                href: "/admin/processos-background",
              },
              {
                label: "Backups",
                icon: Database,
                href: "/admin/backups",
              },
              {
                label: "Logs do Sistema",
                icon: AlertCircle,
                href: "/admin/logs",
              },
              {
                label: "Auditoria",
                icon: ClipboardList,
                href: "/auditoria",
              },
              {
                label: "Migracao RGPD",
                icon: Lock,
                href: "/admin/migracao-rgpd",
              },
              {
                label: "Diagnosticos",
                icon: Activity,
                href: "/diagnosticos",
              },
              {
                label: "Estados do Workflow",
                icon: Settings,
                href: "/workflow-estados",
              },
              {
                label: "Automacoes",
                icon: Zap,
                href: "/automation",
              },
              {
                label: "Perfis e Permissoes",
                icon: Shield,
                href: "/configuracoes-perfis",
              },
              {
                label: "Gestao do Formulario",
                icon: FileSignature,
                href: "/gestao-formulario",
              },
            ],
          },
        ],
      };
    }

    // Para roles de staff (consultor, mediador, intermediario, ceo, etc.)
    const userRole = user?.role?.toLowerCase();
    const userPermissions = user?.permissions || {};
    const userPages = userPermissions?.pages || [];
    const userActions = userPermissions?.actions || [];

    if (["consultor", "mediador", "intermediario", "consultor_intermediario", "ceo", "diretor", "administrativo", "indexacao"].includes(userRole)) {
      // Menu para INDEXACAO - simplificado e focado no fluxo de trabalho
      if (userRole === "indexacao") {
        const indexacaoMain = [];

        // "Quadro Geral" (Kanban) - página principal
        if (userPages.includes("kanban")) {
          indexacaoMain.push({
            label: "Quadro Geral",
            icon: LayoutGrid,
            href: "/kanban",
          });
        }

        // "Os Meus Processos" - processos atribuídos ao utilizador
        if (userPages.includes("processes")) {
          indexacaoMain.push({
            label: "Os Meus Processos",
            icon: FileText,
            href: "/processos",
          });
        }

        // "Lista de Clientes"
        if (userPages.includes("clients")) {
          indexacaoMain.push({
            label: "Lista de Clientes",
            icon: Users,
            href: "/clientes",
          });
        }

        return {
          main: indexacaoMain,
          groups: [],
        };
      }
      
      const mainItems = [
        ...baseItems,
        statsItem,
        {
          label: "Quadro Geral",
          icon: LayoutGrid,
          href: "/kanban",
        },
      ];
      
      const negocioItems = [];
      
      // Adicionar "Os Meus Processos" para consultores e intermediários (incluindo intermediário de crédito)
      if (["consultor", "intermediario", "mediador", "consultor_intermediario"].includes(userRole)) {
        negocioItems.push({
          label: "Os Meus Processos",
          icon: Users,
          href: "/meus-clientes",
        });
      }
      
      // Registo de Clientes para todos
      negocioItems.push({
        label: "Registo de Clientes",
        icon: Users,
        href: "/registos-clientes",
      });

      // Lista de Clientes (Gestão de Processos) para todos
      negocioItems.push({
        label: "Lista de Clientes",
        icon: User,
        href: "/clientes",
      });
      
      // Gestor de Visitas - NÃO para intermediários de crédito
      if (!["intermediario", "consultor_intermediario"].includes(userRole)) {
        negocioItems.push({
          label: "Gestor de Visitas",
          icon: Search,
          href: "/leads",
        });
      }
      
      // Imóveis apenas para roles que não são intermediário/mediador
      if (!["intermediario", "mediador", "consultor_intermediario"].includes(userRole)) {
        negocioItems.push({
          label: "Imóveis",
          icon: Building2,
          href: "/imoveis",
        });
      }
      
      // Minutas para todos os staff
      negocioItems.push({
        label: "Minutas",
        icon: FileArchive,
        href: "/minutas",
      });
      
      // Validades de documentos para todos os staff
      negocioItems.push({
        label: "Validades Docs",
        icon: AlertCircle,
        href: "/validades",
      });
      
      // Estados do Workflow apenas para Admin e CEO
      const configItems = [];
      if (["admin", "ceo"].includes(userRole)) {
        configItems.push({
          label: "Estados do Workflow",
          icon: Settings,
          href: "/workflow-estados",
        });
        configItems.push({
          label: "Automacoes",
          icon: Zap,
          href: "/automation",
        });
        configItems.push({
          label: "Perfis e Permissoes",
          icon: Shield,
          href: "/configuracoes-perfis",
        });
        configItems.push({
          label: "Gestao do Formulario",
          icon: FileSignature,
          href: "/gestao-formulario",
        });
      }
      
      return {
        main: mainItems,
        groups: [
          ...(negocioItems.length > 0 ? [{
            id: "negocio",
            label: "Negócio",
            icon: Building2,
            items: negocioItems,
          }] : []),
          ...(configItems.length > 0 ? [{
            id: "configuracoes",
            label: "Configurações",
            icon: Cog,
            items: configItems,
          }] : []),
        ],
      };
    }

    return { main: [...baseItems], groups: [] };
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
                <span
                  className={`inline-block px-2 py-0.5 text-xs font-semibold rounded-full ${
                    roleColors[user?.role]
                  }`}
                >
                  {roleLabels[user?.role]}
                </span>
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
                className="lg:hidden flex-shrink-0 h-8 w-8"
                onClick={() => setSidebarOpen(true)}
                aria-label="Abrir menu"
              >
                <Menu className="h-4 w-4" />
              </Button>
              <h1 className={`font-semibold tracking-tight transition-all duration-300 truncate text-sm ${
                headerCollapsed ? 'text-xs' : 'text-sm lg:text-xl'
              }`}>{title}</h1>
            </div>

            <div className="flex items-center gap-0.5 sm:gap-1 flex-shrink-0">
              {/* Search Button (Ctrl+K) */}
              <Button 
                variant="ghost" 
                size="icon"
                onClick={() => setShowSearchModal(true)}
                title="Pesquisar (Ctrl+K)"
                aria-label="Pesquisar"
                className="h-8 w-8"
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
                className="h-8 w-8"
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
              
              {/* Notificações - só para utilizadores autenticados (não clientes) */}
              {user?.role !== "cliente" && (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => setChatOpen(true)}
                    className="relative h-8 w-8"
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
                  <Button variant="ghost" size="icon" className="rounded-full h-8 w-8" aria-label="Menu do utilizador">
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
      
      {/* Keyboard Shortcuts Help Modal */}
      <Dialog open={showHelpModal} onOpenChange={setShowHelpModal}>
        <DialogContent>
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
