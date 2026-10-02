// SPDX-License-Identifier: AGPL-3.0-or-later
// WebAuthn (security keys / passkeys): registration on the security page, login on the 2FA page.
// Containers carry data-options-url / data-verify-url; status text goes to [data-webauthn-status].
// Error text comes from the server (JSON {error}); this file holds no user-facing strings.
(function () {
  function b64urlToBuf(s) {
    s = s.replace(/-/g, "+").replace(/_/g, "/");
    while (s.length % 4) s += "=";
    const bin = atob(s);
    const buf = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
    return buf.buffer;
  }
  function bufToB64url(buf) {
    const bytes = new Uint8Array(buf);
    let bin = "";
    for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
    return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }
  function csrf() {
    const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  function post(url, body) {
    return fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { "X-CSRFToken": csrf(), "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : "{}",
    }).then(function (r) { return r.json().then(function (d) { if (!r.ok) throw new Error(d.error || r.status); return d; }); });
  }
  function status(box, text) { const el = box.querySelector("[data-webauthn-status]"); if (el) el.textContent = text; }

  document.addEventListener("click", function (e) {
    const btn = e.target.closest("[data-webauthn]");
    if (!btn || !window.PublicKeyCredential) return;
    const mode = btn.getAttribute("data-webauthn");
    const box = btn.closest("[data-options-url]");
    if (!box) return;
    btn.disabled = true;
    if (mode === "register") {
      post(box.dataset.optionsUrl).then(function (o) {
        o.challenge = b64urlToBuf(o.challenge);
        o.user.id = b64urlToBuf(o.user.id);
        (o.excludeCredentials || []).forEach(function (c) { c.id = b64urlToBuf(c.id); });
        return navigator.credentials.create({ publicKey: o });
      }).then(function (cred) {
        const nameInput = document.getElementById("webauthn-name");
        return post(box.dataset.verifyUrl, {
          name: nameInput ? nameInput.value : "",
          credential: {
            id: cred.id, rawId: bufToB64url(cred.rawId), type: cred.type,
            response: {
              clientDataJSON: bufToB64url(cred.response.clientDataJSON),
              attestationObject: bufToB64url(cred.response.attestationObject),
              transports: cred.response.getTransports ? cred.response.getTransports() : [],
            },
          },
        });
      }).then(function (d) { window.location = d.redirect; })
        .catch(function (err) { status(box, err.message); btn.disabled = false; });
    } else if (mode === "login") {
      post(box.dataset.optionsUrl).then(function (o) {
        o.challenge = b64urlToBuf(o.challenge);
        (o.allowCredentials || []).forEach(function (c) { c.id = b64urlToBuf(c.id); });
        return navigator.credentials.get({ publicKey: o });
      }).then(function (cred) {
        return post(box.dataset.verifyUrl, {
          id: cred.id, rawId: bufToB64url(cred.rawId), type: cred.type,
          response: {
            clientDataJSON: bufToB64url(cred.response.clientDataJSON),
            authenticatorData: bufToB64url(cred.response.authenticatorData),
            signature: bufToB64url(cred.response.signature),
            userHandle: cred.response.userHandle ? bufToB64url(cred.response.userHandle) : null,
          },
        });
      }).then(function (d) { window.location = d.redirect; })
        .catch(function (err) { status(box, err.message); btn.disabled = false; });
    }
  });
})();
