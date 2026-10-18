import eslint from '@eslint/js';
import tseslint from 'typescript-eslint';
import vue from 'eslint-plugin-vue';

export default [
  { ignores: ['dist/**', 'node_modules/**', 'playwright-report/**', 'test-results/**'] },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['src/**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    files: ['src/**/*.{ts,vue}', 'e2e/**/*.ts', '*.config.ts'],
    languageOptions: {
      globals: {
        AbortController: 'readonly', Blob: 'readonly', EventSource: 'readonly', FormData: 'readonly',
        Event: 'readonly', HTMLFormElement: 'readonly', HTMLElement: 'readonly', KeyboardEvent: 'readonly',
        MessageEvent: 'readonly', URL: 'readonly', URLSearchParams: 'readonly', sessionStorage: 'readonly',
        console: 'readonly', crypto: 'readonly', document: 'readonly', fetch: 'readonly', window: 'readonly',
        setTimeout: 'readonly', clearTimeout: 'readonly', setInterval: 'readonly', clearInterval: 'readonly',
      },
    },
    rules: {
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
    },
  },
  {
    files: ['e2e/**/*.mjs'],
    languageOptions: {
      globals: {
        URL: 'readonly', console: 'readonly', document: 'readonly', fetch: 'readonly', process: 'readonly',
      },
    },
  },
  {
    files: ['vite.config.ts'],
    languageOptions: { globals: { process: 'readonly' } },
  },
];
