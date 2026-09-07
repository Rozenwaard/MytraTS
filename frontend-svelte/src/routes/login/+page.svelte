<script lang="ts">
	import { goto } from '$app/navigation';
	import { login } from '$lib/store/auth.svelte';
	import { api } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import Logo from '$lib/components/logo.svelte';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';

	interface UserSuggestion {
		full_name: string;
		position: string;
		staff_id: string;
	}

	let surname = $state('');
	let staffId = $state('');
	let password = $state('');
	let error = $state('');
	let loading = $state(false);
	let suggestions = $state<UserSuggestion[]>([]);
	let showSuggestions = $state(false);
	let timer: ReturnType<typeof setTimeout> | null = null;

	function searchUsers(q: string) {
		if (timer) clearTimeout(timer);
		if (q.length < 3) {
			suggestions = [];
			showSuggestions = false;
			return;
		}
		timer = setTimeout(async () => {
			try {
				const data = await api<UserSuggestion[]>(`/api/users/search?q=${encodeURIComponent(q)}`);
				suggestions = data;
				showSuggestions = data.length > 0;
			} catch {
				suggestions = [];
				showSuggestions = false;
			}
		}, 300);
	}

	function selectUser(s: UserSuggestion) {
		surname = s.full_name;
		staffId = s.staff_id;
		suggestions = [];
		showSuggestions = false;
	}

	function onSurname(e: Event) {
		surname = (e.target as HTMLInputElement).value;
		staffId = '';
		searchUsers(surname);
	}

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (!staffId) {
			error = 'Выберите пользователя из списка подсказок';
			return;
		}
		loading = true;
		error = '';
		try {
			const result = await login(staffId, password);
			await goto(result.changePassword ? '/change-password' : '/main-afl');
		} catch {
			error = 'Неверный логин или пароль';
		} finally {
			loading = false;
		}
	}
</script>

<div class="flex min-h-screen items-center justify-center p-4">
	<Card class="w-full max-w-md">
		<CardHeader>
			<CardTitle class="flex items-center justify-center gap-2">
				<Logo />
				<span>MYTRA</span>
			</CardTitle>
			<CardDescription class="text-center">Управление реестрами</CardDescription>
		</CardHeader>
		<CardContent>
			<form onsubmit={handleSubmit} autocomplete="off" class="space-y-4">
				<div class="relative space-y-1.5">
					<label class="text-sm font-medium" for="surname">Фамилия</label>
					<Input
						id="surname"
						type="text"
						placeholder="Начните вводить фамилию"
						value={surname}
						oninput={onSurname}
						autocomplete="off"
					/>
					{#if showSuggestions}
						<div class="absolute left-0 right-0 top-full z-10 mt-1 overflow-hidden rounded-md border bg-popover shadow-lg">
							{#each suggestions as s (s.staff_id)}
								<button
									type="button"
									class="block w-full border-b px-3 py-2 text-left transition-colors last:border-b-0 hover:bg-accent"
									onmousedown={(e) => {
										e.preventDefault();
										selectUser(s);
									}}
								>
									<div class="text-sm font-medium">{s.full_name}</div>
									<div class="text-xs text-muted-foreground">{s.position} • {s.staff_id}</div>
								</button>
							{/each}
						</div>
					{/if}
				</div>

				<div class="space-y-1.5">
					<label class="text-sm font-medium" for="password">Пароль</label>
					<Input
						id="password"
						type="password"
						placeholder="Введите пароль"
						bind:value={password}
						autocomplete="current-password"
					/>
				</div>

				{#if error}
					<p class="text-sm text-destructive">{error}</p>
				{/if}

				<Button type="submit" class="w-full" disabled={loading}>
					{loading ? 'Вход...' : 'Войти'}
				</Button>
			</form>

			<p class="mt-4 text-center text-xs text-muted-foreground">
				Первый вход — используйте табельный номер
			</p>
		</CardContent>
	</Card>
</div>
