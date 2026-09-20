import pytest

pytestmark = pytest.mark.django_db


def test_anonymous_redirected_to_login(client):
    for url in ["/", "/tasks/", "/projects/new", "/tasks/new"]:
        response = client.get(url)
        assert response.status_code == 302
        assert response.url.startswith("/accounts/login/")
        assert "next=" in response.url


def test_login_page_renders(client):
    response = client.get("/accounts/login/")
    assert response.status_code == 200
    assert "Log in" in response.content.decode()


def test_login_rejects_bad_credentials(client):
    client.post(
        "/accounts/login/",
        {"username": "ghost", "password": "wrong-password"},
    )
    response = client.get("/")
    assert response.status_code == 302
    assert response.url.startswith("/accounts/login/")


def test_login_success_sets_session(client, user):
    response = client.post(
        "/accounts/login/",
        {"username": "smoke", "password": "s3cret-pass"},
    )
    assert response.status_code == 302
    assert client.session.get("_auth_user_id") == str(user.pk)
    assert client.cookies.get("sessionid").value


def test_logout_clears_session(client_logged_in):
    response = client_logged_in.post("/accounts/logout/")
    assert response.status_code == 302
    assert client_logged_in.session.get("_auth_user_id") is None
