/**
 * UploadProgressContext - Gestão global de progresso de uploads
 * 
 * Permite que uploads continuem em background enquanto o utilizador
 * navega para outras páginas, mostrando sempre o progresso.
 */
import { createContext, useContext, useState, useCallback } from "react";

const UploadProgressContext = createContext(null);

export const useUploadProgress = () => {
  const context = useContext(UploadProgressContext);
  if (!context) {
    throw new Error("useUploadProgress must be used within UploadProgressProvider");
  }
  return context;
};

export const UploadProgressProvider = ({ children }) => {
  // Estado de uploads activos: { jobId: { status, total, processed, errors, clientName, startedAt } }
  const [activeUploads, setActiveUploads] = useState({});
  
  // Iniciar um novo upload job
  const startUpload = useCallback((jobId, { total, clientName }) => {
    setActiveUploads(prev => ({
      ...prev,
      [jobId]: {
        status: "running",
        total,
        processed: 0,
        errors: 0,
        clientName: clientName || "Upload Massivo",
        startedAt: new Date().toISOString(),
        currentFile: null,
      }
    }));
  }, []);
  
  // Actualizar progresso de um upload
  const updateProgress = useCallback((jobId, { processed, errors, currentFile }) => {
    setActiveUploads(prev => {
      if (!prev[jobId]) return prev;
      return {
        ...prev,
        [jobId]: {
          ...prev[jobId],
          processed: processed ?? prev[jobId].processed,
          errors: errors ?? prev[jobId].errors,
          currentFile: currentFile ?? prev[jobId].currentFile,
        }
      };
    });
  }, []);
  
  // Finalizar um upload job
  const finishUpload = useCallback((jobId, { success, message }) => {
    setActiveUploads(prev => {
      if (!prev[jobId]) return prev;
      return {
        ...prev,
        [jobId]: {
          ...prev[jobId],
          status: success ? "success" : "error",
          message,
          finishedAt: new Date().toISOString(),
        }
      };
    });
    
    // Auto-remover após 5 segundos se sucesso
    if (success) {
      setTimeout(() => {
        setActiveUploads(prev => {
          const { [jobId]: removed, ...rest } = prev;
          return rest;
        });
      }, 5000);
    }
  }, []);
  
  // Remover um upload job manualmente
  const dismissUpload = useCallback((jobId) => {
    setActiveUploads(prev => {
      const { [jobId]: removed, ...rest } = prev;
      return rest;
    });
  }, []);
  
  // Verificar se há uploads activos
  const hasActiveUploads = Object.values(activeUploads).some(u => u.status === "running");
  
  // Obter lista de uploads
  const uploadList = Object.entries(activeUploads).map(([id, data]) => ({
    id,
    ...data,
    progress: data.total > 0 ? Math.round((data.processed / data.total) * 100) : 0,
  }));
  
  return (
    <UploadProgressContext.Provider value={{
      activeUploads,
      uploadList,
      hasActiveUploads,
      startUpload,
      updateProgress,
      finishUpload,
      dismissUpload,
    }}>
      {children}
    </UploadProgressContext.Provider>
  );
};

export default UploadProgressContext;
