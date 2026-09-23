ALTER TABLE alarm_rules ADD COLUMN observation_json JSON;

ALTER TABLE alarms ADD COLUMN observation_json JSON;
