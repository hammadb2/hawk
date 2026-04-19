/* global chrome */

const DEFAULT_ALARM = "hawk-guardian-refresh";

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(DEFAULT_ALARM, { periodInMinutes: 360 });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== DEFAULT_ALARM) return;
  chrome.storage.sync.get(["apiBase", "secret", "clientId"], (cfg) => {
    if (!cfg.apiBase || !cfg.secret || !cfg.clientId) return;
    const url = `${cfg.apiBase.replace(/\/$/, "")}/api/guardian/client-profile/${encodeURIComponent(cfg.clientId)}`;
    fetch(url, { headers: { "X-Guardian-Extension-Secret": cfg.secret } })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        if (body && body.profile) {
          chrome.storage.local.set({ lastProfile: body.profile, lastProfileAt: new Date().toISOString() });
        }
      })
      .catch(() => {});
  });
});
