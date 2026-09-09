import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-node';
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

			// Прод-сборка — Node-сервер (adapter-node): bun run build → build/index.js.
			// adapter-auto не использован: на голом Debian/Ubuntu он не определяет среду
			// (ищет Vercel/Netlify/Cloudflare) и пишет результат в .svelte-kit/output вместо build/.
			adapter: adapter()
		})
	],
	server: {
		port: 5174,
		proxy: {
			'/api': 'http://localhost:8000'
		}
	}
});
