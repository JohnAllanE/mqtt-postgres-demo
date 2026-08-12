const sensorIdInput = document.getElementById('sensorId');
const loadButton = document.getElementById('loadBtn');
const statusEl = document.getElementById('status');
const commandStatusEl = document.getElementById('commandStatus');
const gatewayStatusEl = document.getElementById('gatewayStatus');
const lastAckEl = document.getElementById('lastAck');
const eventLogEl = document.getElementById('eventLog');

const globalFreqInput = document.getElementById('globalFreq');
const setGlobalBtn = document.getElementById('setGlobalBtn');
const monitorEnabledInput = document.getElementById('monitorEnabled');
const monitorFreqInput = document.getElementById('monitorFreq');
const setMonitorBtn = document.getElementById('setMonitorBtn');
const refreshStatusBtn = document.getElementById('refreshStatusBtn');
const resetBtn = document.getElementById('resetBtn');
const thermostatSensorIdInput = document.getElementById('thermostatSensorId');
const setpointInput = document.getElementById('setpointInput');
const setpointSlider = document.getElementById('setpointSlider');
const setThermostatBtn = document.getElementById('setThermostatBtn');
const thermostatStatusEl = document.getElementById('thermostatStatus');
const autoRefreshReadingsInput = document.getElementById('autoRefreshReadings');
const clearHistoryBtn = document.getElementById('clearHistoryBtn');
const monitorSamplesEl = document.getElementById('monitorSamples');
const monitorStatusEl = document.getElementById('monitorStatus');

let chart;
let monitorChart;
let readingsRefreshTimer = null;
const MONITOR_POINTS_LIMIT = 240;

function appendEventLog(text) {
  const row = document.createElement('div');
  row.textContent = `${new Date().toLocaleTimeString()}  ${text}`;
  eventLogEl.prepend(row);
  while (eventLogEl.children.length > 60) {
    eventLogEl.removeChild(eventLogEl.lastChild);
  }
}

function ensureChart() {
  if (chart) {
    return chart;
  }

  const ctx = document.getElementById('sensorChart');
  chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'condenser_temp_f', data: [], borderWidth: 2 },
        { label: 'evaporator_temp_f', data: [], borderWidth: 2 },
        { label: 'high_side_psi', data: [], borderWidth: 2 },
        { label: 'low_side_psi', data: [], borderWidth: 2 },
      ],
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { maxTicksLimit: 8 } },
      },
    },
  });

  return chart;
}

function ensureMonitorChart() {
  if (monitorChart) {
    return monitorChart;
  }

  const ctx = document.getElementById('monitorChart');
  monitorChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: [],
      datasets: [
        { label: 'monitor.condenser_temp_f', data: [], borderWidth: 2 },
        { label: 'monitor.evaporator_temp_f', data: [], borderWidth: 2 },
        { label: 'monitor.high_side_psi', data: [], borderWidth: 2 },
        { label: 'monitor.low_side_psi', data: [], borderWidth: 2 },
      ],
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { ticks: { maxTicksLimit: 8 } },
      },
    },
  });

  return monitorChart;
}

async function loadReadings() {
  const sensorId = sensorIdInput.value.trim() || 'ac-1';
  statusEl.textContent = 'Loading...';

  try {
    const response = await fetch(`/api/v1/readings?sensor_id=${encodeURIComponent(sensorId)}&limit=200`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    const rows = payload.rows || [];

    const labels = rows.map((r) => new Date(r.sample_ts).toLocaleTimeString());
    const c = ensureChart();

    c.data.labels = labels;
    for (let i = 0; i < 4; i += 1) {
      c.data.datasets[i].data = rows.map((r) => (Array.isArray(r.values) ? r.values[i] : null));
    }
    c.update();

    statusEl.textContent = `Refreshed ${rows.length} historical rows for ${sensorId}`;
  } catch (err) {
    statusEl.textContent = `Load failed: ${err.message}`;
  }
}

function clearChart() {
  const c = ensureChart();
  c.data.labels = [];
  for (let i = 0; i < c.data.datasets.length; i += 1) {
    c.data.datasets[i].data = [];
  }
  c.update();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }
  return response.json();
}

