import pytest
from django.urls import reverse

from jobs.models import Job
from taskboard.models import Project, Task

pytestmark = pytest.mark.django_db


def _create_project(client_logged_in, name="Website relaunch"):
    response = client_logged_in.post(
        reverse("project-create"),
        {"name": name, "description": "desc", "status": "active"},
    )
    assert response.status_code == 302
    return Project.objects.get(name=name)


def test_project_lifecycle(client_logged_in):
    project = _create_project(client_logged_in, "Website relaunch")
    assert Project.objects.count() == 1
    assert project.status == Project.Status.ACTIVE

    response = client_logged_in.get(
        reverse("project-detail", kwargs={"pk": project.pk})
    )
    assert response.status_code == 200
    assert "Website relaunch" in response.content.decode()

    response = client_logged_in.post(
        reverse("project-edit", kwargs={"pk": project.pk}),
        {"name": "Website relaunch v2", "description": "x", "status": "archived"},
    )
    assert response.status_code == 302
    project.refresh_from_db()
    assert project.name == "Website relaunch v2"
    assert project.status == Project.Status.ARCHIVED

    client_logged_in.post(reverse("project-delete", kwargs={"pk": project.pk}))
    assert Project.objects.count() == 0
    assert Task.objects.count() == 0


def test_task_lifecycle_and_progress_jobs(client_logged_in):
    project = _create_project(client_logged_in, "Tasks")
    create_url = reverse("task-create")

    response = client_logged_in.post(
        create_url,
        {
            "project": project.pk,
            "title": "Wireframes",
            "description": "",
            "status": "todo",
            "priority": "medium",
        },
    )
    assert response.status_code == 302
    task = Task.objects.get(title="Wireframes")
    assert task.project_id == project.pk
    assert Job.objects.filter(
        name="recompute_project_progress",
        args={"project_id": project.pk},
    ).exists()

    response = client_logged_in.post(
        reverse("task-edit", kwargs={"pk": task.pk}),
        {
            "project": project.pk,
            "title": "Wireframes (done)",
            "status": "done",
            "priority": "high",
        },
    )
    assert response.status_code == 302
    task.refresh_from_db()
    assert task.title == "Wireframes (done)"
    assert task.status == Task.Status.DONE
    assert task.priority == Task.Priority.HIGH

    client_logged_in.post(reverse("task-delete", kwargs={"pk": task.pk}))
    assert Task.objects.count() == 0


def test_task_creation_requires_project(client_logged_in):
    response = client_logged_in.post(
        reverse("task-create"),
        {"title": "orphan", "status": "todo", "priority": "low"},
    )
    assert response.status_code == 200
    assert "project" in response.context["form"].errors
    assert Task.objects.count() == 0


def test_blank_project_name_rejected(client_logged_in):
    response = client_logged_in.post(
        reverse("project-create"),
        {"name": "   ", "description": "", "status": "active"},
    )
    assert response.status_code == 200
    assert "name" in response.context["form"].errors
    assert Project.objects.count() == 0


def test_invalid_task_status_rejected(client_logged_in):
    project = _create_project(client_logged_in, "Reject")
    response = client_logged_in.post(
        reverse("task-create"),
        {"project": project.pk, "title": "x", "status": "warp"},
    )
    assert response.status_code == 200
    assert "status" in response.context["form"].errors
    assert Task.objects.count() == 0


def test_not_found(client_logged_in):
    assert (
        client_logged_in.get(
            reverse("project-detail", kwargs={"pk": 99999})
        ).status_code
        == 404
    )
    assert (
        client_logged_in.get(reverse("task-edit", kwargs={"pk": 99999})).status_code
        == 404
    )


def test_list_filters_and_search(client_logged_in):
    p1 = _create_project(client_logged_in, "Alpha demo")
    p2 = _create_project(client_logged_in, "Beta demo")
    client_logged_in.post(
        reverse("project-edit", kwargs={"pk": p2.pk}),
        {"name": "Beta demo", "description": "", "status": "archived"},
    )
    t1 = Task.objects.create(
        project=p1, title="Tune search", status="done", priority="high"
    )
    Task.objects.create(project=p1, title="Other task", status="todo", priority="low")

    html = client_logged_in.get(reverse("project-list"), {"q": "alpha"}).content
    assert b"Alpha demo" in html
    assert b"Beta demo" not in html

    html = client_logged_in.get(reverse("project-list"), {"status": "active"}).content
    assert b"Alpha demo" in html
    assert b"Beta demo" not in html

    detail = client_logged_in.get(
        reverse("project-detail", kwargs={"pk": p1.pk}),
        {"status": "done"},
    ).content
    assert b"Tune search" in detail
    assert b"Other task" not in detail

    from jobs.tasks import enqueue_job

    enqueue_job("recompute_project_progress", project_id=p1.pk)
    p1.refresh_from_db()
    assert p1.progress == 0.0


def test_output_is_escaped(client_logged_in):
    project = _create_project(client_logged_in, "Escaping")
    Task.objects.create(
        project=project,
        title="<script>alert('x')</script>",
        status="todo",
    )
    html = client_logged_in.get(
        reverse("project-detail", kwargs={"pk": project.pk})
    ).content.decode()
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html
