// SPDX-License-Identifier: AGPL-3.0-or-later
// The local setup page of EVAC Player: saves the server address through the app (Tauri command set_server).
(function () {
  "use strict";
  const invoke = window.__TAURI__ && window.__TAURI__.core && window.__TAURI__.core.invoke;
  const form = document.getElementById("setup");
  const input = document.getElementById("server");
  const error = document.getElementById("error");
  if (!invoke) {
    error.textContent = "This page only works inside EVAC Player.";
    return;
  }
  invoke("current_server").then(function (s) { if (s) input.value = s; });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    error.textContent = "";
    invoke("set_server", { server: input.value }).catch(function (err) { error.textContent = String(err); });
  });
  input.focus();
})();
