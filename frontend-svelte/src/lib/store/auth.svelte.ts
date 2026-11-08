import { goto } from '$app/navigation';
import { api, setOnUnauthorized, type User } from '$lib/api/client';

export const auth = $state<{
	user: User | null;
	loading: boolean;
	impersonatorId: number | null;
}>({
	user: null,
	loading: true,
	impersonatorId: null
});

// B8: глобально на 401 сбрасываем пользователя и уводим на вход.
setOnUnauthorized(() => {
	auth.user = null;
	auth.impersonatorId = null;
	if (typeof window !== 'undefined') {
		goto('/login');
	}
});

let loadPromise: Promise<void> | null = null;

export function loadAuth(): Promise<void> {
	if (!loadPromise) {
		loadPromise = (async () => {
			try {
				await refreshAuth();
			} catch {
				auth.user = null;
				auth.impersonatorId = null;
				auth.loading = false;
			}
		})();
	}
	return loadPromise;
}

export async function refreshAuth(): Promise<void> {
	const data = await api<{ user: User | null; impersonator_id?: number | null }>('/api/me');
	auth.user = data.user;
	auth.impersonatorId = data.impersonator_id ?? null;
	auth.loading = false;
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
		await refreshAuth();
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
	auth.impersonatorId = null;
}
