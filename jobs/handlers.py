def recompute_project_progress(project_id):
    from taskboard.models import Project, Task

    try:
        project = Project.objects.get(pk=project_id)
    except Project.DoesNotExist:
        return {"project_id": project_id, "progress": None}

    total = Task.objects.filter(project=project).count()
    done = Task.objects.filter(project=project, status=Task.Status.DONE).count()
    progress = round((done / total) * 100, 1) if total else 0.0
    project.progress = progress
    project.save(update_fields=["progress", "updated_at"])
    return {
        "project_id": project_id,
        "progress": progress,
        "total": total,
        "done": done,
    }


HANDLERS = {
    "recompute_project_progress": recompute_project_progress,
}
