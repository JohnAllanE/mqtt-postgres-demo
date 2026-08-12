insert into sensor_type_schema(type_id, display_name, field_names, field_units, value_count)
values
  ('ac_unit_v1', 'Air Conditioner', array['condenser_temp_f','evaporator_temp_f','high_side_psi','low_side_psi'], array['F','F','psi','psi'], 4),
  ('env_quality_v1', 'Environmental Quality', array['temp_f','humidity_pct','air_quality_ppm'], array['F','pct','ppm'], 3),
  ('pump_v1', 'Pump', array['rpm','vibration_mm_s'], array['rpm','mm/s'], 2)
on conflict (type_id) do nothing;

insert into sensor_registry(sensor_id, type_id, display_name, location, active)
values
  ('ac-1', 'ac_unit_v1', 'AC Unit 1', 'Lab A', true),
  ('env-1', 'env_quality_v1', 'Env Sensor 1', 'Lab A', true),
  ('pump-1', 'pump_v1', 'Pump 1', 'Lab B', true)
on conflict (sensor_id) do nothing;
