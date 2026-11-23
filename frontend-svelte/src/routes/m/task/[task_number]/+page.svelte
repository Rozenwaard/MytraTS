<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import { getToken, loadMobileAuth } from '$lib/mobile/auth.svelte';
	import { mobileApi, MobileApiError } from '$lib/mobile/client';
	import type { MobileDicts, MobileTask, SyncResponse } from '$lib/mobile/types';
	import Tile from '$lib/components/mobile/tile.svelte';
	import Panels from '$lib/components/mobile/panels.svelte';
	import { takePhoto, type TakenPhoto } from '$lib/mobile/photo';
	import { getPosition } from '$lib/mobile/geo';
	import { enqueueReport } from '$lib/mobile/queue';

	const taskNumber = $derived(page.params.task_number ?? '');

	let task = $state<MobileTask | null>(null);
	let dicts = $state<MobileDicts | null>(null);
	let alcor = $state(0);
	let screen = $state<'object' | 'point' | 'report'>('object');
	let panel = $state<string | null>(null);
	let error = $state('');
	let submitting = $state(false);
	let clientOpId = $state('');
	let photos = $state<TakenPhoto[]>([]);

	const report = $state<Record<string, any>>({
		object_detected: 'да', object_present: 'да', object_in_operation: 'да',
		object_purpose: 'Бытовое', is_connected: 'да', connected_to_mkd: 'нет',
		inspection_admitted: 'да', network_object_type: '', network_object_name: '',
		final_meter_status: '', meter_model: '', meter_type: '', meter_ownership: '',
		meter_installation_place: '', meter_inspection_results: '', last_verification_date: '',
		seals: '', seal_place: '', seal_type: '', seal_number: '', seal_installed: '',
		new_vpu_installed: 'нет', t1: '', t2: '', t3: '', violations: '', violation_type: '',
		has_current_transformer: '', has_voltage_transformer: '', additional_works: [] as string[],
		acts: '', result: '', contract: '', comment: '', done_day: '', co_executor: '',
		task_report: '', status: '', lat: null, lng: null, h3_res12: '', satellites: null, is_mock: 0
	});

	const workType = $derived(task?.work_type ?? '');
	const isRo = $derived(/проверк\s*ро/i.test(workType));
	const isNotify = $derived(/уведомл/i.test(workType));
	const baseNorm = $derived(task?.norm ?? 0);
	const extraNorm = $derived(
		(dicts?.additional_work ?? [])
			.filter((w) => report.additional_works.includes(w.code) && w.kind !== 'replacement')
			.reduce((s, w) => s + (w.norm ?? 0), 0)
	);
	const normTotal = $derived(baseNorm + extraNorm + alcor);

	onMount(async () => {
		if (!getToken()) {
			goto('/m/login');
			return;
		}
		loadMobileAuth();
		clientOpId = crypto.randomUUID();
		try {
			applySync(await mobileApi<SyncResponse>('/api/m/1/sync'));
		} catch {
			const cached = localStorage.getItem('rks.cache.sync');
			if (cached) applySync(JSON.parse(cached) as SyncResponse);
			else error = 'Ошибка загрузки задания';
		}
	});

	function applySync(data: SyncResponse) {
		dicts = data.dicts;
		alcor = data.alcor;
		task = data.tasks.find((t) => t.task_number === taskNumber) ?? null;
		if (!task) error = 'Задание не найдено';
	}

	function toggle(field: string) {
		report[field] = report[field] === 'да' ? 'нет' : 'да';
	}

	function addWork(code: string) {
		if (!report.additional_works.includes(code)) report.additional_works = [...report.additional_works, code];
	}
	function removeWork(code: string) {
		report.additional_works = report.additional_works.filter((c: string) => c !== code);
	}

	async function addPhoto() {
		try {
			const p = await takePhoto(clientOpId, taskNumber);
			if (p) photos = [...photos, p];
		} catch (err) {
			error = err instanceof Error ? err.message : 'Ошибка фото';
		}
	}

	function resolveResult(): string {
		if (report.inspection_admitted === 'нет') return 'недопуск';
		if (isNotify || isRo) return 'успешно';
		if (report.t1 || report.t2 || report.t3 || report.violations) return 'успешно';
		return 'не выполнено';
	}

	function resolveAct(): string {
		const r = resolveResult();
		if (r === 'недопуск') return 'недопуска';
		if (r === 'не выполнено') return '';
		if (isNotify) return '';
		if (isRo) return 'проверки РО';
		const aw = report.additional_works as string[];
		if (aw.includes('Допуск ПУ')) return 'допуска ПУ';
		if (aw.includes('Осмотр')) return 'осмотра';
		if (aw.includes('Инструментальная проверка')) return 'инструментальной проверки';
		return 'визуальной проверки';
	}

	function advanceObject() {
		if (report.inspection_admitted === 'нет' || isRo || isNotify) screen = 'report';
		else screen = 'point';
	}

	async function submit() {
		submitting = true;
		error = '';
		const result = resolveResult();
		const geo = await getPosition();
		const payload = {
			...report,
			...(geo ? { lat: geo.lat, lng: geo.lng, satellites: geo.satellites, is_mock: geo.is_mock } : {}),
			additional_works: JSON.stringify(report.additional_works),
			result,
			acts: resolveAct(),
			status: result === 'успешно' ? 'выполнено' : 'в работе',
			task_report: workType,
			done_day: new Date().toISOString().slice(0, 10),
			client_op_id: clientOpId,
			task_number: taskNumber
		};
		try {
			await mobileApi('/api/m/1/reports', { method: 'POST', body: JSON.stringify(payload) });
			await goto('/m/tasks');
		} catch (err) {
			if (err instanceof MobileApiError) {
				error = err.message;
				submitting = false;
			} else {
				// сетевая ошибка — сохраняем в офлайн-очередь
				await enqueueReport(payload);
				submitting = false;
				await goto('/m/tasks');
			}
		}
	}
