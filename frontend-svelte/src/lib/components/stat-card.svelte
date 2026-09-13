<script lang="ts">
	import ArrowRight from '@lucide/svelte/icons/arrow-right';
	import type { Component, Snippet } from 'svelte';
	import { cn } from '$lib/utils.js';

	let {
		title,
		icon,
		iconClass = '',
		href = undefined,
		children
	}: {
		title: string;
		icon?: Component;
		iconClass?: string;
		href?: string;
		children?: Snippet;
	} = $props();
</script>

<div class="flex h-[220px] flex-col rounded-xl border border-border bg-card shadow-xs">
	<div class="flex shrink-0 items-center gap-2.5 border-b px-4 py-3">
		{#if icon}
			{@const Icon = icon}
			<span
				class={cn(
					'flex size-9 shrink-0 items-center justify-center rounded-lg',
					iconClass || 'bg-muted text-muted-foreground'
				)}
			>
				<Icon class="size-5" />
			</span>
		{/if}
		<span class="min-w-0 flex-1 truncate text-sm font-medium">{title}</span>
		{#if href}
			<a
				href={href}
				class="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
				aria-label="Перейти"
			>
				<ArrowRight class="size-3.5" />
				<span>Перейти</span>
			</a>
		{/if}
	</div>

	<div class="min-h-0 flex-1 overflow-y-auto p-3">
		{@render children?.()}
	</div>
</div>
