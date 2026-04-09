import React from "react";
import ReactDOM from "react-dom/client";
import * as Sentry from "@sentry/react";
import "./index.css";
import App from "./App";

// O19 - Accessibility testing in development
if (import.meta.env.DEV) {
  import("@axe-core/react").then((axe) => {
    axe.default(React, ReactDOM, 3000);
    console.log("axe-core a11y testing enabled (dev only)");
  }).catch(() => {});
}

// ====================================================================
// SENTRY INITIALIZATION - Observabilidade e tracking de erros
// Suporta: VITE_DSN_SENTRY_FRONTEND (preferido) e VITE_SENTRY_DSN (legado)
// ====================================================================
const SENTRY_DSN = import.meta.env.VITE_DSN_SENTRY_FRONTEND || import.meta.env.VITE_SENTRY_DSN || '';

if (SENTRY_DSN) {
  Sentry.init({
    dsn: SENTRY_DSN,
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || 'development',
    integrations: [
      Sentry.browserTracingIntegration(),
      Sentry.replayIntegration({
        maskAllText: false,
        blockAllMedia: false,
      }),
    ],
    // Performance Monitoring
    tracesSampleRate: parseFloat(import.meta.env.VITE_SENTRY_TRACES_SAMPLE_RATE || '1.0'),
    // Session Replay
    replaysSessionSampleRate: 0.1,
    replaysOnErrorSampleRate: 1.0,
    // Send default PII (personal info)
    sendDefaultPii: import.meta.env.VITE_SENTRY_SEND_DEFAULT_PII === 'true',
  });
  console.log('✅ Sentry initialized for frontend');
} else {
  console.log('⚠️ Sentry DSN not configured - error tracking disabled');
}

// ====================================================================
// REACT APP MOUNT POINT
// ====================================================================
// document.getElementById("root") é a forma CORRETA de montar a app React.
// Isto NÃO é uma violação do paradigma - é o ponto de entrada onde o React
// assume o controlo da DOM. O React 18's createRoot API requer uma referência
// ao elemento DOM onde a app será renderizada.
// ====================================================================
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