</script>

{#if !task}
	<div class="p-4 text-sm text-muted-foreground">{error || 'Загрузка…'}</div>
{:else}
	{#if screen === 'object'}
		<div class="p-4">
			<div class="mb-3">
				<div class="text-sm font-semibold">{task.subscriber_name ?? '—'}</div>
				<div class="text-xs text-muted-foreground">{task.address ?? '—'}</div>
			</div>
			<div class="grid grid-cols-2 gap-2">
				<Tile label="Нет доступа" tone={report.inspection_admitted === 'нет' ? 'red' : 'neutral'} onclick={() => toggle('inspection_admitted')} />
				<Tile label={report.object_present === 'да' ? 'Наличие' : 'Отсутствует'} subtitle="Статус объекта" tone={report.object_present === 'да' ? 'green' : 'neutral'} onclick={() => toggle('object_present')} />
				<Tile label={report.object_in_operation === 'да' ? 'Эксплуатируется' : 'Не эксплуатируется'} subtitle="Статус использования" tone={report.object_in_operation === 'да' ? 'green' : 'neutral'} onclick={() => toggle('object_in_operation')} />
				<Tile label={report.object_purpose === 'Бытовое' ? 'Бытовое' : 'Небытовое'} subtitle="Назначение объекта" tone={report.object_purpose === 'Бытовое' ? 'green' : 'neutral'} onclick={() => (report.object_purpose = report.object_purpose === 'Бытовое' ? 'Небытовое' : 'Бытовое')} />
				<Tile label={report.is_connected === 'да' ? 'Подключен' : 'Не подключен'} subtitle="Статус подключения" tone={report.is_connected === 'да' ? 'green' : 'neutral'} onclick={() => toggle('is_connected')} />
				<Tile label={report.connected_to_mkd === 'да' ? 'Подключен к МКД' : 'Не подключен к МКД'} subtitle="Сети МКД" tone={report.connected_to_mkd === 'да' ? 'green' : 'neutral'} onclick={() => toggle('connected_to_mkd')} />
				<Tile label="Привязать к СО" subtitle={report.network_object_name || 'Тип + имя объекта'} tone="blue" onclick={() => (panel = 'network')} />
				<Tile label="Оформить отчёт" tone="blue" onclick={advanceObject} />
			</div>
		</div>
	{:else if screen === 'point'}
		<div class="p-4">
			<div class="mb-3 text-sm font-semibold">Точка учёта</div>
			<div class="grid grid-cols-2 gap-2">
				<Tile label="Статус учёта" subtitle={report.final_meter_status ? (report.final_meter_status === 'да' ? 'Учёт есть' : 'Нарушение') : 'Определить'} tone={report.final_meter_status ? 'green' : 'yellow'} onclick={() => (panel = 'status')} />
				<Tile label="Прибор учёта" subtitle={report.meter_model || 'Определить'} tone={report.meter_model ? 'green' : 'yellow'} onclick={() => (panel = 'meter')} />
				<Tile label="Место установки ПУ" subtitle={report.meter_installation_place || 'Определить'} tone={report.meter_installation_place ? 'green' : 'yellow'} onclick={() => (panel = 'place')} />
				<Tile label="Пломбы" subtitle={report.seal_number || 'Определить'} tone={report.seal_number ? 'green' : 'yellow'} onclick={() => (panel = 'seals')} />
				<Tile label="Соответствие ПУ и ТУ" subtitle={report.contract || 'Привязка к договору'} tone={report.contract ? 'green' : 'blue'} onclick={() => (panel = 'contract')} />
				<Tile label="Установлен новый ВПУ" tone={report.new_vpu_installed === 'да' ? 'green' : 'neutral'} onclick={() => toggle('new_vpu_installed')} />
				<Tile label="Показания" subtitle={[report.t1, report.t2, report.t3].filter(Boolean).join(' / ') || 'Определить'} tone={report.t1 || report.t2 || report.t3 ? 'green' : 'yellow'} onclick={() => (panel = 'readings')} />
				<Tile label="Завершить отчёт" tone="blue" onclick={() => (screen = 'report')} />
			</div>
		</div>
	{:else}
		<div class="p-4">
			<div class="mb-3 rounded-lg border p-3">
				<div class="text-xs text-muted-foreground">Задание · {workType || '—'}</div>
				<div class="text-sm font-semibold">Норматив: {normTotal} мин</div>
				<div class="text-xs text-muted-foreground">база {baseNorm} + доп {extraNorm} + Алькор {alcor}</div>
			</div>

			<div class="mb-3">
				<div class="mb-1 text-sm font-semibold">Доп. работы</div>
				{#each dicts?.additional_work ?? [] as w (w.code)}
					<label class="flex items-center gap-2 py-1 text-sm">
						<input type="checkbox" checked={report.additional_works.includes(w.code)} onchange={() => (report.additional_works.includes(w.code) ? removeWork(w.code) : addWork(w.code))} />
						<span>{w.title}</span>
						{#if w.norm}<span class="text-xs text-muted-foreground">+{w.norm}</span>{/if}
					</label>
				{/each}
			</div>

			<div class="mb-3 rounded-lg border p-3">
				<div class="text-sm font-semibold">Результат: {resolveResult()}</div>
				<div class="text-sm text-muted-foreground">Акт: {resolveAct() || '—'}</div>
			</div>

			<div class="mb-3">
				<div class="mb-1 flex items-center justify-between">
					<span class="text-sm font-semibold">Фото ({photos.length})</span>
					<button onclick={addPhoto} class="text-sm text-primary">+ Добавить</button>
				</div>
				{#if photos.length}
					<div class="grid grid-cols-3 gap-2">
						{#each photos as p (p.sha256)}
							<img src={p.url} alt="фото" class="h-20 w-full rounded-md object-cover" />
						{/each}
					</div>
				{:else}
					<p class="text-xs text-muted-foreground">Фото не добавлены</p>
				{/if}
			</div>

			<div class="mb-3">
				<label class="text-sm font-medium" for="comment">Комментарий</label>
				<textarea id="comment" bind:value={report.comment} class="mt-1 w-full rounded-md border p-2 text-sm"></textarea>
			</div>

			<button onclick={submit} disabled={submitting} class="w-full rounded-xl bg-green-600 py-3 text-sm font-semibold text-white disabled:opacity-50">
				{submitting ? 'Отправка…' : 'Утвердить отчёт'}
			</button>
			{#if error}<p class="mt-2 text-sm text-destructive">{error}</p>{/if}
		</div>
	{/if}
{/if}

<Panels {panel} {report} {dicts} {workType} onPhoto={addPhoto} onClose={() => (panel = null)} />
