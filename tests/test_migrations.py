import pytest
from django.core.management import call_command
from django.db import connection

from taskboard.models import Project, Task

pytestmark = pytest.mark.django_db


def test_all_migrations_applied_from_zero():
    with connection.cursor() as cursor:
        cursor.execute("SELECT app, name FROM django_migrations")
        rows = set(cursor.fetchall())
    assert ("taskboard", "0001_initial") in rows
    assert ("jobs", "0001_initial") in rows


def test_migrations_are_in_sync():
    try:
        call_command("makemigrations", "--check", "--dry-run", verbosity=0)
    except SystemExit as exc:
        pytest.fail(f"pending migrations detected: exit code {exc.code}")


def test_seed_is_idempotent():
    call_command("seed")
    first = (Project.objects.count(), Task.objects.count())
    call_command("seed")
    second = (Project.objects.count(), Task.objects.count())
    assert first == second
    assert first[0] >= 3
    assert first[1] >= 9
