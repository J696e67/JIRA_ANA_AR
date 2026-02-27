let sessionId = null;
let invoices = [];
let sortKey = null;
let sortAsc = true;
let _activeInvoiceId = null;

// ── Page Navigation ──────────────────────────────────────────────────
const pages = document.querySelectorAll('.page');
const navLinks = document.querySelectorAll('.nav-link');

function navigate(page) {
  pages.forEach(p => p.classList.remove('active'));
  navLinks.forEach(l => l.classList.remove('active'));

  const target = document.getElementById('page-' + page);
  if (target) target.classList.add('active');

  const link = document.querySelector(`.nav-link[data-page="${page}"]`);
  if (link) link.classList.add('active');
}

function handleHash() {
  const hash = window.location.hash.replace('#', '') || 'upload';
  navigate(hash);
}

window.addEventListener('hashchange', handleHash);

navLinks.forEach(link => {
  link.addEventListener('click', (e) => {
    e.preventDefault();
    const page = link.dataset.page;
    window.location.hash = page;
  });
});

handleHash();

// ── LLM Status Check ────────────────────────────────────────────────
function checkLLMStatus() {
  const dot = document.getElementById('llm-dot');
  const text = document.getElementById('llm-text');

  fetch('/triage/llm-status')
    .then(r => r.json())
    .then(data => {
      if (data.llm_available) {
        dot.className = 'status-dot online';
        text.textContent = 'LLM: online';
      } else {
        dot.className = 'status-dot offline';
        text.textContent = 'LLM: offline';
      }
    })
    .catch(() => {
      dot.className = 'status-dot offline';
      text.textContent = 'LLM: offline';
    });
}

checkLLMStatus();
setInterval(checkLLMStatus, 30000);

// ── Upload ────────────────────────────────────────────────────────────
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('drag-over');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  if (e.dataTransfer.files[0]) processFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) processFile(fileInput.files[0]);
});

async function processFile(file) {
  const statusEl = document.getElementById('upload-status');
  statusEl.textContent = 'Processing CSV and generating PDFs…';
  statusEl.classList.remove('hidden');
  dropZone.classList.add('opacity-50', 'pointer-events-none');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const resp = await fetch('/upload', { method: 'POST', body: formData });
    const data = await resp.json();

    if (!resp.ok) {
      statusEl.textContent = 'Error: ' + (data.error || 'Upload failed');
      showToast('Upload failed: ' + (data.error || 'unknown error'), 'error');
      return;
    }

    sessionId = data.session_id;
    invoices = data.invoices;

    const gen = invoices.filter(i => i.status === 'generated').length;
    const skip = invoices.filter(i => i.status === 'skipped').length;
    const err = invoices.filter(i => i.status === 'error').length;

    statusEl.textContent =
      `Loaded ${invoices.length} row(s) from "${file.name}": ` +
      `${gen} PDF(s) generated, ${skip} skipped (send_invoice ≠ yes), ${err} error(s).`;

    // Show invoice content, hide empty state
    document.getElementById('invoices-empty').classList.add('hidden');
    document.getElementById('email-panel').classList.remove('hidden');
    document.getElementById('invoice-table-section').classList.remove('hidden');
    renderTable();

    // Show triage section, hide empty state
    document.getElementById('triage-empty').classList.add('hidden');
    document.getElementById('triage-section').classList.remove('hidden');

    showToast(`${gen} invoice PDF(s) ready`, 'success');

    // Auto-switch to invoices page
    window.location.hash = 'invoices';
  } catch (err) {
    statusEl.textContent = 'Error: ' + err.message;
    showToast('Upload failed: ' + err.message, 'error');
  } finally {
    dropZone.classList.remove('opacity-50', 'pointer-events-none');
  }
}

