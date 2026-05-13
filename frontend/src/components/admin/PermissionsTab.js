/**
 * PermissionsTab — Gestor de Permissões Granulares
 *
 * Matrix visual onde o Admin/CEO pode ligar/desligar capabilities
 * por cargo (role defaults) ou por utilizador específico (overrides).
 *
 * Algoritmo de resolução (igual ao backend):
 * 1. admin/ceo → Super Admin Bypass (sempre true, não editável)
 * 2. User override → user.permissions.capabilities[cap]
 * 3. Fallback → role_defaults[role][cap]
 *
 * @component
 * @see backend/models/permissions.py — CAPABILITIES, ROLE_CAPABILITY_DEFAULTS
 */
import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Switch } from "../ui/switch";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { ScrollArea } from "../ui/scroll-area";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "../ui/select";
import {
  Shield, Users, Save, RotateCcw, Search, ChevronDown, ChevronRight,
  Loader2, AlertTriangle, Eye, Zap,
} from "lucide-react";
import { toast } from "sonner";
import { ROLE_LABELS, ROLE_COLORS, SUPER_ADMIN_ROLES } from "../../utils/roleUtils";
import { useAuth } from "../../contexts/AuthContext";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Cargos editáveis (exclui admin/ceo que têm bypass e cliente/parceiro)
const EDITABLE_ROLES = ["diretor", "administrativo", "consultor", "intermediario", "indexacao"];

