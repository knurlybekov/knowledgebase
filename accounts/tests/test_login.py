import pytest
from django.test import Client

from organizations.tests.factories import make_user

pytestmark = pytest.mark.django_db


def test_login_page_and_credentials():
    user = make_user("karen@example.test", "a-long-and-strong-passphrase")
    c = Client()
    assert c.get("/accounts/login/").status_code == 200
    bad = c.post("/accounts/login/", {"username": user.email, "password": "wrong"})
    assert bad.status_code == 200 and not bad.wsgi_request.user.is_authenticated
    good = c.post(
        "/accounts/login/", {"username": user.email, "password": "a-long-and-strong-passphrase"}
    )
    assert good.status_code == 302
