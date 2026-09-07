<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { auth, logout } from '$lib/store/auth.svelte';
	import { toggleMode } from 'mode-watcher';
	import Logo from '$lib/components/logo.svelte';
	import { Button } from '$lib/components/ui/button';
	import { cn } from '$lib/utils.js';
	import Sun from '@lucide/svelte/icons/sun';
	import Moon from '@lucide/svelte/icons/moon';
	import LogOut from '@lucide/svelte/icons/log-out';
	import { toasts } from '$lib/store/toast.svelte';
	import { TOP_NAV, SUB_NAV, type NavItem, type SubTab } from '$lib/nav';

	let { children } = $props();

	const user = $derived(auth.user);

	const navItems = $derived.by(() =>
		TOP_NAV.filter((item) => {
			if (item.href === '/reports') return user?.role === 'администратор';
			if (item.href === '/upload') {
				return user?.role === 'администратор' || user?.role === 'специалист';
			}
			return true;
		})
	);

	const currentSection = $derived(
		Object.keys(SUB_NAV).find(
			(prefix) => page.url.pathname === prefix || page.url.pathname.startsWith(`${prefix}/`)
		)
	);

	const subTabs = $derived.by(() => {
		if (!currentSection) return [];
		const tabs = SUB_NAV[currentSection] ?? [];
		if (
			currentSection === '/main-afl' &&
			(user?.role === 'администратор' || user?.role === 'специалист')
		) {
			return tabs.filter((t) => t.href !== '/main-afl/list');
		}
		return tabs;
	});

	function isActive(item: NavItem): boolean {
		const path = page.url.pathname;
		return path === item.href || path.startsWith(`${item.href}/`);
	}

	function isTabActive(tab: SubTab): boolean {
		return page.url.pathname === tab.href;
	}

	async function handleLogout() {
		await logout();
		await goto('/login');
	}
</script>

<div class="flex h-screen flex-col overflow-hidden bg-background">
	<header
		class="flex h-14 shrink-0 items-center justify-between gap-4 border-b bg-sidebar px-4 text-sidebar-foreground"
	>
		<a href="/main-afl" class="flex items-center gap-2">
			<Logo />
			<span class="text-lg font-bold">MYTRA</span>
		</a>

		<nav class="flex items-center gap-4">
			{#each navItems as item (item.href)}
				<a
					href={item.href}
					class={cn(
						'inline-flex items-center rounded-md px-3 py-2 text-sm font-medium text-foreground transition-colors',
						isActive(item) ? 'bg-[#d2deda]' : 'bg-[#f4f7f6] hover:bg-[#d2deda]'
					)}
				>
					{item.label}
				</a>
			{/each}
		</nav>

		<div class="flex shrink-0 items-center gap-1.5">
			<Button variant="ghost" size="icon" onclick={toggleMode} aria-label="Переключить тему">
				<Sun class="size-4 dark:hidden" />
				<Moon class="hidden size-4 dark:block" />
			</Button>
			{#if user}
				<span class="hidden text-sm sm:inline">{user.full_name}</span>
				<Button variant="ghost" size="icon" onclick={handleLogout} aria-label="Выйти">
					<LogOut class="size-4" />
				</Button>
			{/if}
		</div>
	</header>

	{#if subTabs.length > 0}
		<nav class="flex shrink-0 items-center gap-1 border-b px-4">
			{#each subTabs as tab (tab.href)}
				<a
					href={tab.href}
					class={cn(
						'inline-flex items-center border-b-2 px-3 py-2 text-sm font-medium transition-colors',
						'-mb-px',
						isTabActive(tab)
							? 'border-primary text-primary'
							: 'border-transparent text-muted-foreground hover:text-foreground'
					)}
				>
					{tab.label}
				</a>
			{/each}
		</nav>
	{/if}

	<main class="min-h-0 flex-1">
		{@render children()}
	</main>

	{#each toasts as t (t.id)}
		<div
			class="fixed bottom-4 right-4 z-50 max-w-sm rounded-md border bg-card px-4 py-2 text-sm shadow-lg"
		>
			{t.text}
		</div>
	{/each}
</div>
