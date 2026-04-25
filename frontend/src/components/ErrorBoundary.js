import React, { Component } from 'react';
import * as Sentry from '@sentry/react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

// ====================================================================
// SECTION ERROR BOUNDARY — "Airbag" para secções individuais
// ====================================================================
// Captura erros de runtime num componente específico e mostra
// uma UI de fallback contida, SEM crashar o resto da aplicação.
//
// Integração automática com Sentry para report de erros.
// ====================================================================

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1500;

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      eventId: null,
      retryCount: 0,
      isRetrying: false,
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    const { moduleName } = this.props;

    // Enviar erro ao Sentry com contexto do módulo
    const eventId = Sentry.captureException(error, {
      contexts: {
        react: {
          componentStack: errorInfo?.componentStack,
        },
        module: {
          name: moduleName || 'unknown',
          type: this.props.variant || 'section',
        },
      },
      tags: {
        error_boundary: moduleName || 'unknown',
        error_boundary_variant: this.props.variant || 'section',
      },
    });

    this.setState({ errorInfo, eventId });
  }

  handleRetry = () => {
    const { retryCount } = this.state;

    if (retryCount >= MAX_RETRIES) {
      // Máximo de tentativas atingido — não tenta mais
      return;
    }

    this.setState({ isRetrying: true });

    setTimeout(() => {
      this.setState(prev => ({
        hasError: false,
        error: null,
        errorInfo: null,
        eventId: null,
        retryCount: prev.retryCount + 1,
        isRetrying: false,
      }));
    }, RETRY_DELAY_MS);
  };

  handleGoHome = () => {
    window.location.href = '/';
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const { variant, moduleName, showRetry = true } = this.props;
    const { error, eventId, retryCount, isRetrying } = this.state;
    const canRetry = retryCount < MAX_RETRIES;
    const errorTime = new Date().toLocaleTimeString('pt-PT');

    // ── SECTION VARIANT (inline within page) ──
    if (variant === 'section') {
      return (
        <div className="rounded-lg border border-red-200 dark:border-red-800/50 bg-red-50 dark:bg-red-950/20 p-6 my-4">
          <div className="flex items-start gap-3">
            <div className="flex-shrink-0 mt-0.5">
              <AlertTriangle className="w-5 h-5 text-red-500" />
            </div>
            <div className="flex-1 min-w-0">
              <h3 className="text-sm font-semibold text-red-800 dark:text-red-300">
                Erro nesta secção{moduleName ? ` — ${moduleName}` : ''}
              </h3>
              <p className="text-xs text-red-600 dark:text-red-400 mt-1">
                {error?.message || 'Ocorreu um erro inesperado.'}
              </p>
              <div className="flex items-center gap-3 mt-3">
                {showRetry && canRetry && (
                  <button
                    onClick={this.handleRetry}
                    disabled={isRetrying}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white text-xs font-medium rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    <RefreshCw className={`w-3 h-3 ${isRetrying ? 'animate-spin' : ''}`} />
                    {isRetrying ? 'A tentar...' : `Tentar novamente (${retryCount}/${MAX_RETRIES})`}
                  </button>
                )}
                <button
                  onClick={this.handleGoHome}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 text-xs font-medium rounded-md hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
                >
                  <Home className="w-3 h-3" />
                  Voltar ao início
                </button>
              </div>
              <p className="text-[10px] text-red-400 dark:text-red-500 mt-2">
                {errorTime} · ID: {eventId || 'N/A'}
              </p>
            </div>
          </div>
        </div>
      );
    }

    // ── PAGE VARIANT (replaces full page content) ──
    if (variant === 'page') {
      return (
        <div className="min-h-[400px] flex items-center justify-center bg-background p-6">
          <div className="max-w-md w-full text-center space-y-4">
            <div className="mx-auto w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center">
              <AlertTriangle className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-lg font-semibold text-foreground">
              {moduleName || 'Página'} — Erro
            </h2>
            <p className="text-sm text-muted-foreground">
              Ocorreu um erro ao carregar esta página. O nosso equipa foi notificada automaticamente.
            </p>
            {error?.message && (
              <pre className="text-xs text-left bg-muted/50 rounded-lg p-3 overflow-auto max-h-32 font-mono text-muted-foreground">
                {error.message}
              </pre>
            )}
            <div className="flex gap-3 justify-center pt-2">
              {showRetry && canRetry && (
                <button
                  onClick={this.handleRetry}
                  disabled={isRetrying}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
                >
                  <RefreshCw className={`w-4 h-4 ${isRetrying ? 'animate-spin' : ''}`} />
                  {isRetrying ? 'A tentar...' : 'Tentar novamente'}
                </button>
              )}
              <button
                onClick={this.handleGoHome}
                className="inline-flex items-center gap-2 px-4 py-2 border border-input rounded-lg text-sm font-medium text-muted-foreground hover:bg-accent transition-colors"
              >
                <Home className="w-4 h-4" />
                Página inicial
              </button>
            </div>
            {retryCount >= MAX_RETRIES && (
              <p className="text-xs text-muted-foreground">
                Máximo de tentativas atingido. Recarregue a página ou contacte o suporte.
              </p>
            )}
            <p className="text-[10px] text-muted-foreground/60">
              {errorTime} · Event ID: {eventId || 'N/A'}
            </p>
          </div>
        </div>
      );
    }

    // ── FULLSCREEN VARIANT (global fallback, last resort) ──
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-950 p-4">
        <div className="max-w-md w-full text-center space-y-4">
          <div className="mx-auto w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full flex items-center justify-center">
            <AlertTriangle className="w-8 h-8 text-red-600 dark:text-red-400" />
          </div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            Algo correu mal
          </h1>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Ocorreu um erro inesperado na aplicação. O nosso equipa foi notificada automaticamente.
          </p>
          {error?.message && (
            <pre className="text-xs text-left bg-gray-100 dark:bg-gray-900 rounded-lg p-3 overflow-auto max-h-32 font-mono text-gray-500">
              {error.message}
            </pre>
          )}
          <div className="flex gap-3 justify-center">
            {showRetry && canRetry && (
              <button
                onClick={this.handleRetry}
                disabled={isRetrying}
                className="px-4 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700 text-sm font-medium disabled:opacity-50 transition-colors"
              >
                <RefreshCw className={`w-4 h-4 inline mr-2 ${isRetrying ? 'animate-spin' : ''}`} />
                {isRetrying ? 'A tentar...' : 'Tentar novamente'}
              </button>
            )}
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded-lg text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              Recarregar página
            </button>
          </div>
          <p className="text-[10px] text-gray-400">
            {errorTime} · Event ID: {eventId || 'N/A'}
          </p>
        </div>
      </div>
    );
  }
}
