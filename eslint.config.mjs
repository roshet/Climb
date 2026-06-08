import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'dist-electron/**',
      'dist-installer/**',
      'node_modules/**',
      'sidecar/**', // Python backend — not linted here
      'test-electron.js', // ad-hoc manual probe
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // React renderer code runs in the browser.
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: { ...globals.browser },
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  {
    // Electron main/preload and build configs run in Node.
    files: ['electron/**/*.ts', '*.config.{ts,mts,js,mjs}'],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
)
