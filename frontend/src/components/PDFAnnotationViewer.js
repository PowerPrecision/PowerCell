/**
 * ====================================================================
 * PDFAnnotationViewer - Visualizador de PDF com Anotações Contextuais
 * ====================================================================
 * Componente de visualização de PDF com sistema completo de anotações.
 * 
 * FUNCIONALIDADES:
 * - Carregamento e renderização de PDF via pdfjs-dist
 * - Pins de anotação posicionados sobre o PDF
 * - Modo de anotação para criar novas anotações por clique
 * - Popups de detalhe com edição, resolução e eliminação
 * - Zoom, navegação de páginas e scroll
 * - Filtros por tipo e estado de resolução
 * - Sidebar com lista de anotações
 * 
 * ====================================================================
 */
import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import * as pdfjsLib from "pdfjs-dist";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "./ui/dialog";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";
import { Textarea } from "./ui/textarea";
import { Input } from "./ui/input";
import { Checkbox } from "./ui/checkbox";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";
import {
  X,
  ZoomIn,
  ZoomOut,
  ChevronLeft,
  ChevronRight,
  MessageSquare,
  Plus,
  Edit,
  Trash2,
  CheckCircle,
  Filter,
  Pin,
  Eye,
  EyeOff,
  PanelRightOpen,
  PanelRightClose,
  Loader2,
  Save,
  CircleDot,
  Maximize2,
} from "lucide-react";
import { format, parseISO } from "date-fns";
import { pt } from "date-fns/locale";

// Configurar worker do pdfjs
pdfjsLib.GlobalWorkerOptions.workerSrc = "/pdf.worker.min.js";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// ====================================================================
// CONSTANTES
// ====================================================================

// Tipos de anotação com labels e cores
const ANNOTATION_TYPES = {
  note: { label: "Nota", color: "#3B82F6" },
  question: { label: "Questão", color: "#F59E0B" },
  warning: { label: "Aviso", color: "#EF4444" },
  financial: { label: "Financeiro", color: "#22C55E" },
  approval: { label: "Aprovação", color: "#8B5CF6" },
};

// Normalizar campos do backend para formato interno do componente
const normalizeAnnotation = (ann) => ({
  ...ann,
  page_number: ann.page || ann.page_number,
  position_x: ann.x ?? ann.position_x,
  position_y: ann.y ?? ann.position_y,
  type: ann.annotation_type || ann.type,
});

// Limites de zoom
const MIN_SCALE = 0.5;
const MAX_SCALE = 2.5;
const SCALE_STEP = 0.25;
const DEFAULT_SCALE = 1.0;

// Distância mínima (em percentagem) para agrupar pins
const PIN_CLUSTER_DISTANCE = 3;

// ====================================================================
// COMPONENTE PRINCIPAL
// ====================================================================

