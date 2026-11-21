"""Queue groups: a batch of jobs shown together (e.g. a season), kept next to each other in the queue order."""

from __future__ import annotations

import sqlite3

from test_server import add, make_client, make_files, wait_for

from videoforge.server.store import Store

EPISODES = ("S01E01", "S01E02", "S01E03")


def jobs(client) -> list[dict]:
    return client.get("/api/jobs").json()


def order(client) -> list[str]:
    return [j["id"] for j in jobs(client)]


def groups(client) -> dict[str, str | None]:
    return {j["id"]: j["group"] for j in jobs(client)}


def season(client, tmp_path, name="Show S01") -> tuple[list[str], str]:
    ids = add(client, tmp_path, group_name=name)
    gid = groups(client)[ids[0]]
    assert gid and all(groups(client)[i] == gid for i in ids)
    return ids, gid


def test_a_batch_is_added_as_one_group(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        ids, gid = season(client, tmp_path)
        assert len(ids) == 3
        assert {j["group_name"] for j in jobs(client)} == {"Show S01"}
        assert client.get(f"/api/jobs/{ids[0]}").json()["group_name"] == "Show S01"


def test_a_single_job_gets_no_group(tmp_path):
    make_files(tmp_path)
    with make_client(tmp_path) as client:
        job = add(client, tmp_path, group_name="Show")[0]
        assert groups(client) == {job: None}


def test_a_group_name_is_checked(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        body = {"sources": [str(tmp_path / "src")], "rule_set": "manual", "group_name": "x" * 81}
        assert client.post("/api/jobs", json=body).status_code == 422
        assert jobs(client) == []


def test_jobs_move_in_and_out_of_a_group(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        ids, gid = season(client, tmp_path)
        make_files(tmp_path, "Movie")
        movie = add(client, tmp_path, sources=[str(tmp_path / "src/Show.Movie.mkv")])[0]

        # out: the last episode goes after the movie, ungrouped
        client.post("/api/jobs/move", json={"ids": [ids[2]], "before": None, "group": ""})
        assert order(client) == [ids[0], ids[1], movie, ids[2]]
        assert groups(client)[ids[2]] is None

        # in: the movie goes between the first two episodes
        client.post("/api/jobs/move", json={"ids": [movie], "before": ids[1], "group": gid})
        assert order(client) == [ids[0], movie, ids[1], ids[2]]
        assert groups(client)[movie] == gid


def test_a_place_inside_another_group_ends_up_past_it(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        ids, _gid = season(client, tmp_path)
        make_files(tmp_path, "Movie")
        movie = add(client, tmp_path, sources=[str(tmp_path / "src/Show.Movie.mkv")])[0]
        client.post("/api/jobs/move", json={"ids": [movie], "before": ids[1], "group": ""})
        assert order(client) == [*ids, movie]


def test_a_whole_group_moves_as_one(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        make_files(tmp_path, "Movie")
        movie = add(client, tmp_path, sources=[str(tmp_path / "src/Show.Movie.mkv")])[0]
        ids, gid = season(client, tmp_path)
        client.post("/api/jobs/move", json={"ids": ids, "before": movie, "group": gid})
        assert order(client) == [*ids, movie]
        # the plain reorder (Up/Down) can't split it either: its jobs stay together where its first one is
        client.post("/api/jobs/reorder", json={"ids": [ids[1], movie]})
        assert order(client) == [ids[1], ids[0], ids[2], movie]


def test_moving_into_an_unknown_group_is_refused(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        ids = add(client, tmp_path)
        r = client.post("/api/jobs/move", json={"ids": ids[:1], "before": None, "group": "nope"})
        assert r.status_code == 404


def test_group_selected_rename_and_ungroup(tmp_path):
    make_files(tmp_path, *EPISODES, "Movie")
    with make_client(tmp_path) as client:
        ids = add(client, tmp_path)  # E01, E02, E03, Movie
        gid = client.post("/api/jobs/group", json={"ids": [ids[3], ids[1]], "name": "Picked"}).json()["group"]
        assert order(client) == [ids[0], ids[1], ids[3], ids[2]]  # gathered where the first of them is
        assert client.post(f"/api/groups/{gid}/rename", json={"name": "  Renamed "}).status_code == 200
        assert {j["group_name"] for j in jobs(client) if j["group"]} == {"Renamed"}
        assert client.post(f"/api/groups/{gid}/rename", json={"name": " "}).status_code == 422
        client.post(f"/api/groups/{gid}/ungroup")
        assert set(groups(client).values()) == {None}
        assert order(client) == [ids[0], ids[1], ids[3], ids[2]]  # its jobs stay where they are
        assert client.post(f"/api/groups/{gid}/ungroup").status_code == 404


def test_an_emptied_group_goes(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        ids, gid = season(client, tmp_path)
        client.post("/api/jobs/move", json={"ids": ids, "before": None, "group": ""})
        assert gid not in client.app.state.queue.group_names()


def test_undo_removal_puts_jobs_back_in_their_group(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        ids, gid = season(client, tmp_path)
        for job in ids:
            wait_for(client, job, "ready", "warn")
        client.post("/api/jobs/remove", json={"ids": ids})
        assert gid in client.app.state.queue.group_names()  # kept while the removal can be undone
        client.post("/api/jobs/restore", json={"ids": ids})
        assert order(client) == ids and all(g == gid for g in groups(client).values())


def test_undo_removal_into_a_group_that_went_comes_back_ungrouped(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        ids, gid = season(client, tmp_path)
        for job in ids:
            wait_for(client, job, "ready", "warn")
        client.post("/api/jobs/remove", json={"ids": [ids[0]]})
        client.post(f"/api/groups/{gid}/ungroup")
        client.post("/api/jobs/restore", json={"ids": [ids[0]]})
        assert groups(client)[ids[0]] is None


def test_a_duplicate_stays_in_its_group(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        ids, gid = season(client, tmp_path)
        wait_for(client, ids[0], "ready", "warn")
        copy = client.post("/api/jobs/duplicate", json={"ids": [ids[0]]}).json()["added"][0]
        assert order(client) == [ids[0], copy, ids[1], ids[2]]
        assert groups(client)[copy] == gid


def test_groups_survive_a_restart(tmp_path):
    make_files(tmp_path, *EPISODES)
    with make_client(tmp_path) as client:
        ids, gid = season(client, tmp_path)
    with make_client(tmp_path) as client:
        assert order(client) == ids
        assert all(j["group"] == gid and j["group_name"] == "Show S01" for j in jobs(client))


def test_a_split_group_is_put_together_on_load(tmp_path):
    make_files(tmp_path, *EPISODES, "Movie")
    with make_client(tmp_path) as client:
        ids = add(client, tmp_path)  # E01, E02, E03, Movie
        gid = client.post("/api/jobs/group", json={"ids": ids[:2], "name": "Two"}).json()["group"]
    db = sqlite3.connect(tmp_path / "data" / "videoforge.db")
    db.execute("UPDATE jobs SET grp = ? WHERE id = ?", (gid, ids[3]))  # E01, E02, E03, Movie: split
    db.commit()
    db.close()
    with make_client(tmp_path) as client:
        assert order(client) == [ids[0], ids[1], ids[3], ids[2]]


def test_a_store_from_before_groups_opens(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE jobs (id TEXT PRIMARY KEY, position REAL NOT NULL, spec TEXT NOT NULL, state TEXT NOT NULL,"
        " queued INTEGER NOT NULL DEFAULT 0, running INTEGER NOT NULL DEFAULT 0, updated TEXT NOT NULL)"
    )
    db.commit()
    db.close()
    store = Store(path)
    assert store.load_jobs() == [] and store.load_groups() == {}
    store.close()
