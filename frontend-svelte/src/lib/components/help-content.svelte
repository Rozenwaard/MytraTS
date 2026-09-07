<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { fetchHelpPage, type HelpBlock, type HelpPageData } from '$lib/api/help';
	import { Skeleton } from '$lib/components/ui/skeleton';

	const NO_WRAP_COLS = ['Работа', 'Тип тарифа', 'Комментарий'];

	interface Section {
		id: string;
		title: string;
		menu?: string;
		blocks: HelpBlock[];
	}

	let { key }: { key: string } = $props();

	const query = createQuery<HelpPageData>(
		toStore(() => ({
			queryKey: ['help', key],
			queryFn: () => fetchHelpPage(key)
		}))
	);
	const result = fromStore(query);
	const page = $derived(result.current.data);
	const isPending = $derived(result.current.isPending);

	const content = $derived.by(() => {
		const blocks = page?.blocks ?? [];
		if (blocks.length === 0) return { title: null as string | null, sections: [] as Section[] };
		const title = blocks[0]?.type === 'p' ? (blocks[0].text ?? null) : null;
		const rest = title !== null ? blocks.slice(1) : blocks;
		const sections: Section[] = [];
		let cur: Section | null = null;
		for (const b of rest) {
			if (b.type === 'h') {
				cur = { id: `sec-${sections.length}`, title: b.text ?? '', menu: b.menu, blocks: [] };
				sections.push(cur);
			} else if (cur) {
				cur.blocks.push(b);
			} else {
				cur = { id: 'sec-0', title: '', blocks: [] };
				sections.push(cur);
				cur.blocks.push(b);
			}
		}
		return { title, sections };
	});
</script>

<div class="h-full overflow-auto p-4">
	{#if isPending}
		<div class="space-y-3">
			{#each Array(6) as _}
				<Skeleton class="h-4 w-full" />
			{/each}
		</div>
	{:else if page && page.blocks.length === 0}
		<p class="text-sm text-muted-foreground">Пока пусто</p>
	{:else}
		<div class="mb-4 flex items-center gap-3">
			<a
				href={`/api/help/${key}/download`}
				class="inline-flex h-8 items-center rounded-md border border-input bg-background px-2.5 text-sm font-medium transition-colors hover:bg-muted"
			>
				Скачать
			</a>
			{#if page?.updated_at}
				<span class="text-xs text-muted-foreground">Обновлено: {page.updated_at}</span>
			{/if}
		</div>

		<div class="mx-auto flex max-w-5xl items-start gap-8">
			<div class="min-w-0 flex-1">
				{#if content.title}
					<h1 class="mb-6 text-2xl font-bold">{content.title}</h1>
				{/if}
				{#each content.sections as s (s.id)}
					<section id={s.id} class="mb-14 scroll-mt-20">
						{#if s.title}
							<h2 class="mb-3 border-b pb-2 text-lg font-semibold">{s.title}</h2>
						{/if}
						{#each s.blocks as b, i (i)}
							{#if b.type === 'p'}
								<p class="mb-2 whitespace-pre-line text-sm leading-relaxed">{b.text}</p>
							{:else if b.type === 'table'}
								{@const rows = b.rows ?? []}
								{#if rows.length > 0}
									<div class="my-3 overflow-x-auto rounded-md border">
										<table class="w-full text-sm">
											<thead>
												<tr class="bg-muted">
													{#each rows[0] as h, hi (hi)}
														<th class="whitespace-nowrap border-b px-3 py-2 text-left font-medium">{h}</th>
													{/each}
												</tr>
											</thead>
											<tbody>
												{#each rows.slice(1) as row, ri (ri)}
													<tr class={ri % 2 ? 'bg-muted/40' : ''}>
														{#each row as c, ci (ci)}
															<td class={NO_WRAP_COLS.includes(rows[0][ci] ?? '') ? 'whitespace-nowrap border-b px-3 py-2 align-top' : 'whitespace-pre-line border-b px-3 py-2 align-top'}>{c}</td>
														{/each}
													</tr>
												{/each}
											</tbody>
										</table>
									</div>
								{/if}
							{/if}
						{/each}
					</section>
				{/each}
			</div>

			{#if content.sections.some((s) => s.title)}
				<nav class="sticky top-16 hidden w-60 shrink-0 lg:block">
					<div class="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
						Разделы
					</div>
					<ul class="space-y-0.5">
						{#each content.sections.filter((s) => s.title) as s (s.id)}
							<li>
								<a
									href={`#${s.id}`}
									class="block border-l-2 border-transparent py-1.5 pl-2 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary"
								>
									{s.menu ?? s.title}
								</a>
							</li>
						{/each}
					</ul>
				</nav>
			{/if}
		</div>
	{/if}
</div>
