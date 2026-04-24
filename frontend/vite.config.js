import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Carregar variáveis de ambiente
  const env = loadEnv(mode, process.cwd(), '')
  
  return {
    plugins: [react()],
    
    // Resolver alias @ para src/
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
      // Dedupe: força o Rollup a usar apenas uma cópia de cada pacote.
      // Isto previne TDZ errors causados por versões duplicadas do mesmo
      // pacote Radix em nested node_modules (ex: react-slot 1.2.3 vs 1.2.4).
      dedupe: [
        'react', 'react-dom', 'react-router-dom',
        '@radix-ui/react-slot',
        '@radix-ui/react-primitive',
        '@radix-ui/react-context',
        '@radix-ui/react-visually-hidden',
        '@radix-ui/react-compose-refs',
        '@radix-ui/react-use-callback-ref',
        '@radix-ui/react-use-controllable-state',
        '@radix-ui/react-use-escape-keydown',
        '@radix-ui/react-use-layout-effect',
        '@radix-ui/react-use-previous',
        '@radix-ui/react-use-size',
        '@radix-ui/react-popper',
        '@radix-ui/react-portal',
        '@radix-ui/react-presence',
        '@radix-ui/react-dismissable-layer',
        '@radix-ui/react-focus-scope',
        '@radix-ui/react-focus-guards',
        '@radix-ui/react-roving-focus',
        '@radix-ui/react-id',
        '@radix-ui/react-direction',
        '@radix-ui/react-collection',
        '@radix-ui/react-arrow',
        '@radix-ui/react-number',
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

