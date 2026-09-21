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
	{ href: '/upload', label: 'Загрузка' },
	{ href: '/reports', label: 'Отчёты' },
	{ href: '/admin', label: 'Админ' },
	{ href: '/help', label: 'Помощь' }
];

export const SUB_NAV: Record<string, SubTab[]> = {
	'/dashboard': [
		{ href: '/dashboard', label: 'Обзор' },
		{ href: '/dashboard/priorities', label: 'Приоритеты' }
	],
	'/main-afl': [
		{ href: '/main-afl', label: 'Обзор' },
		{ href: '/main-afl/list', label: 'Список' }
	],
	'/reports': [
		{ href: '/reports', label: 'Финотчёт' },
		{ href: '/reports/premium', label: 'Премия' },
		{ href: '/reports/rle', label: 'РЛЭ' }
	],
	'/admin': [
		{ href: '/admin', label: 'Пользователи' },
		{ href: '/admin/quarantine', label: 'Карантин' }
	],
	'/help': [
		{ href: '/help', label: 'Инструкция' },
		{ href: '/help/tariffs', label: 'Тарифы' },
		{ href: '/help/task-report', label: 'Отчёт по заданию' },
		{ href: '/help/operators', label: 'Операторы' }
	]
};
