const statusEl = document.getElementById('status');
const roleEl = document.getElementById('role');
const userEl = document.getElementById('user');
const roleHint = document.getElementById('roleHint');
const eventsOutput = document.getElementById('eventsOutput');
const eventSelect = document.getElementById('eventSelect');
const auditOutput = document.getElementById('auditOutput');

function isAdmin() {
  return roleEl.value === 'admin';
}

function headers() {
  return {
    'Content-Type': 'application/json',
    'X-Role': roleEl.value,
    'X-User': userEl.value || 'anonymous'
  };
}

function setStatus(message, ok = true) {
  statusEl.textContent = `${ok ? 'OK' : 'ERROR'}: ${message}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { ...headers(), ...(options.headers || {}) } });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || response.statusText);
  }
  return data;
}

function selectedEventId() {
  return eventSelect.value;
}

function enforceUiRoleProtection() {
  const disabled = !isAdmin();
  document.querySelectorAll('form button, .actions button, #loadAudit').forEach((button) => {
    button.disabled = disabled;
  });
  roleHint.textContent = disabled
    ? 'Viewer role: admin actions are hidden behind backend role checks and disabled in UI.'
    : 'Admin role: full event operations enabled.';
  roleHint.className = disabled ? 'disabled-note' : '';
}

async function refreshEvents() {
  const events = await api('/api/admin/events', { method: 'GET' });
  eventsOutput.textContent = JSON.stringify(events, null, 2);
  eventSelect.innerHTML = '';
  events.forEach((event) => {
    const opt = document.createElement('option');
    opt.value = event.id;
    opt.textContent = `${event.name} (${event.status})`;
    eventSelect.appendChild(opt);
  });
}

document.getElementById('refresh').addEventListener('click', async () => {
  try {
    await refreshEvents();
    setStatus('events refreshed');
  } catch (err) {
    setStatus(err.message, false);
  }
});

roleEl.addEventListener('change', enforceUiRoleProtection);
enforceUiRoleProtection();

document.getElementById('createForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = new FormData(event.target);
  const payload = Object.fromEntries(form.entries());
  payload.capacity = Number(payload.capacity);
  try {
    await api('/api/admin/events', { method: 'POST', body: JSON.stringify(payload) });
    await refreshEvents();
    setStatus('event created');
  } catch (err) {
    setStatus(err.message, false);
  }
});

document.querySelectorAll('.actions button').forEach((button) => {
  button.addEventListener('click', async () => {
    const eventId = selectedEventId();
    if (!eventId) return setStatus('select an event', false);
    try {
      await api(`/api/admin/events/${eventId}/${button.dataset.action}`, { method: 'POST' });
      await refreshEvents();
      setStatus(`${button.dataset.action} complete`);
    } catch (err) {
      setStatus(err.message, false);
    }
  });
});

document.getElementById('editForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const eventId = selectedEventId();
  if (!eventId) return setStatus('select an event', false);
  const payload = Object.fromEntries(new FormData(event.target).entries());
  if (payload.capacity) payload.capacity = Number(payload.capacity);
  Object.keys(payload).forEach((k) => payload[k] === '' && delete payload[k]);
  try {
    await api(`/api/admin/events/${eventId}`, { method: 'PUT', body: JSON.stringify(payload) });
    await refreshEvents();
    setStatus('event edited');
  } catch (err) {
    setStatus(err.message, false);
  }
});

document.getElementById('participantForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const mode = event.submitter?.dataset.mode || 'add';
  const eventId = selectedEventId();
  if (!eventId) return setStatus('select an event', false);
  const payload = Object.fromEntries(new FormData(event.target).entries());
  try {
    await api(`/api/admin/events/${eventId}/participants/${mode}`, { method: 'POST', body: JSON.stringify(payload) });
    await refreshEvents();
    setStatus(`participant ${mode}ed`);
  } catch (err) {
    setStatus(err.message, false);
  }
});

document.getElementById('roundForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const eventId = selectedEventId();
  if (!eventId) return setStatus('select an event', false);
  const payload = Object.fromEntries(new FormData(event.target).entries());
  payload.round_number = Number(payload.round_number);
  try {
    await api(`/api/admin/events/${eventId}/rounds/publish`, { method: 'POST', body: JSON.stringify(payload) });
    await refreshEvents();
    setStatus('round published');
  } catch (err) {
    setStatus(err.message, false);
  }
});

document.getElementById('overrideForm').addEventListener('submit', async (event) => {
  event.preventDefault();
  const eventId = selectedEventId();
  if (!eventId) return setStatus('select an event', false);
  const payload = Object.fromEntries(new FormData(event.target).entries());
  try {
    await api(`/api/admin/events/${eventId}/overrides/report`, { method: 'POST', body: JSON.stringify(payload) });
    await refreshEvents();
    setStatus('override recorded');
  } catch (err) {
    setStatus(err.message, false);
  }
});

document.getElementById('loadAudit').addEventListener('click', async () => {
  try {
    const log = await api('/api/admin/audit-log', { method: 'GET' });
    auditOutput.textContent = JSON.stringify(log, null, 2);
    setStatus('audit log loaded');
  } catch (err) {
    setStatus(err.message, false);
  }
});

refreshEvents().catch((e) => setStatus(e.message, false));
