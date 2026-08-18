const NUM_SENSORS = 10;
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
    lineTension: 0.5,
    interpolation: 'monotone',
    animationDurationMs: 260,
    animationEasing: 'easeOutQuad',
  },
};
const DB_SNAPSHOT_LIMIT = 20;
const LOAD_TEST_STATUS_INTERVAL_MS = 1000;

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

function formatNumber(value) {
  return new Intl.NumberFormat().format(Number(value) || 0);
}

function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const unit = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / (1024 ** unit)).toFixed(unit ? 1 : 0)} ${units[unit]}`;
}

function formatRate(value) {
  const rate = Number(value);
  return Number.isFinite(rate) && rate > 0 ? `${formatNumber(Math.round(rate))} points/s` : 'Reseed to measure';
}

function setLoadTestBusy(busy) {
  ['seed-test-db', 'benchmark-test-db', 'reset-test-db'].forEach((id) => {
    const button = document.getElementById(id);
    if (button) button.disabled = busy;
  });
}

function renderVariantStats(data, benchmarkResults = []) {
  const body = document.getElementById('variant-results-body');
  const workloadBody = document.getElementById('workload-results-body');
  const decision = document.getElementById('decision-summary');
  const variants = Array.isArray(data?.variants) ? data.variants : [];
  if (!body) return;
  if (!variants.length || !data.sample_count) {
    body.innerHTML = '<tr><td colspan="7">Seed the test database to compare variants.</td></tr>';
    if (workloadBody) workloadBody.innerHTML = '<tr><td colspan="5">Run the query comparison after seeding.</td></tr>';
    if (decision) decision.innerHTML = '<div class="chart-title">How to choose</div><p>Seed the database to measure storage, then run the comparison to see which design fits each query workload.</p>';
    const descriptions = {
      raw: 'One row per MQTT message; preserves the original payload.',
      samples: 'One row per sensor reading; simplest indexed sensor queries.',
      arrays: 'Two equipment-group rows per message; compact and compatible with the live demo.',
    };
    document.querySelectorAll('[data-variant]').forEach((card) => {
      card.querySelector('.metric-value').textContent = '—';
      card.querySelector('.metric-detail').textContent = descriptions[card.dataset.variant] || '';
    });
  } else {
    body.innerHTML = '';
    variants.forEach((variant) => {
      const row = document.createElement('tr');
      [
        variant.label,
        formatNumber(variant.rows),
        Number(variant.rows_per_message).toFixed(1),
        formatBytes(variant.size_bytes),
        `${Number(variant.bytes_per_point).toFixed(1)} B`,
        variant.seed_seconds ? `${Number(variant.seed_seconds).toFixed(2)} s` : 'Reseed to measure',
        formatRate(variant.points_per_second),
      ].forEach((value) => {
        const cell = document.createElement('td');
        cell.textContent = value;
        row.appendChild(cell);
      });
      body.appendChild(row);

      const card = document.querySelector(`[data-variant="${variant.key}"]`);
      if (card) {
        card.querySelector('.metric-value').textContent = `${Number(variant.bytes_per_point).toFixed(1)} B / point`;
        const detail = card.querySelector('.metric-detail');
        detail.textContent = `${formatNumber(variant.rows)} rows · ${formatBytes(variant.size_bytes)} total · ${formatRate(variant.points_per_second)}`;
      }
    });

    const storageWinner = variants.reduce((best, variant) => (
      variant.bytes_per_point < best.bytes_per_point ? variant : best
    ));
    const results = Array.isArray(benchmarkResults) ? benchmarkResults : [];
    const workloads = [...new Set(results.map((result) => result.workload))];
    if (workloadBody) {
      workloadBody.innerHTML = '';
      if (!workloads.length) {
        workloadBody.innerHTML = '<tr><td colspan="5">Run the query comparison after seeding.</td></tr>';
      }
      workloads.forEach((workload) => {
        const workloadResults = results.filter((result) => result.workload === workload);
        const byKey = Object.fromEntries(workloadResults.map((result) => [result.key, result]));
        const winner = workloadResults.reduce((best, result) => (
          result.query_ms < best.query_ms ? result : best
        ));
        const slowest = Math.max(...workloadResults.map((result) => result.query_ms));
        const speedup = winner.query_ms > 0 ? slowest / winner.query_ms : 1;
        const row = document.createElement('tr');
        const values = [
          workloadResults[0]?.workload_label || workload,
          byKey.raw ? `${byKey.raw.query_ms.toFixed(2)} ms · ${formatNumber(byKey.raw.points_scanned)} points` : '—',
          byKey.samples ? `${byKey.samples.query_ms.toFixed(2)} ms · ${formatNumber(byKey.samples.points_scanned)} points` : '—',
          byKey.arrays ? `${byKey.arrays.query_ms.toFixed(2)} ms · ${formatNumber(byKey.arrays.points_scanned)} points` : '—',
          `${winner.label} · ${speedup.toFixed(1)}× vs slowest`,
        ];
        values.forEach((value, index) => {
          const cell = document.createElement('td');
          if (index === 4) {
            const badge = document.createElement('span');
            badge.className = 'best-badge';
            badge.textContent = value;
            cell.appendChild(badge);
          } else {
            cell.textContent = value;
          }
          row.appendChild(cell);
        });
        workloadBody.appendChild(row);
      });
    }

    if (decision) {
      decision.innerHTML = '';
      const title = document.createElement('div');
      title.className = 'chart-title';
      title.textContent = 'How to choose';
      decision.appendChild(title);
      const storage = document.createElement('p');
      storage.textContent = `${storageWinner.label} uses the least measured storage at ${Number(storageWinner.bytes_per_point).toFixed(1)} bytes per sensor point.`;
      decision.appendChild(storage);
      if (workloads.length) {
        workloads.forEach((workload) => {
          const workloadResults = results.filter((result) => result.workload === workload);
          const winner = workloadResults.reduce((best, result) => result.query_ms < best.query_ms ? result : best);
          const line = document.createElement('p');
          line.textContent = `${winner.workload_label}: ${winner.label} was fastest at ${winner.query_ms.toFixed(2)} ms.`;
          decision.appendChild(line);
        });
      } else {
        const prompt = document.createElement('p');
        prompt.textContent = 'Run the query comparison to add workload-specific recommendations.';
        decision.appendChild(prompt);
      }
    }
  }
}

async function refreshLoadTestStatus(keepPolling = true) {
  const status = document.getElementById('load-test-status');
  try {
    const response = await fetch(`${API_BASE}/api/test-db/status`);
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'status request failed');
    setLoadTestBusy(Boolean(data.running));
    if (data.running) {
      status.textContent = `Seeding ${formatNumber(data.sample_count)} points — ${data.phase}…`;
      if (keepPolling) setTimeout(() => refreshLoadTestStatus(true), LOAD_TEST_STATUS_INTERVAL_MS);
      return data;
    }
    if (data.error) {
      status.textContent = `Seed failed: ${data.error}`;
    } else if (data.sample_count) {
      status.textContent = `${formatNumber(data.sample_count)} equivalent sensor points seeded in ${Number(data.seed_seconds).toFixed(2)}s.`;
    } else {
      status.textContent = 'Test database is empty.';
    }
    renderVariantStats(data);
    return data;
  } catch (error) {
    setLoadTestBusy(false);
    status.textContent = `Load-test API unavailable: ${error.message}`;
    return null;
  }
}

async function seedTestDatabase() {
  const status = document.getElementById('load-test-status');
  const countInput = document.getElementById('load-sample-count');
  const sampleCount = Number(countInput.value);
  setLoadTestBusy(true);
  status.textContent = `Starting a ${formatNumber(sampleCount)}-point seed…`;
  try {
    const response = await fetch(`${API_BASE}/api/test-db/seed`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sample_count: sampleCount }),
    });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'seed request failed');
    setTimeout(() => refreshLoadTestStatus(true), 250);
  } catch (error) {
    setLoadTestBusy(false);
    status.textContent = `Could not start seed: ${error.message}`;
  }
}

async function benchmarkTestDatabase() {
  const status = document.getElementById('load-test-status');
  setLoadTestBusy(true);
  status.textContent = 'Running the same 10-minute sensor aggregate across all variants…';
  try {
    const response = await fetch(`${API_BASE}/api/test-db/benchmark`, { method: 'POST' });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'benchmark failed');
    const current = await refreshLoadTestStatus(false);
    renderVariantStats(current, data.results);
    status.textContent = 'Comparison complete. Query values are median wall-clock timings from 3 warm runs on this PostgreSQL instance.';
  } catch (error) {
    status.textContent = `Benchmark failed: ${error.message}`;
  } finally {
    setLoadTestBusy(false);
  }
}

async function resetTestDatabase() {
  const status = document.getElementById('load-test-status');
  setLoadTestBusy(true);
  try {
    const response = await fetch(`${API_BASE}/api/test-db/reset`, { method: 'POST' });
    const data = await response.json();
    if (!response.ok || !data.ok) throw new Error(data.error || 'clear failed');
    await refreshLoadTestStatus(false);
  } catch (error) {
    status.textContent = `Clear failed: ${error.message}`;
  } finally {
    setLoadTestBusy(false);
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
    tension: CHART_CONFIG.maintenance.lineTension,
    cubicInterpolationMode: CHART_CONFIG.maintenance.interpolation,
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
  maintenanceChart.update();
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
      animation: {
        duration: CHART_CONFIG.maintenance.animationDurationMs,
        easing: CHART_CONFIG.maintenance.animationEasing,
      },
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

  document.getElementById('seed-test-db').onclick = seedTestDatabase;
  document.getElementById('benchmark-test-db').onclick = benchmarkTestDatabase;
  document.getElementById('reset-test-db').onclick = resetTestDatabase;

  connect();
  startPolling(clampInterval(document.getElementById('poll-interval').value));
  refreshLoadTestStatus(true);
});
