# SPDX-License-Identifier: AGPL-3.0-or-later
"""Signals between modules that must not import each other."""
from django.dispatch import Signal

#: a time anchor moved or disappeared (sender: the TimeAnchorSpec key; kwargs: event, anchor_id), ADR-0025
anchor_moved = Signal()
