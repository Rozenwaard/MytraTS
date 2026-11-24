// Capacitor — нативный shell для мобильного контура РКС (/m/*).
// Установка (на машине с Android Studio):
//   bun add @capacitor/core @capacitor/cli
//   bun add -D @capacitor/android
//   bun add @capacitor/geolocation @capacitor/camera @capacitor/preferences
//   npx cap add android && npx cap sync
// В dev Capacitor грузит веб с dev-сервера (раскомментируй server.url под свой IP).
const config = {
	appId: 'ru.mytra.rks',
	appName: 'MytraGo',
	webDir: 'build',
	// server: { url: 'http://192.168.1.10:5174', cleartext: true },
	plugins: {
		CapacitorGeolocation: {},
		CapacitorCamera: {},
		CapacitorPreferences: {}
	}
};

export default config;
