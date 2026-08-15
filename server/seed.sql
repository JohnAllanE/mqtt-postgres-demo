-- Seed two equipment types: one with 6 sensors, one with 4 sensors
INSERT INTO equipment_type (name, sensor_count) VALUES ('group-6', 6) ON CONFLICT DO NOTHING;
INSERT INTO equipment_type (name, sensor_count) VALUES ('group-4', 4) ON CONFLICT DO NOTHING;
