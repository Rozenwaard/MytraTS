import { api, type User } from '$lib/api/client';

export const auth = $state<{
	user: User | null;
	loading: boolean;
}>({
	user: null,
	loading: true
});

let loadPromise: Promise<void> | null = null;

export function loadAuth(): Promise<void> {
	if (!loadPromise) {
		loadPromise = (async () => {
			try {
				const data = await api<{ user: User | null }>('/api/me');
				auth.user = data.user;
			} catch {
				auth.user = null;
			} finally {
				auth.loading = false;
			}
		})();
	}
	return loadPromise;
}

export async function login(
	staffId: string,
	password: string
): Promise<{ changePassword: boolean }> {
	const data = await api<{
		ok: boolean;
		change_password: boolean;
		full_name: string;
		role: User['role'];
	}>('/api/login', {
		method: 'POST',
		body: JSON.stringify({ staff_id: staffId, password })
	});
	if (data.ok) {
		const me = await api<{ user: User }>('/api/me');
		auth.user = me.user;
	}
	return { changePassword: data.change_password };
}

export async function logout(): Promise<void> {
	try {
		await api('/api/logout', { method: 'POST' });
	} catch {
		// игнорируем — сессия могла уже истечь
	}
	auth.user = null;
}
