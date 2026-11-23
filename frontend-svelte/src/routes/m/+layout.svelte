<script lang="ts">
	import { goto } from '$app/navigation';
	import { browser } from '$app/environment';
	import { page } from '$app/state';
	import { clearMobileAuth, loadMobileAuth, mobileAuth } from '$lib/mobile/auth.svelte';

	let { children } = $props();
	const isLogin = $derived(page.url.pathname === '/m/login');

	$effect(() => {
		if (!browser) return;
		loadMobileAuth();
		if (!mobileAuth.token && !isLogin) goto('/m/login');
		else if (mobileAuth.token && isLogin) goto('/m/tasks');
	});

	function logout() {
		clearMobileAuth();
		goto('/m/login');
	}
</script>

<div class="flex min-h-screen justify-center bg-muted/40">
	<div class="relative w-full max-w-md bg-background shadow-sm">
		{#if mobileAuth.token && !isLogin}
			<header class="flex items-center justify-between border-b px-4 py-3">
				<span class="text-sm font-semibold">РКС · {mobileAuth.fullName ?? 'мобильный'}</span>
				<button onclick={logout} class="text-sm text-muted-foreground hover:text-foreground">Выйти</button>
			</header>
		{/if}
		{@render children()}
	</div>
</div>
