export interface NavItem {
	href: string;
	label: string;
}

export interface SubTab {
	href: string;
	label: string;
}

export const TOP_NAV: NavItem[] = [
	{ href: '/dashboard', label: 'Дашборд' },
	{ href: '/main-afl', label: 'Реестры' },
	{ href: '/reports', label: 'Отчёты' },
	{ href: '/archive', label: 'Архив' },
	{ href: '/admin', label: 'Админ' },
	{ href: '/help', label: 'Помощь' },
	{ href: '/ulr', label: 'УЛР' }
];

export const SUB_NAV: Record<string, SubTab[]> = {
	'/dashboard': [
		{ href: '/dashboard', label: 'Обзор' },
		{ href: '/dashboard/in-work', label: 'В работе' },
		{ href: '/dashboard/priorities', label: 'Приоритеты' }
	],
	'/main-afl': [
		{ href: '/main-afl/upload', label: 'Загрузка' },
		{ href: '/main-afl', label: 'Обзор' },
		{ href: '/main-afl/list', label: 'Список' }
	],
	'/ulr': [
		{ href: '/ulr', label: 'Регистрация' },
		{ href: '/ulr/execution', label: 'Выполнение' }
	],
	'/reports': [
		{ href: '/reports', label: 'Финотчёт' },
		{ href: '/reports/premium', label: 'Премия' },
		{ href: '/reports/rle', label: 'РЛЭ' },
		{ href: '/reports/sla', label: 'СЛА' }
	],
	'/admin': [
		{ href: '/admin', label: 'Пользователи' },
		{ href: '/admin/quarantine', label: 'Карантин' }
	],
	'/help': [
		{ href: '/help', label: 'Инструкция' },
		{ href: '/help/tariffs', label: 'Тарифы' },
		{ href: '/help/task-report', label: 'Отчёт по заданию' },
		{ href: '/help/operators', label: 'Операторы' },
		{ href: '/help/questions', label: 'Вопросы' }
	]
};
