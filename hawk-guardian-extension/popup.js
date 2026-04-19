/* global chrome */

function $(id) {
  return document.getElementById(id);
}

function setStatus(msg) {
  $("status").textContent = msg || "";
}

chrome.storage.sync.get(["apiBase", "secret", "clientId", "expectedDomain"], (cfg) => {
  $("apiBase").value = cfg.apiBase || "";
  $("secret").value = cfg.secret || "";
  $("clientId").value = cfg.clientId || "";
  $("expectedDomain").value = cfg.expectedDomain || "";
});

$("save").addEventListener("click", () => {
  const apiBase = $("apiBase").value.trim();
  const secret = $("secret").value.trim();
  const clientId = $("clientId").value.trim();
  const expectedDomain = $("expectedDomain").value.trim().toLowerCase();
  chrome.storage.sync.set({ apiBase, secret, clientId, expectedDomain }, () => setStatus("Saved."));
});

$("refresh").addEventListener("click", () => {
  const apiBase = $("apiBase").value.trim();
  const secret = $("secret").value.trim();
  const clientId = $("clientId").value.trim();
  if (!apiBase || !secret || !clientId) {
    setStatus("Fill API base, secret, and client id first.");
    return;
  }
  setStatus("Loading…");
  const url = `${apiBase.replace(/\/$/, "")}/api/guardian/client-profile/${encodeURIComponent(clientId)}`;
  fetch(url, { headers: { "X-Guardian-Extension-Secret": secret } })
    .then(async (r) => {
      const txt = await r.text();
      let j;
      try {
        j = JSON.parse(txt);
      } catch {
        j = { raw: txt };
      }
      if (!r.ok) throw new Error(j.detail || txt || r.status);
      return j;
    })
    .then((body) => {
      $("out").textContent = JSON.stringify(body.profile || body, null, 2);
      setStatus("OK");
    })
    .catch((e) => {
      $("out").textContent = String(e);
      setStatus("Error");
    });
});
