# SPDX-License-Identifier: AGPL-3.0-or-later
from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core import crypto


class Command(BaseCommand):
    help = "Re-encrypt every stored secret with the first key of EVAC_SECRETS_KEYS."

    # (model label, field names) of encrypted columns; plugins with secrets add theirs via ENCRYPTED_FIELDS
    FIELDS = [
        ("accounts.TOTPDevice", ["secret_encrypted"]),
        ("extensions.ExtensionConfig", ["secrets_encrypted", "webhook_secret_encrypted"]),
        ("webhooks.WebhookEndpoint", ["secret_encrypted"]),
    ]

    @transaction.atomic
    def handle(self, *args, **opts):
        total = 0
        for label, fields in self.FIELDS:
            try:
                model = apps.get_model(label)
            except LookupError:
                continue
            for obj in model.objects.all():
                for f in fields:
                    setattr(obj, f, crypto.rotate(getattr(obj, f)))
                obj.save(update_fields=fields)
                total += 1
        self.stdout.write(self.style.SUCCESS(f"Re-encrypted {total} rows."))
