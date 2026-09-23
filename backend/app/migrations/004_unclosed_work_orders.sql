DROP INDEX uq_open_device_reason;

CREATE UNIQUE INDEX uq_open_device_reason ON work_orders (device_id, reason_code) WHERE status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED');
