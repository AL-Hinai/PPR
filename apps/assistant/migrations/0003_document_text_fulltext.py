"""MySQL FULLTEXT index on the extracted page text, for cross-dossier search (other databases: no-op)."""
from django.db import migrations

INDEX = "assistant_doctext_ft"


def add_index(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute(f"ALTER TABLE assistant_documenttext ADD FULLTEXT INDEX {INDEX} (text)")


def drop_index(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        schema_editor.execute(f"ALTER TABLE assistant_documenttext DROP INDEX {INDEX}")


class Migration(migrations.Migration):
    dependencies = [("assistant", "0002_document_text_titles")]
    operations = [migrations.RunPython(add_index, drop_index)]
