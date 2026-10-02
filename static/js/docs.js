// SPDX-License-Identifier: AGPL-3.0-or-later
// Docs page: highlight the current section in the "On this page" table of contents.
(function () {
  var toc = document.querySelector('.docs-toc');
  if (toc && window.matchMedia('(max-width: 1000px)').matches) toc.removeAttribute('open');
  // highlight the TOC entry of the section currently in view
  var links = Array.prototype.slice.call(document.querySelectorAll('.docs-toc a[href^="#"]'));
  if (!links.length || !('IntersectionObserver' in window)) return;
  var byId = {};
  links.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
  var current = null;
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      var a = byId[e.target.id]; if (!a) return;
      if (current) current.removeAttribute('aria-current');
      a.setAttribute('aria-current', 'location'); current = a;
    });
  }, { rootMargin: '-56px 0px -70% 0px' });
  Object.keys(byId).forEach(function (id) { var el = document.getElementById(id); if (el) io.observe(el); });
})();
