import { latLngToCell } from 'h3-js';

export interface GeoResult {
	lat: number;
	lng: number;
	h3_res12: string;
	satellites: number | null;
	is_mock: number;
}

// Геопозиция + h3 (res12). В браузере число спутников недоступно → null (в Capacitor заполним нативно).
export function getPosition(): Promise<GeoResult | null> {
	return new Promise((resolve) => {
		if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
			resolve(null);
			return;
		}
		navigator.geolocation.getCurrentPosition(
			(pos) => {
				const lat = +pos.coords.latitude.toFixed(7);
				const lng = +pos.coords.longitude.toFixed(7);
				let h3_res12 = '';
				try {
					h3_res12 = latLngToCell(lat, lng, 12);
				} catch {
					/* невалидные координаты */
				}
				resolve({ lat, lng, h3_res12, satellites: null, is_mock: 0 });
			},
			() => resolve(null),
			{ enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
		);
	});
}

