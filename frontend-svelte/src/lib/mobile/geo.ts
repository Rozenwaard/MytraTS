export interface GeoResult {
	lat: number;
	lng: number;
	satellites: number | null;
	is_mock: number;
}

// Геопозиция. В браузере число спутников недоступно → null (в Capacitor заполним нативно).
export function getPosition(): Promise<GeoResult | null> {
	return new Promise((resolve) => {
		if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
			resolve(null);
			return;
		}
		navigator.geolocation.getCurrentPosition(
			(pos) =>
				resolve({
					lat: +pos.coords.latitude.toFixed(7),
					lng: +pos.coords.longitude.toFixed(7),
					satellites: null,
					is_mock: 0
				}),
			() => resolve(null),
			{ enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
		);
	});
}
