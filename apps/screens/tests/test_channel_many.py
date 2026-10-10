# SPDX-License-Identifier: AGPL-3.0-or-later
"""channel.send_many: one pass for many screens (an alarm reaches every screen of the event at once)."""
from unittest import mock

from apps.screens import channel


def test_send_many_buffers_and_fans_out(db):
    n = channel.send_many([("s1", "evac.state", {"a": 1}), ("s2", "evac.state", {"a": 2}),
                           ("s1", "evac.state", {"a": 3})])
    assert n == 3
    assert [m["data"]["a"] for m in channel.since("s1", 0)] == [1, 3]
    assert channel.last_seq("s1") == 2 and channel.last_seq("s2") == 1
    with mock.patch.object(channel.cache, "incr", side_effect=RuntimeError("down")):
        assert channel.send_many([("s3", "x", {})]) == 0
    with mock.patch("channels.layers.get_channel_layer", side_effect=RuntimeError("no layer")):
        assert channel.send_many([("s4", "x", {})]) == 1
