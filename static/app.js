let sessionId = null;
let invoices = [];
let sortKey = null;
let sortAsc = true;
let _activeInvoiceId = null;

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

    document.getElementById('email-panel').classList.remove('hidden');
    document.getElementById('invoice-table-section').classList.remove('hidden');
    renderTable();
    showToast(`${gen} invoice PDF(s) ready`, 'success');
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
