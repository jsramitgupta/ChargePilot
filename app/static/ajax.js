// Lightweight AJAX navigation and form handling for ChargePilot
(function () {
  const mainSelector = 'main';
  const mainEl = document.querySelector(mainSelector);
  if (!mainEl) return;
  let discoveredLanDevices = [];
  let linkedSmartLifeDevices = [];
  let selectedLanDeviceId = null;
  let smartLifePollTimer = null;

  function setMappingWizardStep(step) {
    const modal = document.getElementById('mapping-modal');
    if (!modal) return;
    const currentStep = Math.max(1, Math.min(4, Number(step) || 1));
    modal.dataset.currentStep = String(currentStep);
    modal.querySelectorAll('[data-mapping-wizard-step]').forEach((panel) => {
      const isCurrent = Number(panel.dataset.mappingWizardStep) === currentStep;
      panel.classList.toggle('hidden', !isCurrent);
      panel.hidden = !isCurrent;
    });
    modal.querySelectorAll('[data-mapping-progress]').forEach((indicator) => {
      const number = Number(indicator.dataset.mappingProgress);
      indicator.classList.toggle('is-current', number === currentStep);
      indicator.classList.toggle('is-complete', number < currentStep);
      if (number === currentStep) indicator.setAttribute('aria-current', 'step');
      else indicator.removeAttribute('aria-current');
    });
    const back = document.getElementById('mapping-wizard-back');
    const next = modal.querySelector('[data-mapping-wizard-next]');
    const submit = modal.querySelector('[data-mapping-wizard-submit]');
    if (back) back.hidden = currentStep === 1;
    if (next) next.hidden = currentStep === 4;
    if (submit) submit.hidden = currentStep !== 4;
    if (currentStep === 4) updateMappingSummary();
  }

  function updateMappingSummary() {
    const selectedText = (id) => {
      const select = document.getElementById(id);
      return select?.selectedOptions[0]?.textContent.trim() || 'Not selected';
    };
    const deviceId = document.getElementById('deviceSelect')?.value;
    const deviceName = deviceId
      ? document.querySelector(`[data-device-group="${CSS.escape(deviceId)}"] .channel-picker-device-name`)?.textContent.trim()
      : '';
    const channelSelect = document.getElementById('channelSelect');
    const channelOption = channelSelect?.selectedOptions[0];
    const channelText = channelSelect?.value
      ? channelOption?.textContent.trim().split(' - ').slice(-1)[0]
      : 'Default device state';
    const values = {
      'mapping-summary-endpoint': selectedText('endpoint_id'),
      'mapping-summary-device': deviceName || 'Not selected',
      'mapping-summary-channel': channelText || 'Default device state',
      'mapping-summary-on-threshold': `${document.getElementById('on_threshold')?.value || 0}% or below`,
      'mapping-summary-off-threshold': `${document.getElementById('off_threshold')?.value || 0}% or above`,
      'mapping-summary-interval': `${document.getElementById('minimum_state_change_interval')?.value || 0} seconds`,
    };
    Object.entries(values).forEach(([id, value]) => {
      const element = document.getElementById(id);
      if (element) element.textContent = value;
    });
  }

  function initializeMappingWizard() {
    if (document.getElementById('mapping-modal')) setMappingWizardStep(1);
  }

  function openMappingWizard() {
    const modal = document.getElementById('mapping-modal');
    const form = document.getElementById('mapping-wizard-form');
    if (!modal || !form) return;
    form.reset();
    syncChannelPickerToDevice();
    setMappingWizardStep(1);
    modal.dataset.returnFocus = document.activeElement?.id || 'open-mapping-wizard';
    modal.classList.remove('hidden');
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => document.getElementById('endpoint_id')?.focus());
  }

  function closeMappingWizard() {
    const modal = document.getElementById('mapping-modal');
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => {
      if (modal.getAttribute('aria-hidden') === 'true') {
        modal.classList.add('hidden');
        document.getElementById(modal.dataset.returnFocus)?.focus();
      }
    }, 180);
  }

  async function openAgentGuide() {
    const modal = document.getElementById('agent-guide-modal');
    const content = document.getElementById('agent-guide-content');
    if (!modal || !content) return;
    modal.dataset.returnFocus = 'open-agent-guide';
    modal.classList.remove('hidden');
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    modal.querySelector('.agent-guide-close')?.focus();

    if (modal.dataset.loaded === 'true') return;
    content.innerHTML = '<div class="agent-guide-loading"><span class="agent-guide-spinner" aria-hidden="true"></span>Preparing your secure install guide…</div>';
    try {
      const response = await fetch('/agent/guide', { headers: { Accept: 'text/html' } });
      if (!response.ok) {
        if (response.status === 401) throw new Error('Your session has expired. Sign in again to access agent setup.');
        throw new Error(`Could not load agent setup (HTTP ${response.status}).`);
      }
      content.innerHTML = await response.text();
      modal.dataset.loaded = 'true';
      content.querySelector('[data-copy-target]')?.focus({ preventScroll: true });
    } catch (error) {
      console.error('Agent setup guide failed to load', error);
      content.innerHTML = '';
      const message = document.createElement('p');
      message.className = 'agent-guide-error';
      message.setAttribute('role', 'alert');
      message.textContent = error.message || 'Could not load agent setup. Please try again.';
      const retry = document.createElement('button');
      retry.type = 'button';
      retry.className = 'agent-guide-retry';
      retry.textContent = 'Try again';
      retry.addEventListener('click', () => {
        modal.dataset.loaded = '';
        openAgentGuide();
      });
      content.append(message, retry);
    }
  }

  function closeAgentGuide() {
    const modal = document.getElementById('agent-guide-modal');
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
    window.setTimeout(() => {
      if (modal.getAttribute('aria-hidden') === 'true') {
        modal.classList.add('hidden');
        document.getElementById(modal.dataset.returnFocus)?.focus();
      }
    }, 180);
  }

  function validateMappingStep(step) {
    const panel = document.querySelector(`[data-mapping-wizard-step="${step}"]`);
    if (!panel) return true;
    if (step === 2) {
      const deviceId = document.getElementById('deviceSelect')?.value;
      if (!deviceId) {
        document.querySelector('[data-mapping-wizard-step="2"] [data-channel-group-toggle]')?.focus();
        return false;
      }
      const hasChannels = Boolean(document.querySelector(`[data-device-group="${CSS.escape(deviceId)}"] [data-picker-channel]`));
      if (hasChannels && !document.querySelector(`[data-device-group="${CSS.escape(deviceId)}"] [data-picker-channel][aria-pressed="true"]`)) {
        document.querySelector(`[data-device-group="${CSS.escape(deviceId)}"] [data-picker-channel]`)?.focus();
        return false;
      }
      return true;
    }
    for (const field of panel.querySelectorAll('input, select')) {
      if (!field.checkValidity()) {
        field.reportValidity();
        return false;
      }
    }
    return true;
  }

  function updateActiveNavigation() {
    const currentPath = window.location.pathname.replace(/\/+$/, '') || '/';
    document.querySelectorAll('#mainNav a[href]').forEach((link) => {
      const linkPath = new URL(link.href, window.location.href).pathname.replace(/\/+$/, '') || '/';
      if (linkPath === currentPath) {
        link.setAttribute('aria-current', 'page');
      } else {
        link.removeAttribute('aria-current');
      }
    });
  }

  function updateChannelPickerSelection(channelId) {
    const deviceSelect = document.getElementById('deviceSelect');
    const channelSelect = document.getElementById('channelSelect');
    const picker = document.getElementById('channel-picker');
    const selectedLabel = document.getElementById('channel-picker-selected');
    if (!deviceSelect || !channelSelect || !picker || !selectedLabel) return;

    channelSelect.value = channelId || '';
    const selectedOption = channelSelect.selectedOptions[0];
    const selectedDevice = picker.querySelector(`[data-device-group="${CSS.escape(deviceSelect.value)}"] .channel-picker-device-name`);
    if (!deviceSelect.value) {
      selectedLabel.textContent = 'Choose an available switch';
    } else if (channelSelect.value) {
      selectedLabel.textContent = selectedOption?.textContent.trim() || 'Choose a switch channel';
    } else {
      selectedLabel.textContent = `${selectedDevice?.textContent.trim() || 'Switch'} · Default state`;
    }
    picker.querySelectorAll('[data-picker-channel]').forEach((button) => {
      const selected = button.dataset.pickerChannel === channelSelect.value;
      button.setAttribute('aria-pressed', String(selected));
      button.classList.toggle('is-selected', selected);
    });
    picker.querySelectorAll('[data-picker-default]').forEach((button) => {
      const selected = button.dataset.pickerDefault === deviceSelect.value && !channelSelect.value;
      button.setAttribute('aria-pressed', String(selected));
      button.classList.toggle('is-selected', selected);
    });
    picker.querySelectorAll('.channel-picker-group').forEach((group) => {
      group.classList.toggle('is-selected', group.dataset.deviceGroup === deviceSelect.value);
    });
  }

  function syncChannelPickerToDevice() {
    const deviceSelect = document.getElementById('deviceSelect');
    const channelSelect = document.getElementById('channelSelect');
    const picker = document.getElementById('channel-picker');
    if (!deviceSelect || !channelSelect || !picker) return;

    const deviceId = deviceSelect.value;
    const currentOption = channelSelect.selectedOptions[0];
    const currentOptionMatches = currentOption?.dataset.deviceId === deviceId;
    if (!currentOptionMatches) channelSelect.value = '';
    updateChannelPickerSelection(channelSelect.value);

    picker.querySelectorAll('.channel-picker-group').forEach((group) => {
      const isCurrentDevice = group.dataset.deviceGroup === deviceId;
      const toggle = group.querySelector('[data-channel-group-toggle]');
      const panel = group.querySelector('.channel-picker-options');
      if (isCurrentDevice) {
        group.classList.add('is-open');
        toggle?.setAttribute('aria-expanded', 'true');
        panel?.classList.remove('hidden');
      } else {
        group.classList.remove('is-open');
        toggle?.setAttribute('aria-expanded', 'false');
        panel?.classList.add('hidden');
      }
    });
  }

  function initializeChannelPicker() {
    syncChannelPickerToDevice();
  }

  updateActiveNavigation();
  initializeChannelPicker();
  initializeMappingWizard();

  function navigateIfRedirected(response) {
    if (!response.redirected) return false;
    window.location.assign(response.url);
    return true;
  }

  async function replaceMainWithHtml(htmlText, pushUrl) {
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(htmlText, 'text/html');
      const newMain = doc.querySelector(mainSelector);
      const currentNav = document.querySelector('#mainNav');
      const nextNav = doc.querySelector('#mainNav');
      if (Boolean(currentNav) !== Boolean(nextNav)) {
        window.location.assign(pushUrl || window.location.href);
        return;
      }
      if (newMain) {
        mainEl.innerHTML = newMain.innerHTML;
        initializeChannelPicker();
        initializeMappingWizard();
        if (pushUrl) {
          history.pushState({ ajax: true }, '', pushUrl);
          updateActiveNavigation();
        }
        // Re-run any inline initialization from base.html
        if (window.applyTheme) try { window.applyTheme(); } catch (e) {}
        if (window.applyTimezone) try { window.applyTimezone(); } catch (e) {}
      }
    } catch (err) {
      console.error('Failed to replace main content', err);
    }
  }

  async function handleAjaxSubmit(event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.hasAttribute('data-no-ajax')) return;
    const enctype = form.enctype || '';
    if (enctype.includes('multipart/form-data')) return; // skip file uploads
    event.preventDefault();
    if (form.id === 'mapping-wizard-form') {
      for (const step of [1, 2, 3]) {
        if (!validateMappingStep(step)) {
          setMappingWizardStep(step);
          return;
        }
      }
    }

    const action = form.action || window.location.href;
    const method = (form.method || 'GET').toUpperCase();
    const formData = new FormData(form);

    try {
      const resp = await fetch(action, {
        method,
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          Accept: 'application/json',
        },
        body: method === 'GET' ? null : formData,
      });

      if (navigateIfRedirected(resp)) return;

      const contentType = resp.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        const json = await resp.json();
        if (json.error) {
          alert(json.error);
          return;
        }
        if (json.redirect) {
          const r = await fetch(json.redirect, { headers: { Accept: 'text/html' } });
          const text = await r.text();
          await replaceMainWithHtml(text, json.redirect);
        }
        return;
      }

      // Fallback: server returned HTML (e.g., full page)
      const text = await resp.text();
      await replaceMainWithHtml(text, action);
    } catch (err) {
      console.error('AJAX form submit failed', err);
      alert('Request failed; please try again.');
    }
  }

  // Intercept form submits
  document.addEventListener('submit', function (ev) {
    const form = ev.target;
    if (!(form instanceof HTMLFormElement)) return;
    // Only intercept same-origin requests
    try {
      const url = new URL(form.action || window.location.href, window.location.href);
      if (url.origin !== window.location.origin) return;
    } catch (e) {
      return;
    }
    handleAjaxSubmit(ev);
  });

  // Intercept link clicks for same-origin navigation
  document.addEventListener('click', function (ev) {
    const a = ev.target.closest && ev.target.closest('a');
    if (!a) return;
    if (a.hasAttribute('data-no-ajax')) return;
    if (a.target && a.target !== '_self') return;
    const href = a.getAttribute('href');
    if (!href || href.startsWith('#')) return;
    try {
      const url = new URL(href, window.location.href);
      if (url.origin !== window.location.origin) return;
    } catch (e) { return; }

    if (a.closest('#agent-guide-modal')) closeAgentGuide();
    ev.preventDefault();
    fetch(href, { headers: { Accept: 'text/html' } })
      .then(async (response) => {
        if (navigateIfRedirected(response)) return null;
        return response.text();
      })
      .then((text) => {
        if (text !== null) return replaceMainWithHtml(text, href);
      })
      .catch((err) => {
        console.error('AJAX nav failed', err);
        window.location.href = href; // fallback
      });
  });

  window.addEventListener('popstate', function (ev) {
    updateActiveNavigation();
    fetch(window.location.href, { headers: { Accept: 'text/html' } })
      .then((r) => r.text())
      .then((text) => replaceMainWithHtml(text, window.location.href))
      .catch((err) => console.error('popstate fetch failed', err));
  });

  function setWizardStatus(message, isError = false) {
    const status = document.getElementById('device-wizard-status');
    if (!status) return;
    status.textContent = message;
    status.className = `mt-4 text-sm ${isError ? 'text-red-700' : 'text-slate-600'}`;
  }

  function updateSwitchVisualState(form, isOn) {
    const input = form.querySelector('.device-toggle-input');
    if (input) input.checked = isOn;

    const deviceCard = form.closest('.switch-device-card');
    if (deviceCard && !form.dataset.channelId) {
      deviceCard.dataset.state = isOn ? 'on' : 'off';
      const indicator = deviceCard.querySelector('.switch-state-light');
      const stateLabel = deviceCard.querySelector('.switch-state-label');
      if (indicator) indicator.classList.toggle('is-on', isOn);
      if (stateLabel) stateLabel.textContent = isOn ? 'ON' : 'OFF';
      deviceCard.classList.remove('switch-state-changed');
      void deviceCard.offsetWidth;
      deviceCard.classList.add('switch-state-changed');
      window.setTimeout(() => deviceCard.classList.remove('switch-state-changed'), 650);
    }

    const channelRow = form.closest('.switch-channel-row');
    if (channelRow) {
      channelRow.dataset.state = isOn ? 'on' : 'off';
      const stateLabel = channelRow.querySelector('.channel-state-label');
      if (stateLabel) stateLabel.textContent = isOn ? 'On' : 'Off';
      channelRow.classList.remove('switch-state-changed');
      void channelRow.offsetWidth;
      channelRow.classList.add('switch-state-changed');
      window.setTimeout(() => channelRow.classList.remove('switch-state-changed'), 650);
    }
  }

  function selectLanDevice(device) {
    const panel = document.getElementById('manual-add-panel');
    if (!panel) return;
    selectedLanDeviceId = device.device_id;
    document.getElementById('wizard_device_name').value = device.name;
    document.getElementById('wizard_device_id').value = device.device_id;
    document.getElementById('wizard_ip_address').value = device.ip_address === 'unknown' ? '' : device.ip_address;
    document.getElementById('wizard_device_type').value = device.device_type || 'switch';
    document.getElementById('wizard_protocol_version').value = device.protocol_version || '3.5';
    document.getElementById('wizard_local_key').value = '';
    panel.classList.remove('hidden');
    setWizardStatus('Device details selected. The local key remains blank until you retrieve or enter it.');
    applyLinkedKeyForSelectedDevice();
    renderLinkedDevices();
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function renderLanDevices() {
    const panel = document.getElementById('local-scan-results');
    const list = document.getElementById('local-scan-list');
    const count = document.getElementById('local-scan-count');
    if (!panel || !list || !count) return;
    panel.classList.remove('hidden');
    count.textContent = String(discoveredLanDevices.length);
    list.replaceChildren();

    if (!discoveredLanDevices.length) {
      const empty = document.createElement('p');
      empty.className = 'rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-500';
      empty.textContent = 'No Tuya devices were found. Make sure the switch is powered on and this server is connected to the same local network.';
      list.append(empty);
      return;
    }

    discoveredLanDevices.forEach((device) => {
      const card = document.createElement('article');
      card.className = 'rounded-xl border border-slate-200 bg-white p-3';
      const header = document.createElement('div');
      header.className = 'flex items-start justify-between gap-3';
      const details = document.createElement('div');
      details.className = 'min-w-0';
      const title = document.createElement('h4');
      title.className = 'truncate text-sm font-bold text-slate-900';
      title.textContent = device.name;
      const meta = document.createElement('p');
      meta.className = 'mt-1 break-all text-xs leading-5 text-slate-500';
      meta.textContent = `${device.ip_address} · ${device.device_id} · Protocol ${device.protocol_version}`;
      details.append(title, meta);
      const add = document.createElement('button');
      add.type = 'button';
      add.className = 'shrink-0 rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300';
      add.textContent = device.already_added ? 'Added' : 'Use device';
      add.disabled = device.already_added;
      add.addEventListener('click', () => selectLanDevice(device));
      header.append(details, add);
      card.append(header);
      if (device.already_added) {
        const note = document.createElement('p');
        note.className = 'mt-2 text-xs text-slate-500';
        note.textContent = 'This device is already configured in ChargePilot.';
        card.append(note);
      }
      list.append(card);
    });
  }

  function applyLinkedKeyForSelectedDevice() {
    const selectedId = document.getElementById('wizard_device_id')?.value;
    if (!selectedId || selectedId !== selectedLanDeviceId) return;
    const linked = linkedSmartLifeDevices.find((device) => device.device_id === selectedLanDeviceId && device.local_key);
    if (linked) {
      document.getElementById('wizard_local_key').value = linked.local_key;
      const keyStatus = document.getElementById('wizard-local-key-status');
      if (keyStatus) keyStatus.textContent = 'Smart Life key matched to the selected LAN device and filled in automatically.';
      setWizardStatus('Local key retrieved from Smart Life for the selected LAN device.');
      return true;
    }
    return false;
  }

  function renderLinkedDevices() {
    const container = document.getElementById('smartlife-linked-devices');
    if (!container) return;
    container.replaceChildren();
    container.classList.remove('hidden');

    if (!linkedSmartLifeDevices.length) {
      const empty = document.createElement('p');
      empty.className = 'rounded-xl bg-white p-3 text-xs leading-5 text-slate-600';
      empty.textContent = 'Smart Life connected, but no local keys were returned for its devices.';
      container.append(empty);
      return;
    }

    const selectedId = document.getElementById('wizard_device_id')?.value;
    const hasSelectedLanDevice = selectedId === selectedLanDeviceId
      && discoveredLanDevices.some((lanDevice) => lanDevice.device_id === selectedLanDeviceId);

    linkedSmartLifeDevices.forEach((device) => {
      const row = document.createElement('div');
      const matched = hasSelectedLanDevice && device.device_id === selectedLanDeviceId;
      row.className = `flex items-center justify-between gap-3 rounded-xl border p-3 ${matched ? 'border-emerald-300 bg-emerald-50' : 'border-emerald-200 bg-white'}`;
      const title = document.createElement('div');
      title.className = 'min-w-0';
      const id = document.createElement('p');
      id.className = 'break-all text-xs font-semibold text-slate-800';
      id.textContent = device.device_id;
      title.append(id);
      const matchStatus = document.createElement('span');
      matchStatus.className = `shrink-0 rounded-full px-2.5 py-1 text-[10px] font-semibold ${matched ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'}`;
      matchStatus.textContent = matched ? 'Matched automatically' : 'Select matching LAN device';
      row.append(title, matchStatus);
      container.append(row);
    });
    applyLinkedKeyForSelectedDevice();
  }

  async function pollSmartLifeLogin(loginId) {
    try {
      const pollUrl = document.getElementById('start-smartlife-login')?.dataset.pollUrl;
      if (!pollUrl) throw new Error('Smart Life pairing route is not available on this page.');
      const response = await fetch(pollUrl.replace('__LOGIN_ID__', encodeURIComponent(loginId)), {
        headers: { Accept: 'application/json' },
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || 'Could not check Smart Life sign-in.');

      const status = document.getElementById('smartlife-login-status');
      if (result.status === 'pending') {
        if (status) status.textContent = 'Waiting for you to scan the QR code and confirm sign-in in the app…';
        smartLifePollTimer = window.setTimeout(() => pollSmartLifeLogin(loginId), 2000);
        return;
      }
      if (result.status === 'expired') {
        if (status) status.textContent = 'This QR code expired. Start again to generate a fresh code.';
        document.getElementById('smartlife-qr-frame')?.classList.add('hidden');
        return;
      }

      linkedSmartLifeDevices = result.devices || [];
      renderLinkedDevices();
      const matched = applyLinkedKeyForSelectedDevice();
      if (status) {
        status.textContent = matched
          ? 'Connected! The matching local key was added to the form automatically.'
          : `Connected. ${linkedSmartLifeDevices.length} local key(s) retrieved. Select the matching LAN device to auto-fill its key.`;
      }
    } catch (error) {
      const status = document.getElementById('smartlife-login-status');
      if (status) status.textContent = error.message;
      console.error('Smart Life sign-in polling failed', error);
    }
  }

  function openSmartLifeModal() {
    const modal = document.getElementById('smartlife-modal');
    if (!modal) return;
    const openButton = document.getElementById('open-smartlife-modal');
    if (openButton) modal.dataset.returnFocus = openButton.id;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    modal.setAttribute('aria-hidden', 'false');
    requestAnimationFrame(() => modal.classList.add('is-open'));
    window.setTimeout(() => document.getElementById('smartlife_user_code')?.focus(), 80);
  }

  function closeSmartLifeModal() {
    const modal = document.getElementById('smartlife-modal');
    if (!modal) return;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    window.setTimeout(() => {
      if (modal.getAttribute('aria-hidden') === 'true') {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
        document.getElementById(modal.dataset.returnFocus)?.focus();
      }
    }, 180);
  }

  document.addEventListener('click', async (event) => {
    const target = event.target.closest('button');
    if (!target) {
      if (event.target.id === 'smartlife-modal') closeSmartLifeModal();
      if (event.target.id === 'mapping-modal' || event.target.matches('[data-close-mapping-wizard]')) closeMappingWizard();
      return;
    }

    if (target.matches('[data-copy-target]')) {
      const source = document.getElementById(target.dataset.copyTarget);
      const status = document.getElementById('agent-copy-status');
      if (!source) return;
      try {
        await navigator.clipboard.writeText(source.textContent.trim());
        target.textContent = 'Copied';
        if (status) status.textContent = 'Install command copied to clipboard.';
        window.setTimeout(() => { target.textContent = 'Copy'; }, 1800);
      } catch (error) {
        console.error('Could not copy the agent install command', error);
        if (status) status.textContent = 'Copy was blocked by the browser. Select and copy the command manually.';
      }
      return;
    }

    if (target.id === 'open-agent-guide') {
      openAgentGuide();
      return;
    }

    if (target.matches('[data-close-agent-guide]')) {
      closeAgentGuide();
      return;
    }

    if (target.id === 'open-mapping-wizard' || target.matches('[data-open-mapping-wizard]')) {
      openMappingWizard();
      return;
    }

    if (target.id === 'close-mapping-wizard' || target.matches('[data-close-mapping-wizard]')) {
      closeMappingWizard();
      return;
    }

    if (target.matches('[data-mapping-wizard-back]')) {
      setMappingWizardStep(Number(document.getElementById('mapping-modal')?.dataset.currentStep) - 1);
      return;
    }

    if (target.matches('[data-mapping-wizard-next]')) {
      const currentStep = Number(document.getElementById('mapping-modal')?.dataset.currentStep) || 1;
      if (validateMappingStep(currentStep)) setMappingWizardStep(currentStep + 1);
      return;
    }

    if (target.id === 'open-smartlife-modal') {
      openSmartLifeModal();
      return;
    }

    if (target.id === 'close-smartlife-modal') {
      closeSmartLifeModal();
      return;
    }

    if (target.matches('[data-channel-group-toggle]')) {
      const group = target.closest('.channel-picker-group');
      const panelId = target.getAttribute('aria-controls');
      const panel = panelId ? document.getElementById(panelId) : null;
      if (!group || !panel) return;
      const deviceSelect = document.getElementById('deviceSelect');
      const channelSelect = document.getElementById('channelSelect');
      const selectedNewDevice = deviceSelect?.value !== target.dataset.deviceSelect;
      if (deviceSelect) deviceSelect.value = target.dataset.deviceSelect || '';
      if (selectedNewDevice && channelSelect) channelSelect.value = '';
      const isOpen = target.getAttribute('aria-expanded') !== 'true';
      document.querySelectorAll('[data-channel-group-toggle]').forEach((toggle) => {
        const isCurrent = toggle === target && isOpen;
        toggle.setAttribute('aria-expanded', String(isCurrent));
        toggle.closest('.channel-picker-group')?.classList.toggle('is-open', isCurrent);
        const togglePanel = document.getElementById(toggle.getAttribute('aria-controls'));
        togglePanel?.classList.toggle('hidden', !isCurrent);
      });
      if (!isOpen) {
        target.setAttribute('aria-expanded', 'true');
        group.classList.add('is-open');
        panel.classList.remove('hidden');
      }
      updateChannelPickerSelection(channelSelect?.value || '');
      return;
    }

    if (target.matches('[data-picker-channel]')) {
      const deviceSelect = document.getElementById('deviceSelect');
      if (deviceSelect) deviceSelect.value = target.dataset.deviceId || '';
      updateChannelPickerSelection(target.dataset.pickerChannel);
      return;
    }

    if (target.matches('[data-picker-default]')) {
      const deviceSelect = document.getElementById('deviceSelect');
      const channelSelect = document.getElementById('channelSelect');
      if (deviceSelect) deviceSelect.value = target.dataset.pickerDefault || '';
      if (channelSelect) channelSelect.value = '';
      updateChannelPickerSelection('');
      return;
    }

    if (target.id === 'show-manual-add') {
      selectedLanDeviceId = null;
      renderLinkedDevices();
      document.getElementById('manual-add-panel')?.classList.remove('hidden');
      document.getElementById('wizard_device_name')?.focus();
      return;
    }

    if (target.id === 'scan-local-network') {
      target.disabled = true;
      target.setAttribute('aria-busy', 'true');
      setWizardStatus('Searching for Tuya devices on the server’s local network. This may take a few seconds.');
      try {
        if (!target.dataset.scanUrl) {
          throw new Error('The scan route is not available. Restart or update the ChargePilot server, then reload this page.');
        }
        const response = await fetch(target.dataset.scanUrl, {
          method: 'POST',
          headers: { Accept: 'application/json' },
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
          if (response.status === 404) {
            throw new Error('The scan route was not found. Restart or update the ChargePilot server, then reload this page.');
          }
          throw new Error(result.detail || 'Local network scan failed.');
        }
        discoveredLanDevices = result.devices || [];
        renderLanDevices();
        setWizardStatus(`Scan complete. ${discoveredLanDevices.length} device(s) found.`);
      } catch (error) {
        setWizardStatus(error.message, true);
      } finally {
        target.disabled = false;
        target.removeAttribute('aria-busy');
      }
      return;
    }

    if (target.id === 'start-smartlife-login') {
      const userCode = document.getElementById('smartlife_user_code')?.value.trim();
      const status = document.getElementById('smartlife-login-status');
      const qr = document.getElementById('smartlife-login-qr');
      if (!userCode) {
        if (status) status.textContent = 'Enter your Smart Life account ID / user code to continue.';
        document.getElementById('smartlife_user_code')?.focus();
        return;
      }
      target.disabled = true;
      if (status) status.textContent = 'Preparing secure sign-in…';
      if (smartLifePollTimer !== null) window.clearTimeout(smartLifePollTimer);
      try {
        if (!target.dataset.startUrl || !target.dataset.preferenceUrl) {
          throw new Error('Smart Life pairing is not available. Reload the page after updating ChargePilot.');
        }
        const preferenceResponse = await fetch(target.dataset.preferenceUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            user_code: userCode,
            remember: document.getElementById('smartlife_remember_user_code')?.checked || false,
          }),
        });
        const preferenceResult = await preferenceResponse.json();
        if (!preferenceResponse.ok) {
          throw new Error(preferenceResult.detail || 'Could not save the Smart Life account preference.');
        }
        const response = await fetch(target.dataset.startUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify({
            user_code: userCode,
            qr_scheme: document.getElementById('smartlife_qr_scheme')?.value || 'smartlife',
          }),
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.detail || 'Could not start Smart Life sign-in.');
        qr.src = result.qr;
        document.getElementById('smartlife-qr-frame')?.classList.remove('hidden');
        if (status) status.textContent = 'QR ready. Scan it in the Smart Life app (+ → Scan), then approve the sign-in.';
        pollSmartLifeLogin(result.login_id);
      } catch (error) {
        if (status) status.textContent = error.message;
      } finally {
        target.disabled = false;
      }
    }
  });

  document.addEventListener('change', (event) => {
    if (event.target.id === 'deviceSelect') syncChannelPickerToDevice();
    if (event.target.closest('#mapping-wizard-form')) updateMappingSummary();
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.getElementById('smartlife-modal')?.getAttribute('aria-hidden') === 'false') {
      closeSmartLifeModal();
    }
    if (event.key === 'Escape' && document.getElementById('mapping-modal')?.getAttribute('aria-hidden') === 'false') {
      closeMappingWizard();
    }
    if (event.key === 'Escape' && document.getElementById('agent-guide-modal')?.getAttribute('aria-hidden') === 'false') {
      closeAgentGuide();
    }
  });

  document.addEventListener('input', (event) => {
    if (event.target.closest('#mapping-wizard-form')) updateMappingSummary();
  });

  // Poll device states and update toggle checkboxes/actions
  async function pollDeviceStates() {
    try {
      const resp = await fetch('/api/v1/devices', { headers: { Accept: 'application/json' } });
      if (!resp.ok) return;
      const devices = await resp.json();

      // Update device-level toggles (forms without data-channel-id)
      devices.forEach((device) => {
        const selector = `form.state-toggle-form[data-device-id="${device.id}"]:not([data-channel-id])`;
        const form = document.querySelector(selector);
        if (!form) return;
        const input = form.querySelector('.device-toggle-input');
        if (!input) return;
        const shouldBeChecked = !!device.current_state;
        if (input.checked !== shouldBeChecked) updateSwitchVisualState(form, shouldBeChecked);
        // ensure action points to correct endpoint (turn-off when currently on)
        const action = `/devices/${device.id}/${shouldBeChecked ? 'turn-off' : 'turn-on'}`;
        if (form.action && !form.action.endsWith(action)) {
          form.action = action;
        }
      });

      // Find all devices that have channel forms in the DOM and fetch channels per device
      const channelForms = Array.from(document.querySelectorAll('form.state-toggle-form[data-channel-id]'));
      const deviceIds = [...new Set(channelForms.map((f) => f.dataset.deviceId))];
      await Promise.all(
        deviceIds.map(async (did) => {
          try {
            const r = await fetch(`/api/v1/devices/${did}/channels`, { headers: { Accept: 'application/json' } });
            if (!r.ok) return;
            const channels = await r.json();
            channels.forEach((ch) => {
              const sel = `form.state-toggle-form[data-channel-id="${ch.id}"]`;
              const f = document.querySelector(sel);
              if (!f) return;
              const inp = f.querySelector('.device-toggle-input');
              if (!inp) return;
              const shouldBeChecked = !!ch.current_state;
              if (inp.checked !== shouldBeChecked) updateSwitchVisualState(f, shouldBeChecked);
              const action = `/devices/${did}/channels/${ch.id}/${shouldBeChecked ? 'turn-off' : 'turn-on'}`;
              if (f.action && !f.action.endsWith(action)) f.action = action;
            });
          } catch (err) {
            console.error('Failed to fetch channels for device', did, err);
          }
        })
      );
    } catch (err) {
      console.error('Device state poll failed', err);
    }
  }

  function applyEventToDom(item) {
    try {
      if (!item || !item.type) return;
      if (item.type === 'device_state_change') {
        const did = item.device_id;
        const cid = item.channel_id;
        const newState = !!item.new_state;
        if (cid) {
          const sel = `form.state-toggle-form[data-channel-id="${cid}"]`;
          const f = document.querySelector(sel);
          if (f) {
            const inp = f.querySelector('.device-toggle-input');
            if (inp) updateSwitchVisualState(f, newState);
            const action = `/devices/${did}/channels/${cid}/${newState ? 'turn-off' : 'turn-on'}`;
            f.action = action;
          }
        } else {
          const selector = `form.state-toggle-form[data-device-id="${did}"]:not([data-channel-id])`;
          const form = document.querySelector(selector);
          if (form) {
            const input = form.querySelector('.device-toggle-input');
            if (input) updateSwitchVisualState(form, newState);
            const action = `/devices/${did}/${newState ? 'turn-off' : 'turn-on'}`;
            form.action = action;
          }
        }
      } else if (item.type === 'device_updated' || item.type === 'device_created') {
        // simple handling: update device forms if present
        const d = item.device || item.device_id || item.device;
        const id = d && d.id ? d.id : (item.device && item.device.id) || item.device_id;
        if (!id) return;
        const selector = `form[state-toggle-form][data-device-id]`;
        // noop for now; poll will pick up new devices or full page refresh
      }
    } catch (err) {
      console.error('applyEventToDom error', err);
    }
  }

  const sseStatusEl = document.getElementById('sseStatus');
  let pollingTimer = null;

  function updateSseStatus(text, connected) {
    if (!sseStatusEl) return;
    sseStatusEl.textContent = text;
    sseStatusEl.classList.toggle('live-pill', connected);
    sseStatusEl.classList.toggle('mini-badge', true);
  }

  function startPolling() {
    if (pollingTimer !== null) return;
    pollDeviceStates();
    pollingTimer = window.setInterval(pollDeviceStates, 5000);
  }

  function stopPolling() {
    if (pollingTimer === null) return;
    window.clearInterval(pollingTimer);
    pollingTimer = null;
  }

  startPolling();

  if (window.EventSource) {
    try {
      const es = new EventSource('/api/v1/telemetry/stream');

      es.onmessage = function (ev) {
        try {
          const data = JSON.parse(ev.data);
          applyEventToDom(data);
        } catch (err) {
          // ignore parse errors (heartbeats)
        }
      };
      es.onerror = function (ev) {
        console.warn('SSE error, falling back to polling', ev);
        updateSseStatus('Reconnecting', false);
        startPolling();
      };
      es.onopen = function () {
        updateSseStatus('Connected', true);
        stopPolling();
      };
    } catch (err) {
      console.warn('Failed to open SSE connection', err);
      updateSseStatus('Polling', false);
    }
  } else {
    updateSseStatus('Polling', false);
  }

})();
