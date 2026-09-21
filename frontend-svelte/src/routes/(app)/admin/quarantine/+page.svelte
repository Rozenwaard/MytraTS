<script lang="ts">
	import { goto } from '$app/navigation';
	import { auth } from '$lib/store/auth.svelte';
	import { toast } from '$lib/store/toast.svelte';
	import {
		fetchUsers,
		fetchMissing,
		createUser,
		fetchQuarantine,
		toggleQuarantineBlock,
		updateExecutorName,
		type AdminUser,
		type MissingPerson,
		type Role,
		type UserPayload,
		type QuarantineItem
	} from '$lib/api/admin';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import { Badge } from '$lib/components/ui/badge';
	import {
		Table,
		TableBody,
		TableCell,
		TableHead,
		TableHeader,
		TableRow
	} from '$lib/components/ui/table';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';
	import Plus from '@lucide/svelte/icons/plus';
	import X from '@lucide/svelte/icons/x';
	import UserPlus from '@lucide/svelte/icons/user-plus';
	import ShieldAlert from '@lucide/svelte/icons/shield-alert';
	import Ban from '@lucide/svelte/icons/ban';
	import CircleCheck from '@lucide/svelte/icons/circle-check';

	const ROLE_OPTIONS = ['администратор', 'специалист', 'менеджер', 'оператор', 'работник'];

	const isAdmin = $derived(auth.user?.role === 'администратор');

	let users = $state<AdminUser[]>([]);
	let missing = $state<MissingPerson[]>([]);
	let quarantine = $state<QuarantineItem[]>([]);
	let loading = $state(true);
	let started = $state(false);

	let formOpen = $state(false);
	let saving = $state(false);
	let form = $state<UserPayload>(emptyForm());

	let matchOpen = $state(false);
	let matchUser = $state<AdminUser | null>(null);
	let matchExecutor = $state('');
	let matchSaving = $state(false);

	function emptyForm(): UserPayload {
		return {
			full_name: '',
			staff_id: '',
			dept: '',
			position: '',
			locale: '',
			role: null,
			executor_name: ''
		};
	}

	const unmatchedUsers = $derived(users.filter((u) => !u.executor_name));

	const deptOptions = $derived([...new Set(users.map((u) => u.dept).filter(Boolean))].sort());
	const localeOptions = $derived([...new Set(users.map((u) => u.locale).filter(Boolean))].sort());
	const positionOptions = $derived([...new Set(users.map((u) => u.position).filter(Boolean))].sort());

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
			const [u, m, q] = await Promise.all([fetchUsers(), fetchMissing(), fetchQuarantine()]);
			users = u;
			missing = m;
			quarantine = q;
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка загрузки');
		} finally {
			loading = false;
		}
	}

	function openCreate() {
		form = emptyForm();
		formOpen = true;
	}

	function openFromMissing(m: MissingPerson) {
		form = { ...emptyForm(), full_name: m.name, staff_id: m.staff_id, position: m.position };
		formOpen = true;
	}

	function closeForm() {
		formOpen = false;
	}

	async function save() {
		if (!form.full_name.trim() || !form.staff_id.trim() || !form.position || !form.dept || !form.locale) {
			toast('Все поля обязательны');
			return;
		}
		saving = true;
		try {
			await createUser({
				full_name: form.full_name.trim(),
				staff_id: form.staff_id.trim(),
				dept: form.dept,
				position: form.position,
				locale: form.locale,
				role: form.role,
				executor_name: form.executor_name.trim()
			});
			toast('Пользователь добавлен');
			closeForm();
			await load();
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка сохранения');
		} finally {
			saving = false;
		}
	}

	function onMatchChange(item: QuarantineItem, value: string) {
		if (value.startsWith('user:')) {
			const id = Number(value.slice(5));
			const u = users.find((x) => x.id === id);
			if (u) openMatch(item.executor, u);
		} else if (value.startsWith('missing:')) {
			const sid = value.slice(8);
			const m = missing.find((x) => x.staff_id === sid);
			if (m) {
				form = {
					...emptyForm(),
					full_name: m.name,
					staff_id: m.staff_id,
					position: m.position,
					executor_name: item.executor
				};
				formOpen = true;
			}
		}
	}

	function openMatch(executor: string, u: AdminUser) {
		matchExecutor = executor;
		matchUser = u;
		matchOpen = true;
	}

	function closeMatch() {
		matchOpen = false;
		matchUser = null;
	}

	async function saveMatch() {
		if (!matchUser) return;
		matchSaving = true;
		try {
			await updateExecutorName(matchUser.id, matchExecutor);
			toast('Сопоставлено');
			closeMatch();
			await load();
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка сопоставления');
		} finally {
			matchSaving = false;
		}
	}

	async function toggleBlock(item: QuarantineItem) {
		const blocking = item.status !== 'блок';
		const msg = blocking
			? `Заблокировать «${item.executor}»? Его строки будут удалены из main_afl.`
			: `Снять блок с «${item.executor}»?`;
		if (!confirm(msg)) return;
		try {
			await toggleQuarantineBlock(item.executor);
			await load();
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Ошибка');
		}
	}
