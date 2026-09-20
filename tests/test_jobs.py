import pytest
from django.core.management import call_command

from jobs.models import Job
from taskboard.models import Project, Task

pytestmark = pytest.mark.django_db


def _project_with_tasks(name="Launchpad", done_count=2, todo_count=2):
    project = Project.objects.create(name=name)
    for i in range(done_count):
        Task.objects.create(project=project, title=f"done {i}", status=Task.Status.DONE)
    for i in range(todo_count):
        Task.objects.create(project=project, title=f"todo {i}", status=Task.Status.TODO)
    return project


def test_worker_runs_queued_job_and_recomputes_progress(db):
    from jobs.tasks import enqueue_job

    project = _project_with_tasks()
    job = enqueue_job("recompute_project_progress", project_id=project.pk)

    call_command("runworker", "--once")

    job.refresh_from_db()
    assert job.status == Job.Status.SUCCEEDED
    assert job.result["progress"] == 50.0

    project.refresh_from_db()
    assert project.progress == 50.0


def test_task_save_enqueues_progress_job(db):
    from taskboard.models import Project, Task

    project = Project.objects.create(name="Trigger")
    task = Task.objects.create(project=project, title="t", status="todo")

    job = Job.objects.filter(
        name="recompute_project_progress",
        args={"project_id": project.pk},
    ).latest("created_at")
    assert job.status == Job.Status.QUEUED
    assert task.pk is not None


def test_worker_marks_unknown_job_failed(db):
    from jobs.tasks import enqueue_job

    job = enqueue_job("no_such_handler", key="value")
    call_command("runworker", "--once")
    job.refresh_from_db()
    assert job.status == Job.Status.FAILED
    assert "no handler registered" in job.error


def test_worker_marks_failing_job_failed(db):
    from jobs.tasks import enqueue_job

    job = enqueue_job("recompute_project_progress", project_id=424242)
    call_command("runworker", "--once")
    job.refresh_from_db()
    assert job.status == Job.Status.SUCCEEDED
    assert job.result["progress"] is None


def test_worker_drains_all_queued_jobs(db):
    from jobs.tasks import enqueue_job

    p = _project_with_tasks()
    for pid in (p.pk, p.pk, p.pk):
        enqueue_job("recompute_project_progress", project_id=pid)
    call_command("runworker", "--once")
    assert not Job.objects.filter(status=Job.Status.QUEUED).exists()
    assert Job.objects.filter(status=Job.Status.SUCCEEDED).count() >= 3
