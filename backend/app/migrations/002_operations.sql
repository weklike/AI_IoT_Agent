ALTER TABLE devices ADD COLUMN rated_power_w INTEGER NOT NULL DEFAULT 20000;

ALTER TABLE devices ADD COLUMN command_generation INTEGER NOT NULL DEFAULT 0;

ALTER TABLE devices ADD COLUMN model VARCHAR NOT NULL DEFAULT 'SIM-CHG-V2';

ALTER TABLE telemetry ADD COLUMN session_id VARCHAR;

ALTER TABLE telemetry ADD COLUMN session_state VARCHAR;

ALTER TABLE telemetry ADD COLUMN requested_power_w INTEGER;

ALTER TABLE telemetry ADD COLUMN power_limit_w INTEGER;

ALTER TABLE telemetry ADD COLUMN meter_total_wh INTEGER;

ALTER TABLE telemetry ADD COLUMN session_energy_wh INTEGER;

ALTER TABLE telemetry ADD COLUMN applied_control_generation INTEGER;

ALTER TABLE agent_runs ADD COLUMN kind VARCHAR NOT NULL DEFAULT 'chat';

ALTER TABLE agent_runs ADD COLUMN answer_refs JSON;

ALTER TABLE work_orders ADD COLUMN version INTEGER NOT NULL DEFAULT 1;

ALTER TABLE work_orders ADD COLUMN closed_at VARCHAR(27);

ALTER TABLE work_orders ADD COLUMN alarm_id VARCHAR REFERENCES alarms(alarm_id);

CREATE TABLE operation_requests (
	request_id VARCHAR NOT NULL, 
	request_hash VARCHAR NOT NULL, 
	route VARCHAR NOT NULL, 
	action VARCHAR NOT NULL, 
	result_json JSON NOT NULL, 
	created_at VARCHAR(27) NOT NULL, 
	PRIMARY KEY (request_id)
);

