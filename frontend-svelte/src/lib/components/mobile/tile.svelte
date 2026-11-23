<script lang="ts">
	import { cn } from '$lib/utils';

	let {
		label,
		subtitle = '',
		tone = 'blue',
		onclick = () => {}
	}: {
		label: string;
		subtitle?: string;
		tone?: 'green' | 'yellow' | 'blue' | 'red' | 'neutral';
		onclick?: () => void;
	} = $props();
</script>

<button
	{onclick}
	class={cn(
		'flex min-h-[4.25rem] w-full flex-col items-start justify-center rounded-xl border px-3 py-2 text-left transition-colors',
		tone === 'green' && 'border-green-600 bg-green-100 text-green-950',
		tone === 'yellow' && 'border-amber-500 bg-amber-100 text-amber-950',
		tone === 'blue' && 'border-blue-600 bg-blue-100 text-blue-950',
		tone === 'red' && 'border-red-600 bg-red-100 text-red-950',
		tone === 'neutral' && 'border-slate-300 bg-slate-100 text-slate-700'
	)}
>
	<span class="text-sm font-semibold leading-tight">{label}</span>
	{#if subtitle}
		<span class="mt-0.5 text-xs opacity-80">{subtitle}</span>
	{/if}
</button>
