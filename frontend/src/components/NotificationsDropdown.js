import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { ScrollArea } from "./ui/scroll-area";
import { Bell, BellRing, UserPlus, Clock, FileText, Calendar, AlertTriangle, CheckCircle, Volume2, VolumeX, ArrowRight } from "lucide-react";
import { getNotifications, markNotificationRead } from "../services/api";
import { toast } from "sonner";

const notificationIcons = {
  new_registration: UserPlus,
  age_under_35: AlertTriangle,
  pre_approval_countdown: Clock,
  document_expiry: FileText,
  document_expiry_watchdog: FileText,
  property_docs_check: FileText,
  deed_reminder: Calendar,
  process_status_change: ArrowRight,
  default: Bell
};

const notificationColors = {
  new_registration: "text-blue-500 bg-blue-50",
  age_under_35: "text-amber-500 bg-amber-50",
  pre_approval_countdown: "text-orange-500 bg-orange-50",
  document_expiry: "text-red-500 bg-red-50",
  document_expiry_watchdog: "text-red-500 bg-red-50",
  property_docs_check: "text-purple-500 bg-purple-50",
  deed_reminder: "text-green-500 bg-green-50",
  process_status_change: "text-indigo-500 bg-indigo-50",
  default: "text-gray-500 bg-gray-50"
};

// Polling interval for real-time notifications (10 seconds)
const POLLING_INTERVAL = 10000;

