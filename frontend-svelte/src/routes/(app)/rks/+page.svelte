<script lang="ts">
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { toast } from '$lib/store/toast.svelte';
	import { uploadRks, type RksUploadResult } from '$lib/api/rks';

	let taskType = $state('');
	let file = $state<File | null>(null);
	let ulrFile = $state<File | null>(null);
	let uploading = $state(false);
	let result = $state<RksUploadResult | null>(null);

	function onFileChange(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		file = input.files?.[0] ?? null;
	}

	function onUlrFileChange(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		ulrFile = input.files?.[0] ?? null;
	}

	async function submit() {
		if (!file || !taskType) return;
		uploading = true;
		result = null;
		try {
			result = await uploadRks(file, ulrFile, taskType);
			toast(`Загружено: ${result.stats.tasks} заданий, ${result.stats.consumers} потребителей`);
			file = null;
			ulrFile = null;
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
				<CardTitle>Регистрация РКС</CardTitle>
				<CardDescription>
					Загрузка файла заданий РКС.xlsx (+ опционально РКС УЛР.xlsx для сопоставления дат). Тип поручения — из формы.
				</CardDescription>
			</CardHeader>
			<CardContent class="space-y-4">
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
					<label class="text-sm font-medium" for="rks-file">Файл РКС (.xlsx)</label>
					<Input id="rks-file" type="file" accept=".xlsx" disabled={uploading} onchange={onFileChange} />
				</div>

				<div class="space-y-1.5">
					<label class="text-sm font-medium" for="rks-ulr-file">Файл РКС УЛР (.xlsx, опционально)</label>
					<Input id="rks-ulr-file" type="file" accept=".xlsx" disabled={uploading} onchange={onUlrFileChange} />
				</div>

				<Button onclick={submit} disabled={uploading || !file || !taskType}>
					{uploading ? 'Загружаем…' : 'Загрузить'}
				</Button>
			</CardContent>
		</Card>

		{#if result}
			<Card>
				<CardHeader>
					<CardTitle>Результат</CardTitle>
					<CardDescription>
						Заданий: {result.stats.tasks}, потребителей: {result.stats.consumers}, точек: {result.stats.points}
					</CardDescription>
				</CardHeader>
				<CardContent>
					<ul class="space-y-1 text-sm">
						<li>Сопоставлено по коду: {result.stats.matched_code}</li>
						<li>Сопоставлено по адресу: {result.stats.matched_address}</li>
						<li>Не сопоставлено: {result.stats.unmatched}</li>
					</ul>
				</CardContent>
			</Card>
		{/if}
	</div>
</div>
