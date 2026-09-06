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
	import Search from '@lucide/svelte/icons/search';
	import PanelLeftClose from '@lucide/svelte/icons/panel-left-close';
	import PanelLeftOpen from '@lucide/svelte/icons/panel-left-open';
	import { Input } from '$lib/components/ui/input';
	import { search } from '$lib/store/search.svelte';
	import { toasts } from '$lib/store/toast.svelte';

	let { children } = $props();

	let collapsed = $state(false);

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
	<aside
		class={cn(
			'flex shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-200',
			collapsed ? 'w-16' : 'w-56'
		)}
	>
		<div class={cn('flex h-14 items-center gap-2 border-b', collapsed ? 'justify-center px-2' : 'px-4')}>
			<Logo />
			{#if !collapsed}
				<span class="text-lg font-bold">MYTRA</span>
			{/if}
		</div>
		<nav class="flex-1 space-y-1 p-2">
			{#each navItems as item (item.href)}
				<a
					href={item.href}
					title={collapsed ? item.label : undefined}
					class={cn(
						'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-sidebar-accent',
						collapsed && 'justify-center px-0',
						page.url.pathname === item.href && 'bg-sidebar-accent text-sidebar-accent-foreground'
					)}
				>
					<item.icon class="size-4 shrink-0" />
					{#if !collapsed}
						<span>{item.label}</span>
					{/if}
				</a>
			{/each}
		</nav>
	</aside>

	<div class="flex min-w-0 flex-1 flex-col">
		<header class="flex h-14 shrink-0 items-center justify-between gap-4 border-b bg-[#ffeccc] px-4 text-foreground">
			<div class="flex min-w-0 flex-1 items-center gap-2">
				<Button
					variant="ghost"
					size="icon"
					onclick={() => (collapsed = !collapsed)}
					aria-label={collapsed ? 'Развернуть меню' : 'Свернуть меню'}
				>
					{#if collapsed}
						<PanelLeftOpen class="size-4" />
					{:else}
						<PanelLeftClose class="size-4" />
					{/if}
				</Button>
				<div class="relative w-full max-w-xs">
					<Search class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
					<Input bind:value={search.value} placeholder="Поиск по адресу, № задания или л/с" class="bg-card pl-8 text-foreground" />
				</div>
			</div>
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

		<main class="min-h-0 flex-1 overflow-auto p-4">
			{@render children()}
		</main>
	</div>

	{#each toasts as t (t.id)}
		<div
			class="fixed bottom-4 right-4 z-50 max-w-sm rounded-md border bg-card px-4 py-2 text-sm shadow-lg"
		>
			{t.text}
		</div>
	{/each}
</div>
