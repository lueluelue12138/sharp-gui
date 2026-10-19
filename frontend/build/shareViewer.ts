import path from 'node:path';
import fs from 'node:fs';
import { build } from 'vite';
import type { Plugin } from 'vite';

/** Keep offline exports available in installations without node_modules. */
export function shareViewerBuild(root: string): Plugin {
  return {
    name: 'sharp-share-viewer',
    apply: 'build',
    async closeBundle() {
      await build({
        configFile: false,
        root,
        publicDir: false,
        define: { 'process.env.NODE_ENV': JSON.stringify('production') },
        resolve: { alias: { '@': path.join(root, 'src') } },
        esbuild: { legalComments: 'inline', jsx: 'automatic' },
        build: {
          outDir: 'dist/share',
          emptyOutDir: true,
          sourcemap: false,
          lib: {
            entry: path.join(root, 'src/share/main.tsx'),
            name: 'SharpShareViewer',
            formats: ['iife'],
            fileName: () => 'share-viewer.js',
            cssFileName: 'share-viewer',
          },
          rollupOptions: { output: { inlineDynamicImports: true } },
        },
      });
      const notices = ['three', '@sparkjsdev/spark', 'react', 'react-dom', 'scheduler'].map((name) => {
        const folder = path.join(root, 'node_modules', name);
        const license = ['LICENSE', 'LICENSE.txt', 'LICENSE.md'].find((file) => fs.existsSync(path.join(folder, file)));
        if (!license) throw new Error(`Missing standalone viewer license: ${name}`);
        const info = JSON.parse(fs.readFileSync(path.join(folder, 'package.json'), 'utf8'));
        return `${name} ${info.version}\n${fs.readFileSync(path.join(folder, license), 'utf8')}`;
      }).join('\n\n');
      fs.writeFileSync(path.join(root, 'dist/share/LICENSES.txt'), notices, 'utf8');
    },
  };
}
