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
	let subdivision = $state('');
	let dueDate = $state('');
	let taskType = $state('');
	let file = $state<File | null>(null);
	let uploading = $state(false);
	let result = $state<UlrUploadResult | null>(null);

	const assignmentOptions = $derived(
		customer
			? (options?.assignment_types?.[customer] ?? []).filter(
					(a) => taskType !== 'Плановый' || a === 'КСП' || a === 'ИП'
				)
			: []
	);

	const subdivisionOptions = $derived(
		customer ? (options?.subdivisions?.[customer] ?? []) : []
	);

	const canSubmit = $derived(
		!!file && !!customer && !!visitReason && !!workType && !!dueDate && !!taskType && !!subdivision
	);

	$effect(() => {
		if (workType && !assignmentOptions.includes(workType)) {
			workType = '';
		}
		if (subdivision && !subdivisionOptions.includes(subdivision)) {
			subdivision = '';
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
				{ customer, visit_reason: visitReason, work_type_in_task: workType, subdivision, due_date: dueDate, task_type: taskType },
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
						<label class="text-sm font-medium" for="ulr-subdivision">Подразделение заказчика</label>
						<select
							id="ulr-subdivision"
							class="h-9 w-full rounded-md border border-input bg-background px-2 text-sm outline-none focus-visible:border-ring"
							bind:value={subdivision}
						>
							<option value="">—</option>
							{#each subdivisionOptions as s (s)}
								<option value={s}>{s}</option>
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

				<div class="grid grid-cols-2 gap-4">
					<div class="space-y-1.5">
						<span class="text-sm font-medium">Тип поручения</span>
						<div class="flex items-center gap-4 pt-1">
							<label class="flex items-center gap-1.5 text-sm">
								<input
									type="checkbox"
									class="size-4 cursor-pointer accent-primary"
									checked={taskType === 'Плановый'}
									onchange={() => (taskType = taskType === 'Плановый' ? '' : 'Плановый')}
								/>
								Плановый
							</label>
							<label class="flex items-center gap-1.5 text-sm">
								<input
									type="checkbox"
									class="size-4 cursor-pointer accent-primary"
									checked={taskType === 'Внеплановый'}
									onchange={() => (taskType = taskType === 'Внеплановый' ? '' : 'Внеплановый')}
								/>
								Внеплановый
							</label>
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
							{#each assignmentOptions as a (a)}
								<option value={a}>{a}</option>
							{/each}
						</select>
					</div>
				</div>

				<div class="space-y-1.5">
					<label class="text-sm font-medium" for="ulr-file">Файл реестра (.xlsx)</label>
					<Input id="ulr-file" type="file" accept=".xlsx" disabled={uploading} onchange={onFileChange} />
				</div>

				<Button onclick={submit} disabled={uploading || !canSubmit}>
					{uploading ? 'Загружаем…' : 'Загрузить реестр'}
				</Button>
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
