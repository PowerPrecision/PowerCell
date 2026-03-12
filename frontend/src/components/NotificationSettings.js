/**
 * NotificationSettings - Componente de Configuração de Notificações
 */
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Bell, BellOff, CheckCircle, XCircle, Loader2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { usePushNotifications } from "../hooks/usePushNotifications";

const NotificationSettings = () => {
  const {
    isSupported,
    permission,
    isSubscribed,
    loading,
    enableNotifications,
    disableNotifications,
    showNotification
  } = usePushNotifications();

  const handleEnable = async () => {
    const result = await enableNotifications();
    if (result.success) {
      toast.success('Notificações ativadas com sucesso!');
      // Mostrar notificação de teste
      setTimeout(() => {
        showNotification('PowerCell', {
          body: 'As notificações estão ativas! Receberá alertas importantes.',
          tag: 'test-notification'
        });
      }, 1000);
    } else {
      toast.error(result.error || 'Erro ao ativar notificações');
    }
  };

  const handleDisable = async () => {
    const result = await disableNotifications();
    if (result.success) {
      toast.info('Notificações desativadas');
    } else {
      toast.error(result.error || 'Erro ao desativar notificações');
    }
  };

  const handleTestNotification = () => {
    showNotification('Teste - PowerCell', {
      body: 'Esta é uma notificação de teste.',
      tag: 'test-notification',
      data: { test: true }
    });
  };

  if (!isSupported) {
    return (
      <Card className="border-border">
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Bell className="h-5 w-5" />
            Notificações Push
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3 p-4 bg-amber-50 border border-amber-200 rounded-lg">
            <AlertTriangle className="h-5 w-5 text-amber-600" />
            <p className="text-sm text-amber-800">
              O seu browser não suporta notificações push. 
              Utilize um browser moderno como Chrome, Firefox ou Edge.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-border">
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <Bell className="h-5 w-5" />
          Notificações Push
        </CardTitle>
        <CardDescription>
          Receba notificações no browser mesmo quando não está na aplicação
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Estado atual */}
        <div className="flex items-center justify-between p-4 bg-muted/30 rounded-lg">
          <div className="flex items-center gap-3">
            {isSubscribed ? (
              <>
                <CheckCircle className="h-5 w-5 text-green-600" />
                <div>
                  <p className="font-medium">Notificações Ativas</p>
                  <p className="text-sm text-muted-foreground">Receberá alertas importantes</p>
                </div>
              </>
            ) : permission === 'denied' ? (
              <>
                <XCircle className="h-5 w-5 text-red-600" />
                <div>
                  <p className="font-medium">Notificações Bloqueadas</p>
                  <p className="text-sm text-muted-foreground">Altere nas definições do browser</p>
                </div>
              </>
            ) : (
              <>
                <BellOff className="h-5 w-5 text-muted-foreground" />
                <div>
                  <p className="font-medium">Notificações Desativadas</p>
                  <p className="text-sm text-muted-foreground">Ative para receber alertas</p>
                </div>
              </>
            )}
          </div>
          <Badge className={isSubscribed ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}>
            {isSubscribed ? 'Ativo' : permission === 'denied' ? 'Bloqueado' : 'Inativo'}
          </Badge>
        </div>

        {/* Botões de ação */}
        <div className="flex flex-wrap gap-2">
          {permission !== 'denied' && (
            <>
              {!isSubscribed ? (
                <Button 
                  onClick={handleEnable} 
                  disabled={loading}
                  className="bg-teal-600 hover:bg-teal-700"
                >
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin mr-2" />
                  ) : (
                    <Bell className="h-4 w-4 mr-2" />
                  )}
                  Ativar Notificações
                </Button>
              ) : (
                <>
                  <Button 
                    variant="outline" 
                    onClick={handleDisable} 
                    disabled={loading}
                  >
                    {loading ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <BellOff className="h-4 w-4 mr-2" />
                    )}
                    Desativar
                  </Button>
                  <Button 
                    variant="outline" 
                    onClick={handleTestNotification}
                    disabled={loading}
                  >
                    Testar Notificação
                  </Button>
                </>
              )}
            </>
          )}
          
          {permission === 'denied' && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-800">
              <p className="font-medium mb-1">Notificações bloqueadas</p>
              <p>Para ativar, clique no ícone de cadeado na barra de endereço e permita notificações.</p>
            </div>
          )}
        </div>

        {/* Info sobre tipos de notificação */}
        <div className="pt-4 border-t">
          <p className="text-sm font-medium mb-2">Receberá notificações sobre:</p>
          <ul className="text-sm text-muted-foreground space-y-1">
            <li className="flex items-center gap-2">
              <CheckCircle className="h-3 w-3 text-green-600" />
              Novos processos atribuídos
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle className="h-3 w-3 text-green-600" />
              Alterações de estado em processos
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle className="h-3 w-3 text-green-600" />
              Documentos a expirar
            </li>
            <li className="flex items-center gap-2">
              <CheckCircle className="h-3 w-3 text-green-600" />
              Prazos e eventos agendados
            </li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
};

export default NotificationSettings;