// ── Table ─────────────────────────────────────────────────────────────
function renderTable() {
  const search = document.getElementById('search-input').value.toLowerCase();

  let rows = invoices.filter(inv => {
    if (!search) return true;
    return (
      (inv.issue_key || '').toLowerCase().includes(search) ||
      (inv.pi_name   || '').toLowerCase().includes(search) ||
      (inv.summary   || '').toLowerCase().includes(search)
    );
  });

  if (sortKey) {
    rows = [...rows].sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (av == null) av = sortAsc ? Infinity : -Infinity;
      if (bv == null) bv = sortAsc ? Infinity : -Infinity;
      if (typeof av === 'number' && typeof bv === 'number')
        return sortAsc ? av - bv : bv - av;
      return sortAsc
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
  }

  document.getElementById('row-count').textContent = `${rows.length} of ${invoices.length} row(s)`;

  document.getElementById('invoice-tbody').innerHTML = rows.map(inv => {
    const canPreview = inv.status === 'generated';
    const canSend = inv.status === 'generated';
    return `
      <tr class="border-b last:border-0 hover:bg-gray-50 transition-colors">
        <td class="px-4 py-3 font-mono text-xs text-gray-700">${esc(inv.issue_key)}</td>
        <td class="px-4 py-3 text-gray-800">${esc(inv.pi_name)}</td>
        <td class="px-4 py-3 text-gray-600 max-w-xs">
          <span class="block truncate" title="${esc(inv.summary)}">${esc(inv.summary) || '<span class="text-gray-300 italic">—</span>'}</span>
        </td>
        <td class="px-4 py-3 text-right text-gray-700">${inv.hours != null ? inv.hours : '<span class="text-gray-300">—</span>'}</td>
        <td class="px-4 py-3 text-right text-gray-700 font-medium">${inv.amount != null ? '$' + inv.amount.toFixed(2) : '<span class="text-gray-300">—</span>'}</td>
        <td class="px-4 py-3 text-xs text-gray-500">${esc(inv.created)}</td>
        <td class="px-4 py-3 text-center">${pdfBadge(inv.status, inv.error)}</td>
        <td class="px-4 py-3 text-center" id="email-cell-${inv.invoice_id}">${emailBadge(inv.email_status)}</td>
        <td class="px-4 py-3 text-center">
          <div class="flex items-center justify-center gap-1.5">
            ${canPreview
              ? `<button onclick="previewInvoice('${inv.invoice_id}')"
                   class="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-md px-2.5 py-1 transition-colors">
                   Preview
                 </button>`
              : ''}
            ${canSend
              ? `<button onclick="openEmailModal('${inv.invoice_id}')"
                   class="text-xs bg-blue-100 hover:bg-blue-200 text-blue-700 rounded-md px-2.5 py-1 transition-colors">
                   Send
                 </button>`
              : ''}
          </div>
        </td>
      </tr>`;
  }).join('');

  // Update sort icons
  document.querySelectorAll('th.sortable').forEach(th => {
    const key = th.getAttribute('onclick').match(/'(\w+)'/)?.[1];
    const icon = th.querySelector('.sort-icon');
    if (!icon) return;
    if (key === sortKey) icon.textContent = sortAsc ? '↑' : '↓';
    else icon.textContent = '↕';
  });
}

function pdfBadge(status, error) {
  if (status === 'generated')
    return `<span class="inline-flex items-center gap-1 bg-green-100 text-green-700 text-xs rounded-full px-2.5 py-0.5 font-medium">&#10003; Generated</span>`;
  if (status === 'skipped')
    return `<span class="inline-flex items-center gap-1 bg-gray-100 text-gray-500 text-xs rounded-full px-2.5 py-0.5">&#8212; Skipped</span>`;
  if (status === 'error')
    return `<span class="inline-flex items-center gap-1 bg-red-100 text-red-600 text-xs rounded-full px-2.5 py-0.5 font-medium" title="${esc(error || '')}">&#10007; Error</span>`;
  return `<span class="text-gray-300 text-xs">—</span>`;
}

function emailBadge(status) {
  if (!status) return `<span class="text-gray-300 text-xs">—</span>`;
  if (status === 'sent')
    return `<span class="inline-flex items-center gap-1 bg-green-100 text-green-700 text-xs rounded-full px-2.5 py-0.5 font-medium">&#10003; Sent</span>`;
  if (status === 'error')
    return `<span class="inline-flex items-center gap-1 bg-red-100 text-red-600 text-xs rounded-full px-2.5 py-0.5">&#10007; Error</span>`;
  if (status === 'sending')
    return `<span class="text-gray-400 text-xs animate-pulse">Sending…</span>`;
  return `<span class="text-gray-400 text-xs">${esc(status)}</span>`;
}

function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function filterTable() { renderTable(); }

function sortTable(key) {
  if (sortKey === key) sortAsc = !sortAsc;
  else { sortKey = key; sortAsc = true; }
  renderTable();
}

// ── Preview ───────────────────────────────────────────────────────────
function previewInvoice(invoiceId) {
  window.open(`/preview/${sessionId}/${invoiceId}`, '_blank');
}

