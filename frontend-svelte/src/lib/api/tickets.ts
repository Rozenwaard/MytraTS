import { api } from './client';

export interface Ticket {
	id: number;
	task_numbers: string[];
	question: string;
	answer: string | null;
	status: 'open' | 'closed';
	author_name: string;
	author_staff_id: string;
	created_at: string;
	answered_at: string | null;
	answered_by: string | null;
}

export async function fetchTickets(): Promise<Ticket[]> {
	const data = await api<{ tickets: Ticket[] }>('/api/tickets');
	return data.tickets;
}

export async function createTicket(taskNumbers: string, question: string): Promise<void> {
	await api('/api/tickets', {
		method: 'POST',
		body: JSON.stringify({ task_numbers: taskNumbers, question })
	});
}

export async function answerTicket(id: number, answer: string): Promise<void> {
	await api(`/api/tickets/${id}/answer`, {
		method: 'POST',
		body: JSON.stringify({ answer })
	});
}
