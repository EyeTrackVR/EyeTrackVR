import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
const path = require('path')

export default defineConfig({
  clearScreen: false,
  // Tauri expects a fixed port, fail if that port is not available
  // to make use of `TAURI_PLATFORM`, `TAURI_ARCH`, `TAURI_FAMILY`,
  // `TAURI_PLATFORM_VERSION`, `TAURI_PLATFORM_TYPE` and `TAURI_DEBUG`
  // env variables
  envPrefix: ['VITE_', 'TAURI_'],
  // also change alias in tsconfig.json compilerOptions > path
  resolve: {
    alias: {
      '@interfaces': path.resolve(__dirname, './src/interfaces'),
      '@components': path.resolve(__dirname, './src/components'),
      '@redux': path.resolve(__dirname, './src/redux'),
      '@pages': path.resolve(__dirname, './src/pages'),
      '@styles': path.resolve(__dirname, './src/styles'),
      '@config': path.resolve(__dirname, './src/config'),
      '@src': path.resolve(__dirname, './src'),
      '@assets': path.resolve(__dirname, './assets'),
      '@tauri': path.resolve(__dirname, './src-tauri'),
      '@hooks': path.resolve(__dirname, './src/utils/hooks'),
      '@static': path.resolve(__dirname, './src/static'),
      '@utils': path.resolve(__dirname, './src/utils'),
    },
  },
  server: {
    host: true,
    strictPort: true,
  },
  build: {
    // Tauri supports es2021
    target: ['es2021', 'chrome100', 'safari13'],
    // don't minify for debug builds
    minify: !process.env.TAURI_DEBUG ? 'esbuild' : false,
    // produce sourcemaps for debug builds
    sourcemap: !!process.env.TAURI_DEBUG,
  },
  plugins: [react()],
})
