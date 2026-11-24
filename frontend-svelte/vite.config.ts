import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) => filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// SPA (ssr=false в корневом +layout.ts) → статический build/index.html.
			// Нужен для Capacitor (нативный shell грузит статику) и раздачи статикой (Apache/nginx).
			adapter: adapter({ fallback: 'index.html' })
		})
	],
	server: {
		host: true,
		allowedHosts: true,
		port: 5174,
		proxy: {
			'/api': 'http://localhost:8000'
		}
	},
	preview: {
		host: true,
		allowedHosts: true,
		port: 5174
	}
});
