/* ──────────────────────────────────────────────────────────────
   Broker Agentic Challenge — Auto-fill & SSE controller
   ────────────────────────────────────────────────────────────── */

(function () {
  'use strict';

  // ── Clock ─────────────────────────────────────────────────────
  const sbTime = document.getElementById('sb-time');
  function updateClock() {
    const now = new Date();
    sbTime.textContent = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }
  updateClock();
  setInterval(updateClock, 1000);

  // ── Tab switching ─────────────────────────────────────────────
  const tabBtns = document.querySelectorAll('.tab-btn');
  const tabPanels = document.querySelectorAll('.tab-panel');

  function switchTab(tabId, smooth) {
    tabBtns.forEach(b => b.classList.remove('active'));
    tabPanels.forEach(p => p.classList.remove('active'));
    const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
    const panel = document.getElementById(`tab-${tabId}`);
    if (btn) btn.classList.add('active');
    if (panel) panel.classList.add('active');
  }

  tabBtns.forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));

  // ── Status bar helpers ────────────────────────────────────────
  const sbDot = document.getElementById('sb-status');
  const sbMsg = document.getElementById('sb-msg');

  function setStatus(state, msg) {
    sbDot.className = `sb-dot ${state}`;
    sbMsg.textContent = msg;
  }

  // ── AI banner helpers ─────────────────────────────────────────
  const aiBanner   = document.getElementById('ai-banner');
  const aiStatusMsg = document.getElementById('ai-status-msg');
  const aiProgressFill = document.getElementById('ai-progress-fill');
  const aiBannerCheck  = document.getElementById('ai-banner-check');

  function showBanner(msg, progress) {
    aiBanner.classList.remove('hidden');
    aiBannerCheck.classList.add('hidden');
    aiStatusMsg.textContent = msg;
    if (progress !== undefined) aiProgressFill.style.width = `${progress}%`;
  }

  function completeBanner() {
    aiStatusMsg.textContent = 'Extraction complete!';
    aiProgressFill.style.width = '100%';
    document.querySelector('.ai-spinner').style.display = 'none';
    aiBannerCheck.classList.remove('hidden');
    setTimeout(() => { aiBanner.classList.add('hidden'); }, 4000);
  }

  // ── Typing / fill animation ───────────────────────────────────
  // Each call queues behind the previous so fields fill one at a time.
  let fillQueue = Promise.resolve();

  function typeValue(input, value) {
    fillQueue = fillQueue.then(() => new Promise(resolve => {
      const str = String(value);
      if (!str) { resolve(); return; }

      // Switch to the field's tab first
      const tabId = input.dataset.tab;
      if (tabId) switchTab(tabId, true);

      // Scroll the field into view
      input.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

      // ── SELECT elements: instant set + flash ──────────────────
      if (input.tagName === 'SELECT') {
        input.value = str;
        input.dispatchEvent(new Event('change')); // fire any onchange handlers (e.g. finance toggle)
        input.classList.add('auto-filling');
        // Mark the tab as having data
        const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
        if (btn) btn.classList.add('has-data');
        setTimeout(() => {
          input.classList.remove('auto-filling');
          input.classList.add('auto-filled');
          setTimeout(() => { input.classList.remove('auto-filled'); resolve(); }, 600);
        }, 120);
        return;
      }

      // ── TEXTAREA elements: same as input (char-by-char) ──────
      // ── INPUT elements: character-by-character typing ─────────
      input.value = '';
      input.classList.add('auto-filling');

      const speed = Math.max(18, Math.min(55, 600 / str.length));
      let i = 0;

      const tick = () => {
        if (i < str.length) {
          input.value += str[i++];
          setTimeout(tick, speed);
        } else {
          input.classList.remove('auto-filling');
          input.classList.add('auto-filled');
          // Mark the tab as having data
          const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
          if (btn) btn.classList.add('has-data');
          setTimeout(() => { input.classList.remove('auto-filled'); resolve(); }, 600);
        }
      };
      tick();
    }));
  }

  function findField(key) {
    return document.querySelector(`[data-field="${key}"]`);
  }

  // ── Locations renderer ────────────────────────────────────────
  function renderLocation(index, data) {
    const container = document.getElementById('locations-container');
    // Clear placeholder on first location
    if (index === 0) container.innerHTML = '';

    const card = document.createElement('div');
    card.className = 'location-card';
    card.innerHTML = `
      <div class="location-card-header">
        <span class="loc-badge">LOC ${data.location_number || (index + 1)}</span>
        ${data.address || 'Address not found'}
      </div>
      <div class="location-grid">
        ${locField('Building Value', data.building_value)}
        ${locField('BPP Value', data.bpp_value)}
        ${locField('Year Built', data.year_built)}
        ${locField('Construction', data.construction_type)}
        ${locField('Occupancy', data.occupancy)}
        ${locField('Sq. Footage', data.square_footage)}
        ${locField('Stories', data.num_stories)}
        ${locField('Description', data.building_description)}
        ${locField('Roof Type', data.roof_type)}
        ${locField('Roof Year', data.roof_year)}
        ${locField('Wiring Year', data.wiring_year)}
        ${locField('Plumbing Year', data.plumbing_year)}
        ${locField('HVAC Year', data.hvac_year)}
        ${locField('Sprinklered', data.sprinklered)}
        ${locField('Alarm Type', data.alarm_type)}
        ${locField('Dist. to Hydrant', data.distance_to_hydrant)}
        ${locField('Dist. to Station', data.distance_to_station)}
        ${locField('Flood Zone', data.flood_zone)}
        ${locField('Earthquake Zone', data.earthquake_zone)}
        ${locField('County', data.county)}
        ${locField('Territory Code', data.territory_code)}
        ${locField('Other Structures (Cov B)', data.other_structures)}
        ${locField('Rental Value', data.rental_value)}
        ${locField('Flood Deductible', data.flood_deductible)}
        ${locField('Earthquake Deductible', data.earthquake_deductible)}
        ${locField('Deductible Type', data.deductible_type_code)}
      </div>
    `;
    container.appendChild(card);

    const btn = document.querySelector('.tab-btn[data-tab="locations"]');
    if (btn) btn.classList.add('has-data');
  }

  function locField(label, value) {
    return `<div class="loc-field">
      <label>${label}</label>
      <span>${value || '—'}</span>
    </div>`;
  }

  // ── SSE handler ───────────────────────────────────────────────
  function connectSSE(sessionId) {
    const es = new EventSource(`/api/stream/${sessionId}`);

    es.onmessage = (e) => {
      const data = JSON.parse(e.data);

      if (data.type === 'connected') return;
      if (data.type === 'ping') return;

      if (data.type === 'status') {
        const phaseProgress = { reading: 5, extracting: 30, populating: 55 };
        showBanner(data.message, phaseProgress[data.phase] || 50);
        setStatus('working', data.message);
        return;
      }

      if (data.type === 'field') {
        showBanner(
          `Populating fields… ${data.label}`,
          data.progress ? Math.max(55, 55 + data.progress * 0.45) : undefined
        );
        const input = findField(data.key);
        if (input) {
          typeValue(input, data.value);
          // Special: also update premium display
          if (data.key === 'premium.total_premium') {
            document.getElementById('premium-total-display').textContent = data.value;
          }
        }
        return;
      }

      if (data.type === 'location') {
        renderLocation(data.index, data.data);
        return;
      }

      if (data.type === 'complete') {
        fillQueue = fillQueue.then(() => {
          completeBanner();
          setStatus('done', `Extraction complete — policy data loaded`);
          document.getElementById('upload-label').textContent = 'Upload Another PDF';
        });
        es.close();
        return;
      }

      if (data.type === 'error') {
        aiBanner.classList.add('hidden');
        setStatus('error', `Error: ${data.message}`);
        es.close();
        return;
      }
    };

    es.onerror = () => {
      setStatus('error', 'Connection lost — please refresh and try again');
      es.close();
    };
  }

  // ── File upload ───────────────────────────────────────────────
  async function uploadFile(file) {
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
      alert('Please select a PDF file.');
      return;
    }

    // Reset all fields
    document.querySelectorAll('[data-field]').forEach(el => {
      el.value = '';
      el.classList.remove('auto-filling', 'auto-filled');
    });
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('has-data'));
    document.getElementById('locations-container').innerHTML = `
      <div class="locations-empty">
        <svg viewBox="0 0 16 16" width="32" height="32"><path fill="currentColor" d="M8 16s6-5.686 6-10A6 6 0 0 0 2 6c0 4.314 6 10 6 10zm0-7a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"/></svg>
        <p>Locations will populate after PDF extraction</p>
      </div>`;
    document.getElementById('premium-total-display').textContent = '—';
    fillQueue = Promise.resolve();

    document.getElementById('upload-label').textContent = `Processing: ${file.name}`;
    showBanner('Uploading PDF…', 2);
    setStatus('working', `Uploading ${file.name}…`);
    switchTab('policy');

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      const json = await res.json();
      if (json.error) { setStatus('error', json.error); return; }
      connectSSE(json.session_id);
    } catch (err) {
      setStatus('error', `Upload failed: ${err.message}`);
    }
  }

  // ── File input binding ────────────────────────────────────────
  document.getElementById('pdf-input').addEventListener('change', (e) => {
    if (e.target.files[0]) uploadFile(e.target.files[0]);
    e.target.value = '';
  });

  // ── Drag & drop on entire page ────────────────────────────────
  const dropOverlay = document.getElementById('drop-overlay');

  let dragCounter = 0;
  document.addEventListener('dragenter', (e) => {
    e.preventDefault();
    dragCounter++;
    if (dragCounter === 1) dropOverlay.classList.add('active');
  });
  document.addEventListener('dragleave', () => {
    dragCounter--;
    if (dragCounter <= 0) { dragCounter = 0; dropOverlay.classList.remove('active'); }
  });
  document.addEventListener('dragover', (e) => e.preventDefault());
  document.addEventListener('drop', (e) => {
    e.preventDefault();
    dragCounter = 0;
    dropOverlay.classList.remove('active');
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  });

  // ── Premium Finance show/hide ─────────────────────────────────
  window.toggleFinanceFields = function (value) {
    document.querySelectorAll('.finance-conditional').forEach(el => {
      el.classList.toggle('visible', value === 'Yes');
    });
  };

  // ── Save button (mock) ────────────────────────────────────────
  window.savePolicy = function () {
    setStatus('done', 'Policy saved to AMS (demo mode)');
    const btn = document.querySelector('.btn-primary');
    btn.textContent = '✓ Saved';
    btn.style.background = '#1d7a4a';
    setTimeout(() => {
      btn.innerHTML = `<svg viewBox="0 0 16 16" width="13" height="13"><path fill="currentColor" d="M2 1a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V2a1 1 0 0 0-1-1H9.5a1 1 0 0 0-1 1v7.293l2.646-2.647a.5.5 0 0 1 .708.708l-3.5 3.5a.5.5 0 0 1-.708 0l-3.5-3.5a.5.5 0 1 1 .708-.708L7.5 9.293V2a2 2 0 0 1 2-2H14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h2.5a.5.5 0 0 1 0 1H2z"/></svg> Save Policy`;
      btn.style.background = '';
    }, 2500);
  };

})();
