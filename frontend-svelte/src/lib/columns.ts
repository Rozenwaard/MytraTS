import type { MainAflRow } from '$lib/api/main-afl';

export interface ColumnMeta {
	key: keyof MainAflRow;
	header: string;
}

// 11 видимых колонок (из настроек пользователя staff_id=660).
export const VISIBLE_COLUMNS: ColumnMeta[] = [
	{ key: 'task_number', header: 'Номер задания' },
	{ key: 'work_type_in_task', header: 'Поручение' },
	{ key: 'personal_account', header: 'Точка учёта' },
	{ key: 'address', header: 'Адрес' },
	{ key: 'customer', header: 'Заказчик' },
	{ key: 'executor', header: 'Исполнитель' },
	{ key: 'task_report', header: 'Вид работ' },
	{ key: 'done_day', header: 'Дата' },
	{ key: 'reestr_number', header: 'Реестр' },
	{ key: 'errors', header: 'Ошибки' },
	{ key: 'norm', header: 'Норматив' }
];

// Оставшиеся 14 колонок — показываются при раскрытии строки (левый клик).
export const EXPAND_COLUMNS: ColumnMeta[] = [
	{ key: 'task_source', header: 'Источник' },
	{ key: 'task_type', header: 'Вид задания' },
	{ key: 'subscriber_name', header: 'Потребитель' },
	{ key: 'municipal_district', header: 'Район' },
	{ key: 'house_type', header: 'Тип дома' },
	{ key: 'service_object_type', header: 'Объект' },
	{ key: 'meter_installation_place', header: 'Место ПУ' },
	{ key: 'meter_status', header: 'Статус' },
	{ key: 'meter_ownership', header: 'Принадлежность' },
	{ key: 'violations', header: 'Нарушения' },
	{ key: 'comment', header: 'Комментарий' },
	{ key: 'visit_reason', header: 'Основание' },
	{ key: 'task_output', header: 'Результат' },
	{ key: 'grid', header: 'Сеть' }
];
