import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import path from 'path'
import { resolveBuildTimeBackendUrl } from './src/utils/apiBaseUrl.js'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Carregar variáveis de ambiente (prefixo '' = carregar TODAS as vars dos ficheiros .env)
  const env = loadEnv(mode, process.cwd(), '')

  // Sentry: Só ativa source map upload em produção
  const isProduction = mode === 'production'
  // Auth token: prioridade system env (Render) → .env file (local dev)
  const sentryAuthToken = process.env.SENTRY_AUTH_TOKEN || env.SENTRY_AUTH_TOKEN
  const sentryOrg = process.env.SENTRY_ORG || env.SENTRY_ORG || 'power-precision'
  const sentryProject = process.env.SENTRY_PROJECT || env.SENTRY_PROJECT || 'powercell-frontend'
  const sentryRelease = process.env.SENTRY_RELEASE || env.SENTRY_RELEASE || `powercell@${Date.now()}`

  // URL do backend embebido no bundle. A regra está centralizada para que um
  // build de dev sem REACT_APP_BACKEND_URL não fale, em silêncio, com produção.
  const backendUrl = resolveBuildTimeBackendUrl({
    envUrl: env.REACT_APP_BACKEND_URL || process.env.REACT_APP_BACKEND_URL,
    mode,
  })
  if (backendUrl.source === 'local-fallback') {
    console.warn(
      `⚠️  REACT_APP_BACKEND_URL não definido (mode=${mode}). A usar o backend local ${backendUrl.url}. ` +
      'Defina a variável no .env do frontend para apontar para o ambiente pretendido.'
    )
  } else if (backendUrl.source === 'production-fallback') {
    console.warn(
      `⚠️  REACT_APP_BACKEND_URL não definido num build de produção. A usar o fallback ${backendUrl.url}. ` +
      'Configure a variável no serviço de deploy.'
    )
  } else {
    console.log(`🔗 Backend do bundle: ${backendUrl.url} (REACT_APP_BACKEND_URL)`)
  }

  return {
    plugins: [
      react(),
      // Sentry: Upload automático de source maps para o dashboard
      // Só corre em build de produção quando SENTRY_AUTH_TOKEN está configurado
      isProduction && sentryAuthToken && sentryVitePlugin({
        authToken: sentryAuthToken,
        org: sentryOrg,
        project: sentryProject,
        sourcemaps: {
          // Gerar source maps mesmo que não estejam expostos ao browser
          filesToDeleteAfterUpload: ['**/*.map'],
        },
        release: {
          name: sentryRelease,
        },
      }),
    ].filter(Boolean),

    // Resolver alias @ para src/
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
      dedupe: ['react', 'react-dom', 'react-router-dom', 'react-is'],
      // conditions: ['development'], // Disabled — production mode
    },

    // Tratar ficheiros .js como JSX (compatibilidade CRA)
    esbuild: {
      loader: 'jsx',
      include: /src\/.*\.jsx?$/,
      exclude: [],
      // Segurança: remover TODAS as chamadas console.* e debugger em produção
      // Em desenvolvimento os logs mantêm-se para debugging
      drop: isProduction ? ['console', 'debugger'] : [],
    },

    // Optimizações de dependências - TAMBÉM precisa do loader JSX
    optimizeDeps: {
      include: [
        'react',
        'react-dom',
        'react-router-dom',
        'axios',
        'date-fns',
        'lucide-react',
      ],
      esbuildOptions: {
        loader: {
          '.js': 'jsx',
        },
      },
    },

    // Servidor de desenvolvimento
    server: {
      port: 3000,
      host: '0.0.0.0',
      strictPort: true,
      // Permitir todos os hosts (necessário para preview environments)
      allowedHosts: true,
      hmr: {
        overlay: true,
      },
      watch: {
        usePolling: true,
        interval: 100,
      },
    },

    // Preview server (para produção)
    preview: {
      port: 3000,
      host: '0.0.0.0',
    },

    // Build configuration
    build: {
      outDir: 'dist',
      // Source Maps: 'hidden' gera os .map mas NÃO os referencia no JS final.
      // O ficheiro .map é gerado e enviado ao Sentry, mas o browser nunca o descarrega.
      sourcemap: isProduction ? 'hidden' : true,
      minify: true,
      chunkSizeWarningLimit: 1000,
      rollupOptions: {
        output: {
          // Group packages with internal circular deps into single chunks
          // to prevent TDZ errors from cross-chunk initialization order
          manualChunks(id) {
            if (
              id.includes('node_modules/@radix-ui/') ||
              id.includes('node_modules/cmdk/') ||
              id.includes('node_modules/vaul/')
            ) {
              return 'vendor-radix'
            }
            if (id.includes('node_modules/recharts/') || id.includes('node_modules/victory-vendor/')) {
              return 'vendor-recharts'
            }
          },
        },
      },
    },

    // Definir variáveis de ambiente que começam com REACT_APP_
    // Usando import.meta.env para compatibilidade com Vite
    define: {
      // Manter compatibilidade com process.env (CRA legacy)
      ...Object.keys(env)
        .filter(key => key.startsWith('REACT_APP_'))
        .reduce((acc, key) => {
          acc[`process.env.${key}`] = JSON.stringify(env[key])
          return acc
        }, {}),
      // SEMPRE definir REACT_APP_BACKEND_URL.
      // A regra do fallback vive em `src/utils/apiBaseUrl.js` (ponto único):
      // um build que NÃO seja de produção nunca cai para a API de produção —
      // cai para o backend local. Ver o cabeçalho desse módulo.
      'process.env.REACT_APP_BACKEND_URL': JSON.stringify(backendUrl.url),
      // Note: NODE_ENV is set by Vite automatically based on mode
    },

    // ── VITEST (Épico 6) ───────────────────────────────────────────────
    // Vive aqui, e não num vitest.config.js separado, para herdar o que o
    // build já define e que os testes PRECISAM: o alias `@`, o `define` do
    // process.env e — sobretudo — o loader JSX para ficheiros `.js` (neste
    // projecto há JSX dentro de `.js`, herança do CRA). Duplicar isso num
    // segundo ficheiro seria a próxima fonte de divergência silenciosa.
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.js'],
      css: false,
      include: ['src/**/*.{test,spec}.{js,jsx}'],
      exclude: ['node_modules/**', 'dist/**', 'e2e/**', 'plugins/**'],
      alias: {
        // Os 276 testes de utilitários importam de `node:test`. Sem esta
        // ponte registavam-se no corredor do Node e o Vitest não via nada.
        // Só no ambiente de teste — o build não conhece este alias.
        'node:test': new URL('./src/test/nodeTestShim.js', import.meta.url).pathname,
      },
      coverage: {
        provider: 'v8',
        reporter: ['text', 'html', 'lcov'],
        include: ['src/**/*.{js,jsx}'],
        exclude: [
          'src/**/*.{test,spec}.{js,jsx}',
          'src/test/**',
          'src/components/ui/**',
        ],
      },
    },

    // CSS configuration
    css: {
      devSourcemap: true,
    },

    logLevel: 'info',
    clearScreen: false,
  }
})