// ── Email Modal ───────────────────────────────────────────────────────
function openEmailModal(invoiceId) {
  _activeInvoiceId = invoiceId;
  const inv = invoices.find(i => i.invoice_id === invoiceId);
  document.getElementById('modal-subject').value = inv.email_subject || '';
  document.getElementById('modal-body').value = inv.email_body || '';
  document.getElementById('email-modal').classList.remove('hidden');
}

function closeEmailModal() {
  document.getElementById('email-modal').classList.add('hidden');
  _activeInvoiceId = null;
}

async function sendModalEmail() {
  const invoiceId = _activeInvoiceId;
  const inv = invoices.find(i => i.invoice_id === invoiceId);
  const payload = {
    session_id: sessionId,
    invoice_id: invoiceId,
    from_addr: document.getElementById('from-addr').value,
    password:  document.getElementById('gmail-password').value,
    to_addr:   document.getElementById('to-addr').value,
    cc_addr:   document.getElementById('cc-addr').value,
    subject:   document.getElementById('modal-subject').value,
    body:      document.getElementById('modal-body').value,
  };

  closeEmailModal();

  // Optimistic UI update
  inv.email_status = 'sending';
  renderTable();

  try {
    const resp = await fetch('/send-email', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (resp.ok) {
      inv.email_status = 'sent';
      showToast(`Email sent for ${inv.issue_key}`, 'success');
    } else {
      inv.email_status = 'error';
      showToast(`Failed: ${data.error}`, 'error');
    }
  } catch (err) {
    inv.email_status = 'error';
    showToast('Error: ' + err.message, 'error');
  }
  renderTable();
}

// ── Send All ──────────────────────────────────────────────────────────
async function sendAll() {
  const generated = invoices.filter(i => i.status === 'generated');
  if (!generated.length) {
    showToast('No generated invoices to send', 'error');
    return;
  }

  const btn = document.getElementById('send-all-btn');
  btn.disabled = true;
  btn.textContent = 'Sending…';

  const payload = {
    session_id: sessionId,
    from_addr:  document.getElementById('from-addr').value,
    password:   document.getElementById('gmail-password').value,
    to_addr:    document.getElementById('to-addr').value,
    cc_addr:    document.getElementById('cc-addr').value,
  };

  try {
    const resp = await fetch('/send-all', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();

    if (!resp.ok) {
      showToast('Error: ' + (data.error || 'Send all failed'), 'error');
      return;
    }

    let sent = 0, failed = 0;
    for (const result of data.results) {
      const inv = invoices.find(i => i.invoice_id === result.invoice_id);
      if (inv) inv.email_status = result.success ? 'sent' : 'error';
      result.success ? sent++ : failed++;
    }

    renderTable();
    showToast(
      `Sent ${sent} email(s)` + (failed ? `, ${failed} failed` : ''),
      sent > 0 ? 'success' : 'error'
    );
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Send All Generated Invoices';
  }
}

// ── Toast ─────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  const colors = { success: 'bg-green-600', error: 'bg-red-600', info: 'bg-blue-700' };
  const toast = document.createElement('div');
  toast.className = `toast text-white text-sm px-4 py-3 rounded-lg shadow-lg ${colors[type] || colors.info} max-w-sm pointer-events-auto`;
  toast.textContent = msg;
  document.getElementById('toast-container').appendChild(toast);
  setTimeout(() => toast.remove(), 4000);
}

// Close modal on backdrop click
document.getElementById('email-modal').addEventListener('click', function(e) {
  if (e.target === this) closeEmailModal();
});

// ── Triage ────────────────────────────────────────────────────────────
let triageResults = [];
let triagePollingTimer = null;

async function runTriage() {
  if (!sessionId) {
    showToast('Upload a CSV first', 'error');
    return;
  }

  const btn = document.getElementById('run-triage-btn');
  btn.disabled = true;
  btn.textContent = 'Starting…';

  const progressEl = document.getElementById('triage-progress');
  progressEl.classList.remove('hidden');
  document.getElementById('triage-results').classList.add('hidden');
  document.getElementById('triage-chart-container').classList.add('hidden');
  showTriageProgress(0, 1);

  try {
    const resp = await fetch('/triage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await resp.json();

    if (!resp.ok) {
      showToast('Triage failed: ' + (data.error || 'unknown'), 'error');
      btn.disabled = false;
      btn.textContent = 'Run Triage';
      progressEl.classList.add('hidden');
      return;
    }

    showTriageProgress(0, data.total);
    startTriagePolling();
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
    btn.disabled = false;
    btn.textContent = 'Run Triage';
    progressEl.classList.add('hidden');
  }
}

function startTriagePolling() {
  if (triagePollingTimer) clearInterval(triagePollingTimer);
  triagePollingTimer = setInterval(pollTriageStatus, 1500);
}

async function pollTriageStatus() {
  try {
    const resp = await fetch(`/triage/status/${sessionId}`);
    const data = await resp.json();

    if (data.status === 'processing') {
      const p = data.progress || {};
      showTriageProgress(p.completed || 0, p.total || 1, p.current);
    } else if (data.status === 'complete') {
      clearInterval(triagePollingTimer);
      triagePollingTimer = null;
      triageResults = data.results || [];
      document.getElementById('triage-progress').classList.add('hidden');
      document.getElementById('triage-results').classList.remove('hidden');
      renderTriageResults();
      document.getElementById('triage-status-text').textContent =
        `${triageResults.length} ticket(s) triaged`;
      showToast(`Triage complete: ${triageResults.length} ticket(s)`, 'success');
      const btn = document.getElementById('run-triage-btn');
      btn.disabled = false;
      btn.textContent = 'Re-run Triage';
    } else if (data.status === 'failed') {
      clearInterval(triagePollingTimer);
      triagePollingTimer = null;
      document.getElementById('triage-progress').classList.add('hidden');
      showToast('Triage failed: ' + (data.error || 'unknown'), 'error');
      const btn = document.getElementById('run-triage-btn');
      btn.disabled = false;
      btn.textContent = 'Run Triage';
    }
  } catch (_) {
    // Silently retry on next poll
  }
}

function showTriageProgress(completed, total, currentKey) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  document.getElementById('triage-progress-bar').style.width = pct + '%';
  document.getElementById('triage-progress-text').textContent = `${completed} / ${total}`;
  const currentEl = document.getElementById('triage-progress-current');
  currentEl.textContent = currentKey ? `Processing ${currentKey}…` : '';
}

function renderTriageResults() {
  // Group by assignee
  const groups = {};
  triageResults.forEach(r => {
    const assignee = (r.assignee || '').trim() || 'Unassigned';
    if (!groups[assignee]) groups[assignee] = [];
    groups[assignee].push(r);
  });

  const sortedAssignees = Object.keys(groups).sort((a, b) => {
    if (a === 'Unassigned') return 1;
    if (b === 'Unassigned') return -1;
    return a.localeCompare(b);
  });

  const container = document.getElementById('triage-groups');
  container.innerHTML = sortedAssignees.map(assignee => {
    const tickets = groups[assignee];
    const rowsHtml = tickets.map(r => {
      const outputHtml = formatTriageOutput(r.output || '');
      const jiraUrl = `https://scicomp.atlassian.net/browse/${encodeURIComponent(r.issue_key)}`;
      return `
        <tr class="border-b last:border-0 hover:bg-gray-50 transition-colors align-top">
          <td class="px-4 py-3 font-mono text-xs whitespace-nowrap">
            <a href="${jiraUrl}" target="_blank" rel="noopener noreferrer"
               class="text-blue-600 hover:text-blue-800 hover:underline">${esc(r.issue_key)}</a>
          </td>
          <td class="px-4 py-3">${triageCategoryBadge(r.category)}</td>
          <td class="px-4 py-3 text-xs text-gray-600">${esc(r.status)}</td>
          <td class="px-4 py-3 text-xs text-gray-700 max-w-lg">
            <div class="triage-output whitespace-pre-wrap">${outputHtml}</div>
          </td>
          <td class="px-4 py-3 text-center">
            <button onclick="retriageSingle('${esc(r.issue_key)}')"
              class="text-xs bg-purple-100 hover:bg-purple-200 text-purple-700 rounded-md px-2.5 py-1 transition-colors">
              Re-triage
            </button>
          </td>
        </tr>`;
    }).join('');

    return `
      <details class="triage-group bg-white rounded-xl shadow mb-3" open>
        <summary class="px-6 py-4 cursor-pointer select-none flex items-center gap-2 text-sm font-semibold text-gray-700">
          <span class="triage-arrow"></span>
          ${esc(assignee)}
          <span class="inline-flex items-center justify-center bg-purple-100 text-purple-700 text-xs rounded-full px-2 py-0.5 font-medium ml-1">${tickets.length}</span>
        </summary>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-gray-50 border-b text-gray-600">
              <tr>
                <th class="px-4 py-3 text-left font-medium">Issue Key</th>
                <th class="px-4 py-3 text-left font-medium">Category</th>
                <th class="px-4 py-3 text-left font-medium">Status</th>
                <th class="px-4 py-3 text-left font-medium">Action / Output</th>
                <th class="px-4 py-3 text-center font-medium">Re-triage</th>
              </tr>
            </thead>
            <tbody>${rowsHtml}</tbody>
          </table>
        </div>
      </details>`;
  }).join('');

  renderTriageChart();
}

let triageChartInstance = null;

function renderTriageChart() {
  const canvas = document.getElementById('triage-chart');
  if (!canvas || typeof Chart === 'undefined') return;

  // Count categories
  const counts = {};
  triageResults.forEach(r => {
    const cat = r.category || 'Unknown';
    counts[cat] = (counts[cat] || 0) + 1;
  });

  const labels = Object.keys(counts);
  const data = Object.values(counts);

  // Colors matching the badge color scheme
  const colorMap = {
    'Priority 1': { bg: 'rgba(254,202,202,0.8)', border: '#dc2626' },
    'Priority 2': { bg: 'rgba(254,215,170,0.8)', border: '#ea580c' },
    'Priority 3a': { bg: 'rgba(254,240,138,0.8)', border: '#a16207' },
    'Priority 3b': { bg: 'rgba(254,240,138,0.8)', border: '#a16207' },
    'Priority 3c': { bg: 'rgba(191,219,254,0.8)', border: '#2563eb' },
    'Priority 3d': { bg: 'rgba(191,219,254,0.8)', border: '#2563eb' },
    'No Action':   { bg: 'rgba(229,231,235,0.8)', border: '#6b7280' },
    'Triage Failed': { bg: 'rgba(254,202,202,0.8)', border: '#dc2626' },
  };

  const bgColors = labels.map(l => {
    for (const [key, val] of Object.entries(colorMap)) {
      if (l.includes(key)) return val.bg;
    }
    return 'rgba(229,231,235,0.8)';
  });
  const borderColors = labels.map(l => {
    for (const [key, val] of Object.entries(colorMap)) {
      if (l.includes(key)) return val.border;
    }
    return '#6b7280';
  });

  if (triageChartInstance) {
    triageChartInstance.destroy();
  }

  triageChartInstance = new Chart(canvas, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Tickets',
        data: data,
        backgroundColor: bgColors,
        borderColor: borderColors,
        borderWidth: 1,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
      },
      scales: {
        x: {
          beginAtZero: true,
          ticks: { stepSize: 1, precision: 0 },
        },
      },
    },
  });

  document.getElementById('triage-chart-container').classList.remove('hidden');
}

