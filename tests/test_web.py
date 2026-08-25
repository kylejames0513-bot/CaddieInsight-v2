import pytest
from fastapi.testclient import TestClient

from caddieinsight.web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CADDIE_DB", str(tmp_path / "web.db"))
    monkeypatch.setenv("CADDIE_SECRET", "test-secret")
    app = create_app()
    with TestClient(app) as client:
        yield client


def signup(client, name="Kyle", email="kyle@example.com", password="sandy-lies-8"):
    return client.post(
        "/signup",
        data={"display_name": name, "email": email, "password": password},
        follow_redirects=False,
    )


def onboard(client):
    signup(client)
    client.post("/bag/setup", data={"clubs": ["DR", "7I", "8I"]})


def test_landing_for_the_signed_out(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "Know your carry" in page.text
    assert "No GPS" in page.text


def test_auth_wall_redirects_to_login(client):
    for path in ["/bag", "/range", "/gapping", "/caddie", "/clubhouse", "/settings"]:
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303, path
        assert response.headers["location"].startswith("/login")


def test_signup_sets_session_and_lands_on_bag_setup(client):
    response = signup(client)
    assert response.status_code == 303
    assert response.headers["location"] == "/bag/setup?msg=welcome"
    assert "ci_session" in response.cookies
    setup = client.get("/bag/setup")
    assert "What do you carry?" in setup.text
    assert 'value="7I" checked' in setup.text  # default bag pre-ticked


def test_signup_rejects_thin_credentials(client):
    response = client.post(
        "/signup",
        data={"display_name": "", "email": "bad", "password": "short"},
        follow_redirects=False,
    )
    assert "signup-invalid" in response.headers["location"]


def test_duplicate_email_is_pointed_at_login(client):
    signup(client)
    client.post("/logout")
    response = signup(client)
    assert "email-taken" in response.headers["location"]


def test_login_and_bad_login(client):
    signup(client)
    client.post("/logout")
    bad = client.post(
        "/login",
        data={"email": "kyle@example.com", "password": "wrong"},
        follow_redirects=False,
    )
    assert "bad-login" in bad.headers["location"]
    good = client.post(
        "/login",
        data={"email": "kyle@example.com", "password": "sandy-lies-8", "next": "/gapping"},
        follow_redirects=False,
    )
    assert good.headers["location"] == "/gapping"


def test_login_next_cannot_leave_the_site(client):
    signup(client)
    client.post("/logout")
    response = client.post(
        "/login",
        data={
            "email": "kyle@example.com",
            "password": "sandy-lies-8",
            "next": "//evil.example",
        },
        follow_redirects=False,
    )
    assert response.headers["location"] == "/bag"


def test_bag_shows_honest_empty_state_then_numbers(client):
    onboard(client)
    bag = client.get("/bag")
    assert "No numbers yet" in bag.text
    client.post("/range", data={"club": "7I", "carries": "150 152 154", "note": ""})
    bag = client.get("/bag")
    assert "152" in bag.text
    assert "No numbers yet" not in bag.text


def test_range_rejects_garbage_carries(client):
    onboard(client)
    response = client.post(
        "/range",
        data={"club": "7I", "carries": "150 nope"},
        follow_redirects=False,
    )
    assert "bad-carries" in response.headers["location"]
    response = client.post(
        "/range",
        data={"club": "PW", "carries": "120"},
        follow_redirects=False,
    )
    assert "pick-club" in response.headers["location"]  # PW not in this bag


def test_gapping_flags_the_wide_gap(client):
    onboard(client)
    client.post("/range", data={"club": "DR", "carries": "240 242 238"})
    client.post("/range", data={"club": "7I", "carries": "150 152 154"})
    page = client.get("/gapping")
    assert "Wide gap" in page.text
    assert "own nothing" in page.text


def test_caddie_recommends_from_measured_carries(client):
    onboard(client)
    client.post("/range", data={"club": "7I", "carries": "150 152 154"})
    client.post("/range", data={"club": "8I", "carries": "138 140 142"})
    page = client.get("/caddie", params={"target": 150})
    assert "ci-verdict__club" in page.text
    assert "carries 152" in page.text
    assert "Plays like" in page.text


def test_caddie_never_guesses(client):
    onboard(client)
    page = client.get("/caddie", params={"target": 150})
    assert "does not guess" in page.text


def test_caddie_rejects_a_bad_target(client):
    onboard(client)
    response = client.get(
        "/caddie", params={"target": "elephant"}, follow_redirects=False
    )
    assert "bad-target" in response.headers["location"]


def test_clubhouse_post_comment_tap(client):
    onboard(client)
    response = client.post(
        "/clubhouse/post",
        data={"body": "Closed the 100 yard gap."},
        follow_redirects=False,
    )
    assert response.status_code == 303
    thread = client.get(response.headers["location"])
    assert "Closed the 100 yard gap." in thread.text

    post_path = response.headers["location"].split("?")[0]
    client.post(f"{post_path}/comment", data={"body": "Which club filled it?"})
    thread = client.get(post_path)
    assert "Which club filled it?" in thread.text

    client.post(f"{post_path}/tap")
    feed = client.get("/clubhouse")
    assert "is-tapped" in feed.text


def test_bag_rack_respects_privacy(client):
    onboard(client)
    me = client.get("/settings")
    assert "Share my bag" in me.text

    # Not shared: rack is empty and the direct card bounces.
    rack = client.get("/clubhouse/bags")
    assert "nobody is sharing yet" in rack.text
    card = client.get("/clubhouse/bags/1", follow_redirects=False)
    # Own bag is always visible to its owner.
    assert card.status_code == 200

    client.post("/logout")
    signup(client, name="Pat", email="pat@example.com", password="green-reads-9")
    other_view = client.get("/clubhouse/bags/1", follow_redirects=False)
    assert other_view.status_code == 303
    assert "private-bag" in other_view.headers["location"]


def test_sharing_puts_the_bag_on_the_rack(client):
    onboard(client)
    client.post("/range", data={"club": "7I", "carries": "150 152 154"})
    client.post(
        "/settings",
        data={"display_name": "Kyle", "home_course": "Dunes GC", "share_bag": "on"},
    )
    rack = client.get("/clubhouse/bags")
    assert "Kyle" in rack.text and "Dunes GC" in rack.text
    card = client.get("/clubhouse/bags/1")
    assert "152" in card.text


def test_unknown_post_is_a_404(client):
    onboard(client)
    assert client.get("/clubhouse/p/999").status_code == 404


def test_notices_only_come_from_the_whitelist(client):
    onboard(client)
    page = client.get("/bag", params={"msg": "<script>alert(1)</script>"})
    assert "alert(1)" not in page.text


def test_healthz_manifest_and_service_worker(client):
    assert client.get("/healthz").json()["ok"] is True
    manifest = client.get("/manifest.webmanifest")
    assert manifest.json()["name"] == "CaddieInsight"
    worker = client.get("/service-worker.js")
    assert worker.status_code == 200
    assert "ci-static" in worker.text
