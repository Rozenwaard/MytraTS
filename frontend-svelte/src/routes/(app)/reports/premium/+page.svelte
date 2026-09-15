<script lang="ts">
	import {
		fetchPremiumSummary,
		uploadTabel,
		aggregateNorms,
		premiumDownloadUrl,
		type PremiumSummary
	} from '$lib/api/premium';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { auth } from '$lib/store/auth.svelte';
	import { toast } from '$lib/store/toast.svelte';

	const MONTHS = [
		'январь', 'февраль', 'март', 'апрель', 'май', 'июнь',
		'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь'
	];

	const cardDefs = [
		{ key: 'engineers', label: 'Инженеры' },
		{ key: 'controllers', label: 'Контролёры' },
		{ key: 'drivers', label: 'Водители' }
	] as const;

	const isAdmin = $derived(auth.user?.role === 'администратор');

	let summary = $state<PremiumSummary | null>(null);
	let period = $state('');
	let loading = $state(true);
	let uploading = $state(false);
	let aggregating = $state(false);
	let fileInput = $state<HTMLInputElement | undefined>(undefined);
	let started = $state(false);

	function premiumPeriodLabel(p: string): string {
		if (!p) return p;
		const [year, month] = p.split(' ');
		const mi = Number(month) - 1;
		return mi >= 0 && mi < 12 ? `${MONTHS[mi]} ${year}` : p;
	}

	async function load(p: string) {
		loading = true;
		try {
			const data = await fetchPremiumSummary(p);
			summary = data;
			if (p === '') period = data.period ?? '';
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка загрузки премии');
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (isAdmin && !started) {
			started = true;
			load('');
		}
	});

	function openPicker() {
		if (fileInput) {
			fileInput.value = '';
			fileInput.click();
		}
	}

	function onFileChange(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (file) handleUpload(file);
	}

	async function handleUpload(file: File) {
		uploading = true;
		try {
			const res = await uploadTabel(file);
			toast(`Табель загружен: ${res.stored} строк`);
			await load('');
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка загрузки табеля');
		} finally {
			uploading = false;
		}
	}

	async function handleAggregate() {
		aggregating = true;
		try {
			const res = await aggregateNorms();
			toast(`Нормативы агрегированы: ${res.rows} строк`);
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка агрегации нормативов');
		} finally {
			aggregating = false;
		}
	}

	function handleDownload() {
		if (!period) {
			toast('Выберите период');
			return;
		}
		const a = document.createElement('a');
		a.href = premiumDownloadUrl(period);
		document.body.appendChild(a);
		a.click();
		a.remove();
	}
</script>

{#if auth.loading}
	<div class="p-6"><Skeleton class="h-6 w-40" /></div>
{:else if !isAdmin}
	<div class="p-6 text-sm text-muted-foreground">Нет доступа</div>
{:else}
	<div class="flex h-full flex-col gap-3 overflow-auto p-3">
		<div class="flex flex-wrap items-center gap-2">
			<Button size="sm" variant="outline" onclick={openPicker} disabled={uploading}>
				{uploading ? 'Загружаем…' : 'Добавить табель'}
			</Button>
			<input
				bind:this={fileInput}
				type="file"
				accept=".xlsx,.xls"
				class="hidden"
				onchange={onFileChange}
			/>

			<select
				value={period}
				disabled={loading}
				onchange={(e) => {
					const p = (e.currentTarget as HTMLSelectElement).value;
					period = p;
					load(p);
				}}
				class="h-8 rounded-md border border-input bg-background px-2 text-sm"
			>
				<option value="" disabled>Выберите период</option>
				{#each summary?.periods ?? [] as p (p)}
					<option value={p}>{premiumPeriodLabel(p)}</option>
				{/each}
			</select>

			<Button size="sm" onclick={handleAggregate} disabled={aggregating}>
				{aggregating ? 'Агрегируем…' : 'Отчёт по нормативам'}
			</Button>

			<Button size="sm" variant="outline" onclick={handleDownload} disabled={!period}>
				Скачать отчёт
			</Button>
		</div>

		{#if loading && !summary}
			<div class="flex flex-wrap gap-3">
				{#each cardDefs as c (c.key)}
					<div class="min-w-[170px] rounded-md border bg-card p-4">
						<Skeleton class="h-4 w-24" />
						<Skeleton class="mt-2 h-8 w-16" />
						<Skeleton class="mt-2 h-4 w-28" />
					</div>
				{/each}
			</div>
		{:else}
			<div class="flex flex-wrap gap-3">
				{#each cardDefs as c (c.key)}
					{@const card = summary?.cards[c.key] ?? { count: 0, man_days: 0 }}
					<div class="min-w-[170px] rounded-md border bg-card p-4">
						<div class="text-xs text-muted-foreground">{c.label}</div>
						<div class="mt-1 text-2xl font-semibold tabular-nums">{card.count.toLocaleString('ru-RU')}</div>
						<div class="mt-1 text-sm text-muted-foreground tabular-nums">
							человекодни: {card.man_days.toLocaleString('ru-RU')}
						</div>
					</div>
				{/each}
			</div>
		{/if}

		{#if (summary?.missing.length ?? 0) > 0}
			<div class="rounded-md border border-warning/30 bg-warning/10 p-4">
				<div class="text-sm font-medium">Отсутствуют в таблице работников следующие лица:</div>
				<ul class="mt-2 space-y-1 text-sm text-muted-foreground">
					{#each summary?.missing ?? [] as m (m.staff_id)}
						<li>
							{m.name || '—'}{m.position ? ` (${m.position})` : ''} — таб. № {m.staff_id}
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	</div>
{/if}
