import { api, ApiError } from './client';

export interface Attachment {
	id: number;
	filename: string;
	content_type: string | null;
	size: number;
}

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
	attachments: Attachment[];
}

export async function fetchTickets(): Promise<Ticket[]> {
	const data = await api<{ tickets: Ticket[] }>('/api/tickets');
	return data.tickets;
}

export async function createTicket(taskNumbers: string, question: string): Promise<{ id: number }> {
	return api<{ id: number }>('/api/tickets', {
		method: 'POST',
		body: JSON.stringify({ task_numbers: taskNumbers, question })
	});
}

export async function uploadAttachments(ticketId: number, files: File[]): Promise<void> {
	const fd = new FormData();
	for (const f of files) fd.append('files', f);
	const res = await fetch(`/api/tickets/${ticketId}/attachments`, {
		method: 'POST',
		body: fd,
		credentials: 'include'
	});
	if (!res.ok) {
		const body = await res.json().catch(() => ({}));
		throw new ApiError(res.status, body.error ?? res.statusText);
	}
}

export async function answerTicket(id: number, answer: string): Promise<void> {
	await api(`/api/tickets/${id}/answer`, {
		method: 'POST',
		body: JSON.stringify({ answer })
	});
}
