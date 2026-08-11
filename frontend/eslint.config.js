import js from '@eslint/js'
import globals from 'globals'
import reactPlugin from 'eslint-plugin-react'
import reactHooksPlugin from 'eslint-plugin-react-hooks'
import jsxPlugin from 'eslint-plugin-jsx-a11y'
import importPlugin from 'eslint-plugin-import'

// ─── DARK-MODE SAFE COLORS (Fase 6 audit) ───────────────────────────────────
// Raw Tailwind palette utilities (e.g. `bg-gray-200`, `text-blue-600`) hardcode
// a fixed lightness and break Dark Mode, since they don't respond to the
// `.dark` class the way Shadcn semantic tokens do (`bg-primary`,
// `text-muted-foreground`, `bg-destructive`, `bg-secondary`, `bg-accent`, ...).
// This block forbids raw palette utilities in `className`/`class` JSX attributes
// and in `cn()`/`clsx()`/`classnames()`/`cva()` calls, so new code is forced to
// use semantic Shadcn tokens instead. Existing offenders in legacy files are
// intentionally left as warnings — see AGENTS.md Fase 6 notes.
const TAILWIND_COLOR_FAMILIES = [
  'slate', 'gray', 'zinc', 'neutral', 'stone',
  'red', 'orange', 'amber', 'yellow', 'lime', 'green', 'emerald', 'teal',
  'cyan', 'sky', 'blue', 'indigo', 'violet', 'purple', 'fuchsia', 'pink', 'rose',
].join('|')
const TAILWIND_COLOR_UTILITIES = [
  'bg', 'text', 'border', 'ring', 'ring-offset', 'divide', 'from', 'via', 'to',
  'fill', 'stroke', 'outline', 'decoration', 'shadow', 'accent', 'caret', 'placeholder',
].join('|')
// Matches e.g. `bg-gray-200`, `hover:text-blue-600`, `dark:bg-red-500/50` (word-boundary safe).
const RAW_TAILWIND_COLOR_PATTERN = `\\b(${TAILWIND_COLOR_UTILITIES})-(${TAILWIND_COLOR_FAMILIES})-(50|100|200|300|400|500|600|700|800|900|950)\\b`
const RAW_COLOR_MESSAGE =
  'Não uses cores Tailwind cruas (quebram o Dark Mode). Usa os tokens semânticos do Shadcn: ' +
  'bg-primary, bg-secondary, bg-accent, bg-muted, bg-destructive, text-foreground, ' +
  'text-muted-foreground, border-border, etc.'
const NO_RAW_TAILWIND_COLOR_SELECTORS = [
  // className="bg-gray-200" / className={"..."}
  `JSXAttribute[name.name=/^(className|class)$/] Literal[value=/${RAW_TAILWIND_COLOR_PATTERN}/]`,
  // className={`bg-gray-200 ${x}`}
  `JSXAttribute[name.name=/^(className|class)$/] TemplateElement[value.raw=/${RAW_TAILWIND_COLOR_PATTERN}/]`,
  // cn("bg-gray-200", ...) / clsx(...) / classnames(...) / cva(...)
  `CallExpression[callee.name=/^(cn|clsx|classnames|cva|twMerge)$/] Literal[value=/${RAW_TAILWIND_COLOR_PATTERN}/]`,
  `CallExpression[callee.name=/^(cn|clsx|classnames|cva|twMerge)$/] TemplateElement[value.raw=/${RAW_TAILWIND_COLOR_PATTERN}/]`,
].map((selector) => ({ selector, message: RAW_COLOR_MESSAGE }))

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

      // ─── DARK-MODE SAFE COLORS (Fase 6) ─────────────────────────
      // Warn-only safety net: prevents *new* raw Tailwind color debt
      // without requiring an immediate fix of the (many) legacy offenders.
      'no-restricted-syntax': ['warn', ...NO_RAW_TAILWIND_COLOR_SELECTORS],
    },
  },
]
