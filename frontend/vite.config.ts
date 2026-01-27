import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

// 检查证书文件是否存在（用于开发模式 HTTPS）
const keyPath = path.resolve(__dirname, '../key.pem')
const certPath = path.resolve(__dirname, '../cert.pem')
const hasHttpsCerts = fs.existsSync(keyPath) && fs.existsSync(certPath)

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  
  // 路径别名
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  
  // 开发服务器配置
  server: {
    host: true, // Listen on all addresses (0.0.0.0)
    port: 3000,
    // HTTPS 仅在证书存在时启用
    ...(hasHttpsCerts ? {
      https: {
        key: fs.readFileSync(keyPath),
        cert: fs.readFileSync(certPath),
      },
    } : {}),
    // 代理到 Flask 后端
    proxy: {
      '/api': {
        target: hasHttpsCerts ? 'https://localhost:5050' : 'http://localhost:5050',
        changeOrigin: true,
        secure: false, 
      },
      '/files': {
        target: hasHttpsCerts ? 'https://localhost:5050' : 'http://localhost:5050',
        changeOrigin: true,
        secure: false,
      },
    },
  },
  
  // 构建配置
  build: {
    outDir: 'dist',
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          // 3D 渲染库单独分包
          'three': ['three'],
          'gaussian-splats': ['@mkkellogg/gaussian-splats-3d'],
          // React 核心
          'react-vendor': ['react', 'react-dom'],
          // 状态管理 + i18n
          'utils': ['zustand', 'i18next', 'react-i18next'],
        },
      },
    },
  },
})

