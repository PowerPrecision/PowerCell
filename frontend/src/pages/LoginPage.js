/**
 * LoginPage — Página de autenticação do CRM PowerCell.
 *
 * PORQUÊ: Ponto de entrada do sistema com design split-screen. Suporta autenticação por
 * email/password com redirecionamento baseado no role do utilizador.
 *
 * @context {AuthContext} — Consome user, token para autenticação e permissões
 */

import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import { Button } from "../components/ui/button";
import { hasRole } from "../utils/roleUtils";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Mail, Lock, Loader2, Eye, EyeOff, Info } from "lucide-react";
import { toast } from "sonner";
import { extractErrorMessage } from "../utils/extractErrorMessage";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const showPortalInfo = searchParams.get("info") === "portal";

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const user = await login(email, password);
      toast.success("Login efetuado com sucesso!");
      
      // Redirecionar baseado no role
      if (hasRole(user, "admin")) {
        navigate("/admin");
      } else if (hasRole(user, "cliente")) {
        // Clientes não usam o dashboard de staff — redirecionar para aviso
        navigate("/login?info=portal");
      } else {
        // CEO e outros staff vão para /processos
        navigate("/processos");
      }
    } catch (error) {
      console.error("Login error:", error);
      toast.error(extractErrorMessage(error.response?.data?.detail, "Erro ao fazer login"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex">
      {/* Left side - Image/Brand - PowerCell Blue */}
      <div
        className="hidden lg:flex lg:w-1/2 bg-cover bg-center relative"
        style={{
          backgroundImage:
            "url('https://images.pexels.com/photos/18435276/pexels-photo-18435276.jpeg')",
        }}
      >
        <div className="absolute inset-0 bg-blue-950/90" />
        <div className="relative z-10 flex flex-col justify-center px-12 text-white">
          <div className="flex items-center gap-3 mb-6">
            <img
              src="/PowerCell-default.png"
              alt="PowerCell"
              className="h-12 w-auto object-contain"
            />
          </div>
          <h1 className="text-4xl font-bold mb-4 tracking-tight">PowerCell</h1>
          <p className="text-lg text-blue-100 max-w-md">
            Sistema de gestão de processos de crédito habitação e transações imobiliárias. 
            Acompanhe os seus processos em tempo real.
          </p>
          <div className="mt-8 flex gap-4">
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 rounded-full bg-amber-400"></div>
              <span className="text-sm text-blue-200">Crédito Habitação</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 rounded-full bg-blue-400"></div>
              <span className="text-sm text-blue-200">Imobiliária</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right side - Form */}
      <div className="flex-1 flex items-center justify-center p-4 md:p-8 bg-background">
        <Card className="w-full max-w-md border-border shadow-sm">
          <CardHeader className="space-y-1 text-center">
            <div className="flex justify-center mb-4 lg:hidden">
              <img
                src="/PowerCell-default.png"
                alt="PowerCell"
                className="h-10 w-auto object-contain"
              />
            </div>
            <CardTitle className="text-2xl font-bold tracking-tight text-foreground">
              Bem-vindo de volta
            </CardTitle>
            <CardDescription>
              Introduza as suas credenciais para aceder à sua conta
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Aviso para clientes que tentam login de staff */}
            {showPortalInfo && (
              <Alert className="mb-4 border-amber-200 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800">
                <Info className="h-4 w-4 text-amber-600" />
                <AlertDescription className="text-amber-800 dark:text-amber-200 text-sm">
                  Como cliente, deve aceder ao portal através do link enviado pelo seu consultor.
                  Este login é exclusivo para a equipa PowerCell.
                </AlertDescription>
              </Alert>
            )}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="email"
                    type="email"
                    placeholder="seu@email.com"
                    className="pl-10"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                    data-testid="login-email-input"
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    placeholder="••••••••"
                    className="pl-10 pr-10"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    data-testid="login-password-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    tabIndex={-1}
                    data-testid="toggle-password-visibility"
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </button>
                </div>
              </div>
              <Button
                type="submit"
                className="w-full bg-teal-600 hover:bg-teal-700 text-white"
                disabled={loading}
                data-testid="login-submit-btn"
              >
                {loading ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    A entrar...
                  </>
                ) : (
                  "Entrar"
                )}
              </Button>
            </form>
            <p className="mt-4 text-xs text-center text-muted-foreground">
              Para criar uma conta, contacte o administrador do sistema.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

