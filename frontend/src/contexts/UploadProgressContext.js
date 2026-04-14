/**
 * UploadProgressContext — Contexto global de progresso de uploads com navegação persistente.
 *
 * PORQUÊ: No PowerCell, os uploads de documentos podem demorar (ficheiros grandes, upload S3,
 * processamento IA). Sem este contexto, o utilizador perderia o feedback de progresso ao
 * navegar para outra página durante um upload. Este contexto mantém o estado globalmente,
 * permitindo que qualquer componente mostre o progresso independente da rota activa.
 *
 * DECISÕES ARQUITECTURAIS:
 * - Estado por jobId: cada upload é identificado por um ID único, permitindo uploads
 *   paralelos com progresso independente.
 * - Auto-remoção em sucesso: uploads concluídos são removidos automaticamente após 5s
 *   para não poluir a interface. Uploads com erro persistem até descarte manual.
 * - startUpdate/updateProgress/finishUpload API: interface explícita em vez de estado
 *   directo, garantindo transições de estado válidas (running → success/error).
 * - ProgressBar global (GlobalUploadProgress): consome este contexto para mostrar uma
 *   barra fixa no topo da página durante uploads activos.
 *
 * @context {UploadProgressContext} — Fornecido via UploadProgressProvider em App.js
 * @hook {useUploadProgress} — Hook para consumir o contexto em componentes React
 *
 * @returns {Object} Estado e funções do progresso:
 *   - activeUploads {Object} — Mapa de uploads activos por jobId
 *   - uploadList {Array} — Lista formatada com percentagem de progresso
 *   - hasActiveUploads {boolean} — true se há uploads em curso
 *   - startUpload, updateProgress, finishUpload, dismissUpload {Function}
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
