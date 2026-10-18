"""Existing reviews keep working: each lead reviewer is assigned every required module of their applications,
and reviewers created before specialties existed are qualified for all modules (narrow them in the admin)."""
from django.db import migrations

ALL = ["M1", "M2", "M3", "M4", "M5"]
REQUIRED = {
    "NEW_DRUG": ALL,
    "GENERIC": ["M1", "M2", "M3", "M5"],
    "VARIATION": ["M1"],
    "RENEWAL": ["M1"],
}


def forwards(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    Application = apps.get_model("applications", "Application")
    ReviewAssignment = apps.get_model("applications", "ReviewAssignment")
    StatusHistory = apps.get_model("applications", "StatusHistory")

    User.objects.filter(role="REVIEWER", specialties=[]).update(specialties=ALL)
    for application in Application.objects.exclude(assigned_reviewer=None):
        entry = (
            StatusHistory.objects.filter(application=application, to_status="UNDER_REVIEW", actor__role="HOD")
            .order_by("created_at")
            .first()
        )
        assigned_by_id = entry.actor_id if entry else application.assigned_reviewer_id
        for section in REQUIRED.get(application.application_type, ["M1"]):
            ReviewAssignment.objects.get_or_create(
                application=application,
                section=section,
                defaults={"reviewer_id": application.assigned_reviewer_id, "assigned_by_id": assigned_by_id},
            )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_user_specialties"),
        ("applications", "0002_review_assignments"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
