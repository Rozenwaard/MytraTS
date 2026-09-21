import { api } from './client';

export type Role = 'администратор' | 'специалист' | 'менеджер' | 'оператор' | 'работник';

export interface AdminUser {
	id: number;
	full_name: string;
	dept: string;
	locale: string | null;
	position: string;
	staff_id: string;
	role: Role | null;
	effective_role: Role;
	executor_name: string | null;
	has_password: boolean;
}

export interface MissingPerson {
	staff_id: string;
	name: string;
	position: string;
}

export interface UserPayload {
	full_name: string;
	staff_id: string;
	dept: string;
	position: string;
	locale: string;
	role: Role | null;
	executor_name: string;
}

export interface QuarantineItem {
	executor: string;
	executor_organization: string;
	status: 'рассмотрение' | 'блок';
}

export async function fetchUsers(q = ''): Promise<AdminUser[]> {
	const qs = q ? `?q=${encodeURIComponent(q)}` : '';
	const data = await api<{ users: AdminUser[] }>(`/api/admin/users${qs}`);
	return data.users;
}

export async function fetchMissing(): Promise<MissingPerson[]> {
	const data = await api<{ missing: MissingPerson[] }>('/api/admin/missing');
	return data.missing;
}

export async function createUser(payload: UserPayload): Promise<void> {
	await api('/api/admin/users', { method: 'POST', body: JSON.stringify(payload) });
}

export async function deleteUser(id: number): Promise<void> {
	await api(`/api/admin/users/${id}`, { method: 'DELETE' });
}

export async function resetPassword(id: number): Promise<void> {
	await api(`/api/admin/users/${id}/reset-password`, { method: 'POST' });
}

export async function updateExecutorName(id: number, executorName: string): Promise<void> {
	await api(`/api/admin/users/${id}/executor-name`, {
		method: 'PATCH',
		body: JSON.stringify({ executor_name: executorName })
	});
}

export async function fetchQuarantine(): Promise<QuarantineItem[]> {
	const data = await api<{ items: QuarantineItem[] }>('/api/admin/quarantine');
	return data.items;
}

export async function toggleQuarantineBlock(executor: string): Promise<{ ok: boolean; status: string }> {
	return api('/api/admin/quarantine/toggle', {
		method: 'POST',
		body: JSON.stringify({ executor })
	});
}
