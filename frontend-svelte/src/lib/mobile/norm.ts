// Поручение → конкретная работа (short) — зеркало services/rks.py resolve_short().
const PORUCHENIE_TO_SHORT: Record<string, string | Record<string, string>> = {
	'Проверка': { плановый: 'Массовое КСП', текущий: 'Штучное КСП' },
	'Инструментальная проверка': { '1ф': 'Инструментальная проверка 1ф', '3ф': 'Инструментальная проверка 3ф' },
	'Чтение архива': 'Чтение архива РЛЭ',
	'Привязка': { КЛ: 'Привязка КЛ', ВЛ: 'Привязка ВЛ' },
	'Идентификация': 'Идентификация',
	'Допуск ПУ': { '1ф': 'Допуск ПУ 1ф', '3ф': 'Допуск ПУ 3ф' },
	'Проверка РО': 'Проверка РО РЛЭ'
};

export function resolveShort(poruchenie: string, taskType?: string | null, phase?: string | null): string {
	const m = PORUCHENIE_TO_SHORT[poruchenie];
	if (!m) return poruchenie;
	if (typeof m === 'string') return m;
	if (poruchenie === 'Проверка') {
		return m[taskType === 'Плановый' ? 'плановый' : 'текущий'] ?? 'Штучное КСП';
	}
	if (poruchenie === 'Привязка') {
		return m['ВЛ'];
	}
	return m[phase ?? '1ф'] ?? m['1ф'];
}
