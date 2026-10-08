// Lightweight AJAX navigation and form handling for ChargePilot
(function () {
  const mainSelector = 'main';
  const mainEl = document.querySelector(mainSelector);
  if (!mainEl) return;

  async function replaceMainWithHtml(htmlText, pushUrl) {
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(htmlText, 'text/html');
      const newMain = doc.querySelector(mainSelector);
      if (newMain) {
        mainEl.innerHTML = newMain.innerHTML;
        if (pushUrl) history.pushState({ ajax: true }, '', pushUrl);
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

    ev.preventDefault();
    fetch(href, { headers: { Accept: 'text/html' } })
      .then((r) => r.text())
      .then((text) => replaceMainWithHtml(text, href))
      .catch((err) => {
        console.error('AJAX nav failed', err);
        window.location.href = href; // fallback
      });
  });

  window.addEventListener('popstate', function (ev) {
    fetch(window.location.href, { headers: { Accept: 'text/html' } })
      .then((r) => r.text())
      .then((text) => replaceMainWithHtml(text, window.location.href))
      .catch((err) => console.error('popstate fetch failed', err));
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
        if (input.checked !== shouldBeChecked) {
          input.checked = shouldBeChecked;
        }
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
              if (inp.checked !== shouldBeChecked) inp.checked = shouldBeChecked;
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

  let sseEnabled = false;

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
            if (inp) inp.checked = newState;
            const action = `/devices/${did}/channels/${cid}/${newState ? 'turn-off' : 'turn-on'}`;
            f.action = action;
          }
        } else {
          const selector = `form.state-toggle-form[data-device-id="${did}"]:not([data-channel-id])`;
          const form = document.querySelector(selector);
          if (form) {
            const input = form.querySelector('.device-toggle-input');
            if (input) input.checked = newState;
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

  if (window.EventSource) {
    try {
      const es = new EventSource('/api/v1/telemetry/stream');
      sseEnabled = true;
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
        sseEnabled = false;
        es.close();
      };
    } catch (err) {
      console.warn('Failed to open SSE connection', err);
      sseEnabled = false;
    }
  }

  if (!sseEnabled) {
    setInterval(pollDeviceStates, 5000);
    // Run once immediately
    pollDeviceStates();
  }

})();
