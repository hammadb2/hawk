/* global chrome */

function normHost(h) {
  return String(h || "")
    .toLowerCase()
    .replace(/^www\./, "");
}

function postEvent(payload) {
  chrome.storage.sync.get(["apiBase", "secret", "clientId", "expectedDomain"], (cfg) => {
    if (!cfg.apiBase || !cfg.secret || !cfg.clientId) return;
    const base = cfg.apiBase.replace(/\/$/, "");
    fetch(`${base}/api/guardian/log-event`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Guardian-Extension-Secret": cfg.secret,
      },
      body: JSON.stringify({
        client_id: cfg.clientId,
        source: "extension",
        ...payload,
      }),
    }).catch(() => {});
  });
}

function checkPasswordContext(el) {
  chrome.storage.sync.get(["expectedDomain", "clientId"], (cfg) => {
    if (!cfg.clientId) return;
    const loc = window.location;
    const host = normHost(loc.hostname);
    const expected = normHost(cfg.expectedDomain || "");
    if (!loc.protocol.startsWith("https")) {
      postEvent({
        event_type: "cleartext_transport",
        severity: "high",
        page_url: loc.href,
        details: { hostname: loc.hostname, reason: "password_field_on_non_https" },
      });
      return;
    }
    if (expected && host && !host.endsWith(expected) && host !== expected) {
      postEvent({
        event_type: "credential_phishing",
        severity: "high",
        page_url: loc.href,
        details: {
          hostname: loc.hostname,
          expected_domain: expected,
          field: el.name || el.id || "password",
        },
      });
    }
  });
}

document.addEventListener(
  "focusin",
  (ev) => {
    const t = ev.target;
    if (!t || t.tagName !== "INPUT") return;
    const type = (t.getAttribute("type") || "").toLowerCase();
    if (type !== "password") return;
    checkPasswordContext(t);
  },
  true,
);
