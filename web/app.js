const NUM_SENSORS = 4;
const API_BASE = `${location.protocol}//${location.hostname}:8080`;

const CHART_CONFIG = {
  phase1: {
    maxPoints: 60,
    windowSeconds: 5,
    height: '4cm',
    yMin: -2.5,
    yMax: 2.5,
  },
  logged: {
    maxPoints: 100,
    windowSeconds: 30,
    height: '8cm',
    yMin: -2.5,
    yMax: 2.5,
  },
  maintenance: {
    maxPoints: 150,
    windowSeconds: 30,
    height: '10cm',
    yMin: -2.5,
    yMax: 2.5,
  },
};
const DB_SNAPSHOT_LIMIT = 20;

const charts = [];
const TOPIC_PANEL_IDS = {
  'sensors/broadcast': 'topic-broadcast',
  'sensors/maintenance': 'topic-maintenance',
  'sensors/config': 'topic-config',
};

function formatTopicMessage(topic, payload) {
  const ts = new Date().toLocaleTimeString();
  const pretty = typeof payload === 'string' ? payload : JSON.stringify(payload, null, 2);
  return `[${ts}] ${topic}\n${pretty}`;
}

function updateTopicPanel(topic, payload) {
  const panelId = TOPIC_PANEL_IDS[topic];
  if (!panelId) return;
  const panel = document.getElementById(panelId);
  if (!panel) return;
  panel.textContent = formatTopicMessage(topic, payload);
}

function setChartWindow(chart, latestTs, windowSeconds) {
  if (!latestTs) return;
  const latestMs = latestTs.getTime ? latestTs.getTime() : latestTs;
  chart.options.scales.x.min = latestMs - (windowSeconds * 1000);
  chart.options.scales.x.max = latestMs;
}

function clearChartWindow(chart) {
  delete chart.options.scales.x.min;
  delete chart.options.scales.x.max;
}

function makeChart(ctx, label, settings) {
  return new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [{
        label,
        data: [],
        borderColor: 'rgba(33,150,243,1)',
        borderWidth: 1,
        pointRadius: 0,
      }],
    },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      scales: {
        x: {
          type: 'linear',
          display: false,
          ticks: {
            callback: (value) => new Date(Number(value)).toLocaleTimeString(),
            maxRotation: 0,
          },
        },
        y: { display: true, min: settings.yMin, max: settings.yMax },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function createGrid() {
  const container = document.getElementById('charts');
  container.innerHTML = '';
  for (let i = 0; i < NUM_SENSORS; i++) {
    const card = document.createElement('div');
    card.className = 'chart-card';
    card.style.height = CHART_CONFIG.phase1.height;

    const title = document.createElement('div');
    title.className = 'chart-title';
    title.textContent = `Sensor ${i}`;

    const canvas = document.createElement('canvas');

    card.appendChild(title);
    card.appendChild(canvas);
    container.appendChild(card);

    charts[i] = makeChart(canvas.getContext('2d'), `S${i}`, CHART_CONFIG.phase1);
  }
}

function pushSample(sensorId, ts, value) {
  const chart = charts[sensorId];
  if (!chart) return;
  const ds = chart.data.datasets[0];
  ds.data.push({ x: ts.getTime ? ts.getTime() : ts, y: value });
  if (ds.data.length > CHART_CONFIG.phase1.maxPoints) ds.data.shift();
  setChartWindow(chart, ts, CHART_CONFIG.phase1.windowSeconds);
  chart.update('none');
}

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const url = `${proto}://${location.hostname}:8765`;
  const ws = new WebSocket(url);
  ws.onopen = () => setStatus('WebSocket connected');
  ws.onmessage = (evt) => {
    try {
      const msg = JSON.parse(evt.data);
      if (msg.topic && Object.prototype.hasOwnProperty.call(msg, 'payload')) {
        updateTopicPanel(msg.topic, msg.payload);
        if (msg.topic === 'sensors/broadcast' && msg.payload?.type === 'broadcast' && Array.isArray(msg.payload.samples)) {
          msg.payload.samples.forEach((sample) => pushSample(sample.sensor_id, new Date(sample.ts), sample.value));
        }
        if (msg.topic === 'sensors/maintenance' && msg.payload?.type === 'maintenance' && Array.isArray(msg.payload.samples)) {
          msg.payload.samples.forEach((sample) => pushMaintenanceSample(sample.sensor_id, new Date(sample.ts), sample.value));
        }
        return;
      }
      if (msg.type === 'batch' && Array.isArray(msg.samples)) {
        msg.samples.forEach((sample) => pushSample(sample.sensor_id, new Date(sample.ts), sample.value));
      }
      if (msg.type === 'maintenance' && Array.isArray(msg.samples)) {
        msg.samples.forEach((sample) => pushMaintenanceSample(sample.sensor_id, new Date(sample.ts), sample.value));
      }
    } catch (error) {
      console.error('parse error', error);
    }
  };
  ws.onclose = () => {
    setStatus('WebSocket disconnected, retrying...');
    setTimeout(connect, 1000);
  };
}

