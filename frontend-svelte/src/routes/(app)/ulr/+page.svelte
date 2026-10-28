<script lang="ts">
	import { onMount } from 'svelte';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { toast } from '$lib/store/toast.svelte';
	import {
		fetchUlrOptions,
		uploadUlr,
		type UlrOptions,
		type UlrUploadResult
	} from '$lib/api/ulr';

	let options = $state<UlrOptions | null>(null);
	let customer = $state('');
	let visitReason = $state('');
	let workType = $state('');
	let grid = $state('');
	let dueDate = $state('');
	let file = $state<File | null>(null);
	let uploading = $state(false);
	let result = $state<UlrUploadResult | null>(null);

	const workTypeOptions = $derived(
		options ? options.work_types.filter((w) => !customer || !w.customer || w.customer === customer) : []
	);

	const canSubmit = $derived(
		!!file && !!customer && !!visitReason && !!workType && !!dueDate && (customer !== 'РЛЭ' || !!grid)
	);

	$effect(() => {
		if (workType && !workTypeOptions.some((w) => w.short === workType)) {
			workType = '';
		}
	});

	onMount(async () => {
		try {
			options = await fetchUlrOptions();
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка загрузки справочников');
		}
	});

	function onFileChange(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		file = input.files?.[0] ?? null;
	}

	function downloadFeedback(res: UlrUploadResult) {
		if (!res.feedback_file_base64 || !res.feedback_filename) return;
		const bin = atob(res.feedback_file_base64);
		const bytes = new Uint8Array(bin.length);
		for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
		const blob = new Blob([bytes], {
			type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
		});
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = res.feedback_filename;
		document.body.appendChild(a);
		a.click();
		a.remove();
		URL.revokeObjectURL(url);
	}

	async function submit() {
		if (!canSubmit || !file) return;
		uploading = true;
		result = null;
		try {
			result = await uploadUlr(
				{ customer, visit_reason: visitReason, work_type_in_task: workType, grid, due_date: dueDate },
				file
			);
			toast(`Загружено: ${result.inserted} строк, неидентифицировано: ${result.feedback.length}`);
			downloadFeedback(result);
			customer = '';
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка загрузки');
		} finally {
			uploading = false;
		}
	}
</script>

<div class="h-full overflow-auto p-4">
	<div class="mx-auto max-w-2xl space-y-4">
		<Card>
			<CardHeader>
				<CardDescription>
					Форма реестра — 3 колонки: № Энергообъекта (договора), № ТУ (при наличии), № ПУ (при наличии).
				</CardDescription>
			</CardHeader>
			<CardContent class="space-y-4">
				<div class="grid grid-cols-2 gap-4">
					<div class="space-y-1.5">
						<span class="text-sm font-medium">Заказчик</span>
						<div class="flex items-center gap-4 pt-1">
							{#each options?.customers ?? [] as c (c)}
								<label class="flex items-center gap-1.5 text-sm">
									<input
										type="checkbox"
										class="size-4 cursor-pointer accent-primary"
										checked={customer === c}
										onchange={() => (customer = customer === c ? '' : c)}
									/>
									{c}
								</label>
							{/each}
						</div>
					</div>
					<div class="space-y-1.5">
						<label class="text-sm font-medium" for="ulr-grid">Сети (филиал) *</label>
						<select
							id="ulr-grid"
							class="h-9 w-full rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring"
							bind:value={grid}
						>
							<option value="">—</option>
							{#each options?.grids ?? [] as g (g)}
								<option value={g}>{g}</option>
							{/each}
						</select>
					</div>
				</div>

				<div class="grid grid-cols-2 gap-4">
					<div class="space-y-1.5">
						<label class="text-sm font-medium" for="ulr-reason">Основание</label>
						<Input id="ulr-reason" bind:value={visitReason} placeholder="Исходящий номер письма" />
					</div>
					<div class="space-y-1.5">
						<label class="text-sm font-medium" for="ulr-due">Плановая дата выполнения</label>
						<Input id="ulr-due" type="date" bind:value={dueDate} />
					</div>
				</div>

				<div class="space-y-1.5">
					<label class="text-sm font-medium" for="ulr-work">Поручение</label>
					<select
						id="ulr-work"
						class="h-9 w-full rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring"
						bind:value={workType}
					>
						<option value="">—</option>
						{#each workTypeOptions as w (w.short)}
							<option value={w.short}>{w.short}</option>
						{/each}
					</select>
				</div>

				<div class="space-y-1.5">
					<label class="text-sm font-medium" for="ulr-file">Файл реестра (.xlsx)</label>
					<Input id="ulr-file" type="file" accept=".xlsx" disabled={uploading} onchange={onFileChange} />
				</div>

				<Button onclick={submit} disabled={uploading || !canSubmit}>
					{uploading ? 'Загружаем…' : 'Загрузить реестр'}
				</Button>

				<p class="text-xs text-muted-foreground">
					«Сети (филиал)» обязателен только для заказчика РЛЭ.
				</p>
			</CardContent>
		</Card>

		{#if result}
			<Card>
				<CardHeader>
					<CardTitle>Результат</CardTitle>
					<CardDescription>
						В main_afl добавлено строк: {result.inserted} из {result.total}
					</CardDescription>
				</CardHeader>
				<CardContent>
					{#if result.feedback.length === 0}
						<p class="text-sm text-muted-foreground">Все строки идентифицированы.</p>
					{:else}
						<p class="mb-2 text-sm font-medium">
							Неидентифицированные строки — в скачанном файле {result.feedback_filename ?? 'фидбек.xlsx'}.
						</p>
						<ul class="space-y-1 text-sm">
							{#each result.feedback as fb (fb.row)}
								<li class="rounded-md border px-3 py-2">
									<span class="font-semibold">Строка {fb.row}</span> — {fb.reason}
									<span class="text-muted-foreground">
										(объект: {fb.object_code ?? '—'}, ПУ: {fb.meter_serial_number ?? '—'}, ТУ: {fb.tu_number ?? '—'})
									</span>
								</li>
							{/each}
						</ul>
					{/if}
				</CardContent>
			</Card>
		{/if}
	</div>
</div>
