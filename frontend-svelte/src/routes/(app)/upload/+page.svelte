<script lang="ts">
	import { onDestroy } from 'svelte';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Input } from '$lib/components/ui/input';
	import { queryClient } from '$lib/query';
	import { uploadXlsx, fetchUploadProgress, type UploadProgress } from '$lib/api/upload';

	let uploading = $state(false);
	let progress = $state<UploadProgress | null>(null);

	let pollTimer: ReturnType<typeof setInterval> | undefined;

	const isDone = $derived(progress?.status === 'complete' || progress?.status === 'error');

	function statusLabel(p: UploadProgress | null): string {
		switch (p?.status) {
			case 'starting':
				return 'Старт…';
			case 'loading':
				return 'Загрузка в БД…';
			case 'loaded':
				return `Готово: ${p.loaded ?? 0} строк`;
			case 'processing':
				return 'Обработка…';
			case 'merging':
				return 'Перенос в основную таблицу…';
			default:
				return '';
		}
	}

	function stopPolling() {
		if (pollTimer) {
			clearInterval(pollTimer);
			pollTimer = undefined;
		}
	}

	async function handleFile(file: File) {
		if (uploading) return;
		uploading = true;
		progress = { status: 'starting', progress: 0 };

		try {
			const { upload_id } = await uploadXlsx(file);
			pollTimer = setInterval(async () => {
				try {
					const p = await fetchUploadProgress(upload_id);
					progress = p;
					if (p.status === 'complete' || p.status === 'error') {
						stopPolling();
						uploading = false;
						if (p.status === 'complete') {
							queryClient.invalidateQueries({ queryKey: ['main-afl'] });
						}
					}
				} catch {
					stopPolling();
					uploading = false;
					progress = { status: 'error', progress: 0, message: 'Ошибка опроса прогресса' };
				}
			}, 500);
		} catch (e) {
			uploading = false;
			progress = {
				status: 'error',
				progress: 0,
				message: e instanceof Error ? e.message : 'Ошибка загрузки'
			};
		}
	}

	function onFileChange(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (file) handleFile(file);
	}

	onDestroy(stopPolling);
</script>

<div class="h-full overflow-auto p-4">
	<div class="mx-auto max-w-2xl">
		<Card>
			<CardHeader>
				<CardTitle>Загрузка</CardTitle>
				<CardDescription>Выгрузка «Отчёт по заданиям ФЛ» (.xlsx)</CardDescription>
			</CardHeader>
			<CardContent class="space-y-4">
				<p class="text-sm leading-relaxed text-muted-foreground">
					В «Отчете по заданиям ФЛ» выберите параметр отчета «Дата создания», далее выберите
					«Дату создания» (в календаре слева — начало периода, в календаре справа — окончание
					периода).<br /><br />
					!! Периоды разных отчётов могут накладываться друг на друга — это не приведёт к
					задвоению строк в таблице реестров !!<br /><br />
					Сформируйте отчёт, скачайте и сохраните файл на свой компьютер.
				</p>

				<Input type="file" accept=".xlsx" disabled={uploading} onchange={onFileChange} />

				{#if progress && !isDone}
					<div class="space-y-1.5">
						<span class="text-xs text-muted-foreground">{statusLabel(progress)}</span>
						<div class="h-2 w-full overflow-hidden rounded-full bg-muted">
							<div class="h-full bg-primary transition-all" style={`width: ${progress.progress}%`}></div>
						</div>
					</div>
				{/if}

				{#if progress?.status === 'complete'}
					<div class="rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-primary">
						{progress.message}
					</div>
				{/if}

				{#if progress?.status === 'error'}
					<div class="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
						{progress.message || 'Ошибка загрузки'}
					</div>
				{/if}
			</CardContent>
		</Card>
	</div>
</div>
