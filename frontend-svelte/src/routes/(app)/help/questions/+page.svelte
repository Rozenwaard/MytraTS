<script lang="ts">
	import { createQuery } from '@tanstack/svelte-query';
	import { toStore, fromStore } from 'svelte/store';
	import { fetchTickets, createTicket, uploadAttachments, answerTicket, type Ticket } from '$lib/api/tickets';
	import { auth } from '$lib/store/auth.svelte';
	import { toast } from '$lib/store/toast.svelte';
	import { queryClient } from '$lib/query';
	import { Button } from '$lib/components/ui/button';
	import { Skeleton } from '$lib/components/ui/skeleton';
	import {
		Card,
		CardContent,
		CardDescription,
		CardHeader,
		CardTitle
	} from '$lib/components/ui/card';
	import TicketIcon from '@lucide/svelte/icons/ticket';
	import Send from '@lucide/svelte/icons/send';
	import Paperclip from '@lucide/svelte/icons/paperclip';
	import CircleCheck from '@lucide/svelte/icons/circle-check';
	import CircleDashed from '@lucide/svelte/icons/circle-dashed';

	const isAdmin = $derived(auth.user?.role === 'администратор');

	const query = createQuery<Ticket[]>(
		toStore(() => ({
			queryKey: ['tickets'],
			queryFn: fetchTickets
		}))
	);
	const result = fromStore(query);
	const tickets = $derived(result.current.data ?? []);
	const isPending = $derived(result.current.isPending);

	let taskNumbers = $state('');
	let question = $state('');
	let files = $state<File[]>([]);
	let submitting = $state(false);
	let answers: Record<number, string> = $state({});
	let answeringId = $state<number | null>(null);

	const canSubmit = $derived(taskNumbers.trim() !== '' && question.trim() !== '' && !submitting);

	function onFilesChange(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		files = Array.from(input.files ?? []);
		input.value = '';
	}

	function fmtSize(bytes: number): string {
		if (bytes < 1024) return `${bytes} Б`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
	}

	async function submit() {
		if (!taskNumbers.trim() || !question.trim()) {
			toast('Укажите номер задания и текст вопроса');
			return;
		}
		if (files.length > 5) {
			toast('Не более 5 файлов на тикет');
			return;
		}
		if (files.some((f) => f.size > 10 * 1024 * 1024)) {
			toast('Файл больше 10 МБ');
			return;
		}
		submitting = true;
		try {
			const { id } = await createTicket(taskNumbers, question);
			if (files.length > 0) {
				await uploadAttachments(id, files);
			}
			taskNumbers = '';
			question = '';
			files = [];
			await queryClient.invalidateQueries({ queryKey: ['tickets'] });
			await queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
			toast('Тикет создан');
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Не удалось создать тикет');
		} finally {
			submitting = false;
		}
	}

	async function submitAnswer(t: Ticket) {
		const text = (answers[t.id] ?? '').trim();
		if (!text) {
			toast('Введите ответ');
			return;
		}
		answeringId = t.id;
		try {
			await answerTicket(t.id, text);
			await queryClient.invalidateQueries({ queryKey: ['tickets'] });
			await queryClient.invalidateQueries({ queryKey: ['dashboard-overview'] });
			toast('Тикет закрыт');
		} catch (e) {
			toast(e instanceof Error ? e.message : 'Не удалось ответить');
		} finally {
			answeringId = null;
		}
	}
</script>

