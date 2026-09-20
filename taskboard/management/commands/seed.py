from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from taskboard.models import Project, Task


def load_seed():
    created_projects = 0
    created_tasks = 0
    for i, name in enumerate(
        ["Website relaunch", "Q3 roadmap", "Internal tooling"], start=1
    ):
        project, was_created = Project.objects.get_or_create(
            name=name,
            defaults={
                "description": f"Seed project {i} for the taskboard fixture.",
                "status": Project.Status.ACTIVE,
            },
        )
        created_projects += int(was_created)
        for j, title in enumerate(
            [
                f"Define scope ({name})",
                f"Review first draft ({name})",
                f"Ship milestone ({name})",
            ],
            start=1,
        ):
            _, task_created = Task.objects.get_or_create(
                project=project,
                title=title,
                defaults={
                    "description": "Seed task.",
                    "status": Task.Status.TODO,
                    "priority": Task.Priority.MEDIUM,
                },
            )
            created_tasks += int(task_created)
    return created_projects, created_tasks


class Command(BaseCommand):
    help = "Idempotently load repeatable demo seed data."

    def handle(self, *args, **options):
        User = get_user_model()
        user, user_created = User.objects.get_or_create(
            username="demo",
            defaults={"is_active": True},
        )
        if user_created:
            user.set_unusable_password()
            user.save()
        projects, tasks = load_seed()
        self.stdout.write(
            f"seed: {projects} project(s) and {tasks} task(s) created; "
            f"demo user {'created' if user_created else 'already present'}."
        )
        return 0