function triageCategoryBadge(category) {
  const colorMap = {
    'Priority 1': 'bg-red-100 text-red-700',
    'Priority 2': 'bg-orange-100 text-orange-700',
    'Priority 3a': 'bg-yellow-100 text-yellow-800',
    'Priority 3b': 'bg-yellow-100 text-yellow-800',
    'Priority 3c': 'bg-blue-100 text-blue-700',
    'Priority 3d': 'bg-blue-100 text-blue-700',
    'No Action': 'bg-gray-100 text-gray-500',
    'Triage Failed': 'bg-red-100 text-red-600',
  };
  let cls = 'bg-gray-100 text-gray-500';
  for (const [key, val] of Object.entries(colorMap)) {
    if (category && category.includes(key)) { cls = val; break; }
  }
  return `<span class="inline-flex items-center text-xs rounded-full px-2.5 py-0.5 font-medium whitespace-nowrap ${cls}">${esc(category)}</span>`;
}

function formatTriageOutput(text) {
  let html = esc(text);
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/```\n?([\s\S]*?)```/g, '<pre class="bg-gray-100 rounded p-2 mt-1 text-xs overflow-x-auto">$1</pre>');
  return html;
}

async function retriageSingle(issueKey) {
  if (!sessionId) return;

  const idx = triageResults.findIndex(r => r.issue_key === issueKey);

  try {
    const resp = await fetch(`/triage/single/${encodeURIComponent(issueKey)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await resp.json();

    if (!resp.ok) {
      showToast(`Re-triage failed: ${data.error || 'unknown'}`, 'error');
      return;
    }

    if (idx >= 0) {
      triageResults[idx] = data.result;
    } else {
      triageResults.push(data.result);
    }

    renderTriageResults();
    showToast(`Re-triaged ${issueKey}`, 'success');
  } catch (err) {
    showToast('Error: ' + err.message, 'error');
  }
}
