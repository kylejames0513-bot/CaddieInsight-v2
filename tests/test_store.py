from datetime import datetime, timedelta

import pytest

from caddieinsight.bag import DEFAULT_BAG
from caddieinsight.store import Store, hash_password, verify_password


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "test.db")


@pytest.fixture
def user(store):
    return store.create_user("kyle@example.com", "Kyle", "sandy-lies-8")


def test_password_hashing_round_trip():
    stored = hash_password("correct horse")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong horse", stored)
    assert not verify_password("correct horse", "garbage")


def test_create_and_authenticate(store, user):
    assert store.authenticate("kyle@example.com", "sandy-lies-8").id == user.id
    assert store.authenticate("KYLE@EXAMPLE.COM", "sandy-lies-8") is not None
    assert store.authenticate("kyle@example.com", "nope-nope-1") is None
    assert store.user_by_email("kyle@example.com").display_name == "Kyle"


def test_bag_set_and_rank_order(store, user):
    store.set_bag(user.id, ["9I", "DR", "PW"])
    assert store.bag_keys(user.id) == ["DR", "9I", "PW"]
    store.add_club(user.id, "7I")
    store.remove_club(user.id, "PW")
    assert store.bag_keys(user.id) == ["DR", "7I", "9I"]


def test_set_bag_ignores_junk_and_duplicates(store, user):
    store.set_bag(user.id, ["7I", "7i", "XX", "DR"])
    assert store.bag_keys(user.id) == ["DR", "7I"]


def test_default_bag_keys_are_all_valid(store, user):
    store.set_bag(user.id, list(DEFAULT_BAG))
    assert len(store.bag_keys(user.id)) == len(DEFAULT_BAG)


def test_shots_feed_the_rungs(store, user):
    store.set_bag(user.id, ["7I", "8I"])
    store.log_shots(user.id, "7I", [150, 152, 154], note="range")
    rungs = store.rungs(user.id)
    seven = next(r for r in rungs if r.key == "7I")
    eight = next(r for r in rungs if r.key == "8I")
    assert seven.number.carry == 152
    assert seven.number.shots_total == 3
    assert eight.number.carry is None
    assert store.shot_count(user.id) == 3


def test_recent_shots_newest_first(store, user):
    store.set_bag(user.id, ["7I"])
    old = datetime.utcnow() - timedelta(days=2)
    store.log_shots(user.id, "7I", [140], logged_at=old)
    store.log_shots(user.id, "7I", [155])
    recent = store.recent_shots(user.id)
    assert [s["carry"] for s in recent] == [155, 140]


def test_unknown_club_is_rejected(store, user):
    with pytest.raises(KeyError):
        store.log_shots(user.id, "XX", [150])


def test_clubhouse_posts_comments_taps(store, user):
    other = store.create_user("pat@example.com", "Pat", "green-reads-9")
    post_id = store.create_post(user.id, "Closed the 100 yard gap.")
    store.add_comment(post_id, other.id, "Which club filled it?")

    feed = store.feed(other.id)
    assert len(feed) == 1
    assert feed[0].author == "Kyle"
    assert feed[0].comments == 1
    assert feed[0].taps == 0

    assert store.toggle_tap(post_id, other.id) is True
    assert store.post(post_id, other.id).tapped_by_me
    assert not store.post(post_id, user.id).tapped_by_me
    assert store.toggle_tap(post_id, other.id) is False
    assert store.post(post_id, other.id).taps == 0

    comments = store.comments_for(post_id)
    assert [c.author for c in comments] == ["Pat"]


def test_share_bag_is_opt_in(store, user):
    assert store.shared_bags() == []
    store.update_profile(user.id, share_bag=True, home_course="Dunes GC")
    shared = store.shared_bags()
    assert [u.id for u in shared] == [user.id]
    assert shared[0].home_course == "Dunes GC"
    store.update_profile(user.id, share_bag=False)
    assert store.shared_bags() == []
