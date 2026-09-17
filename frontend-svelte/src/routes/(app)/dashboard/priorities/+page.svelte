<script lang="ts">
	import { goto } from '$app/navigation';
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { fetchPriorities, savePriorities, type Priorities } from '$lib/api/dashboard';
	import { auth } from '$lib/store/auth.svelte';
	import { toast } from '$lib/store/toast.svelte';
	import { queryClient } from '$lib/query';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import {
		Card,
		CardContent,
		CardDescription,
		CardFooter,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import ListOrdered from '@lucide/svelte/icons/list-ordered';
	import Plus from '@lucide/svelte/icons/plus';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import ChevronUp from '@lucide/svelte/icons/chevron-up';
	import ChevronDown from '@lucide/svelte/icons/chevron-down';

	const MAX = 6;

	const query = createQuery<Priorities>(
		toStore(() => ({
			queryKey: ['dashboard-priorities'],
			queryFn: () => fetchPriorities()
		}))
	);
	const result = fromStore(query);
	const data = $derived(result.current.data);
	const isError = $derived(result.current.isError);

	let items = $state<string[]>([]);
	let initialized = $state(false);
	let saving = $state(false);

	// Редактор доступен только администратору.
	$effect(() => {
		if (auth.user && auth.user.role !== 'администратор') {
			goto('/dashboard');
		}
	});

	$effect(() => {
		if (data && !initialized) {
			items = [...data.priorities];
			initialized = true;
		}
	});

	const canAdd = $derived(items.length < MAX);
	const canSave = $derived(!saving && items.some((x) => x.trim() !== ''));

	function add() {
		if (items.length >= MAX) return;
		items = [...items, ''];
	}

	function remove(index: number) {
		items = items.filter((_, i) => i !== index);
	}

	function move(index: number, dir: -1 | 1) {
		const target = index + dir;
		if (target < 0 || target >= items.length) return;
		const next = [...items];
		[next[index], next[target]] = [next[target], next[index]];
		items = next;
	}

	async function save() {
		const clean = items.map((x) => x.trim()).filter(Boolean);
		if (clean.length === 0) {
			toast('Укажите хотя бы один приоритет');
			return;
		}
		saving = true;
		try {
			await savePriorities(clean);
			await queryClient.invalidateQueries({ queryKey: ['dashboard-priorities'] });
			await queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
			toast('Приоритеты сохранены');
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Не удалось сохранить');
		} finally {
			saving = false;
		}
	}
</script>

<div class="mx-auto flex h-full w-full max-w-2xl flex-col gap-4 overflow-auto p-4">
	<Card>
		<CardHeader>
			<CardTitle class="flex items-center gap-2">
				<ListOrdered class="size-5" />
				Приоритеты
			</CardTitle>
			<CardDescription>
				Порядок пунктов в виджете «Приоритеты» на вкладке «Обзор». Добавляйте, редактируйте и
				удаляйте пункты — не более {MAX}. Первый пункт считается наивысшим приоритетом.
			</CardDescription>
		</CardHeader>

		{#if isError}
			<CardContent>
				<p class="text-sm text-muted-foreground">
					Ошибка загрузки приоритетов. Повторите позже или сообщите администратору.
				</p>
			</CardContent>
		{:else if !initialized}
			<CardContent class="space-y-3">
				{#each Array(4) as _}
					<Skeleton class="h-10 w-full" />
				{/each}
			</CardContent>
		{:else}
			<CardContent class="space-y-2">
				{#each items as item, i (i)}
					<div class="flex items-center gap-2">
						<span
							class="flex size-8 shrink-0 items-center justify-center rounded-md bg-muted text-sm font-semibold tabular-nums text-muted-foreground"
						>
							{i + 1}
						</span>
						<Input bind:value={items[i]} placeholder={`Приоритет ${i + 1}`} />
						<div class="flex shrink-0 items-center">
							<Button
								variant="ghost"
								size="icon-sm"
								onclick={() => move(i, -1)}
								disabled={i === 0}
								aria-label="Переместить вверх"
							>
								<ChevronUp />
							</Button>
							<Button
								variant="ghost"
								size="icon-sm"
								onclick={() => move(i, 1)}
								disabled={i === items.length - 1}
								aria-label="Переместить вниз"
							>
								<ChevronDown />
							</Button>
							<Button
								variant="ghost"
								size="icon-sm"
								onclick={() => remove(i)}
								aria-label="Удалить"
							>
								<Trash2 class="size-4 text-destructive" />
							</Button>
						</div>
					</div>
				{/each}

				<Button variant="outline" onclick={add} disabled={!canAdd} class="w-full">
					<Plus />
					Добавить приоритет
				</Button>
			</CardContent>

			<CardFooter class="flex items-center justify-between">
				<span class="text-sm text-muted-foreground">{items.length} из {MAX}</span>
				<Button onclick={save} disabled={!canSave}>
					{saving ? 'Сохранение…' : 'Сохранить'}
				</Button>
			</CardFooter>
		{/if}
	</Card>
</div>