</script>

<div class="flex h-full w-full flex-col gap-4 overflow-auto p-4">
	{#if !isAdmin}
		<div class="text-sm text-muted-foreground">Нет доступа</div>
	{:else}
		{#if missing.length > 0}
			<Card class="shrink-0">
				<CardHeader>
					<CardTitle class="flex items-center gap-2">
						<UserPlus class="size-5" />
						Очередь на добавление
					</CardTitle>
					<CardDescription>
						Работники из табеля рабочего времени, которых нет в пользователях.
					</CardDescription>
				</CardHeader>
				<CardContent>
					<div class="flex flex-wrap gap-2">
						{#each missing as m (m.staff_id)}
							<button
								type="button"
								onclick={() => openFromMissing(m)}
								class="flex items-center gap-2 rounded-md border bg-card px-3 py-2 text-left text-sm transition-colors hover:bg-accent"
							>
								<span class="font-medium">{m.name || m.staff_id}</span>
								<span class="text-muted-foreground">{m.position}</span>
								<span class="text-xs tabular-nums text-muted-foreground">№ {m.staff_id}</span>
								<Plus class="size-4" />
							</button>
						{/each}
					</div>
				</CardContent>
			</Card>
		{/if}

		<Card class="min-h-0 flex-1">
			<CardHeader class="shrink-0">
				<CardTitle class="flex items-center gap-2">
					<ShieldAlert class="size-5" />
					Карантин
				</CardTitle>
				<CardDescription>
					Исполнители из отчёта Алькор, не совпадающие с записями о наших работниках.
				</CardDescription>
			</CardHeader>
			<CardContent class="flex min-h-0 flex-1 flex-col">
				{#if loading}
					<div class="space-y-2">
						{#each Array(6) as _}
							<Skeleton class="h-10 w-full" />
						{/each}
					</div>
				{:else if quarantine.length === 0}
					<div class="py-8 text-center text-sm text-muted-foreground">Карантин пуст</div>
				{:else}
					<Table containerClass="min-h-0 flex-1 overflow-auto rounded-md border">
						<TableHeader>
							<TableRow class="hover:bg-transparent">
								<TableHead class="sticky top-0 z-10 whitespace-nowrap bg-muted">Исполнитель</TableHead>
								<TableHead class="sticky top-0 z-10 whitespace-nowrap bg-muted">Отделение</TableHead>
								<TableHead class="sticky top-0 z-10 whitespace-nowrap bg-muted">Статус</TableHead>
								<TableHead class="sticky top-0 z-10 w-10 bg-muted">Блок</TableHead>
								<TableHead class="sticky top-0 z-10 whitespace-nowrap bg-muted">Сопоставление</TableHead>
							</TableRow>
						</TableHeader>
						<TableBody>
							{#each quarantine as item (item.executor)}
								<TableRow>
									<TableCell class="font-medium">{item.executor}</TableCell>
									<TableCell>{item.executor_organization || '—'}</TableCell>
									<TableCell>
										{#if item.status === 'блок'}
											<Badge class="bg-destructive/15 text-destructive">блок</Badge>
										{:else}
											<Badge class="bg-brand-logo text-white">рассмотрение</Badge>
										{/if}
									</TableCell>
									<TableCell>
										<Button
											variant="ghost"
											size="icon-sm"
											onclick={() => toggleBlock(item)}
											aria-label={item.status === 'блок' ? 'Снять блок' : 'Заблокировать'}
										>
											{#if item.status === 'блок'}
												<CircleCheck class="size-4 text-destructive" />
											{:else}
												<Ban class="size-4" />
											{/if}
										</Button>
									</TableCell>
									<TableCell>
										<select
											class="h-9 w-full min-w-48 rounded-md border border-input bg-background px-2 text-sm"
											onchange={(e) => onMatchChange(item, (e.currentTarget as HTMLSelectElement).value)}
										>
											<option value="">Сопоставить…</option>
											{#if missing.length > 0}
												<optgroup label="Очередь на добавление">
													{#each missing as m (m.staff_id)}
														<option value={`missing:${m.staff_id}`}>{m.name} — {m.position}</option>
													{/each}
												</optgroup>
											{/if}
											<optgroup label="Пользователи (без Алькор)">
												{#each unmatchedUsers as u (u.id)}
													<option value={`user:${u.id}`}>{u.full_name}</option>
												{/each}
											</optgroup>
										</select>
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

{#if formOpen}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
		role="button"
		tabindex="-1"
		aria-label="Закрыть"
		onclick={(e) => {
			if (e.target === e.currentTarget) closeForm();
		}}
		onkeydown={(e) => {
			if (e.key === 'Escape') closeForm();
		}}
	>
		<div class="w-full max-w-md rounded-lg border bg-card p-4 shadow-lg" role="dialog" aria-modal="true">
			<div class="mb-3 flex items-center justify-between">
				<h3 class="text-base font-semibold">Добавить пользователя</h3>
				<Button variant="ghost" size="icon-sm" onclick={closeForm} aria-label="Закрыть">
					<X class="size-4" />
				</Button>
			</div>

			<div class="space-y-3">
				<div class="space-y-1.5">
					<label class="text-sm font-medium" for="q-fio">ФИО</label>
					<Input id="q-fio" bind:value={form.full_name} placeholder="Иванов Иван Иванович" />
				</div>
				<div class="space-y-1.5">
					<label class="text-sm font-medium" for="q-staff">Табельный номер</label>
					<Input id="q-staff" bind:value={form.staff_id} placeholder="1234" />
				</div>
				<div class="space-y-1.5">
					<label class="text-sm font-medium" for="q-pos">Должность</label>
					<select
						id="q-pos"
						value={form.position}
						onchange={(e) => {
							form.position = (e.currentTarget as HTMLSelectElement).value;
						}}
						class="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
					>
						<option value="" disabled>Выберите должность</option>
						{#each positionOptions as o (o)}
							<option value={o}>{o}</option>
						{/each}
					</select>
				</div>
				<div class="space-y-1.5">
					<label class="text-sm font-medium" for="q-dept">Отделение</label>
					<select
						id="q-dept"
						value={form.dept}
						onchange={(e) => {
							form.dept = (e.currentTarget as HTMLSelectElement).value;
						}}
						class="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
					>
						<option value="" disabled>Выберите отделение</option>
						{#each deptOptions as o (o)}
							<option value={o}>{o}</option>
						{/each}
					</select>
				</div>
				<div class="grid grid-cols-2 gap-3">
					<div class="space-y-1.5">
						<label class="text-sm font-medium" for="q-locale">Офис</label>
						<select
							id="q-locale"
							value={form.locale}
							onchange={(e) => {
								form.locale = (e.currentTarget as HTMLSelectElement).value;
							}}
							class="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
						>
							<option value="" disabled>Выберите офис</option>
							{#each localeOptions as o (o)}
								<option value={o}>{o}</option>
							{/each}
						</select>
					</div>
					<div class="space-y-1.5">
						<label class="text-sm font-medium" for="q-role">Роль</label>
						<select
							id="q-role"
							value={form.role ?? ''}
							onchange={(e) => {
								form.role = ((e.currentTarget as HTMLSelectElement).value || null) as Role | null;
							}}
							class="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
						>
							<option value="">Автоматически (по должности)</option>
							{#each ROLE_OPTIONS as r (r)}
								<option value={r}>{r}</option>
							{/each}
						</select>
					</div>
				</div>
				<div class="space-y-1.5">
					<label class="text-sm font-medium" for="q-exec">Алькор (ФИО как в main_afl)</label>
					<Input id="q-exec" bind:value={form.executor_name} placeholder="Необязательно" />
				</div>
			</div>

			<div class="mt-4 flex justify-end gap-2">
				<Button variant="outline" onclick={closeForm} disabled={saving}>Отмена</Button>
				<Button onclick={save} disabled={saving}>
					{saving ? 'Сохранение…' : 'Добавить'}
				</Button>
			</div>
		</div>
	</div>
{/if}

{#if matchOpen}
	<div
		class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
		role="button"
		tabindex="-1"
		aria-label="Закрыть"
		onclick={(e) => {
			if (e.target === e.currentTarget) closeMatch();
		}}
		onkeydown={(e) => {
			if (e.key === 'Escape') closeMatch();
		}}
	>
		<div class="w-full max-w-sm rounded-lg border bg-card p-4 shadow-lg" role="dialog" aria-modal="true">
			<div class="mb-3 flex items-center justify-between">
				<h3 class="text-base font-semibold">Сопоставление с «Алькор»</h3>
				<Button variant="ghost" size="icon-sm" onclick={closeMatch} aria-label="Закрыть">
					<X class="size-4" />
				</Button>
			</div>
			<div class="space-y-2 text-sm">
				<div>
					<span class="text-muted-foreground">Исполнитель:</span>{' '}
					<span class="font-medium">{matchExecutor}</span>
				</div>
				<div>
					<span class="text-muted-foreground">Пользователь:</span>{' '}
					<span class="font-medium">{matchUser?.full_name}</span>
				</div>
			</div>
			<div class="mt-4 flex justify-end gap-2">
				<Button variant="outline" onclick={closeMatch} disabled={matchSaving}>Отмена</Button>
				<Button onclick={saveMatch} disabled={matchSaving}>
					{matchSaving ? 'Сохранение…' : 'Сопоставить'}
				</Button>
			</div>
		</div>
	</div>
{/if}


