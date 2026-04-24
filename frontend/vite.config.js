import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Carregar variáveis de ambiente
  const env = loadEnv(mode, process.cwd(), '')

  // Build a dedupe map: resolve each @radix-ui/* to a single copy
  // Scans top-level node_modules first, falls back to any nested copy
  const radixDedupeAlias = {}
  const nmRoot = path.resolve(__dirname, './node_modules')

  const radixPkgs = [
    '@radix-ui/number',
    '@radix-ui/primitive',
    '@radix-ui/react-accordion',
    '@radix-ui/react-alert-dialog',
    '@radix-ui/react-arrow',
    '@radix-ui/react-aspect-ratio',
    '@radix-ui/react-avatar',
    '@radix-ui/react-checkbox',
    '@radix-ui/react-collapsible',
    '@radix-ui/react-collection',
    '@radix-ui/react-compose-refs',
    '@radix-ui/react-context',
    '@radix-ui/react-context-menu',
    '@radix-ui/react-dialog',
    '@radix-ui/react-direction',
    '@radix-ui/react-dismissable-layer',
    '@radix-ui/react-dropdown-menu',
    '@radix-ui/react-focus-guards',
    '@radix-ui/react-focus-scope',
    '@radix-ui/react-hover-card',
    '@radix-ui/react-id',
    '@radix-ui/react-label',
    '@radix-ui/react-menubar',
    '@radix-ui/react-navigation-menu',
    '@radix-ui/react-popover',
    '@radix-ui/react-popper',
    '@radix-ui/react-portal',
    '@radix-ui/react-presence',
    '@radix-ui/react-primitive',
    '@radix-ui/react-progress',
    '@radix-ui/react-radio-group',
    '@radix-ui/react-roving-focus',
    '@radix-ui/react-scroll-area',
    '@radix-ui/react-select',
    '@radix-ui/react-separator',
    '@radix-ui/react-slider',
    '@radix-ui/react-slot',
    '@radix-ui/react-switch',
    '@radix-ui/react-tabs',
    '@radix-ui/react-toast',
    '@radix-ui/react-toggle',
    '@radix-ui/react-toggle-group',
    '@radix-ui/react-tooltip',
    '@radix-ui/react-use-callback-ref',
    '@radix-ui/react-use-controllable-state',
    '@radix-ui/react-use-effect-event',
    '@radix-ui/react-use-escape-keydown',
    '@radix-ui/react-use-is-hydrated',
    '@radix-ui/react-use-layout-effect',
    '@radix-ui/react-use-previous',
    '@radix-ui/react-use-rect',
    '@radix-ui/react-use-size',
    '@radix-ui/react-visually-hidden',
    '@radix-ui/rect',
  ]

  for (const pkg of radixPkgs) {
    const topLevel = path.resolve(nmRoot, pkg)
    if (fs.existsSync(topLevel)) {
      radixDedupeAlias[pkg] = topLevel
    }
  }

  const radixAliasCount = Object.keys(radixDedupeAlias).length

  return {
    plugins: [react()],

    // Resolver alias @ para src/
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
        // Forçar todas as imports de Radix UI para uma única cópia.
        // Previne TDZ errors causados por nested node_modules com versões
        // diferentes (ex: react-slot 1.2.3 vs 1.2.4).
        ...radixDedupeAlias,
      },
      dedupe: [
        'react', 'react-dom', 'react-router-dom',
        ...Object.keys(radixDedupeAlias),
      ],
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
      sourcemap: mode !== 'production',
      chunkSizeWarningLimit: 1000,
    },

    // Definir variáveis de ambiente que começam com REACT_APP_
    // Usando import.meta.env para compatibilidade com Vite
    define: {
      // Manter compatibilidade com process.env (CRA legacy)
      ...Object.keys(env)
        .filter(key => key.startsWith('REACT_APP_'))
        .reduce((acc, key) => {
          // JSON.stringify é necessário porque define substitui literalmente
          acc[`process.env.${key}`] = JSON.stringify(env[key])
          return acc
        }, {}),
      // SEMPRE definir REACT_APP_BACKEND_URL com fallback robusto
      // Importante: Isto garante que mesmo que loadEnv falhe no Vercel, temos um valor válido
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
