<script lang="ts">
	import { goto } from '$app/navigation';
	import { api } from '$lib/api/client';
	import { Button } from '$lib/components/ui/button';
	import { Input } from '$lib/components/ui/input';
	import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '$lib/components/ui/card';

	let newPassword = $state('');
	let confirmPassword = $state('');
	let error = $state('');
	let loading = $state(false);

	async function handleSubmit(e: SubmitEvent) {
		e.preventDefault();
		if (newPassword.length < 4) {
			error = 'Пароль должен быть не менее 4 символов';
			return;
		}
		if (newPassword !== confirmPassword) {
			error = 'Пароли не совпадают';
			return;
		}
		loading = true;
		error = '';
		try {
			await api('/api/change-password', {
				method: 'POST',
				body: JSON.stringify({ new_password: newPassword, confirm_password: confirmPassword })
			});
			await goto('/main-afl');
		} catch {
			error = 'Ошибка при смене пароля';
		} finally {
			loading = false;
		}
	}
</script>

<div class="h-full overflow-auto p-4">
	<div class="mx-auto max-w-md">
		<Card>
			<CardHeader>
				<CardTitle class="text-center">Смена пароля</CardTitle>
				<CardDescription class="text-center">Первый вход — задайте новый пароль</CardDescription>
			</CardHeader>
			<CardContent>
				<form onsubmit={handleSubmit} class="space-y-4">
					<div class="space-y-1.5">
						<label class="text-sm font-medium" for="new-password">Новый пароль</label>
						<Input id="new-password" type="password" bind:value={newPassword} autocomplete="new-password" />
					</div>
					<div class="space-y-1.5">
						<label class="text-sm font-medium" for="confirm-password">Подтверждение</label>
						<Input id="confirm-password" type="password" bind:value={confirmPassword} autocomplete="new-password" />
					</div>
					{#if error}
						<p class="text-sm text-destructive">{error}</p>
					{/if}
					<Button type="submit" class="w-full" disabled={loading}>
						{loading ? 'Смена...' : 'Сменить пароль'}
					</Button>
				</form>
			</CardContent>
		</Card>
	</div>
</div>
