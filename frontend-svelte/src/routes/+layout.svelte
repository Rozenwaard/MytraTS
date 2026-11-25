<script lang="ts">
	import './layout.css';
	import { dev } from '$app/environment';
	import { onMount } from 'svelte';
	import { Capacitor } from '@capacitor/core';
	import favicon from '$lib/assets/favicon.svg';
	import { QueryClientProvider } from '@tanstack/svelte-query';
	import { ModeWatcher } from 'mode-watcher';
	import { queryClient } from '$lib/query';

	let { children } = $props();

	onMount(() => {
		// SW нужен только web-PWA. В Capacitor (нативный WebView) офлайн даёт
		// локальная статика + нативная офлайн-очередь. Дополнительно сносим любые
		// старые SW, оставшиеся от прошлых установок APK.
		if (Capacitor.isNativePlatform()) {
			if ('serviceWorker' in navigator) {
				navigator.serviceWorker
					.getRegistrations()
					.then((regs) => regs.forEach((r) => r.unregister()))
					.catch(() => {});
			}
			return;
		}
		if (!dev && 'serviceWorker' in navigator) {
			navigator.serviceWorker.register('/service-worker.js');
		}
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<ModeWatcher />
<QueryClientProvider client={queryClient}>
	{@render children()}
</QueryClientProvider>

