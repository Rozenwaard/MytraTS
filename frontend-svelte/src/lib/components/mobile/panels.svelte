<script lang="ts">
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import type { MobileDicts } from '$lib/mobile/types';

	let {
		panel,
		report,
		dicts,
		workType = '',
		onClose = () => {}
	}: {
		panel: string | null;
		report: Record<string, any>;
		dicts: MobileDicts | null;
		workType?: string;
		onClose?: () => void;
	} = $props();

	function addWork(code: string) {
		if (!report.additional_works.includes(code)) {
			report.additional_works = [...report.additional_works, code];
		}
	}
	function removeWork(code: string) {
		report.additional_works = report.additional_works.filter((c: string) => c !== code);
	}
	function toggleWork(code: string) {
		if (report.additional_works.includes(code)) removeWork(code);
		else addWork(code);
	}

	function close() {
		if (panel === 'network' && report.network_object_type && report.network_object_name) addWork('Привязка');
		if (panel === 'contract' && report.contract) addWork('Идентификация');
		if (panel === 'seals' && report.seal_installed === 'да') {
			const skip = /инструмент/i.test(workType) || /допуск пu/i.test(workType);
			if (!skip) addWork('Опломбировка');
		}
		onClose();
	}
</script>

{#if panel}
	<div class="fixed inset-0 z-50 flex items-end justify-center bg-black/40" onclick={close}>
		<div class="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-background p-4" onclick={(e) => e.stopPropagation()}>
			{#if panel === 'network'}
				<h2 class="mb-2 text-sm font-semibold">Привязать к СО</h2>
				<div class="space-y-2">
					<label class="text-xs font-medium">Тип объекта (КЛ/ВЛ)</label>
					<select bind:value={report.network_object_type} class="w-full rounded-md border p-2 text-sm">
						<option value="">—</option>
						<option value="КЛ">КЛ</option>
						<option value="ВЛ">ВЛ</option>
					</select>
					<label class="text-xs font-medium">Название объекта</label>
					<Input bind:value={report.network_object_name} placeholder="ВЛ-0,4кВ ф.3" />
				</div>
			{:else if panel === 'meter'}
				<h2 class="mb-2 text-sm font-semibold">Прибор учёта</h2>
				<div class="space-y-2">
					<label class="text-xs font-medium">Модель</label>
					<Input bind:value={report.meter_model} />
					<label class="text-xs font-medium">Тип</label>
					<Input bind:value={report.meter_type} />
					<label class="text-xs font-medium">Балансовая принадлежность</label>
					<Input bind:value={report.meter_ownership} />
					<label class="text-xs font-medium">Дата поверки</label>
					<Input bind:value={report.last_verification_date} placeholder="ДД.ММ.ГГГГ" />
					<label class="text-xs font-medium">Параметры совпадают</label>
					<select bind:value={report.meter_inspection_results} class="w-full rounded-md border p-2 text-sm">
						<option value="">—</option>
						<option value="да">Да</option>
						<option value="нет">Нет</option>
					</select>
					<label class="flex items-center gap-2 text-sm">
						<input type="checkbox" checked={report.additional_works.includes('Допуск ПУ')} onchange={() => toggleWork('Допуск ПУ')} />
						Допуск нового ПУ
					</label>
				</div>
			{:else if panel === 'seals'}
				<h2 class="mb-2 text-sm font-semibold">Пломбы</h2>
				<div class="space-y-2">
					<label class="text-xs font-medium">Место пломбы</label>
					<Input bind:value={report.seal_place} />
					<label class="text-xs font-medium">Тип пломбы</label>
					<Input bind:value={report.seal_type} />
					<label class="text-xs font-medium">Номер пломбы</label>
					<Input bind:value={report.seal_number} />
					<label class="flex items-center gap-2 text-sm">
						<input type="checkbox" checked={report.seal_installed === 'да'} onchange={() => (report.seal_installed = report.seal_installed === 'да' ? '' : 'да')} />
						Пломба установлена при проверке
					</label>
				</div>
			{:else if panel === 'contract'}
				<h2 class="mb-2 text-sm font-semibold">Соответствие ПУ и ТУ</h2>
				<div class="space-y-2">
					<label class="text-xs font-medium">Номер договора (лицевой счёт)</label>
					<Input bind:value={report.contract} />
				</div>
			{:else if panel === 'place'}
				<h2 class="mb-2 text-sm font-semibold">Место установки ПУ</h2>
				<Input bind:value={report.meter_installation_place} />
			{:else if panel === 'readings'}
				<h2 class="mb-2 text-sm font-semibold">Показания</h2>
				<div class="grid grid-cols-3 gap-2">
					<div><label class="text-xs">T1</label><Input bind:value={report.t1} /></div>
					<div><label class="text-xs">T2</label><Input bind:value={report.t2} /></div>
					<div><label class="text-xs">T3</label><Input bind:value={report.t3} /></div>
				</div>
			{:else if panel === 'status'}
				<h2 class="mb-2 text-sm font-semibold">Статус учёта</h2>
				<div class="mb-2 flex gap-2">
					<Button variant={report.final_meter_status === 'да' ? 'default' : 'outline'} onclick={() => (report.final_meter_status = 'да')}>Да</Button>
					<Button variant={report.final_meter_status === 'нет' ? 'default' : 'outline'} onclick={() => (report.final_meter_status = 'нет')}>Нет</Button>
				</div>
				{#if report.final_meter_status === 'нет'}
					<label class="text-xs font-medium">Группа нарушения</label>
					<select bind:value={report.violation_type} class="w-full rounded-md border p-2 text-sm">
						<option value="">—</option>
						{#each dicts?.violation_group ?? [] as g (g.code)}
							<option value={g.code}>{g.title}</option>
						{/each}
					</select>
					<label class="mt-2 text-xs font-medium">Нарушение (описание)</label>
					<Input bind:value={report.violations} placeholder="Несанкционированное присоединение и т.п." />
				{/if}
			{/if}

			<Button class="mt-4 w-full" onclick={close}>Готово</Button>
		</div>
	</div>
{/if}
