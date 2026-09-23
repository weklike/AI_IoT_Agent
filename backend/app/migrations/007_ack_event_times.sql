ALTER TABLE scenario_commands ADD COLUMN ack_received_at VARCHAR(27);
ALTER TABLE scenario_commands ADD COLUMN late_ack_observed_at VARCHAR(27);
ALTER TABLE scenario_commands ADD COLUMN late_ack_received_at VARCHAR(27);
ALTER TABLE device_commands ADD COLUMN ack_observed_at VARCHAR(27);
ALTER TABLE device_commands ADD COLUMN late_ack_observed_at VARCHAR(27);
ALTER TABLE device_commands ADD COLUMN late_ack_received_at VARCHAR(27);
