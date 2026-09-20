from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create an application login user (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--password", required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        password = options["password"]
        user, created = User.objects.get_or_create(
            username=username, defaults={"is_active": True}
        )
        if password:
            user.set_password(password)
            user.is_active = True
            user.save(update_fields=["password", "is_active"])
        self.stdout.write(f"user '{username}' {'created' if created else 'updated'}.")
        return 0
