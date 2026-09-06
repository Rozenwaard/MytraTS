export const toasts = $state<{ id: number; text: string }[]>([]);

let nextId = 0;

export function toast(text: string) {
	const id = ++nextId;
	toasts.push({ id, text });
	setTimeout(() => {
		const idx = toasts.findIndex((t) => t.id === id);
		if (idx !== -1) toasts.splice(idx, 1);
	}, 3000);
}
