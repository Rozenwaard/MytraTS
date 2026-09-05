import { redirect } from '@sveltejs/kit';
import { auth, loadAuth } from '$lib/store/auth.svelte';

export async function load() {
	await loadAuth();
	if (!auth.user) {
		redirect(307, '/login');
	}
}