const PermissionsTab = () => {
  const { user: currentUser } = useAuth();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [capabilities, setCapabilities] = useState({});
  const [categories, setCategories] = useState([]);
  const [roleDefaults, setRoleDefaults] = useState({});
  const [expandedCategories, setExpandedCategories] = useState({});
  const [dirty, setDirty] = useState(false);

  // Modo: "role" (por cargo) ou "user" (por utilizador)
  const [mode, setMode] = useState("role");
  const [selectedRole, setSelectedRole] = useState("consultor");

  // Modo utilizador
  const [users, setUsers] = useState([]);
  const [selectedUserId, setSelectedUserId] = useState("");
  const [userOverrides, setUserOverrides] = useState({});
  const [userEffectiveCaps, setUserEffectiveCaps] = useState({});
  const [userRole, setUserRole] = useState("");
  const [userSearchTerm, setUserSearchTerm] = useState("");

  // Estado local de edição (role defaults ou user overrides)
  const [localState, setLocalState] = useState({});

  // ─── Fetch data ───────────────────────────────────────────────
  const fetchCapabilities = useCallback(async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_URL}/api/admin/permissions/capabilities`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Erro ao carregar capabilities");
      const data = await res.json();

      setCapabilities(data.capabilities || {});
      setCategories(data.categories || []);
      setRoleDefaults(data.role_defaults || {});

      // Expandir todas as categorias por padrão
      const expanded = {};
      (data.categories || []).forEach(c => { expanded[c.id] = true; });
      setExpandedCategories(expanded);
    } catch (err) {
      console.error(err);
      toast.error("Erro ao carregar permissões");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchUsers = useCallback(async () => {
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_URL}/api/admin/users`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setUsers(Array.isArray(data) ? data : data.users || []);
      }
    } catch {
      // silent
    }
  }, []);

  const fetchUserPermissions = useCallback(async (userId) => {
    if (!userId) return;
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_URL}/api/admin/permissions/user/${userId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Erro");
      const data = await res.json();
      setUserOverrides(data.overrides || {});
      setUserEffectiveCaps(data.effective_capabilities || {});
      setUserRole(data.role || "");
      setLocalState(data.overrides || {});
      setDirty(false);
    } catch {
      toast.error("Erro ao carregar permissões do utilizador");
    }
  }, []);

  useEffect(() => { fetchCapabilities(); fetchUsers(); }, [fetchCapabilities, fetchUsers]);

  // Quando muda o role seleccionado, carregar os defaults
  useEffect(() => {
    if (mode === "role" && roleDefaults[selectedRole]) {
      setLocalState(roleDefaults[selectedRole]);
      setDirty(false);
    }
  }, [mode, selectedRole, roleDefaults]);

  // Quando muda o utilizador seleccionado
  useEffect(() => {
    if (mode === "user" && selectedUserId) {
      fetchUserPermissions(selectedUserId);
    }
  }, [mode, selectedUserId, fetchUserPermissions]);

  // ─── Toggle handlers ──────────────────────────────────────────
  const toggleCategory = (catId) => {
    setExpandedCategories(prev => ({ ...prev, [catId]: !prev[catId] }));
  };

  const handleToggle = (capKey, value) => {
    setLocalState(prev => ({ ...prev, [capKey]: value }));
    setDirty(true);
  };

  // ─── Save ─────────────────────────────────────────────────────
  const handleSave = async () => {
    try {
      setSaving(true);
      const token = localStorage.getItem("token");

      if (mode === "role") {
        const res = await fetch(`${API_URL}/api/admin/permissions/role-defaults/${selectedRole}`, {
          method: "PUT",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ capabilities: localState }),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Erro ao guardar");
        }
        toast.success(`Defaults do cargo "${ROLE_LABELS[selectedRole]}" atualizados`);
        // Refresh
        setRoleDefaults(prev => ({ ...prev, [selectedRole]: localState }));
      } else {
        const res = await fetch(`${API_URL}/api/admin/permissions/user/${selectedUserId}`, {
          method: "PUT",
          headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ capabilities: localState }),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || "Erro ao guardar");
        }
        toast.success("Permissões do utilizador atualizadas");
        fetchUserPermissions(selectedUserId);
      }
      setDirty(false);
    } catch (err) {
      toast.error(err.message || "Erro ao guardar permissões");
    } finally {
      setSaving(false);
    }
  };

  // ─── Reset ────────────────────────────────────────────────────
  const handleReset = () => {
    if (mode === "role") {
      setLocalState(roleDefaults[selectedRole] || {});
    } else {
      setLocalState(userOverrides || {});
    }
    setDirty(false);
  };

  const handleResetToRoleDefaults = async () => {
    if (!selectedUserId) return;
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_URL}/api/admin/users/${selectedUserId}/reset-permissions`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Erro");
      toast.success("Permissões redefinidas para o padrão do cargo");
      fetchUserPermissions(selectedUserId);
    } catch {
      toast.error("Erro ao redefinir permissões");
    }
  };

  // ─── Helpers ──────────────────────────────────────────────────
  const getCapValue = (capKey) => {
    if (mode === "role") {
      return Boolean(localState[capKey]);
    }
    // User mode: show effective value
    return Boolean(localState[capKey] !== undefined ? localState[capKey] : userEffectiveCaps[capKey]);
  };

  const isOverride = (capKey) => {
    if (mode !== "user") return false;
    return capKey in userOverrides;
  };

  const isDifferentFromDefault = (capKey) => {
    if (mode !== "user" || !userRole) return false;
    const defaultVal = roleDefaults[userRole]?.[capKey];
    const currentVal = localState[capKey];
    return currentVal !== undefined && currentVal !== defaultVal;
  };

  // Filter users for search
  const filteredUsers = users.filter(u =>
    !SUPER_ADMIN_ROLES.includes(u.role) &&
    u.role !== "cliente" &&
    u.role !== "parceiro" &&
    (u.name?.toLowerCase().includes(userSearchTerm.toLowerCase()) ||
     u.email?.toLowerCase().includes(userSearchTerm.toLowerCase()))
  );

  // ─── Render ───────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Shield className="h-5 w-5 text-red-500" />
            Permissões Granulares
          </CardTitle>
          <CardDescription>
            Controle fino de acessos — ligue ou desligue capabilities por cargo ou utilizador
          </CardDescription>
        </CardHeader>
        <CardContent>
          {/* Super Admin Notice */}
          <div className="flex items-center gap-2 p-3 bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg text-sm">
            <Zap className="h-4 w-4 text-amber-600 shrink-0" />
            <span className="text-amber-800 dark:text-amber-200">
              <strong>Admin</strong> e <strong>CEO</strong> têm acesso total (Super Admin Bypass) — não é possível restringir as suas permissões.
            </span>
          </div>

          {/* Mode Selector + Filters */}
          <div className="flex flex-col sm:flex-row gap-3 mt-4">
            <div className="flex gap-2">
              <Button
                variant={mode === "role" ? "default" : "outline"}
                size="sm"
                onClick={() => { setMode("role"); setDirty(false); }}
                className="gap-1.5"
              >
                <Users className="h-4 w-4" />
                Por Cargo
              </Button>
              <Button
                variant={mode === "user" ? "default" : "outline"}
                size="sm"
                onClick={() => { setMode("user"); setDirty(false); }}
                className="gap-1.5"
              >
                <Eye className="h-4 w-4" />
                Por Utilizador
              </Button>
            </div>

            {mode === "role" && (
              <Select value={selectedRole} onValueChange={setSelectedRole}>
                <SelectTrigger className="w-full sm:w-56">
                  <SelectValue placeholder="Selecionar cargo" />
                </SelectTrigger>
                <SelectContent>
                  {EDITABLE_ROLES.map(role => (
                    <SelectItem key={role} value={role}>
                      <span className="flex items-center gap-2">
                        <span className={`inline-block px-1.5 py-0.5 text-xs rounded ${ROLE_COLORS[role]}`}>
                          {ROLE_LABELS[role]}
                        </span>
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}

            {mode === "user" && (
              <div className="flex gap-2 flex-1">
                <div className="relative flex-1 max-w-xs">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Pesquisar utilizador..."
                    value={userSearchTerm}
                    onChange={(e) => setUserSearchTerm(e.target.value)}
                    className="pl-9"
                  />
                </div>
                <Select value={selectedUserId} onValueChange={setSelectedUserId}>
                  <SelectTrigger className="w-full sm:w-64">
                    <SelectValue placeholder="Selecionar utilizador" />
                  </SelectTrigger>
                  <SelectContent>
                    {filteredUsers.map(u => (
                      <SelectItem key={u.id} value={u.id}>
                        <span className="flex items-center gap-2">
                          {u.name}
                          <span className={`inline-block px-1.5 py-0.5 text-xs rounded ${ROLE_COLORS[u.role]}`}>
                            {ROLE_LABELS[u.role]}
                          </span>
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Permissions Matrix */}
      <Card>
        <CardContent className="p-0">
          <ScrollArea className="max-h-[65vh]">
            <div className="p-4">
              {categories.map(category => {
                const catCaps = Object.entries(capabilities)
                  .filter(([, meta]) => meta.category === category.id);

                if (catCaps.length === 0) return null;

                const isExpanded = expandedCategories[category.id];

                return (
                  <div key={category.id} className="mb-3">
                    {/* Category Header */}
                    <button
                      onClick={() => toggleCategory(category.id)}
                      className="flex items-center gap-2 w-full py-2 px-3 rounded-lg hover:bg-muted/50 transition-colors text-left"
                    >
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                      )}
                      <span className="font-semibold text-sm">{category.label}</span>
                      <Badge variant="outline" className="text-xs ml-auto">
                        {catCaps.filter(([k]) => getCapValue(k)).length}/{catCaps.length}
                      </Badge>
                    </button>

                    {/* Capabilities List */}
                    {isExpanded && (
                      <div className="ml-4 mt-1 space-y-1">
                        {catCaps.map(([capKey, meta]) => {
                          const value = getCapValue(capKey);
                          const override = isOverride(capKey);
                          const diffFromDefault = isDifferentFromDefault(capKey);

                          return (
                            <div
                              key={capKey}
                              className={`flex items-center justify-between py-2 px-3 rounded-md transition-colors ${
                                override || diffFromDefault
                                  ? "bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800"
                                  : "hover:bg-muted/30"
                              }`}
                            >
                              <div className="flex-1 min-w-0 mr-4">
                                <div className="flex items-center gap-2">
                                  <span className="text-sm font-medium">{meta.label}</span>
                                  {override && (
                                    <Badge variant="outline" className="text-[10px] px-1 py-0 bg-amber-100 text-amber-700 border-amber-300 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-700">
                                      OVERRIDE
                                    </Badge>
                                  )}
                                  {diffFromDefault && !override && (
                                    <Badge variant="outline" className="text-[10px] px-1 py-0 bg-orange-100 text-orange-700 border-orange-300">
                                      ALTERADO
                                    </Badge>
                                  )}
                                </div>
                                <p className="text-xs text-muted-foreground mt-0.5">{meta.description}</p>
                              </div>
                              <div className="flex items-center gap-2 shrink-0">
                                {value ? (
                                  <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium w-12 text-right">Permitido</span>
                                ) : (
                                  <span className="text-xs text-red-500 dark:text-red-400 font-medium w-12 text-right">Bloqueado</span>
                                )}
                                <Switch
                                  checked={value}
                                  onCheckedChange={(checked) => handleToggle(capKey, checked)}
                                  disabled={saving}
                                />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Action Bar */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <AlertTriangle className="h-3.5 w-3.5" />
          {dirty ? (
            <span className="text-amber-600 font-medium">Alterações por guardar</span>
          ) : (
            <span>Sem alterações pendentes</span>
          )}
        </div>
        <div className="flex gap-2">
          {mode === "user" && selectedUserId && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleResetToRoleDefaults}
              className="gap-1.5"
            >
              <RotateCcw className="h-4 w-4" />
              Redefinir para Padrão do Cargo
            </Button>
          )}
          <Button
            variant="outline"
            size="sm"
            onClick={handleReset}
            disabled={!dirty || saving}
            className="gap-1.5"
          >
            <RotateCcw className="h-4 w-4" />
            Reverter
          </Button>
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!dirty || saving}
            className="gap-1.5"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Guardar Alterações
          </Button>
        </div>
      </div>
    </div>
  );
};

export default PermissionsTab;
