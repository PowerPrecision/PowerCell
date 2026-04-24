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
      rollupOptions: {
        output: {
          manualChunks: {
            'vendor-react': ['react', 'react-dom', 'react-router-dom'],
            'vendor-charts': ['recharts'],
          },
          // NOTA: vendor-radix removido para evitar TDZ errors.
          // Separar apenas 5 pacotes Radix causava problemas de ordem de
          // inicialização com os outros 20+ pacotes Radix no chunk principal.
          // O Rollup agora decide a divisão automaticamente.
        },
      },
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