const PDFAnnotationViewer = ({
  processId,
  document,
  token,
  onClose,
  user,
}) => {
  // ====================================================================
  // STATE
  // ====================================================================
  const [pdfDoc, setPdfDoc] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [scale, setScale] = useState(DEFAULT_SCALE);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [rendering, setRendering] = useState(false);
  const [annotations, setAnnotations] = useState([]);
  const [annotationsLoading, setAnnotationsLoading] = useState(false);
  const [annotationMode, setAnnotationMode] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedAnnotation, setSelectedAnnotation] = useState(null);
  const [editingAnnotation, setEditingAnnotation] = useState(null);
  const [newAnnotationForm, setNewAnnotationForm] = useState(null);
  const [highlightedAnnotationId, setHighlightedAnnotationId] = useState(null);

  // Filtros
  const [typeFilters, setTypeFilters] = useState({
    note: true,
    question: true,
    warning: true,
    financial: true,
    approval: true,
  });
  const [statusFilter, setStatusFilter] = useState("all"); // "all" | "pending" | "resolved"

  // ====================================================================
  // REFS
  // ====================================================================
  const containerRef = useRef(null);
  const canvasContainerRef = useRef(null);
  const pageViewRefs = useRef({});
  const renderTasksRef = useRef([]);
  const annotationModeRef = useRef(false);

  // Manter ref atualizada para uso em event handlers
  useEffect(() => {
    annotationModeRef.current = annotationMode;
  }, [annotationMode]);

  // ====================================================================
  // MEMOIZADOS
  // ====================================================================

  // Anotações filtradas
  const filteredAnnotations = useMemo(() => {
    return annotations.filter((ann) => {
      if (!typeFilters[ann.type]) return false;
      if (statusFilter === "pending" && ann.resolved) return false;
      if (statusFilter === "resolved" && !ann.resolved) return false;
      return true;
    });
  }, [annotations, typeFilters, statusFilter]);

  // Anotações agrupadas por página
  const annotationsByPage = useMemo(() => {
    const grouped = {};
    filteredAnnotations.forEach((ann) => {
      if (!grouped[ann.page_number]) {
        grouped[ann.page_number] = [];
      }
      grouped[ann.page_number].push(ann);
    });
    // Ordenar por posição Y dentro de cada página
    Object.values(grouped).forEach((pageAnns) => {
      pageAnns.sort((a, b) => a.position_y - b.position_y);
    });
    return grouped;
  }, [filteredAnnotations]);

  // Agrupar anotações próximas para clusters de pins
  const annotationClusters = useMemo(() => {
    const clusters = {};

    Object.entries(annotationsByPage).forEach(([page, pageAnns]) => {
      const used = new Set();
      const pageClusters = [];

      pageAnns.forEach((ann, idx) => {
        if (used.has(idx)) return;
        const cluster = [ann];
        used.add(idx);

        pageAnns.forEach((otherAnn, otherIdx) => {
          if (used.has(otherIdx)) return;
          const dist = Math.sqrt(
            Math.pow(ann.position_x - otherAnn.position_x, 2) +
              Math.pow(ann.position_y - otherAnn.position_y, 2)
          );
          if (dist < PIN_CLUSTER_DISTANCE) {
            cluster.push(otherAnn);
            used.add(otherIdx);
          }
        });

        // Calcular posição média do cluster
        const avgX =
          cluster.reduce((sum, a) => sum + a.position_x, 0) / cluster.length;
        const avgY =
          cluster.reduce((sum, a) => sum + a.position_y, 0) / cluster.length;

        // Cor do cluster é a do primeiro tipo
        const clusterColor = ANNOTATION_TYPES[cluster[0].type]?.color || "#3B82F6";

        pageClusters.push({
          id: `cluster-${page}-${pageClusters.length}`,
          page: parseInt(page),
          x: avgX,
          y: avgY,
          annotations: cluster,
          color: clusterColor,
          count: cluster.length,
        });
      });

      clusters[page] = pageClusters;
    });

    return clusters;
  }, [annotationsByPage]);

  // Contagem de anotações por status
  const annotationCounts = useMemo(() => {
    const total = filteredAnnotations.length;
    const resolved = filteredAnnotations.filter((a) => a.resolved).length;
    const pending = total - resolved;
    return { total, resolved, pending };
  }, [filteredAnnotations]);

  // ====================================================================
  // API HELPERS
  // ====================================================================

  const apiFetch = useCallback(
    async (url, options = {}) => {
      const headers = {
        ...options.headers,
        Authorization: `Bearer ${token}`,
      };
      if (options.body && !(options.body instanceof FormData)) {
        headers["Content-Type"] = "application/json";
      }
      const response = await fetch(url, { ...options, headers });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Erro ${response.status}`);
      }
      return response;
    },
    [token]
  );

  // ====================================================================
  // CARREGAR PDF
  // ====================================================================

  useEffect(() => {
    let cancelled = false;

    const loadPdf = async () => {
      if (!document?.path) {
        setLoadError("Caminho do documento não especificado");
        setLoading(false);
        return;
      }

      setLoading(true);
      setLoadError(null);

      try {
        // Buscar PDF via proxy
        const proxyUrl = `${API_URL}/api/documents/proxy/${encodeURIComponent(document.path)}`;
        const response = await fetch(proxyUrl, {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (!response.ok) {
          throw new Error(`Erro ao carregar PDF: ${response.status}`);
        }

        const arrayBuffer = await response.arrayBuffer();

        if (cancelled) return;

        // Carregar com pdfjs
        const loadingTask = pdfjsLib.getDocument({ data: arrayBuffer });
        const doc = await loadingTask.promise;

        if (cancelled) return;

        setPdfDoc(doc);
        setTotalPages(doc.numPages);
        setCurrentPage(1);
        setLoading(false);
      } catch (error) {
        if (!cancelled) {
          console.error("Erro ao carregar PDF:", error);
          setLoadError(error.message || "Erro ao carregar o PDF");
          setLoading(false);
        }
      }
    };

    loadPdf();

    return () => {
      cancelled = true;
    };
  }, [document?.path, token]);

  // ====================================================================
  // BUSCAR ANOTAÇÕES
  // ====================================================================

  useEffect(() => {
    let cancelled = false;

    const fetchAnnotations = async () => {
      if (!document?.path || !processId) return;

      setAnnotationsLoading(true);
      try {
        const params = new URLSearchParams({
          document_path: document.path,
          process_id: processId,
        });
        const url = `${API_URL}/api/annotations/document?${params}`;
        const response = await apiFetch(url);
        const data = await response.json();

        if (!cancelled) {
          const rawAnnotations = Array.isArray(data) ? data : data.annotations || [];
          setAnnotations(rawAnnotations.map(normalizeAnnotation));
        }
      } catch (error) {
        console.error("Erro ao buscar anotações:", error);
        // Não mostrar erro crítico - anotações são opcionais
      } finally {
        if (!cancelled) {
          setAnnotationsLoading(false);
        }
      }
    };

    fetchAnnotations();

    return () => {
      cancelled = true;
    };
  }, [document?.path, processId, apiFetch]);

  // ====================================================================
  // RENDERIZAR PÁGINA
  // ====================================================================

  const renderPage = useCallback(
    async (pageNum, container) => {
      if (!pdfDoc || !container) return;

      // Cancelar render tasks anteriores para esta página
      if (renderTasksRef.current[pageNum]) {
        renderTasksRef.current[pageNum].cancel();
      }

      try {
        const page = await pdfDoc.getPage(pageNum);
        const viewport = page.getViewport({ scale });

        // Limpar container
        container.innerHTML = "";

        // Criar canvas
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d");

        // Alta resolução para displays Retina
        const dpr = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * dpr);
        canvas.height = Math.floor(viewport.height * dpr);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;

        context.scale(dpr, dpr);

        container.style.width = `${viewport.width}px`;
        container.style.height = `${viewport.height}px`;
        container.appendChild(canvas);

        // Renderizar
        const renderContext = {
          canvasContext: context,
          viewport: viewport,
        };

        const renderTask = page.render(renderContext);
        renderTasksRef.current[pageNum] = renderTask;

        setRendering(true);
        await renderTask.promise;
        setRendering(false);

        if (renderTasksRef.current[pageNum] === renderTask) {
          delete renderTasksRef.current[pageNum];
        }
      } catch (error) {
        if (error?.name !== "RenderingCancelledException") {
          console.error(`Erro ao renderizar página ${pageNum}:`, error);
        }
        setRendering(false);
      }
    },
    [pdfDoc, scale]
  );

  // Re-renderizar quando a escala mudar
  useEffect(() => {
    if (!pdfDoc || !canvasContainerRef.current) return;

    // Cancelar todos os render tasks
    Object.values(renderTasksRef.current).forEach((task) => {
      if (task && task.cancel) task.cancel();
    });
    renderTasksRef.current = {};

    const container = canvasContainerRef.current;
    renderPage(currentPage, container);
  }, [pdfDoc, currentPage, scale, renderPage]);

  // Cleanup ao desmontar
  useEffect(() => {
    return () => {
      Object.values(renderTasksRef.current).forEach((task) => {
        if (task && task.cancel) task.cancel();
      });
      renderTasksRef.current = {};
      if (pdfDoc) {
        pdfDoc.destroy();
      }
    };
  }, [pdfDoc]);

  // ====================================================================
  // HANDLERS DE NAVEGAÇÃO E ZOOM
  // ====================================================================

  const goToPage = useCallback(
    (pageNum) => {
      if (pageNum >= 1 && pageNum <= totalPages) {
        setCurrentPage(pageNum);
        setSelectedAnnotation(null);
        setNewAnnotationForm(null);
      }
    },
    [totalPages]
  );

  const zoomIn = useCallback(() => {
    setScale((prev) => Math.min(prev + SCALE_STEP, MAX_SCALE));
  }, []);

  const zoomOut = useCallback(() => {
    setScale((prev) => Math.max(prev - SCALE_STEP, MIN_SCALE));
  }, []);

  const zoomFit = useCallback(() => {
    setScale(DEFAULT_SCALE);
  }, []);

  // ====================================================================
  // HANDLERS DE ANOTAÇÕES - CRUD
  // ====================================================================

  const handleCanvasClick = useCallback(
    (e) => {
      if (!annotationModeRef.current) {
        // Se não está em modo de anotação, fechar popup de edição
        setSelectedAnnotation(null);
        setEditingAnnotation(null);
        return;
      }

      const container = canvasContainerRef.current;
      if (!container) return;

      const rect = container.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      // Converter para percentagem
      const xPercent = (x / rect.width) * 100;
      const yPercent = (y / rect.height) * 100;

      setNewAnnotationForm({
        page_number: currentPage,
        position_x: Math.round(xPercent * 10) / 10,
        position_y: Math.round(yPercent * 10) / 10,
        comment: "",
        type: "note",
      });
    },
    [currentPage]
  );

  const handleCreateAnnotation = useCallback(async () => {
    if (!newAnnotationForm?.comment?.trim()) return;

    try {
      const response = await apiFetch(`${API_URL}/api/annotations`, {
        method: "POST",
        body: JSON.stringify({
          process_id: processId,
          document_path: document.path,
          document_name: document.name,
          page: newAnnotationForm.page,
          x: newAnnotationForm.x,
          y: newAnnotationForm.y,
          comment: newAnnotationForm.comment.trim(),
          annotation_type: newAnnotationForm.type,
        }),
      });

      const newAnnotation = await response.json();
      setAnnotations((prev) => [...prev, normalizeAnnotation(newAnnotation)]);
      setNewAnnotationForm(null);
      setAnnotationMode(false);
    } catch (error) {
      console.error("Erro ao criar anotação:", error);
    }
  }, [newAnnotationForm, apiFetch, processId, document?.path, user]);

  const handleUpdateAnnotation = useCallback(
    async (annotationId, updates) => {
      try {
        const response = await apiFetch(`${API_URL}/api/annotations/${annotationId}`, {
          method: "PUT",
          body: JSON.stringify({
            comment: updates.comment,
            annotation_type: updates.type,
          }),
        });

        const updated = await response.json();
        setAnnotations((prev) =>
          prev.map((a) => (a.id === annotationId ? normalizeAnnotation({ ...a, ...updated }) : a))
        );
        setEditingAnnotation(null);
      } catch (error) {
        console.error("Erro ao atualizar anotação:", error);
      }
    },
    [apiFetch]
  );

  const handleDeleteAnnotation = useCallback(
    async (annotationId) => {
      try {
        await apiFetch(`${API_URL}/api/annotations/${annotationId}`, {
          method: "DELETE",
        });

        setAnnotations((prev) => prev.filter((a) => a.id !== annotationId));
        setSelectedAnnotation(null);
        setEditingAnnotation(null);
      } catch (error) {
        console.error("Erro ao eliminar anotação:", error);
      }
    },
    [apiFetch]
  );

  const handleToggleResolve = useCallback(
    async (annotation) => {
      try {
        const response = await apiFetch(
          `${API_URL}/api/annotations/${annotation.id}/resolve`,
          {
            method: "PUT",
            body: JSON.stringify({ resolved: !annotation.resolved }),
          }
        );

        const updated = await response.json();
        setAnnotations((prev) =>
          prev.map((a) => (a.id === annotation.id ? normalizeAnnotation({ ...a, ...updated }) : a))
        );
      } catch (error) {
        console.error("Erro ao alterar resolução:", error);
      }
    },
    [apiFetch]
  );

  // ====================================================================
  // HANDLER - NAVEGAR PARA ANOTAÇÃO VIA SIDEBAR
  // ====================================================================

  const handleNavigateToAnnotation = useCallback(
    (annotation) => {
      goToPage(annotation.page_number);
      setHighlightedAnnotationId(annotation.id);
      setSelectedAnnotation(annotation);

      // Remover highlight após 3 segundos
      setTimeout(() => {
        setHighlightedAnnotationId(null);
      }, 3000);
    },
    [goToPage]
  );

  // ====================================================================
  // RENDER - PIN DE ANOTAÇÃO
  // ====================================================================

  const renderPin = (cluster) => {
    const leftPercent = cluster.x;
    const topPercent = cluster.y;
    const isHighlighted = cluster.annotations.some(
      (a) => a.id === highlightedAnnotationId
    );
    const isResolved = cluster.annotations.every((a) => a.resolved);

    return (
      <TooltipProvider key={cluster.id} delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>
            <div
              onClick={(e) => {
                e.stopPropagation();
                if (cluster.count === 1) {
                  setSelectedAnnotation(cluster.annotations[0]);
                } else {
                  // Se cluster com múltiplas, selecionar a primeira
                  setSelectedAnnotation(cluster.annotations[0]);
                }
                setNewAnnotationForm(null);
              }}
              style={{
                position: "absolute",
                left: `${leftPercent}%`,
                top: `${topPercent}%`,
                transform: "translate(-50%, -50%)",
                zIndex: 20,
                cursor: "pointer",
              }}
            >
              <div
                style={{
                  width: isHighlighted ? 32 : 24,
                  height: isHighlighted ? 32 : 24,
                  borderRadius: "50%",
                  backgroundColor: cluster.color,
                  border: isHighlighted ? "3px solid #000" : "2px solid rgba(255,255,255,0.9)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  boxShadow: "0 2px 8px rgba(0,0,0,0.3)",
                  transition: "all 0.2s ease",
                  opacity: isResolved ? 0.5 : 1,
                  position: "relative",
                }}
                className="hover:scale-125"
              >
                {cluster.count > 1 && (
                  <span
                    style={{
                      color: "#fff",
                      fontSize: "10px",
                      fontWeight: 700,
                      lineHeight: 1,
                    }}
                  >
                    {cluster.count}
                  </span>
                )}
                {cluster.count === 1 && (
                  <div
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      backgroundColor: "#fff",
                    }}
                  />
                )}
              </div>
              {/* Indicador de resolvido */}
              {isResolved && (
                <div
                  style={{
                    position: "absolute",
                    top: -4,
                    right: -4,
                    width: 14,
                    height: 14,
                    borderRadius: "50%",
                    backgroundColor: "#22C55E",
                    border: "2px solid #fff",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <CheckCircle style={{ width: 8, height: 8, color: "#fff" }} />
                </div>
              )}
            </div>
          </TooltipTrigger>
          <TooltipContent
            side="top"
            className="max-w-[250px]"
          >
            <div className="text-xs space-y-1">
              {cluster.annotations.slice(0, 3).map((ann, idx) => (
                <div key={ann.id} className="flex items-start gap-1">
                  <div
                    className="w-2 h-2 rounded-full mt-1 shrink-0"
                    style={{ backgroundColor: ANNOTATION_TYPES[ann.type]?.color }}
                  />
                  <span className="line-clamp-2">
                    {ann.comment || "Sem comentário"}
                  </span>
                </div>
              ))}
              {cluster.count > 3 && (
                <p className="text-muted-foreground">
                  +{cluster.count - 3} mais...
                </p>
              )}
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  };

  // ====================================================================
  // RENDER - POPUP DE DETALHE DA ANOTAÇÃO
  // ====================================================================

  const renderAnnotationPopup = () => {
    if (!selectedAnnotation) return null;

    const ann = selectedAnnotation;
    const typeInfo = ANNOTATION_TYPES[ann.type] || ANNOTATION_TYPES.note;
    const isAuthor = ann.author_id === user?.id;
    const isAdmin = user?.role === "admin" || user?.role === "CEO";
    const isEditing = editingAnnotation?.id === ann.id;

    // Posicionar popup próximo ao pin
    const popupLeft = Math.min(Math.max(ann.position_x, 20), 60);
    const popupTop = ann.position_y > 50 ? ann.position_y - 25 : ann.position_y + 5;

    return (
      <div
        style={{
          position: "absolute",
          left: `${popupLeft}%`,
          top: `${popupTop}%`,
          zIndex: 50,
          width: "340px",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-white border border-gray-200 rounded-lg shadow-xl overflow-hidden">
          {/* Header do popup */}
          <div
            className="px-3 py-2 flex items-center justify-between"
            style={{ backgroundColor: typeInfo.color + "15" }}
          >
            <div className="flex items-center gap-2">
              <Badge
                className="text-white border-0 text-xs"
                style={{ backgroundColor: typeInfo.color }}
              >
                {typeInfo.label}
              </Badge>
              {ann.resolved && (
                <Badge
                  variant="outline"
                  className="text-xs bg-green-50 text-green-700 border-green-200"
                >
                  <CheckCircle className="w-3 h-3 mr-1" />
                  Resolvida
                </Badge>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => {
                setSelectedAnnotation(null);
                setEditingAnnotation(null);
              }}
            >
              <X className="h-3 w-3" />
            </Button>
          </div>

          {/* Corpo do popup */}
          <div className="p-3 space-y-3">
            {isEditing ? (
              /* Modo de edição */
              <>
                <div className="space-y-2">
                  <label className="text-xs font-medium text-gray-500">
                    Comentário
                  </label>
                  <Textarea
                    value={editingAnnotation.comment}
                    onChange={(e) =>
                      setEditingAnnotation((prev) => ({
                        ...prev,
                        comment: e.target.value,
                      }))
                    }
                    rows={3}
                    className="text-sm resize-none"
                    autoFocus
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-xs font-medium text-gray-500">
                    Tipo
                  </label>
                  <Select
                    value={editingAnnotation.type}
                    onValueChange={(value) =>
                      setEditingAnnotation((prev) => ({
                        ...prev,
                        type: value,
                      }))
                    }
                  >
                    <SelectTrigger className="h-8 text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(ANNOTATION_TYPES).map(([key, info]) => (
                        <SelectItem key={key} value={key}>
                          <div className="flex items-center gap-2">
                            <div
                              className="w-2.5 h-2.5 rounded-full"
                              style={{ backgroundColor: info.color }}
                            />
                            {info.label}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex justify-end gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setEditingAnnotation(null)}
                  >
                    Cancelar
                  </Button>
                  <Button
                    size="sm"
                    onClick={() =>
                      handleUpdateAnnotation(ann.id, {
                        comment: editingAnnotation.comment,
                        type: editingAnnotation.type,
                      })
                    }
                    disabled={!editingAnnotation.comment?.trim()}
                  >
                    <Save className="w-3 h-3 mr-1" />
                    Guardar
                  </Button>
                </div>
              </>
            ) : (
              /* Modo de visualização */
              <>
                <p className="text-sm text-gray-800 whitespace-pre-wrap">
                  {ann.comment}
                </p>

                {/* Metadados */}
                <div className="flex items-center gap-3 text-xs text-gray-500">
                  <span className="font-medium">{ann.author_name || "Desconhecido"}</span>
                  <span>•</span>
                  <span>
                    {ann.created_at
                      ? format(parseISO(ann.created_at), "dd/MM/yyyy HH:mm", {
                          locale: pt,
                        })
                      : ""}
                  </span>
                </div>

                {/* Ações */}
                <div className="flex items-center gap-1 pt-1 border-t">
                  {isAuthor && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() =>
                        setEditingAnnotation({
                          id: ann.id,
                          comment: ann.comment,
                          type: ann.type,
                        })
                      }
                    >
                      <Edit className="w-3 h-3 mr-1" />
                      Editar
                    </Button>
                  )}

                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => handleToggleResolve(ann)}
                  >
                    {ann.resolved ? (
                      <>
                        <Eye className="w-3 h-3 mr-1" />
                        Reabrir
                      </>
                    ) : (
                      <>
                        <CheckCircle className="w-3 h-3 mr-1" />
                        Resolver
                      </>
                    )}
                  </Button>

                  {(isAuthor || isAdmin) && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 text-xs text-red-600 hover:text-red-700 hover:bg-red-50"
                      onClick={() => handleDeleteAnnotation(ann.id)}
                    >
                      <Trash2 className="w-3 h-3 mr-1" />
                      Eliminar
                    </Button>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    );
  };

  // ====================================================================
  // RENDER - FORMULÁRIO DE NOVA ANOTAÇÃO
  // ====================================================================

  const renderNewAnnotationForm = () => {
    if (!newAnnotationForm) return null;

    const formLeft = Math.min(
      Math.max(newAnnotationForm.position_x, 15),
      55
    );
    const formTop =
      newAnnotationForm.position_y > 50
        ? newAnnotationForm.position_y - 20
        : newAnnotationForm.position_y + 5;

    return (
      <div
        style={{
          position: "absolute",
          left: `${formLeft}%`,
          top: `${formTop}%`,
          zIndex: 50,
          width: "320px",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-white border-2 border-blue-300 rounded-lg shadow-xl overflow-hidden">
          <div className="px-3 py-2 bg-blue-50 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Plus className="w-4 h-4 text-blue-600" />
              <span className="text-sm font-medium text-blue-700">
                Nova Anotação
              </span>
              <span className="text-xs text-blue-500">
                Pág. {newAnnotationForm.page_number}
              </span>
            </div>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => setNewAnnotationForm(null)}
            >
              <X className="h-3 w-3" />
            </Button>
          </div>

          <div className="p-3 space-y-3">
            {/* Tipo */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-500">Tipo</label>
              <Select
                value={newAnnotationForm.type}
                onValueChange={(value) =>
                  setNewAnnotationForm((prev) => ({
                    ...prev,
                    type: value,
                  }))
                }
              >
                <SelectTrigger className="h-8 text-sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(ANNOTATION_TYPES).map(([key, info]) => (
                    <SelectItem key={key} value={key}>
                      <div className="flex items-center gap-2">
                        <div
                          className="w-2.5 h-2.5 rounded-full"
                          style={{ backgroundColor: info.color }}
                        />
                        {info.label}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Comentário */}
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-500">
                Comentário
              </label>
              <Textarea
                value={newAnnotationForm.comment}
                onChange={(e) =>
                  setNewAnnotationForm((prev) => ({
                    ...prev,
                    comment: e.target.value,
                  }))
                }
                rows={3}
                className="text-sm resize-none"
                placeholder="Escreva a sua anotação..."
                autoFocus
              />
            </div>

            {/* Ações */}
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setNewAnnotationForm(null)}
              >
                Cancelar
              </Button>
              <Button
                size="sm"
                onClick={handleCreateAnnotation}
                disabled={!newAnnotationForm.comment?.trim()}
              >
                <MessageSquare className="w-3 h-3 mr-1" />
                Criar Anotação
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  // ====================================================================
  // RENDER - SIDEBAR DE ANOTAÇÕES
  // ====================================================================

  const renderSidebar = () => {
    if (!sidebarOpen) return null;

    // Lista ordenada por página e posição
    const sortedAnnotations = [...filteredAnnotations].sort((a, b) => {
      if (a.page_number !== b.page_number) return a.page_number - b.page_number;
      return a.position_y - b.position_y;
    });

    return (
      <div className="w-80 border-l bg-gray-950 text-gray-100 flex flex-col shrink-0">
        {/* Header da sidebar */}
        <div className="p-3 border-b border-gray-800">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-sm flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-blue-400" />
              Anotações
            </h3>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-gray-400 hover:text-white hover:bg-gray-800"
              onClick={() => setSidebarOpen(false)}
            >
              <PanelRightClose className="h-4 w-4" />
            </Button>
          </div>

          {/* Contagens */}
          <div className="flex items-center gap-2 mb-3">
            <Badge variant="secondary" className="bg-gray-800 text-gray-300 text-xs">
              {annotationCounts.total} total
            </Badge>
            <Badge variant="secondary" className="bg-amber-900/50 text-amber-300 text-xs">
              {annotationCounts.pending} pendentes
            </Badge>
            <Badge variant="secondary" className="bg-green-900/50 text-green-300 text-xs">
              {annotationCounts.resolved} resolvidas
            </Badge>
          </div>

          {/* Filtro por estado */}
          <div className="space-y-1">
            <label className="text-xs text-gray-500 font-medium">Estado</label>
            <div className="flex gap-1">
              {[
                { value: "all", label: "Todas" },
                { value: "pending", label: "Pendentes" },
                { value: "resolved", label: "Resolvidas" },
              ].map((opt) => (
                <Button
                  key={opt.value}
                  variant={statusFilter === opt.value ? "default" : "ghost"}
                  size="sm"
                  className={`h-6 text-xs px-2 ${
                    statusFilter === opt.value
                      ? "bg-blue-600 hover:bg-blue-700 text-white"
                      : "text-gray-400 hover:text-white hover:bg-gray-800"
                  }`}
                  onClick={() => setStatusFilter(opt.value)}
                >
                  {opt.label}
                </Button>
              ))}
            </div>
          </div>
        </div>

        {/* Filtros por tipo */}
        <div className="p-3 border-b border-gray-800">
          <label className="text-xs text-gray-500 font-medium mb-2 block">
            <Filter className="w-3 h-3 inline mr-1" />
            Filtrar por Tipo
          </label>
          <div className="space-y-2">
            {Object.entries(ANNOTATION_TYPES).map(([key, info]) => (
              <label
                key={key}
                className="flex items-center gap-2 cursor-pointer group"
              >
                <Checkbox
                  checked={typeFilters[key]}
                  onCheckedChange={(checked) =>
                    setTypeFilters((prev) => ({
                      ...prev,
                      [key]: !!checked,
                    }))
                  }
                  className="data-[state=checked]:bg-blue-600 data-[state=checked]:border-blue-600"
                />
                <div
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: info.color }}
                />
                <span className="text-xs text-gray-300 group-hover:text-white">
                  {info.label}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Lista de anotações */}
        <ScrollArea className="flex-1">
          <div className="p-2">
            {annotationsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-5 h-5 text-gray-500 animate-spin" />
              </div>
            ) : sortedAnnotations.length === 0 ? (
              <div className="text-center py-8">
                <MessageSquare className="w-8 h-8 text-gray-600 mx-auto mb-2" />
                <p className="text-xs text-gray-500">
                  {annotations.length === 0
                    ? "Sem anotações neste documento"
                    : "Nenhuma anotação corresponde aos filtros"}
                </p>
              </div>
            ) : (
              <div className="space-y-1">
                {sortedAnnotations.map((ann) => {
                  const typeInfo = ANNOTATION_TYPES[ann.type] || ANNOTATION_TYPES.note;
                  const isSelected = selectedAnnotation?.id === ann.id;
                  const isOnCurrentPage = ann.page_number === currentPage;

                  return (
                    <div
                      key={ann.id}
                      onClick={() => handleNavigateToAnnotation(ann)}
                      className={`p-2 rounded-lg cursor-pointer transition-all ${
                        isSelected
                          ? "bg-blue-900/40 border border-blue-700/50"
                          : "hover:bg-gray-800/80 border border-transparent"
                      } ${highlightedAnnotationId === ann.id ? "ring-1 ring-blue-400" : ""}`}
                    >
                      <div className="flex items-start gap-2">
                        <div
                          className="w-3 h-3 rounded-full mt-0.5 shrink-0"
                          style={{ backgroundColor: typeInfo.color }}
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1 mb-0.5">
                            <span className="text-[10px] text-gray-500 font-medium">
                              Pág. {ann.page_number}
                            </span>
                            {ann.resolved && (
                              <CheckCircle className="w-3 h-3 text-green-500" />
                            )}
                            {!isOnCurrentPage && (
                              <span className="text-[10px] text-gray-600 bg-gray-800 px-1 rounded">
                                outra pág.
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-gray-300 line-clamp-2">
                            {ann.comment || "Sem comentário"}
                          </p>
                          <div className="flex items-center gap-1 mt-1">
                            <span className="text-[10px] text-gray-600">
                              {ann.author_name || ""}
                            </span>
                            {ann.created_at && (
                              <>
                                <span className="text-[10px] text-gray-700">•</span>
                                <span className="text-[10px] text-gray-600">
                                  {format(parseISO(ann.created_at), "dd/MM/yy", {
                                    locale: pt,
                                  })}
                                </span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </ScrollArea>
      </div>
    );
  };

  // ====================================================================
  // RENDER - HEADER / TOOLBAR
  // ====================================================================

  const renderHeader = () => {
    return (
      <div className="flex items-center justify-between px-4 py-2 border-b bg-white shrink-0">
        {/* Lado esquerdo - Nome e navegação */}
        <div className="flex items-center gap-3 min-w-0">
          {/* Botão sidebar */}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            title={sidebarOpen ? "Ocultar painel" : "Mostrar painel"}
          >
            {sidebarOpen ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRightOpen className="h-4 w-4" />
            )}
          </Button>

          {/* Nome do documento */}
          <div className="min-w-0">
            <h2 className="text-sm font-semibold truncate max-w-[200px]" title={document?.name}>
              {document?.name || "Documento"}
            </h2>
          </div>

          {/* Navegação de páginas */}
          {totalPages > 0 && (
            <div className="flex items-center gap-1 ml-2">
              <Button
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={() => goToPage(currentPage - 1)}
                disabled={currentPage <= 1}
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </Button>
              <div className="flex items-center gap-1 px-2">
                <Input
                  type="number"
                  value={currentPage}
                  onChange={(e) => {
                    const val = parseInt(e.target.value);
                    if (!isNaN(val)) goToPage(val);
                  }}
                  className="w-12 h-7 text-center text-xs"
                  min={1}
                  max={totalPages}
                />
                <span className="text-xs text-gray-500">/ {totalPages}</span>
              </div>
              <Button
                variant="outline"
                size="icon"
                className="h-7 w-7"
                onClick={() => goToPage(currentPage + 1)}
                disabled={currentPage >= totalPages}
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </div>

        {/* Lado direito - Controles */}
        <div className="flex items-center gap-1.5">
          {/* Badge de contagem */}
          <Badge variant="secondary" className="text-xs bg-gray-100">
            <Pin className="w-3 h-3 mr-1" />
            {annotationCounts.total}
          </Badge>

          {/* Controles de zoom */}
          <div className="flex items-center gap-0.5 border rounded-md px-0.5">
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={zoomOut} disabled={scale <= MIN_SCALE}>
              <ZoomOut className="h-3.5 w-3.5" />
            </Button>
            <span className="text-xs text-gray-600 px-1.5 min-w-[40px] text-center">
              {Math.round(scale * 100)}%
            </span>
            <Button variant="ghost" size="icon" className="h-7 w-7" onClick={zoomIn} disabled={scale >= MAX_SCALE}>
              <ZoomIn className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={zoomFit}
              title="Ajustar à página"
            >
              <Maximize2 className="h-3.5 w-3.5" />
            </Button>
          </div>

          {/* Toggle modo de anotação */}
          <Button
            variant={annotationMode ? "default" : "outline"}
            size="sm"
            className={`h-8 text-xs ${
              annotationMode
                ? "bg-blue-600 hover:bg-blue-700 text-white"
                : ""
            }`}
            onClick={() => {
              setAnnotationMode(!annotationMode);
              setNewAnnotationForm(null);
              setSelectedAnnotation(null);
            }}
          >
            {annotationMode ? (
              <>
                <CircleDot className="w-3.5 h-3.5 mr-1.5 animate-pulse" />
                A Anotar...
              </>
            ) : (
              <>
                <Plus className="w-3.5 h-3.5 mr-1.5" />
                Adicionar Anotação
              </>
            )}
          </Button>

          {/* Fechar */}
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
    );
  };

  // ====================================================================
  // RENDER - ÁREA DO PDF
  // ====================================================================

  const renderPdfArea = () => {
    if (loading) {
      return (
        <div className="flex-1 flex items-center justify-center bg-gray-100">
          <div className="text-center space-y-3">
            <Loader2 className="w-8 h-8 text-blue-500 animate-spin mx-auto" />
            <p className="text-sm text-gray-500">A carregar documento...</p>
          </div>
        </div>
      );
    }

    if (loadError) {
      return (
        <div className="flex-1 flex items-center justify-center bg-gray-100">
          <div className="text-center space-y-3 max-w-md">
            <div className="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto">
              <X className="w-6 h-6 text-red-500" />
            </div>
            <p className="text-sm text-gray-700 font-medium">
              Erro ao carregar o documento
            </p>
            <p className="text-xs text-gray-500">{loadError}</p>
            <Button variant="outline" size="sm" onClick={onClose}>
              Fechar
            </Button>
          </div>
        </div>
      );
    }

    return (
      <div
        className="flex-1 overflow-auto bg-gray-200 relative"
        ref={containerRef}
        onClick={handleCanvasClick}
        style={{
          cursor: annotationMode ? "crosshair" : "default",
        }}
      >
        {/* Indicador de modo de anotação */}
        {annotationMode && (
          <div className="absolute top-3 left-1/2 transform -translate-x-1/2 z-30 bg-blue-600 text-white px-4 py-1.5 rounded-full shadow-lg flex items-center gap-2 text-xs font-medium">
            <CircleDot className="w-3.5 h-3.5 animate-pulse" />
            Clique no PDF para adicionar uma anotação
            <Button
              variant="ghost"
              size="sm"
              className="h-5 px-2 text-xs text-blue-100 hover:text-white hover:bg-blue-700"
              onClick={(e) => {
                e.stopPropagation();
                setAnnotationMode(false);
              }}
            >
              Cancelar
            </Button>
          </div>
        )}

        {/* Indicador de carregamento de renderização */}
        {rendering && (
          <div className="absolute top-3 right-3 z-30 bg-white/90 backdrop-blur-sm px-3 py-1 rounded-full shadow text-xs text-gray-500 flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 animate-spin" />
            A renderizar...
          </div>
        )}

        {/* Container da página do PDF */}
        <div className="flex justify-center py-6 px-4">
          <div className="relative shadow-2xl bg-white" style={{ lineHeight: 0 }}>
            <div
              ref={canvasContainerRef}
              className="relative"
              style={{
                overflow: "hidden",
              }}
            >
              {/* Canvas container - será preenchido pelo render */}
            </div>

            {/* Overlay de pins de anotação */}
            {annotationClusters[currentPage] &&
              annotationClusters[currentPage].map((cluster) =>
                renderPin(cluster)
              )}

            {/* Popup de detalhe */}
            {renderAnnotationPopup()}

            {/* Formulário de nova anotação */}
            {renderNewAnnotationForm()}
          </div>
        </div>
      </div>
    );
  };

  // ====================================================================
  // RENDER PRINCIPAL
  // ====================================================================

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent
        className="max-w-[95vw] max-h-[95vh] p-0 gap-0 overflow-hidden flex flex-col"
        title="Visualizador de Documento"
      >
        <VisuallyHidden>
          <DialogTitle>
            {document?.name
              ? `Anotações - ${document.name}`
              : "Visualizador de Documento"}
          </DialogTitle>
          <DialogDescription>
            Visualizador de PDF com sistema de anotações contextuais
          </DialogDescription>
        </VisuallyHidden>

        {/* Header / Toolbar */}
        {renderHeader()}

        {/* Conteúdo principal */}
        <div className="flex flex-1 overflow-hidden">
          {/* Área do PDF */}
          {renderPdfArea()}

          {/* Sidebar */}
          {renderSidebar()}
        </div>
      </DialogContent>
    </Dialog>
  );
};

export default PDFAnnotationViewer;