<div class="mx-auto flex h-full w-full max-w-3xl flex-col gap-4 overflow-auto p-4">
	<Card>
		<CardHeader>
			<CardTitle class="flex items-center gap-2">
				<TicketIcon class="size-5" />
				Вопросы
			</CardTitle>
			<CardDescription>
				Задайте вопрос по заданию — укажите один или несколько номеров заданий и текст вопроса.
				Администратор ответит и закроет тикет.
			</CardDescription>
		</CardHeader>
		<CardContent class="space-y-3">
			<div class="space-y-1.5">
				<label class="text-sm font-medium" for="t-task">
					Номер задания (можно несколько, через запятую или с новой строки)
				</label>
				<textarea
					id="t-task"
					class="min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
					bind:value={taskNumbers}
					placeholder="Например: 123456, 789012"
				></textarea>
			</div>
			<div class="space-y-1.5">
				<label class="text-sm font-medium" for="t-question">Вопрос</label>
				<textarea
					id="t-question"
					class="min-h-24 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
					bind:value={question}
					placeholder="Текст вопроса"
				></textarea>
			</div>
			<div class="space-y-1.5">
				<label class="text-sm font-medium" for="t-files">
					Файлы (картинки/PDF/xlsx, до 5 шт. по 10 МБ)
				</label>
				<input
					id="t-files"
					type="file"
					multiple
					accept=".png,.jpg,.jpeg,.webp,.gif,.pdf,.xlsx"
					class="block w-full text-sm text-muted-foreground file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-3 file:py-1.5 file:text-sm file:font-medium"
					onchange={onFilesChange}
				/>
				{#if files.length > 0}
					<ul class="space-y-1 text-xs text-muted-foreground">
						{#each files as f}
							<li>{f.name} · {fmtSize(f.size)}</li>
						{/each}
					</ul>
				{/if}
			</div>
			<Button onclick={submit} disabled={!canSubmit} class="gap-2">
				<Send class="size-4" />
				{submitting ? 'Отправка…' : 'Отправить'}
			</Button>
		</CardContent>
	</Card>

	<div class="space-y-3">
		{#if isPending}
			{#each Array(3) as _}
				<Skeleton class="h-24 w-full" />
			{/each}
		{:else if tickets.length === 0}
			<p class="text-sm text-muted-foreground">Тикетов пока нет</p>
		{:else}
			{#each tickets as t (t.id)}
				<Card>
					<CardContent class="space-y-3 pt-4">
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0">
								<div class="text-sm">
									<span class="font-semibold tabular-nums">#{t.id}</span>
									<span class="ml-2 text-muted-foreground">{t.task_numbers.join(', ')}</span>
								</div>
								{#if isAdmin}
									<div class="mt-0.5 text-xs text-muted-foreground">
										{t.author_name} · {t.created_at}
									</div>
								{/if}
							</div>
							{#if t.status === 'closed'}
								<span
									class="inline-flex shrink-0 items-center gap-1 rounded-md bg-muted px-2 py-0.5 text-xs text-muted-foreground"
								>
									<CircleCheck class="size-3.5" />
									Закрыт
								</span>
							{:else}
								<span
									class="inline-flex shrink-0 items-center gap-1 rounded-md bg-amber-100 px-2 py-0.5 text-xs text-amber-800"
								>
									<CircleDashed class="size-3.5" />
									Открыт
								</span>
							{/if}
						</div>

						<p class="whitespace-pre-line text-sm">{t.question}</p>

						{#if t.attachments?.length}
							<div class="space-y-1">
								{#each t.attachments as a (a.id)}
									<a
										href={`/api/tickets/${t.id}/attachments/${a.id}`}
										class="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
									>
										<Paperclip class="size-3.5" />
										{a.filename}
										<span class="text-xs text-muted-foreground">({fmtSize(a.size)})</span>
									</a>
								{/each}
							</div>
						{/if}

						{#if t.answer}
							<div class="rounded-md border bg-muted/40 px-3 py-2 text-sm">
								<span class="font-medium">Ответ:</span> {t.answer}
								{#if t.answered_by}
									<span class="ml-1 text-xs text-muted-foreground">({t.answered_by})</span>
								{/if}
							</div>
						{/if}

						{#if isAdmin && t.status === 'open'}
							<div class="space-y-2">
								<textarea
									class="min-h-20 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
									placeholder="Ответ"
									value={answers[t.id] ?? ''}
									oninput={(e) => {
										answers[t.id] = (e.currentTarget as HTMLTextAreaElement).value;
									}}
								></textarea>
								<Button
									size="sm"
									onclick={() => submitAnswer(t)}
									disabled={answeringId === t.id}
								>
									{answeringId === t.id ? 'Отправка…' : 'Ответить и закрыть'}
								</Button>
							</div>
						{/if}
					</CardContent>
				</Card>
			{/each}
		{/if}
	</div>
</div>