let pollTimer = null;
let loggedChart6 = null;
let loggedChart4 = null;

function setStatus(message) {
  const status = document.getElementById('ui-status');
  if (status) {
    status.textContent = message;
  }
}

function clampInterval(value) {
  const parsed = parseFloat(value);
  if (!Number.isFinite(parsed)) {
    return 0.5;
  }
  return Math.max(0.5, parsed);
}

function clearLoggedCharts() {
  if (loggedChart6) {
    loggedChart6.data.datasets.forEach((ds) => { ds.data = []; });
    clearChartWindow(loggedChart6);
    loggedChart6.update('none');
  }
  if (loggedChart4) {
    loggedChart4.data.datasets.forEach((ds) => { ds.data = []; });
    clearChartWindow(loggedChart4);
    loggedChart4.update('none');
  }
}

function applyLoggedPollingConfig() {
  const interval = clampInterval(document.getElementById('poll-interval').value);
  document.getElementById('poll-interval').value = String(interval);
  return fetch(`${API_BASE}/api/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ broadcast_interval: interval }),
  })
    .then(async (res) => {
      const data = await res.json();
      if (!data || !data.ok) {
        throw new Error(data?.error || 'unknown error');
      }
      updateTopicPanel('sensors/config', { type: 'config', applied: data.applied || { broadcast_interval: interval } });
      startPolling(interval);
      setStatus(`Broadcast config applied: ${interval}s`);
      return data;
    })
    .catch((error) => {
      setStatus(`Broadcast config failed: ${error.message}`);
      throw error;
    });
}

function makeMultiSensorChart(ctx, sensorCount, settings) {
  const datasets = [];
  for (let i = 0; i < sensorCount; i++) {
    const hue = Math.round((i / Math.max(1, sensorCount)) * 360);
    datasets.push({
      label: `s${i}`,
      data: [],
      borderColor: `hsl(${hue} 70% 40%)`,
      pointRadius: 0,
    });
  }
  return new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      scales: {
        x: {
          type: 'linear',
          display: true,
          ticks: {
            callback: (value) => new Date(Number(value)).toLocaleTimeString(),
            maxRotation: 0,
          },
        },
        y: { display: true, min: settings.yMin, max: settings.yMax },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function renderDbSnapshot(rows) {
  const body = document.getElementById('db-snapshot-body');
  if (!body) return;

  const safeRows = Array.isArray(rows) ? rows : [];
  if (safeRows.length === 0) {
    body.innerHTML = '<tr><td colspan="3" style="padding:6px; color:#666;">No rows returned.</td></tr>';
    return;
  }

  body.innerHTML = '';
  safeRows.forEach((row) => {
    const tr = document.createElement('tr');

    const tdTs = document.createElement('td');
    tdTs.style.padding = '6px';
    tdTs.style.borderBottom = '1px solid #f0f0f0';
    tdTs.textContent = row.ts || '';

    const values = Array.isArray(row.values) ? row.values : [];

    const tdLen = document.createElement('td');
    tdLen.style.padding = '6px';
    tdLen.style.borderBottom = '1px solid #f0f0f0';
    tdLen.textContent = String(values.length);

    const tdValues = document.createElement('td');
    tdValues.style.padding = '6px';
    tdValues.style.borderBottom = '1px solid #f0f0f0';
    tdValues.textContent = `[${values.join(', ')}]`;

    tr.appendChild(tdTs);
    tr.appendChild(tdLen);
    tr.appendChild(tdValues);
    body.appendChild(tr);
  });
}

function startPolling(interval) {
  stopPolling();
  const pollIntervalSeconds = clampInterval(interval);
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/recent?limit=${DB_SNAPSHOT_LIMIT}`);
      const data = await res.json();
      updateLoggedCharts(data || []);
      renderDbSnapshot(data || []);
    } catch (error) {
      console.error('poll error', error);
    }
  }, pollIntervalSeconds * 1000);
  setStatus(`Polling every ${pollIntervalSeconds}s`);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

const maintenanceDatasetsBySensor = new Map();
let maintenanceChart = null;

function maintenanceDatasetForSensor(sensorId) {
  const existing = maintenanceDatasetsBySensor.get(sensorId);
  if (existing) {
    return existing;
  }
  const hue = Math.round((sensorId / 10) * 360);
  const dataset = {
    label: `s${sensorId}`,
    data: [],
    borderColor: `hsl(${hue} 70% 40%)`,
    pointRadius: 0,
  };
  maintenanceDatasetsBySensor.set(sensorId, dataset);
  maintenanceChart.data.datasets.push(dataset);
  return dataset;
}

function resetMaintenanceChart() {
  maintenanceDatasetsBySensor.clear();
  maintenanceChart.data.datasets = [];
  clearChartWindow(maintenanceChart);
  maintenanceChart.update('none');
}