const NotificationsDropdown = () => {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const previousUnreadCount = useRef(0);
  const isFirstLoad = useRef(true);

  // Play notification sound
  const playNotificationSound = useCallback(() => {
    if (!soundEnabled) return;
    
    try {
      // Create a simple beep sound using Web Audio API
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();
      
      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);
      
      oscillator.frequency.value = 800;
      oscillator.type = 'sine';
      gainNode.gain.value = 0.3;
      
      oscillator.start();
      oscillator.stop(audioContext.currentTime + 0.15);
      
      // Second beep
      setTimeout(() => {
        const osc2 = audioContext.createOscillator();
        const gain2 = audioContext.createGain();
        osc2.connect(gain2);
        gain2.connect(audioContext.destination);
        osc2.frequency.value = 1000;
        osc2.type = 'sine';
        gain2.gain.value = 0.3;
        osc2.start();
        osc2.stop(audioContext.currentTime + 0.15);
      }, 150);
    } catch (e) {
      console.log("Audio not available");
    }
  }, [soundEnabled]);

  const fetchNotifications = useCallback(async () => {
    try {
      if (!isFirstLoad.current) {
        setLoading(true);
      }
      const res = await getNotifications();
      const newNotifications = res.data.notifications || [];
      const newUnreadCount = res.data.unread || 0;
      
      setNotifications(newNotifications);
      setUnreadCount(newUnreadCount);
      
      // Check for new notifications (after first load)
      if (!isFirstLoad.current && newUnreadCount > previousUnreadCount.current) {
        const newCount = newUnreadCount - previousUnreadCount.current;
        const latestNotification = newNotifications.find(n => !n.read);
        
        // Show toast for new notification
        if (latestNotification) {
          playNotificationSound();
          
          toast.info(
            latestNotification.message,
            {
              description: latestNotification.client_name || "Nova notificação",
              action: latestNotification.process_id ? {
                label: "Ver",
                onClick: () => navigate(`/process/${latestNotification.process_id}`)
              } : undefined,
              duration: 8000,
              icon: <UserPlus className="h-4 w-4 text-blue-500" />
            }
          );
        }
      }
      
      previousUnreadCount.current = newUnreadCount;
      isFirstLoad.current = false;
    } catch (error) {
      console.error("Erro ao carregar notificações:", error);
    } finally {
      setLoading(false);
    }
  }, [navigate, playNotificationSound]);

  useEffect(() => {
    fetchNotifications();
    // Fast polling for real-time notifications (10 seconds)
    const interval = setInterval(fetchNotifications, POLLING_INTERVAL);
    return () => clearInterval(interval);
  }, [fetchNotifications]);

  const handleNotificationClick = async (notification) => {
    try {
      // Mark as read
      if (!notification.read) {
        await markNotificationRead(notification.id);
        setNotifications(prev => 
          prev.map(n => n.id === notification.id ? { ...n, read: true } : n)
        );
        setUnreadCount(prev => Math.max(0, prev - 1));
      }
      
      // Navigate to process if exists
      if (notification.process_id) {
        navigate(`/process/${notification.process_id}`);
      }
      
      setIsOpen(false);
    } catch (error) {
      console.error("Erro ao marcar notificação:", error);
    }
  };

  const markAllAsRead = async () => {
    try {
      const unreadNotifications = notifications.filter(n => !n.read);
      await Promise.all(unreadNotifications.map(n => markNotificationRead(n.id)));
      setNotifications(prev => prev.map(n => ({ ...n, read: true })));
      setUnreadCount(0);
      toast.success("Todas as notificações marcadas como lidas");
    } catch (error) {
      toast.error("Erro ao marcar notificações");
    }
  };

  const getIcon = (type) => {
    const IconComponent = notificationIcons[type] || notificationIcons.default;
    return IconComponent;
  };

  const getColorClass = (type) => {
    return notificationColors[type] || notificationColors.default;
  };

  const formatDate = (dateStr) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return "Agora mesmo";
    if (diff < 3600000) return `${Math.floor(diff / 60000)} min`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} h`;
    return date.toLocaleDateString('pt-PT', { day: 'numeric', month: 'short' });
  };

  return (
    <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuTrigger asChild>
        <Button 
          variant="ghost" 
          size="icon" 
          className="relative"
          data-testid="notifications-trigger"
        >
          {unreadCount > 0 ? (
            <>
              <BellRing className="h-5 w-5 text-amber-500" />
              <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-red-500 text-white text-xs flex items-center justify-center font-bold">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            </>
          ) : (
            <Bell className="h-5 w-5" />
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80" data-testid="notifications-dropdown">
        <div className="flex items-center justify-between px-3 py-2 border-b">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm">Notificações</span>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={(e) => {
                e.stopPropagation();
                setSoundEnabled(!soundEnabled);
                toast.info(soundEnabled ? "Som desativado" : "Som ativado");
              }}
              title={soundEnabled ? "Desativar som" : "Ativar som"}
            >
              {soundEnabled ? (
                <Volume2 className="h-3.5 w-3.5 text-green-600" />
              ) : (
                <VolumeX className="h-3.5 w-3.5 text-muted-foreground" />
              )}
            </Button>
          </div>
          {unreadCount > 0 && (
            <Button 
              variant="ghost" 
              size="sm" 
              className="text-xs text-blue-600 hover:text-blue-800 h-auto p-1"
              onClick={markAllAsRead}
            >
              Marcar todas como lidas
            </Button>
          )}
        </div>
        
        <ScrollArea className="h-80">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="animate-spin h-6 w-6 border-2 border-blue-500 border-t-transparent rounded-full" />
            </div>
          ) : notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
              <CheckCircle className="h-10 w-10 mb-2 opacity-50" />
              <p className="text-sm">Sem notificações</p>
            </div>
          ) : (
            <div className="py-1">
              {notifications.slice(0, 20).map((notification) => {
                const Icon = getIcon(notification.type);
                const colorClass = getColorClass(notification.type);
                
                return (
                  <DropdownMenuItem 
                    key={notification.id}
                    className={`px-3 py-3 cursor-pointer ${!notification.read ? 'bg-blue-50/50' : ''}`}
                    onClick={() => handleNotificationClick(notification)}
                    data-testid={`notification-item-${notification.id}`}
                  >
                    <div className="flex items-start gap-3 w-full">
                      <div className={`p-2 rounded-full ${colorClass}`}>
                        <Icon className="h-4 w-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className={`text-sm ${!notification.read ? 'font-medium' : ''}`}>
                          {notification.message}
                        </p>
                        {notification.client_name && (
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {notification.client_name}
                          </p>
                        )}
                        <p className="text-xs text-muted-foreground mt-1">
                          {formatDate(notification.created_at)}
                        </p>
                      </div>
                      {!notification.read && (
                        <div className="h-2 w-2 rounded-full bg-blue-500 mt-1" />
                      )}
                    </div>
                  </DropdownMenuItem>
                );
              })}
            </div>
          )}
        </ScrollArea>
        
        {notifications.length > 20 && (
          <>
            <DropdownMenuSeparator />
            <div className="px-3 py-2 text-center">
              <Button variant="ghost" size="sm" className="text-xs text-blue-600">
                Ver todas ({notifications.length})
              </Button>
            </div>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};

export default NotificationsDropdown;
