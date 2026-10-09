<script lang="ts">
	import ArrowRight from '@lucide/svelte/icons/arrow-right';
	import Download from '@lucide/svelte/icons/download';
	import CalendarDays from '@lucide/svelte/icons/calendar-days';
	import type { Component, Snippet } from 'svelte';
	import { cn } from '$lib/utils.js';

	let {
		title,
		icon,
		iconClass = '',
		href = undefined,
		downloadHref = undefined,
		downloadLabel = 'Скачать',
		downloadIcon = Download,
		onMonth = undefined,
		monthLabel = 'Месяц',
		monthIcon = CalendarDays,
		preHref = undefined,
		preIcon = undefined,
		preLabel = 'Открыть',
		children
	}: {
		title: string;
		icon?: Component;
		iconClass?: string;
		href?: string;
		downloadHref?: string;
		downloadLabel?: string;
		downloadIcon?: Component;
		onMonth?: () => void;
		monthLabel?: string;
		monthIcon?: Component;
		preHref?: string;
		preIcon?: Component;
		preLabel?: string;
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
		{#if preHref && preIcon}
			{@const PreIcon = preIcon}
			<a
				href={preHref}
				class="flex shrink-0 items-center rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
				aria-label={preLabel}
			>
				<PreIcon class="size-4" />
			</a>
		{/if}
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
		{#if onMonth}
			{@const MonthIcon = monthIcon}
			<button
				type="button"
				onclick={onMonth}
				class="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
				aria-label={monthLabel}
			>
				<MonthIcon class="size-3.5" />
				<span>{monthLabel}</span>
			</button>
		{/if}
		{#if downloadHref}
			{@const DownloadIcon = downloadIcon}
			<a
				href={downloadHref}
				target="_blank"
				rel="noreferrer"
				class="flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
				aria-label={downloadLabel}
			>
				<DownloadIcon class="size-3.5" />
				<span>{downloadLabel}</span>
			</a>
		{/if}
	</div>

	<div class="min-h-0 flex-1 overflow-y-auto p-3">
		{@render children?.()}
	</div>
</div>
