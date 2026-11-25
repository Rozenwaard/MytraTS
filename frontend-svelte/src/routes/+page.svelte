<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { Capacitor } from '@capacitor/core';

	onMount(() => {
		// В нативном Capacitor-приложении (MytraGo) — сразу мобильный вход.
		// В браузере — бэкофис (дашборд).
		if (Capacitor.isNativePlatform()) {
			goto('/m/login');
		} else {
			goto('/dashboard');
		}
	});
</script>

