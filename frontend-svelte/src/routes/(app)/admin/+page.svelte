<script lang="ts">
	import { goto } from '$app/navigation';
	import { auth } from '$lib/store/auth.svelte';
	import { toast } from '$lib/store/toast.svelte';
	import { cn } from '$lib/utils.js';
	import {
		fetchUsers,
		deleteUser,
		resetPassword,
		updateExecutorName,
		type AdminUser
	} from '$lib/api/admin';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Badge, badgeVariants } from '$lib/components/ui/badge';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import Trash2 from '@lucide/svelte/icons/trash-2';
	import X from '@lucide/svelte/icons/x';
	import Users from '@lucide/svelte/icons/users';

	type SortKey =
		| 'full_name'
		| 'staff_id'
		| 'position'
		| 'dept'
		| 'locale'
		| 'executor_name'
		| 'effective_role';

	const isAdmin = $derived(auth.user?.role === 'администратор');

	let users = $state<AdminUser[]>([]);
	let loading = $state(true);
	let search = $state('');
	let started = $state(false);

	let sortKey = $state<SortKey>('full_name');
	let sortDir = $state<'asc' | 'desc'>('asc');

	let editNameOpen = $state(false);
	let editUser = $state<AdminUser | null>(null);
	let editValue = $state('');
	let editSaving = $state(false);

	const filteredUsers = $derived(
		search.trim()
			? users.filter((u) =>
					`${u.full_name} ${u.staff_id} ${u.position} ${u.dept}`
						.toLowerCase()
						.includes(search.trim().toLowerCase())
				)
			: users
	);

	const sortedUsers = $derived(
		[...filteredUsers].sort((a, b) => {
			const av = (a[sortKey] ?? '') as string;
			const bv = (b[sortKey] ?? '') as string;
			const cmp = compareValues(av, bv);
			return sortDir === 'asc' ? cmp : -cmp;
		})
	);

	function compareValues(a: string, b: string): number {
		const an = Number(a);
		const bn = Number(b);
		if (a !== '' && b !== '' && !Number.isNaN(an) && !Number.isNaN(bn)) {
			return an - bn;
		}
		return a.localeCompare(b, 'ru');
	}

	function toggleSort(key: SortKey) {
		if (sortKey === key) {
			sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		} else {
			sortKey = key;
			sortDir = 'asc';
		}
	}

	function sortIndicator(key: SortKey): string {
		if (sortKey !== key) return '';
		return sortDir === 'asc' ? '↑' : '↓';
	}

	$effect(() => {
		if (isAdmin && !started) {
			started = true;
			load();
		}
	});

	$effect(() => {
		if (auth.user && auth.user.role !== 'администратор') {
			goto('/dashboard');
		}
	});

	async function load() {
		loading = true;
		try {
			users = await fetchUsers();
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка загрузки');
		} finally {
			loading = false;
		}
	}

	function openEditName(u: AdminUser) {
		editUser = u;
		editValue = u.executor_name ?? '';
		editNameOpen = true;
	}

	function closeEditName() {
		editNameOpen = false;
		editUser = null;
	}

	async function saveEditName() {
		if (!editUser) return;
		editSaving = true;
		try {
			await updateExecutorName(editUser.id, editValue.trim());
			toast('Алькор сохранён');
			closeEditName();
			await load();
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка сохранения');
		} finally {
			editSaving = false;
		}
	}

	async function remove(u: AdminUser) {
		if (!confirm(`Удалить пользователя «${u.full_name}» (таб. № ${u.staff_id})?`)) return;
		try {
			await deleteUser(u.id);
			toast('Пользователь удалён');
			await load();
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка удаления');
		}
	}

	async function reset(u: AdminUser) {
		if (!confirm(`Сбросить пароль «${u.full_name}» на табельный номер?`)) return;
		try {
			await resetPassword(u.id);
			toast('Пароль сброшен (вход по табельному номеру)');
			await load();
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка сброса');
		}
	}
</script>

