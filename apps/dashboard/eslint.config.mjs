import { fileURLToPath } from 'node:url';
import { FlatCompat } from '@eslint/eslintrc';

const compat = new FlatCompat({
  baseDirectory: fileURLToPath(new URL('.', import.meta.url)),
});

const eslintConfig = [
  { ignores: ['.next/**', 'out/**', 'next-env.d.ts'] },
  ...compat.extends('next/core-web-vitals'),
  { files: ['**/*.{js,mjs,ts,tsx}'] },
];

export default eslintConfig;
