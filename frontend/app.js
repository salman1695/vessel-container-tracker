let allHistoryCache = [];
let currentSeverityFilter = '';

function formatDate(dateStr) {
  if (!dateStr) return 'Pending';
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return dateStr;
  return d.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  });
}

function switchPage(pageName) {
  ['tracking', 'history', 'logs'].forEach(p => {
    const sec = document.getElementById(`page-${p}`);
    const navBtn = document.getElementById(`nav${p.charAt(0).toUpperCase() + p.slice(1)}`);
    if (sec) sec.classList.toggle('hidden', p !== pageName);
    if (navBtn) {
      navBtn.className = p === pageName
        ? 'px-3.5 py-2 rounded-lg text-xs font-bold bg-white text-sky-700 shadow-xs transition cursor-pointer'
        : 'px-3.5 py-2 rounded-lg text-xs font-semibold text-slate-600 hover:text-slate-900 transition cursor-pointer';
    }
  });

  document.getElementById('errorBox').classList.add('hidden');

  if (pageName === 'history') loadHistoryData();
  if (pageName === 'logs') loadAuditLogs();
  if (pageName === 'tracking' && typeof map !== 'undefined' && map) {
    setTimeout(() => map.invalidateSize(), 120);
  }
}

function switchSearchMode(mode) {
  const isContainer = mode === 'container';
  document.getElementById('containerForm').classList.toggle('hidden', !isContainer);
  document.getElementById('vesselForm').classList.toggle('hidden', isContainer);

  document.getElementById('tabContainer').className = isContainer
    ? 'px-4 py-2 rounded-lg text-sm font-bold bg-white text-sky-700 shadow-xs transition cursor-pointer'
    : 'px-4 py-2 rounded-lg text-sm font-semibold text-slate-600 hover:text-slate-900 transition cursor-pointer';

  document.getElementById('tabVessel').className = !isContainer
    ? 'px-4 py-2 rounded-lg text-sm font-bold bg-white text-sky-700 shadow-xs transition cursor-pointer'
    : 'px-4 py-2 rounded-lg text-sm font-semibold text-slate-600 hover:text-slate-900 transition cursor-pointer';
}

function quickTrackContainer(containerNum) {
  switchPage('tracking');
  switchSearchMode('container');
  document.getElementById('shipmentInput').value = containerNum;
  handleContainerSearch(null, false);
}

function renderMilestonesList(containerId, events, emptyMessage) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';

  if (!events || events.length === 0) {
    container.innerHTML = `<p class="text-xs text-slate-400 pl-4">${emptyMessage}</p>`;
    return;
  }

  events.forEach(m => {
    const dotColor = m.is_actual
      ? 'bg-emerald-500 border-white ring-2 ring-emerald-200'
      : 'bg-slate-300 border-white ring-2 ring-slate-200';

    const statusTag = m.is_actual
      ? '<span class="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200">Actual</span>'
      : '<span class="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200">Estimated</span>';

    const extraInfo = [
      m.location ? `${m.location}${m.country ? ', ' + m.country : ''}` : null,
      m.facility ? `🏢 ${m.facility}` : null,
      m.voyage ? `Voyage: ${m.voyage}` : null
    ].filter(Boolean).join(' • ');

    container.innerHTML += `
      <div class="pl-5 relative">
        <span class="w-3.5 h-3.5 rounded-full ${dotColor} border-2 absolute -left-[8px] top-1"></span>
        <div class="flex items-start justify-between gap-2">
          <p class="text-sm font-bold text-slate-900">${m.description || 'Event'}</p>
          ${statusTag}
        </div>
        <p class="text-xs text-slate-600 mt-0.5">${extraInfo}</p>
        <p class="text-[11px] font-mono text-slate-400 mt-1">${formatDate(m.date)}</p>
      </div>
    `;
  });
}

