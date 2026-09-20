import traceback
from time import sleep

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from jobs.handlers import HANDLERS
from jobs.models import Job


class Command(BaseCommand):
    help = (
        "Run the background job worker. Picks up queued Job rows, executes "
        "their registered handler, and records the outcome. "
        "Use --once to process currently queued jobs and exit."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="drain currently queued jobs and exit",
        )
        parser.add_argument(
            "--interval",
            type=float,
            default=1.0,
            help="seconds to sleep between polls (default 1.0)",
        )

    def handle(self, *args, **options):
        once = options["once"]
        interval = options["interval"]
        self.stdout.write(
            f"worker started at {timezone.now().isoformat()} "
            f"(once={once}, interval={interval})"
        )
        total = 0
        while True:
            processed = self._drain_once()
            total += processed
            self.stdout.write(
                f"processed {processed} job(s) "
                f"[running total {total}] at {timezone.now().isoformat()}"
            )
            if once or processed == 0:
                break
            sleep(interval)
        self.stdout.write(
            f"worker finished at {timezone.now().isoformat()}, "
            f"total jobs processed={total}"
        )
        return 0

    @transaction.atomic
    def _claim(self):
        return (
            Job.objects.select_for_update(skip_locked=True)
            .filter(status=Job.Status.QUEUED)
            .order_by("created_at")
            .first()
        )

    def _drain_once(self):
        processed = 0
        while True:
            job = self._claim()
            if job is None:
                break
            self._run(job)
            processed += 1
        return processed

    def _run(self, job):
        handler = HANDLERS.get(job.name)
        if handler is None:
            self.stderr.write(f"unknown job name: {job.name}")
            job.status = Job.Status.FAILED
            job.error = f"no handler registered for {job.name}"
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "error", "finished_at"])
            return

        self.stdout.write(f"running job #{job.pk} {job.name} args={job.args}")
        job.status = Job.Status.RUNNING
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at"])
        try:
            result = handler(**job.args or {})
        except Exception as exc:  # noqa: BLE001
            job.status = Job.Status.FAILED
            job.error = (f"{exc}\n{traceback.format_exc()}")[:4000]
            job.finished_at = timezone.now()
            job.save(update_fields=["status", "error", "finished_at"])
            self.stderr.write(f"job #{job.pk} failed: {exc}")
            return
        job.status = Job.Status.SUCCEEDED
        job.result = result
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "result", "finished_at"])
        self.stdout.write(f"job #{job.pk} {job.name} succeeded: {result}")
