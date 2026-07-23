import js from '@eslint/js'
import globals from 'globals'
import reactPlugin from 'eslint-plugin-react'
import reactHooksPlugin from 'eslint-plugin-react-hooks'
import jsxPlugin from 'eslint-plugin-jsx-a11y'
import importPlugin from 'eslint-plugin-import'

export default [
  // Ignore patterns
  {
    ignores: [
      'node_modules/**',
      'dist/**',
      'build/**',
      '*.config.js',
      '*.config.mjs',
      'coverage/**',
      'public/**',
      'craco.config.js',
      // Tooling / Playwright (CommonJS plugins + Playwright fixtures named `use`)
      'plugins/**',
      'e2e/**',
      'e2e-report/**',
      'playwright-report/**',
      'test-results/**',
    ],
  },

  // Base JS rules
  js.configs.recommended,

  // Unit tests (Vitest/Jest-style globals: describe/it/expect)
  {
    files: ['**/*.{test,spec}.{js,jsx}'],
    languageOptions: {
      globals: {
        ...globals.jest,
      },
    },
  },

  // React + JSX rules
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.es2020,
        // Vite define process.env em build time via vite.config.js → define
        process: 'readonly',
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      'react': reactPlugin,
      'react-hooks': reactHooksPlugin,
      'jsx-a11y': jsxPlugin,
      'import': importPlugin,
    },
    settings: {
      'react': { version: 'detect' },
      'import/resolver': {
        node: { extensions: ['.js', '.jsx'] },
      },
      'import/parsers': {
        '@typescript-eslint/parser': ['.ts', '.tsx'],
      },
    },
    rules: {
      // ─── REACT ─────────────────────────────────────────────────
      'react/react-in-jsx-scope': 'off', // React 19+ não precisa
      'react/prop-types': 'off', // TypeScript/zod handles this
      'react/display-name': 'warn',
      // CRITICAL: sem esta regra, no-unused-vars não sabe que um componente
      // usado apenas em JSX (ex: `<Foo />`) está "usado" — dá falsos positivos
      // que, se "corrigidos", apagam componentes que estão realmente em uso.
      'react/jsx-uses-vars': 'error',
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',

      // ─── IMPORT / CIRCULAR DEPENDENCY PREVENTION ────────────────
      // CRITICAL: Bloqueia circular imports que causam TDZ errors
      'import/no-cycle': ['error', {
        maxDepth: 10,           // Profundidade máxima para detectar ciclos
        ignoreExternal: true,   // Ignora ciclos em node_modules (ex: Radix UI)
        allowUnsafeDynamicCyclicDependency: false,
      }],
      // Prevenir imports duplicados (limpeza de código)
      'import/no-duplicates': 'error',
      // Alertar sobre exports default inconsistentes
      'import/default': 'error',
      // Prevenir imports de ficheiros que não exportam nada
      'import/no-self-import': 'error',
      // Prevenir re-export de um ficheiro de si próprio
      'import/export': 'error',

      // ─── JSX-A11Y ──────────────────────────────────────────────
      'jsx-a11y/alt-text': 'warn',
      'jsx-a11y/anchor-is-valid': 'warn',
      'jsx-a11y/click-events-have-key-events': 'warn',
      'jsx-a11y/no-static-element-interactions': 'warn',

      // ─── GENERAL ───────────────────────────────────────────────
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
      'no-debugger': 'error',
    },
  },
]
