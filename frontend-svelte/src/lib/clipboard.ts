export async function copyText(text: string): Promise<void> {
	// Clipboard API доступен только в secure-контексте (HTTPS или localhost).
	if (navigator.clipboard && window.isSecureContext) {
		await navigator.clipboard.writeText(text);
		return;
	}

	// Fallback для небезопасных origin (например, HTTP по LAN-IP).
	const el = document.createElement('textarea');
	el.value = text;
	el.style.position = 'fixed';
	el.style.opacity = '0';
	document.body.appendChild(el);
	el.focus();
	el.select();
	try {
		const ok = document.execCommand('copy');
		if (!ok) throw new Error("execCommand('copy') failed");
	} finally {
		document.body.removeChild(el);
	}
}
