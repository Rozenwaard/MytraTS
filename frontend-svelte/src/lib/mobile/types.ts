// Типы мобильного контура РКС (/api/m/1/*).

export interface MobileDictItem {
	code: string;
	title: string;
	norm?: number;
	kind?: string | null;
}

export interface MobileDicts {
	act_type: MobileDictItem[];
	additional_work: MobileDictItem[];
	return_reason: MobileDictItem[];
	violation_group: MobileDictItem[];
}

export interface MobileTask {
	task_number: string;
	work_type: string;
	task_type: string | null;
	phase: string | null;
	due_date: string | null;
	status: string;
	subscriber_name: string | null;
	address: string | null;
	meter_serial: string | null;
	meter_model: string | null;
	contract_number: string | null;
	fl_yul: string | null;
	phone: string | null;
	last_result: string | null;
	nedopusk_count: number;
	letter_number: string | null;
	note: string | null;
	norm: number;
}

export interface SyncResponse {
	tasks: MobileTask[];
	dicts: MobileDicts;
	alcor: number;
	models: { model: string; phase: string }[];
	base_works: { short: string; norm: number }[];
}

export interface EnrollResponse {
	token: string;
	user: { full_name: string; staff_id: string };
}