CREATE TABLE device_commands (
	command_id VARCHAR NOT NULL, 
	device_id VARCHAR NOT NULL, 
	generation INTEGER NOT NULL, 
	action VARCHAR NOT NULL, 
	args_json JSON NOT NULL, 
	status VARCHAR NOT NULL, 
	issued_at VARCHAR(27) NOT NULL, 
	expires_at VARCHAR(27) NOT NULL, 
	ack_at VARCHAR(27), 
	ack_json JSON, 
	late_ack_json JSON, 
	verification_status VARCHAR NOT NULL, 
	verification_json JSON, 
	error_code VARCHAR, 
	PRIMARY KEY (command_id), 
	UNIQUE (device_id, generation), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE TABLE charging_sessions (
	session_id VARCHAR NOT NULL, 
	device_id VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	requested_power_w INTEGER NOT NULL, 
	started_at VARCHAR(27), 
	observed_at VARCHAR(27), 
	ended_at VARCHAR(27), 
	start_meter_wh INTEGER, 
	end_meter_wh INTEGER, 
	energy_wh INTEGER, 
	meter_quality VARCHAR, 
	end_reason VARCHAR, 
	report_seq INTEGER NOT NULL, 
	PRIMARY KEY (session_id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE UNIQUE INDEX uq_active_device_session ON charging_sessions (device_id) WHERE status = 'ACTIVE';

CREATE TABLE session_reports (
	report_id VARCHAR NOT NULL, 
	session_id VARCHAR NOT NULL, 
	report_seq INTEGER NOT NULL, 
	payload_json JSON NOT NULL, 
	observed_at VARCHAR(27) NOT NULL, 
	received_at VARCHAR(27) NOT NULL, 
	PRIMARY KEY (report_id), 
	UNIQUE (session_id, report_seq), 
	FOREIGN KEY(session_id) REFERENCES charging_sessions (session_id)
);

CREATE TABLE scenario_scripts (
	script_id VARCHAR NOT NULL, 
	device_id VARCHAR NOT NULL, 
	script_name VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	created_at VARCHAR(27) NOT NULL, 
	steps_json JSON NOT NULL, 
	cancel_reason VARCHAR, 
	PRIMARY KEY (script_id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE UNIQUE INDEX uq_running_device_script ON scenario_scripts (device_id) WHERE status = 'running';

CREATE TABLE station_state (
	id INTEGER NOT NULL, 
	budget_w INTEGER NOT NULL, 
	revision INTEGER NOT NULL, 
	executing_plan_id VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(executing_plan_id) REFERENCES power_plans (plan_id)
);

CREATE TABLE power_plans (
	plan_id VARCHAR NOT NULL, 
	strategy VARCHAR NOT NULL, 
	budget_w INTEGER NOT NULL, 
	station_revision INTEGER NOT NULL, 
	snapshot_json JSON NOT NULL, 
	allocation_json JSON NOT NULL, 
	results_json JSON NOT NULL, 
	status VARCHAR NOT NULL, 
	created_at VARCHAR(27) NOT NULL, 
	finished_at VARCHAR(27), 
	PRIMARY KEY (plan_id)
);

CREATE TABLE alarm_rules (
	device_id VARCHAR NOT NULL, 
	reason_code VARCHAR NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	version INTEGER NOT NULL, 
	trigger_duration_seconds INTEGER NOT NULL, 
	clear_below_c FLOAT NOT NULL, 
	clear_duration_seconds INTEGER NOT NULL, 
	updated_at VARCHAR(27) NOT NULL, 
	PRIMARY KEY (device_id, reason_code), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE TABLE alarms (
	alarm_id VARCHAR NOT NULL, 
	device_id VARCHAR NOT NULL, 
	reason_code VARCHAR NOT NULL, 
	condition VARCHAR NOT NULL, 
	version INTEGER NOT NULL, 
	acknowledged_at VARCHAR(27), 
	evaluation_state VARCHAR NOT NULL, 
	peak_temperature_c FLOAT, 
	started_at VARCHAR(27) NOT NULL, 
	observed_at VARCHAR(27) NOT NULL, 
	cleared_at VARCHAR(27), 
	rule_json JSON NOT NULL, 
	evidence_json JSON NOT NULL, 
	PRIMARY KEY (alarm_id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE UNIQUE INDEX uq_active_device_alarm ON alarms (device_id, reason_code) WHERE condition = 'ACTIVE';

CREATE TABLE alarm_events (
	event_id VARCHAR NOT NULL, 
	alarm_id VARCHAR, 
	device_id VARCHAR NOT NULL, 
	event_type VARCHAR NOT NULL, 
	observed_at VARCHAR(27) NOT NULL, 
	received_at VARCHAR(27) NOT NULL, 
	evidence_json JSON NOT NULL, 
	PRIMARY KEY (event_id), 
	FOREIGN KEY(alarm_id) REFERENCES alarms (alarm_id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE TABLE work_order_events (
	event_id VARCHAR NOT NULL, 
	order_id VARCHAR NOT NULL, 
	request_id VARCHAR NOT NULL, 
	from_status VARCHAR NOT NULL, 
	to_status VARCHAR NOT NULL, 
	note TEXT NOT NULL, 
	checked_at VARCHAR(27) NOT NULL, 
	evidence_json JSON NOT NULL, 
	PRIMARY KEY (event_id), 
	FOREIGN KEY(order_id) REFERENCES work_orders (order_id), 
	FOREIGN KEY(request_id) REFERENCES operation_requests (request_id)
);

CREATE TABLE knowledge_documents (
	id INTEGER NOT NULL, 
	source_id VARCHAR NOT NULL, 
	version VARCHAR NOT NULL, 
	title VARCHAR NOT NULL, 
	category VARCHAR NOT NULL, 
	applicable_model VARCHAR NOT NULL, 
	source_kind VARCHAR NOT NULL, 
	source_url VARCHAR, 
	license_note VARCHAR NOT NULL, 
	content_hash VARCHAR NOT NULL, 
	content TEXT NOT NULL, 
	current BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (source_id, version)
);

CREATE TABLE knowledge_chunks (
	id INTEGER NOT NULL, 
	chunk_id VARCHAR NOT NULL, 
	document_id INTEGER NOT NULL, 
	heading VARCHAR NOT NULL, 
	content TEXT NOT NULL, 
	search_text TEXT NOT NULL, 
	content_hash VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (chunk_id), 
	FOREIGN KEY(document_id) REFERENCES knowledge_documents (id)
);

CREATE TABLE patrol_schedules (
	id INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	interval_seconds INTEGER NOT NULL, 
	window_minutes INTEGER NOT NULL, 
	next_due_at VARCHAR(27), 
	version INTEGER NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE patrol_reports (
	report_id VARCHAR NOT NULL, 
	schedule_id INTEGER, 
	due_at VARCHAR(27), 
	request_id VARCHAR, 
	run_id VARCHAR, 
	"trigger" VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	snapshot_json JSON, 
	refs_json JSON, 
	created_at VARCHAR(27) NOT NULL, 
	PRIMARY KEY (report_id), 
	UNIQUE (schedule_id, due_at), 
	FOREIGN KEY(schedule_id) REFERENCES patrol_schedules (id), 
	UNIQUE (request_id), 
	FOREIGN KEY(run_id) REFERENCES agent_runs (run_id)
);

CREATE VIRTUAL TABLE knowledge_fts USING fts5(title, tags, body, tokenize='unicode61');

INSERT INTO station_state(id,budget_w,revision) VALUES (1,60000,1);

INSERT INTO patrol_schedules(id,enabled,interval_seconds,window_minutes,version) VALUES (1,0,1800,30,1);
