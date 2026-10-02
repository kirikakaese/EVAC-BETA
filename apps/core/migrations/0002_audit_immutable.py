# SPDX-License-Identifier: AGPL-3.0-or-later
"""PostgreSQL: forbid UPDATE and DELETE on audit rows at database level (defence in depth; the hash chain
detects tampering by anyone who bypasses this, e.g. a superuser dropping the trigger)."""
from django.db import migrations

CREATE = """
CREATE OR REPLACE FUNCTION evac_audit_immutable() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'core_auditlog rows are immutable (append-only audit log)';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS evac_audit_no_change ON core_auditlog;
CREATE TRIGGER evac_audit_no_change BEFORE UPDATE OR DELETE ON core_auditlog
  FOR EACH ROW EXECUTE FUNCTION evac_audit_immutable();
DROP TRIGGER IF EXISTS evac_audit_no_truncate ON core_auditlog;
CREATE TRIGGER evac_audit_no_truncate BEFORE TRUNCATE ON core_auditlog
  FOR EACH STATEMENT EXECUTE FUNCTION evac_audit_immutable();
"""
DROP = """
DROP TRIGGER IF EXISTS evac_audit_no_change ON core_auditlog;
DROP TRIGGER IF EXISTS evac_audit_no_truncate ON core_auditlog;
DROP FUNCTION IF EXISTS evac_audit_immutable();
"""


def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(CREATE)


def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DROP)


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(forwards, backwards)]