function pushMaintenanceSample(sensorId, ts, value) {
  const dataset = maintenanceDatasetForSensor(sensorId);
  dataset.data.push({ x: ts.getTime ? ts.getTime() : ts, y: value });
  if (dataset.data.length > CHART_CONFIG.maintenance.maxPoints) dataset.data.shift();
  setChartWindow(maintenanceChart, ts, CHART_CONFIG.maintenance.windowSeconds);
  maintenanceChart.update('none');
}

function updateLoggedCharts(rows) {
  const chron = (rows || []).slice().reverse();
  const latest6 = [...chron].reverse().find((row) => Array.isArray(row.values) && row.values.length === 6);
  const latest4 = [...chron].reverse().find((row) => Array.isArray(row.values) && row.values.length === 4);

  if (loggedChart6 && latest6) {
    const latestTs = new Date(latest6.ts);
    for (let i = 0; i < 6; i++) {
      const ds = loggedChart6.data.datasets[i];
      ds.data.push({ x: latestTs.getTime(), y: latest6.values[i] });
      if (ds.data.length > CHART_CONFIG.logged.maxPoints) ds.data.shift();
    }
    setChartWindow(loggedChart6, latestTs, CHART_CONFIG.logged.windowSeconds);
    loggedChart6.update('none');
  }

  if (loggedChart4 && latest4) {
    const latestTs = new Date(latest4.ts);
    for (let i = 0; i < 4; i++) {
      const ds = loggedChart4.data.datasets[i];
      ds.data.push({ x: latestTs.getTime(), y: latest4.values[i] });
      if (ds.data.length > CHART_CONFIG.logged.maxPoints) ds.data.shift();
    }
    setChartWindow(loggedChart4, latestTs, CHART_CONFIG.logged.windowSeconds);
    loggedChart4.update('none');
  }
}

document.addEventListener('DOMContentLoaded', () => {
  createGrid();

  const logged6Card = document.getElementById('logged-6-canvas').closest('.chart-card');
  const logged4Card = document.getElementById('logged-4-canvas').closest('.chart-card');
  const maintenanceCard = document.getElementById('maintenance-canvas').closest('.chart-card');
  if (logged6Card) logged6Card.style.height = CHART_CONFIG.logged.height;
  if (logged4Card) logged4Card.style.height = CHART_CONFIG.logged.height;
  if (maintenanceCard) maintenanceCard.style.height = CHART_CONFIG.maintenance.height;

  const ctx6 = document.getElementById('logged-6-canvas').getContext('2d');
  const ctx4 = document.getElementById('logged-4-canvas').getContext('2d');
  const maintenanceCtx = document.getElementById('maintenance-canvas').getContext('2d');

  loggedChart6 = makeMultiSensorChart(ctx6, 6, CHART_CONFIG.logged);
  loggedChart4 = makeMultiSensorChart(ctx4, 4, CHART_CONFIG.logged);
  maintenanceChart = new Chart(maintenanceCtx, {
    type: 'line',
    data: { datasets: [] },
    options: {
      animation: false,
      responsive: true,
      maintainAspectRatio: false,
      parsing: false,
      scales: {
        x: {
          type: 'linear',
          display: true,
          ticks: {
            callback: (value) => new Date(Number(value)).toLocaleTimeString(),
            maxRotation: 0,
          },
        },
        y: { display: true, min: CHART_CONFIG.maintenance.yMin, max: CHART_CONFIG.maintenance.yMax },
      },
      plugins: { legend: { display: false } },
    },
  });

  document.getElementById('apply-poll-config').onclick = () => {
    applyLoggedPollingConfig();
  };

  document.getElementById('reset-db').onclick = async () => {
    const res = await fetch(`${API_BASE}/api/reset-db`, { method: 'POST' });
    const json = await res.json();
    if (json && json.ok) {
      clearLoggedCharts();
      setStatus('Database reset');
    } else {
      setStatus(`Reset failed: ${json && json.error ? json.error : 'unknown error'}`);
    }
  };

  document.getElementById('apply-config').onclick = async () => {
    const sensors = document.getElementById('maintenance-sensors').value;
    const interval = parseFloat(document.getElementById('maintenance-interval').value) || 0.5;
    const body = { maintenance_sensors: sensors, maintenance_interval: interval };
    const res = await fetch(`${API_BASE}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const json = await res.json();
    if (json && json.ok) {
      updateTopicPanel('sensors/config', { type: 'config', applied: body, response: json.applied || body });
      setStatus('Config published');
    } else {
      setStatus(`Config failed: ${json && json.error ? json.error : 'unknown error'}`);
    }
  };

  document.getElementById('reset-maintenance').onclick = () => resetMaintenanceChart();

  connect();
  startPolling(clampInterval(document.getElementById('poll-interval').value));
});