async function sendGlobalConfig() {
  try {
    const freq = Number(globalFreqInput.value || '1.0');
    const payload = { sensor_ids: ['ac-1'], freq_hz: freq, batch_window_ms: 1000 };
    const result = await postJson('/api/v1/gateway/config/global', payload);
    commandStatusEl.textContent = `Global config command accepted: ${result.cmd_id}`;
    appendEventLog(`Sent global config cmd_id=${result.cmd_id}`);
  } catch (err) {
    commandStatusEl.textContent = `Global config failed: ${err.message}`;
  }
}

async function sendMonitorConfig() {
  try {
    const payload = {
      enabled: monitorEnabledInput.checked,
      sensor_ids: ['ac-1'],
      freq_hz: Number(monitorFreqInput.value || '10.0'),
      batch_window_ms: 500,
    };
    const result = await postJson('/api/v1/gateway/config/monitor', payload);
    commandStatusEl.textContent = `Monitor config command accepted: ${result.cmd_id}`;
    appendEventLog(`Sent monitor config cmd_id=${result.cmd_id}`);
  } catch (err) {
    commandStatusEl.textContent = `Monitor config failed: ${err.message}`;
  }
}

async function requestStatus() {
  try {
    const result = await postJson('/api/v1/sensors/refresh-status', {});
    commandStatusEl.textContent = `Status request sent: ${result.cmd_id}`;
    appendEventLog(`Sent status request cmd_id=${result.cmd_id}`);
  } catch (err) {
    commandStatusEl.textContent = `Status request failed: ${err.message}`;
  }
}

async function resetGateway() {
  try {
    const result = await postJson('/api/v1/gateway/reset', { clear_monitor: true, restore_defaults: true });
    commandStatusEl.textContent = `Gateway reset command sent: ${result.cmd_id}`;
    appendEventLog(`Sent reset cmd_id=${result.cmd_id}`);
  } catch (err) {
    commandStatusEl.textContent = `Reset failed: ${err.message}`;
  }
}

async function setThermostatSetpoint() {
  try {
    const payload = {
      sensor_id: (thermostatSensorIdInput.value || 'ac-1').trim() || 'ac-1',
      setpoint_f: Number(setpointInput.value || '72'),
    };
    const result = await postJson('/api/v1/gateway/config/thermostat-setpoint', payload);
    commandStatusEl.textContent = `Thermostat setpoint command accepted: ${result.cmd_id}`;
    appendEventLog(`Sent thermostat setpoint cmd_id=${result.cmd_id}`);
  } catch (err) {
    commandStatusEl.textContent = `Thermostat setpoint failed: ${err.message}`;
  }
}

async function clearHistoricalReadings() {
  try {
    const result = await postJson('/api/v1/admin/reset-readings', {});
    clearChart();
    statusEl.textContent = `Cleared historical readings. Deleted rows: ${result.deleted_rows}`;
    appendEventLog(`Cleared historical readings rows=${result.deleted_rows}`);
  } catch (err) {
    statusEl.textContent = `Clear history failed: ${err.message}`;
  }
}

function syncReadingsAutoRefresh() {
  const enabled = Boolean(autoRefreshReadingsInput.checked);
  if (enabled && readingsRefreshTimer === null) {
    readingsRefreshTimer = setInterval(loadReadings, 4000);
    appendEventLog('Historical auto-refresh enabled (4s)');
    statusEl.textContent = 'Historical auto-refresh enabled (4s)';
  } else if (!enabled && readingsRefreshTimer !== null) {
    clearInterval(readingsRefreshTimer);
    readingsRefreshTimer = null;
    appendEventLog('Historical auto-refresh disabled');
    statusEl.textContent = 'Historical auto-refresh disabled';
  }
}

