# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every portal page renders without accessibility findings, as anonymous, member and admin."""
import pytest

from apps.core.a11y import audit_url, check_html, smoke_urls
from conftest import login_2fa


def _check(client, urls):
    problems = {}
    for url in urls:
        findings = audit_url(client, url)
        if findings:
            problems[url] = findings
    assert problems == {}


@pytest.mark.django_db
def test_pages_anonymous(client, admin, event):
    _check(client, smoke_urls("demo", "hall")["anonymous"])


@pytest.mark.django_db
def test_pages_member(client, member, event):
    client.force_login(member)
    _check(client, smoke_urls("demo", "hall")["member"])


@pytest.mark.django_db
def test_pages_admin(client, admin, event):
    login_2fa(client, admin)
    _check(client, smoke_urls("demo", "hall")["admin"] + ["/e/demo/roles/new/", "/e/demo/roles/orga/"])


def test_linter_catches_problems():
    html = ('<html><body><main><h1>x</h1><h3>y</h3><img src="a.png"><button></button>'
            '<a onclick="x()">z</a></main></body></html>')
    rules = {f.split(":")[0] for f in check_html(html)}
    assert {"heading-order", "img-alt", "button-name", "no-onclick", "lang"} <= rules
