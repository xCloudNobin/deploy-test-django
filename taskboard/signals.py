from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from jobs.tasks import enqueue_job

from .models import Task


@receiver(post_save, sender=Task)
def task_saved(sender, instance, **kwargs):
    enqueue_job("recompute_project_progress", project_id=instance.project_id)


@receiver(post_delete, sender=Task)
def task_deleted(sender, instance, **kwargs):
    enqueue_job("recompute_project_progress", project_id=instance.project_id)