function updateThermostatDisplay(thermostat) {
  if (!thermostat || typeof thermostat !== 'object') {
    return;
  }

  if (typeof thermostat.setpoint_f === 'number') {
    const numericValue = thermostat.setpoint_f.toFixed(1);
    setpointInput.value = numericValue;
    setpointSlider.value = numericValue;
  }

  const response = thermostat.response || {};
  const updatedAt = thermostat.last_set_cmd_ts || 'n/a';
  thermostatStatusEl.textContent =
    `Last setpoint ${thermostat.setpoint_f} F at ${updatedAt} ` +
    `(tau=${response.time_constant_seconds}s, max_delta=${response.max_delta_per_minute} F/min)`;
}

function pushMonitorSamplesToChart(payloadData) {
  const samples = Array.isArray(payloadData?.samples) ? payloadData.samples : [];
  if (samples.length === 0) {
    return 0;
  }

  const c = ensureMonitorChart();
  let appended = 0;
  for (const sample of samples) {
    if (!Array.isArray(sample?.values) || sample.values.length < 4) {
      continue;
    }

    const label = sample.sample_ts ? new Date(sample.sample_ts).toLocaleTimeString() : new Date().toLocaleTimeString();
    c.data.labels.push(label);
    for (let i = 0; i < 4; i += 1) {
      c.data.datasets[i].data.push(sample.values[i]);
    }

    while (c.data.labels.length > MONITOR_POINTS_LIMIT) {
      c.data.labels.shift();
      for (let i = 0; i < 4; i += 1) {
        c.data.datasets[i].data.shift();
      }
    }
    appended += 1;
  }

  if (appended > 0) {
    c.update();
  }
  return appended;
}

function connectWebSocket() {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws`);

  ws.onopen = () => appendEventLog('WebSocket connected');
  ws.onclose = () => {
    appendEventLog('WebSocket disconnected; retrying');
    setTimeout(connectWebSocket, 2000);
  };
  ws.onerror = () => appendEventLog('WebSocket error');

  ws.onmessage = (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      return;
    }

    const eventType = payload.event;
    if (eventType === 'status_update') {
      gatewayStatusEl.textContent = JSON.stringify(payload.data, null, 2);
      updateThermostatDisplay(payload.data.thermostat);
      appendEventLog('Received status_update');
    } else if (eventType === 'command_ack') {
      lastAckEl.textContent = JSON.stringify(payload.data, null, 2);
      appendEventLog(`Received command_ack cmd_id=${payload.data.cmd_id} ok=${payload.data.ok}`);
    } else if (eventType === 'monitor_samples') {
      const samples = Array.isArray(payload.data?.samples) ? payload.data.samples : [];
      monitorSamplesEl.textContent = JSON.stringify(payload.data, null, 2);
      const plotted = pushMonitorSamplesToChart(payload.data);
      monitorStatusEl.textContent = `Latest monitor batch: ${samples.length} sample(s) at ${new Date().toLocaleTimeString()}`;
      appendEventLog(`Received monitor_samples count=${samples.length} plotted=${plotted}`);
    } else if (eventType === 'connection_update') {
      appendEventLog(`MQTT connection: ${JSON.stringify(payload.data)}`);
    }
  };
}

loadButton.addEventListener('click', loadReadings);
setGlobalBtn.addEventListener('click', sendGlobalConfig);
setMonitorBtn.addEventListener('click', sendMonitorConfig);
refreshStatusBtn.addEventListener('click', requestStatus);
resetBtn.addEventListener('click', resetGateway);
setThermostatBtn.addEventListener('click', setThermostatSetpoint);
clearHistoryBtn.addEventListener('click', clearHistoricalReadings);
autoRefreshReadingsInput.addEventListener('change', syncReadingsAutoRefresh);
setpointInput.addEventListener('input', () => {
  setpointSlider.value = setpointInput.value;
});
setpointSlider.addEventListener('input', () => {
  setpointInput.value = setpointSlider.value;
});

connectWebSocket();
loadReadings();
ensureMonitorChart();