async function handleContainerSearch(e, forceRefresh = false) {
  if (e) e.preventDefault();
  const num = document.getElementById('shipmentInput').value.trim();
  if (!num) return;

  const sealine = document.getElementById('sealineSelect').value;
  const loader = document.getElementById('loader');
  const errorBox = document.getElementById('errorBox');
  const resultsSection = document.getElementById('resultsSection');
  const vesselResultsSection = document.getElementById('vesselResultsSection');

  loader.classList.remove('hidden');
  errorBox.classList.add('hidden');
  vesselResultsSection.classList.add('hidden');

  try {
    const params = new URLSearchParams({ shipment_number: num, force_refresh: forceRefresh });
    if (sealine) params.append('sealine', sealine);

    const res = await fetch(`/api/v1/track?${params.toString()}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Tracking failed');

    renderContainerData(data);
    resultsSection.classList.remove('hidden');
  } catch (err) {
    errorBox.textContent = `⚠️ ${err.message}`;
    errorBox.classList.remove('hidden');
    resultsSection.classList.add('hidden');
  } finally {
    loader.classList.add('hidden');
  }
}

function renderContainerData(data) {
  const s = data.summary || {};
  const badge = document.getElementById('dataSourceBadge');
  badge.textContent = `⚡ ${data.source || 'LIVE'}`;
  badge.classList.remove('hidden');

  const statusUpper = (s.status || '').toUpperCase();
  const progressBar = document.getElementById('routeProgressFill');
  if (progressBar) {
    if (statusUpper === 'DELIVERED') progressBar.style.width = '100%';
    else if (statusUpper === 'IN_TRANSIT') progressBar.style.width = '60%';
    else progressBar.style.width = '20%';
  }

  document.getElementById('bannerOrigin').textContent = s.origin_port || 'Origin Port';
  document.getElementById('bannerDest').textContent = s.destination_port || 'Destination Port';
  document.getElementById('bannerCarrier').textContent = `Carrier: ${s.shipping_line || 'Auto-Detected'}`;
  document.getElementById('bannerVessel').textContent = s.vessel_name
    ? `Vessel: ${s.vessel_name} ${s.voyage ? '• Voy ' + s.voyage : ''}`
    : 'Vessel Pending';
  document.getElementById('bannerEta').textContent = `ETA: ${formatDate(s.eta)}`;
  document.getElementById('resStatusBadge').textContent = (s.status || 'UNKNOWN').replace('_', ' ');

  document.getElementById('resContainer').textContent = s.container_number || '-';
  document.getElementById('resSize').textContent = s.container_size || 'Standard Container';

  document.getElementById('resVessel').textContent = s.vessel_name || 'N/A';
  document.getElementById('resImo').textContent = s.vessel_imo
    ? `IMO: ${s.vessel_imo} • MMSI: ${s.vessel_mmsi || '-'}`
    : 'IMO unavailable';

  const coords = s.vessel_coordinates;
  document.getElementById('resCoords').textContent = coords
    ? `${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)}`
    : 'Unavailable';
  document.getElementById('resCoordTime').textContent = coords?.updatedAt
    ? `AIS Ping: ${formatDate(coords.updatedAt)}`
    : 'Awaiting satellite ping';

  document.getElementById('resEta').textContent = formatDate(s.eta);
  document.getElementById('resType').textContent = `${data.detected_type || 'CT'} • Synced: ${formatDate(data.last_synced_at)}`;

  const containerEvents = (data.container_milestones && data.container_milestones.length > 0)
    ? data.container_milestones
    : data.milestones;

  renderMilestonesList('timelineContainer', containerEvents, 'No container equipment events recorded.');

  renderSeaMap({
    seaRoutePath: data.sea_route_path,
    coords: coords,
    vesselName: s.vessel_name,
    vesselImo: s.vessel_imo,
    originPort: s.origin_port,
    destPort: s.destination_port,
    formatDateFn: formatDate
  });
}

async function handleVesselSearch(e) {
  if (e) e.preventDefault();
  const name = document.getElementById('vesselInput').value.trim();
  if (!name) return;

  const loader = document.getElementById('loader');
  const errorBox = document.getElementById('errorBox');
  const vesselResultsSection = document.getElementById('vesselResultsSection');
  const resultsSection = document.getElementById('resultsSection');

  loader.classList.remove('hidden');
  errorBox.classList.add('hidden');
  resultsSection.classList.add('hidden');

  try {
    const res = await fetch(`/api/v1/vessel?name=${encodeURIComponent(name)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Vessel not found');

    document.getElementById('vResName').textContent = data.vessel_name || name.toUpperCase();
    document.getElementById('vResMeta').textContent = `Flag: ${data.vessel_flag || '-'} • Call Sign: ${data.vessel_call_sign || '-'} • Voyage: ${data.voyage || '-'}`;
    document.getElementById('vResImo').textContent = data.vessel_imo || '-';
    document.getElementById('vResMmsi').textContent = data.vessel_mmsi || '-';
    document.getElementById('vResCount').textContent = data.total_containers_tracked || 0;

    renderMilestonesList('vesselTimelineContainer', data.vessel_milestones, 'No vessel voyage events recorded.');

    const list = document.getElementById('vContainersList');
    list.innerHTML = '';
    (data.containers || []).forEach(c => {
      list.innerHTML += `
        <div onclick="quickTrackContainer('${c.container_number}')"
          class="cursor-pointer bg-slate-50 hover:bg-sky-50 border border-slate-200 hover:border-sky-300 rounded-xl p-4 flex items-center justify-between transition">
          <div>
            <div class="font-mono font-bold text-sky-700">${c.container_number}</div>
            <div class="text-xs text-slate-600 mt-0.5">${c.origin_port || '?'} → ${c.destination_port || '?'} (${c.shipping_line || ''})</div>
          </div>
          <span class="text-xs font-bold px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700">Inspect →</span>
        </div>
      `;
    });

    vesselResultsSection.classList.remove('hidden');
  } catch (err) {
    errorBox.textContent = `⚠️ ${err.message}`;
    errorBox.classList.remove('hidden');
    vesselResultsSection.classList.add('hidden');
  } finally {
    loader.classList.add('hidden');
  }
}

async function loadHistoryData() {
  try {
    const res = await fetch('/api/v1/history?limit=50');
    if (!res.ok) return;
    const data = await res.json();
    allHistoryCache = data.history || [];
    renderHistoryTable();
  } catch (err) {
    console.error('History fetch error:', err);
  }
}

function renderHistoryTable() {
  const tbody = document.getElementById('historyTableBody');
  if (!tbody) return;

  const q = (document.getElementById('historyFilterInput')?.value || '').trim().toLowerCase();
  const filtered = allHistoryCache.filter(item =>
    !q ||
    (item.container_number || '').toLowerCase().includes(q) ||
    (item.vessel_name || '').toLowerCase().includes(q) ||
    (item.shipping_line || '').toLowerCase().includes(q)
  );

  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="py-6 text-center text-xs text-slate-400">No matching shipments found.</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(item => `
    <tr class="border-b border-slate-100 hover:bg-slate-50/80">
      <td class="py-3 px-3 font-mono text-xs font-bold text-sky-700">${item.container_number}</td>
      <td class="py-3 px-3 text-xs font-semibold text-slate-800">${item.vessel_name || '-'}</td>
      <td class="py-3 px-3 text-xs text-slate-600">${item.shipping_line || '-'}</td>
      <td class="py-3 px-3">
        <span class="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700">${(item.status || 'UNKNOWN').replace('_', ' ')}</span>
      </td>
      <td class="py-3 px-3 font-mono text-[11px] text-slate-500">${formatDate(item.updated_at)}</td>
      <td class="py-3 px-3 text-right">
        <button type="button" onclick="quickTrackContainer('${item.container_number}')"
          class="text-xs font-bold text-sky-600 hover:underline cursor-pointer">Open →</button>
      </td>
    </tr>
  `).join('');
}

function filterLogsBySeverity(sev) {
  currentSeverityFilter = sev;
  loadAuditLogs();
}

async function loadAuditLogs() {
  try {
    const params = new URLSearchParams({ limit: 100 });
    if (currentSeverityFilter) params.append('severity', currentSeverityFilter);

    const res = await fetch(`/api/v1/logs?${params.toString()}`);
    if (!res.ok) return;
    const data = await res.json();
    renderLogsTable(data.logs || []);
  } catch (err) {
    console.error('Audit logs fetch error:', err);
  }
}

function renderLogsTable(logs) {
  const tbody = document.getElementById('auditLogsBody');
  if (!tbody) return;

  if (logs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="py-6 text-center text-xs text-slate-400">No audit logs found for this filter.</td></tr>';
    return;
  }

  const sevStyles = {
    SUCCESS: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    WARNING: 'bg-amber-50 text-amber-700 border-amber-200',
    ERROR: 'bg-rose-50 text-rose-700 border-rose-200',
    INFO: 'bg-sky-50 text-sky-700 border-sky-200'
  };

  tbody.innerHTML = logs.map(log => {
    const sev = (log.severity || 'INFO').toUpperCase();
    const badgeClass = sevStyles[sev] || sevStyles.INFO;

    return `
      <tr class="border-b border-slate-100 hover:bg-slate-50/70">
        <td class="py-2.5 px-3 font-mono text-[11px] text-slate-500 whitespace-nowrap">${formatDate(log.timestamp)}</td>
        <td class="py-2.5 px-3 whitespace-nowrap">
          <span class="text-[10px] font-extrabold px-2 py-0.5 rounded border ${badgeClass}">${sev}</span>
        </td>
        <td class="py-2.5 px-3 text-xs font-bold text-slate-800 whitespace-nowrap">${log.action_type}</td>
        <td class="py-2.5 px-3 font-mono text-xs font-semibold text-sky-700 whitespace-nowrap">${log.query_target}</td>
        <td class="py-2.5 px-3 text-xs font-medium text-slate-600 whitespace-nowrap">${log.source}</td>
        <td class="py-2.5 px-3 text-xs text-slate-700">${log.details}</td>
      </tr>
    `;
  }).join('');
}

async function triggerFleetSync() {
  const btn = document.getElementById('syncFleetBtn');
  btn.disabled = true;
  btn.textContent = 'Syncing...';
  try {
    const res = await fetch('/api/v1/sync-active', { method: 'POST' });
    const data = await res.json();
    alert(`Fleet Sync Complete! Checked: ${data.checked_stale}, Updated: ${data.synced}, Failed: ${data.failed}`);
    if (!document.getElementById('page-logs').classList.contains('hidden')) loadAuditLogs();
    if (!document.getElementById('page-history').classList.contains('hidden')) loadHistoryData();
  } catch (err) {
    alert('Sync failed: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔄 Sync Fleet';
  }
}