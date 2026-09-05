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
	import LayoutDashboard from '@lucide/svelte/icons/layout-dashboard';
	import FileText from '@lucide/svelte/icons/file-text';
	import ChartBar from '@lucide/svelte/icons/chart-bar';
	import CircleQuestionMark from '@lucide/svelte/icons/circle-question-mark';

	let { children } = $props();

	const user = $derived(auth.user);

	const navItems = $derived.by(() => [
		{ href: '/dashboard', label: 'Дашборд', icon: LayoutDashboard },
		{ href: '/main-afl', label: 'Реестры', icon: FileText },
		...(user?.role === 'администратор' ? [{ href: '/reports', label: 'Отчёты', icon: ChartBar }] : []),
		{ href: '/help', label: 'Помощь', icon: CircleQuestionMark }
	]);

	async function handleLogout() {
		await logout();
		await goto('/login');
	}
</script>

<div class="flex h-screen w-full overflow-hidden bg-background">
	<aside class="flex w-56 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
		<div class="flex h-14 items-center gap-2 border-b px-4">
			<Logo />
			<span class="text-lg font-bold">MYTRA</span>
		</div>
		<nav class="flex-1 space-y-1 p-2">
			{#each navItems as item (item.href)}
				<a
					href={item.href}
					class={cn(
						'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-sidebar-accent',
						page.url.pathname === item.href && 'bg-sidebar-accent text-sidebar-accent-foreground'
					)}
				>
					<item.icon class="size-4" />
					{item.label}
				</a>
			{/each}
		</nav>
	</aside>

	<div class="flex min-w-0 flex-1 flex-col">
		<header class="flex h-14 shrink-0 items-center justify-between border-b px-4">
			<div class="text-sm text-muted-foreground">Управление реестрами заданий</div>
			<div class="flex items-center gap-1.5">
				<Button variant="ghost" size="icon" onclick={toggleMode} aria-label="Переключить тему">
					<Sun class="size-4 dark:hidden" />
					<Moon class="hidden size-4 dark:block" />
				</Button>
				{#if user}
					<span class="hidden text-sm text-muted-foreground sm:inline">{user.full_name}</span>
					<Button variant="ghost" size="icon" onclick={handleLogout} aria-label="Выйти">
						<LogOut class="size-4" />
					</Button>
				{/if}
			</div>
		</header>

		<main class="min-h-0 flex-1 overflow-auto p-4">
			{@render children()}
		</main>
	</div>
</div>
