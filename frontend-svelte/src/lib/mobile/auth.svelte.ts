// Авторизация мобильного контура: токен устройства + device_id.
// Храним в localStorage (в Capacitor позже заменим на SecureStorage/Preferences).

const TOKEN_KEY = 'rks.device.token';
const NAME_KEY = 'rks.device.name';
const DEVICE_KEY = 'rks.device.id';

export const mobileAuth = $state<{ token: string | null; fullName: string | null }>({
	token: null,
	fullName: null
});

export function getDeviceId(): string {
	if (typeof localStorage === 'undefined') return '';
	let id = localStorage.getItem(DEVICE_KEY);
	if (!id) {
		id = crypto.randomUUID();
		localStorage.setItem(DEVICE_KEY, id);
	}
	return id;
}

export function getToken(): string | null {
	if (mobileAuth.token) return mobileAuth.token;
	if (typeof localStorage === 'undefined') return null;
	return localStorage.getItem(TOKEN_KEY);
}

export function loadMobileAuth(): void {
	if (typeof localStorage === 'undefined') return;
	const t = localStorage.getItem(TOKEN_KEY);
	if (t) {
		mobileAuth.token = t;
		mobileAuth.fullName = localStorage.getItem(NAME_KEY);
	}
}

export function setMobileAuth(token: string, fullName: string): void {
	mobileAuth.token = token;
	mobileAuth.fullName = fullName;
	localStorage.setItem(TOKEN_KEY, token);
	localStorage.setItem(NAME_KEY, fullName);
}

export function clearMobileAuth(): void {
	mobileAuth.token = null;
	mobileAuth.fullName = null;
	localStorage.removeItem(TOKEN_KEY);
	localStorage.removeItem(NAME_KEY);
}
