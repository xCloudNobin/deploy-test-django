import django

from config.settings import RELEASE_SHA


def release_ctx(request):
    return {
        "release": RELEASE_SHA,
        "django_version": django.get_version(),
    }
