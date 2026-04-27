import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { sentryVitePlugin } from '@sentry/vite-plugin'
import path from 'path'

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
    },

    // Tratar ficheiros .js como JSX (compatibilidade CRA)
    esbuild: {
      loader: 'jsx',
      include: /src\/.*\.jsx?$/,
      exclude: [],
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
      minify: false,
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
      // SEMPRE definir REACT_APP_BACKEND_URL com fallback robusto
      'process.env.REACT_APP_BACKEND_URL': JSON.stringify(
        env.REACT_APP_BACKEND_URL ||
        process.env.REACT_APP_BACKEND_URL ||
        'https://powercell.onrender.com'
      ),
    },

    // CSS configuration
    css: {
      devSourcemap: true,
    },

    logLevel: 'info',
    clearScreen: false,
  }
})
