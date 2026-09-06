<script lang="ts">
	import { cn } from '$lib/utils.js';

	let { className = '' }: { className?: string } = $props();
</script>

<div
	class={cn(
		'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-logo text-primary-foreground',
		className
	)}
>
	<span class="flex -translate-x-2 items-center">
		{#each [0, 1, 2] as _}
			<svg
				xmlns="http://www.w3.org/2000/svg"
				viewBox="0 0 24 24"
				fill="currentColor"
				class="h-6 w-6"
				style="transform: scale(0.6, 1.1); margin-right: -17px; display: inline-block;"
			>
				<path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
			</svg>
		{/each}
	</span>
</div>
