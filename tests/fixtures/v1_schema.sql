CREATE TABLE devices (
	device_id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	latest_telemetry_id INTEGER, 
	last_live_received_at VARCHAR(27), 
	PRIMARY KEY (device_id), 
	FOREIGN KEY(latest_telemetry_id) REFERENCES telemetry (id)
);

CREATE TABLE telemetry (
	id INTEGER NOT NULL, 
	message_id VARCHAR NOT NULL, 
	device_id VARCHAR NOT NULL, 
	boot_id VARCHAR NOT NULL, 
	seq INTEGER NOT NULL, 
	schema_version INTEGER NOT NULL, 
	ts VARCHAR(27) NOT NULL, 
	received_at VARCHAR(27) NOT NULL, 
	temperature_c FLOAT NOT NULL, 
	voltage_v FLOAT NOT NULL, 
	current_a FLOAT NOT NULL, 
	power_kw FLOAT NOT NULL, 
	operating_state VARCHAR NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (device_id, boot_id, seq), 
	UNIQUE (message_id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE INDEX ix_telemetry_device_ts ON telemetry (device_id, ts);

CREATE TABLE scenario_commands (
	command_id VARCHAR NOT NULL, 
	device_id VARCHAR NOT NULL, 
	scenario VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	requested_at VARCHAR(27) NOT NULL, 
	ack_at VARCHAR(27), 
	error VARCHAR, 
	late_ack_json JSON, 
	PRIMARY KEY (command_id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id)
);

CREATE TABLE agent_runs (
	run_id VARCHAR NOT NULL, 
	request_id VARCHAR NOT NULL, 
	request_hash VARCHAR NOT NULL, 
	question TEXT NOT NULL, 
	allow_work_order BOOLEAN NOT NULL, 
	status VARCHAR NOT NULL, 
	answer TEXT, 
	created_at VARCHAR(27) NOT NULL, 
	finished_at VARCHAR(27), 
	error_code VARCHAR, 
	messages_json JSON NOT NULL, 
	model_metrics_json JSON NOT NULL, 
	PRIMARY KEY (run_id), 
	UNIQUE (request_id)
);

CREATE TABLE tool_calls (
	tool_call_id VARCHAR NOT NULL, 
	provider_call_id VARCHAR NOT NULL, 
	ordinal INTEGER NOT NULL, 
	run_id VARCHAR NOT NULL, 
	tool_name VARCHAR NOT NULL, 
	args_json JSON NOT NULL, 
	result_json JSON, 
	status VARCHAR NOT NULL, 
	started_at VARCHAR(27) NOT NULL, 
	duration_ms FLOAT, 
	error_code VARCHAR, 
	PRIMARY KEY (tool_call_id), 
	FOREIGN KEY(run_id) REFERENCES agent_runs (run_id)
);

CREATE INDEX ix_tool_calls_run_id ON tool_calls (run_id);

CREATE TABLE work_orders (
	order_id VARCHAR NOT NULL, 
	device_id VARCHAR NOT NULL, 
	reason_code VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	evidence_json JSON NOT NULL, 
	created_from_run_id VARCHAR NOT NULL, 
	created_at VARCHAR(27) NOT NULL, 
	PRIMARY KEY (order_id), 
	FOREIGN KEY(device_id) REFERENCES devices (device_id), 
	FOREIGN KEY(created_from_run_id) REFERENCES agent_runs (run_id)
);

CREATE UNIQUE INDEX uq_open_device_reason ON work_orders (device_id, reason_code) WHERE status = 'OPEN';

CREATE TABLE diagnostic_events (
	id INTEGER NOT NULL, 
	event_type VARCHAR NOT NULL, 
	device_id VARCHAR, 
	received_at VARCHAR(27) NOT NULL, 
	summary VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);
