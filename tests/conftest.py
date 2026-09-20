import pytest
from django.contrib.auth import get_user_model

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    User = get_user_model()
    return User.objects.create_user(username="smoke", password="s3cret-pass")


@pytest.fixture
def client_logged_in(client, user):
    client.login(username="smoke", password="s3cret-pass")
    return client