<div class="flex h-full w-full flex-col gap-4 overflow-hidden p-4">
	{#if !isAdmin}
		<div class="text-sm text-muted-foreground">Нет доступа</div>
	{:else}
		<Card class="min-h-0 flex-1">
			<CardHeader class="shrink-0">
				<div class="flex flex-wrap items-center justify-between gap-2">
					<div>
						<CardTitle class="flex items-center gap-2">
							<Users class="size-5" />
							Пользователи
						</CardTitle>
						<CardDescription>Всего: {users.length}</CardDescription>
					</div>
					<div class="flex items-center gap-2">
						<Input bind:value={search} placeholder="Поиск…" class="w-56" />
					</div>
				</div>
			</CardHeader>
			<CardContent class="flex min-h-0 flex-1 flex-col">
				{#if loading}
					<div class="space-y-2">
						{#each Array(6) as _}
							<Skeleton class="h-10 w-full" />
						{/each}
					</div>
				{:else if sortedUsers.length === 0}
					<div class="py-8 text-center text-sm text-muted-foreground">Пользователи не найдены</div>
				{:else}
					<Table containerClass="min-h-0 flex-1 overflow-auto rounded-md border">
						<TableHeader>
							<TableRow class="hover:bg-transparent">
								<TableHead
									class="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap bg-muted"
									onclick={() => toggleSort('full_name')}
								>
									ФИО {sortIndicator('full_name')}
								</TableHead>
								<TableHead
									class="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap bg-muted"
									onclick={() => toggleSort('staff_id')}
								>
									Таб. № {sortIndicator('staff_id')}
								</TableHead>
								<TableHead
									class="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap bg-muted"
									onclick={() => toggleSort('position')}
								>
									Должность {sortIndicator('position')}
								</TableHead>
								<TableHead
									class="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap bg-muted"
									onclick={() => toggleSort('dept')}
								>
									Отделение {sortIndicator('dept')}
								</TableHead>
								<TableHead
									class="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap bg-muted"
									onclick={() => toggleSort('locale')}
								>
									Офис {sortIndicator('locale')}
								</TableHead>
								<TableHead
									class="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap bg-muted"
									onclick={() => toggleSort('executor_name')}
								>
									Алькор {sortIndicator('executor_name')}
								</TableHead>
								<TableHead
									class="sticky top-0 z-10 cursor-pointer select-none whitespace-nowrap bg-muted"
									onclick={() => toggleSort('effective_role')}
								>
									Роль {sortIndicator('effective_role')}
								</TableHead>
								<TableHead class="sticky top-0 z-10 whitespace-nowrap bg-muted text-right">Пароль</TableHead>
								<TableHead class="sticky top-0 z-10 w-10 bg-muted"></TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each sortedUsers as u (u.id)}
								<TableRow class="cursor-pointer" onclick={() => openEditName(u)}>
									<TableCell class="font-medium">{u.full_name}</TableCell>
									<TableCell class="tabular-nums">{u.staff_id}</TableCell>
									<TableCell>{u.position}</TableCell>
									<TableCell>{u.dept}</TableCell>
									<TableCell>{u.locale ?? '—'}</TableCell>
									<TableCell>{u.executor_name ?? '—'}</TableCell>
									<TableCell>
										<span class="rounded bg-muted px-1.5 py-0.5 text-xs">{u.effective_role}</span>
									</TableCell>
									<TableCell class="text-right">
										{#if u.has_password}
											<button
												type="button"
												class={cn(
													badgeVariants({ variant: 'default' }),
													'cursor-pointer bg-brand-brown text-white'
												)}
												onclick={(e) => {
													e.stopPropagation();
													reset(u);
												}}
												title="Сбросить пароль в табельный номер"
											>
												custom
											</button>
										{:else}
											<Badge class="bg-brand-logo text-white">system</Badge>
										{/if}
									</TableCell>
									<TableCell class="text-right">
										<Button
											variant="ghost"
											size="icon-sm"
											onclick={(e) => {
												e.stopPropagation();
												remove(u);
											}}
											aria-label="Удалить"
										>
											<Trash2 class="size-4 text-destructive" />
										</Button>
									</TableCell>
								</TableRow>
							{/each}
						</TableBody>
					</Table>
				{/if}
			</CardContent>
		</Card>
	{/if}
</div>

{#if editNameOpen}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
		role="button"
		tabindex="-1"
		aria-label="Закрыть"
		onclick={(e) => {
			if (e.target === e.currentTarget) closeEditName();
		}}
		onkeydown={(e) => {
			if (e.key === 'Escape') closeEditName();
		}}
	>
		<div class="w-full max-w-sm rounded-lg border bg-card p-4 shadow-lg" role="dialog" aria-modal="true">
			<div class="mb-3 flex items-center justify-between">
				<h3 class="text-base font-semibold">Поле «Алькор»</h3>
				<Button variant="ghost" size="icon-sm" onclick={closeEditName} aria-label="Закрыть">
					<X class="size-4" />
				</Button>
			</div>
			<p class="mb-3 text-sm text-muted-foreground">
				{editUser?.full_name} (таб. № {editUser?.staff_id})
			</p>
			<div class="space-y-1.5">
				<label class="text-sm font-medium" for="admin-exec-name">Алькор (ФИО как в main_afl)</label>
				<Input id="admin-exec-name" bind:value={editValue} placeholder="Точное ФИО из Алькора" />
			</div>
			<div class="mt-4 flex justify-end gap-2">
				<Button variant="outline" onclick={closeEditName} disabled={editSaving}>Отмена</Button>
				<Button onclick={saveEditName} disabled={editSaving}>
					{editSaving ? 'Сохранение…' : 'Сохранить'}
				</Button>
			</div>
		</div>
	</div>
{/if}


