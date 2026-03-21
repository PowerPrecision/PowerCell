/**
 * ====================================================================
 * BANNER DE IMPERSONATE - CREDITOIMO
 * ====================================================================
 * Mostra um banner fixo no topo quando o admin está a ver o sistema
 * como outro utilizador.
 * ====================================================================
 */

import { useAuth } from "../contexts/AuthContext";
import { Button } from "./ui/button";
import { Eye, X, User } from "lucide-react";
import { toast } from "sonner";

const ImpersonateBanner = () => {
  const { user, isImpersonating, originalAdminName, stopImpersonating } = useAuth();

  if (!isImpersonating) {
    return null;
  }

  const handleStopImpersonating = async () => {
    try {
      await stopImpersonating();
      toast.success("Voltou à sua conta de administrador");
    } catch (error) {
      toast.error("Erro ao terminar sessão de visualização");
    }
  };

  return (
    <>
      {/* Banner fixo no topo - z-index alto para estar acima de tudo */}
      <div 
        className="fixed top-0 left-0 right-0 bg-amber-500 text-amber-950 h-12 shadow-md flex items-center"
        style={{ zIndex: 9999 }}
      >
        <div className="max-w-7xl mx-auto flex items-center justify-between w-full px-4">
          <div className="flex items-center gap-3">
            <Eye className="h-5 w-5 flex-shrink-0" />
            <span className="font-medium text-sm sm:text-base truncate">
              A ver como: <strong>{user?.name}</strong> ({user?.role})
            </span>
            <span className="text-amber-800 text-xs sm:text-sm hidden sm:inline truncate">
              • Sessão iniciada por {originalAdminName}
            </span>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={handleStopImpersonating}
            className="bg-white hover:bg-amber-50 text-amber-900 border-amber-600 flex-shrink-0"
            data-testid="stop-impersonate-btn"
          >
            <X className="h-4 w-4 sm:mr-1" />
            <span className="hidden sm:inline">Terminar Visualização</span>
          </Button>
        </div>
      </div>
      
      {/* Spacer para empurrar todo o conteúdo da página para baixo */}
      <div className="h-12 w-full flex-shrink-0" />
    </>
  );
};

export default ImpersonateBanner;
