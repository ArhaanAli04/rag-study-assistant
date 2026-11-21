"""Projects API (Day 18): CRUD, moves, deletion choices, archive, and ownership.

Ownership is the security property: another user's project id must behave exactly like a missing
one (404, not 403, and nothing changes) on every route that takes one. Retrieval scoping (a chat in
project A never cites project B) is tested in test_project_retrieval.py.
"""
from typing import Any, Callable, Dict, List, Optional

import pytest

from app.db.models import Document
from app.db.session import SessionLocal
from tests.conftest import Account, register_and_login
from tests.fakes import FakeGemini
from tests.test_api_smoke import SAMPLE_PDF, assert_contract, chat, parse_sse

INSTRUCTIONS_LIMIT = 4000


# --- helpers ------------------------------------------------------------------------------------

def create_project(client: Any, account: Account, name: str = "DL Unit 5", **fields: Any) -> Dict[str, Any]:
    response = client.post("/projects", headers=account.headers, json={"name": name, **fields})
    assert response.status_code == 201, response.text
    return response.json()


def upload_into(
    client: Any, account: Account, project_id: Optional[int], file_name: str = "samples.pdf",
    content: Optional[bytes] = None,
) -> Any:
    data = {} if project_id is None else {"project_id": str(project_id)}
    body = content if content is not None else SAMPLE_PDF.read_bytes()
    return client.post(
        "/upload", headers=account.headers, data=data, files={"file": (file_name, body, "application/pdf")}
    )


def chat_in(client: Any, account: Account, project_id: Optional[int], session_id: int = 0) -> Any:
    params: Dict[str, Any] = {"query": "What is a recurrent network?", "session_id": session_id,
                              "mode": "quick", "token": account.token}
    if project_id is not None:
        params["project_id"] = project_id
    return client.get("/chat/stream", params=params)


def documents(client: Any, account: Account) -> List[Dict[str, Any]]:
    return client.get("/documents", headers=account.headers).json()


def sessions(client: Any, account: Account) -> List[Dict[str, Any]]:
    return client.get("/sessions", headers=account.headers).json()


def project(client: Any, account: Account, project_id: int) -> Any:
    return client.get(f"/projects/{project_id}", headers=account.headers)


# --- create, list, read, update -----------------------------------------------------------------

def test_create_list_and_open_a_project(client: Any, account: Account) -> None:
    created = create_project(client, account, "  BDA  ", description="Big data", instructions="Answer in bullets.")

    assert created["name"] == "BDA"  # trimmed
    assert created["archived"] is False
    assert (created["document_count"], created["chat_count"], created["last_activity"]) == (0, 0, None)

    listed = client.get("/projects", headers=account.headers).json()
    assert [p["id"] for p in listed] == [created["id"]]

    opened = project(client, account, created["id"]).json()
    assert opened["instructions"] == "Answer in bullets."
    assert opened["documents"] == [] and opened["chats"] == []


def test_counts_documents_and_chats(client: Any, account: Account, gemini: FakeGemini) -> None:
    created = create_project(client, account)
    assert upload_into(client, account, created["id"]).status_code == 200
    assert_contract(parse_sse(chat_in(client, account, created["id"]).text))

    (listed,) = client.get("/projects", headers=account.headers).json()
    assert (listed["document_count"], listed["chat_count"]) == (1, 1)
    assert listed["last_activity"] is not None
    opened = project(client, account, created["id"]).json()
    assert [d["filename"] for d in opened["documents"]] == ["samples.pdf"]
    assert opened["documents"][0]["chunks"] > 0
    assert len(opened["chats"]) == 1


def test_last_activity_counts_uploads_as_well_as_chats(client: Any, account: Account, gemini: FakeGemini) -> None:
    files_only = create_project(client, account, "Files only")
    untouched = create_project(client, account, "Untouched")
    assert upload_into(client, account, files_only["id"]).status_code == 200

    listed = {p["id"]: p for p in client.get("/projects", headers=account.headers).json()}
    uploaded_at = project(client, account, files_only["id"]).json()["documents"][0]["created_at"]
    assert listed[files_only["id"]]["last_activity"] == uploaded_at
    assert listed[untouched["id"]]["last_activity"] is None

    # A chat after the upload is newer, so it becomes the last activity.
    assert_contract(parse_sse(chat_in(client, account, files_only["id"]).text))
    after_chat = {p["id"]: p for p in client.get("/projects", headers=account.headers).json()}
    assert after_chat[files_only["id"]]["last_activity"] > uploaded_at


@pytest.mark.parametrize(
    "body",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 81},
        {"name": "ok", "description": "d" * 501},
        {"name": "ok", "instructions": "i" * (INSTRUCTIONS_LIMIT + 1)},
    ],
    ids=["empty", "blank", "long-name", "long-description", "long-instructions"],
)
def test_invalid_project_bodies_are_refused(client: Any, account: Account, body: Dict[str, Any]) -> None:
    assert client.post("/projects", headers=account.headers, json=body).status_code == 422
    assert client.get("/projects", headers=account.headers).json() == []


def test_instructions_at_the_limit_are_accepted(client: Any, account: Account) -> None:
    created = create_project(client, account, instructions="i" * INSTRUCTIONS_LIMIT)
    assert len(created["instructions"]) == INSTRUCTIONS_LIMIT


def test_project_names_are_unique_per_user_only(client: Any, account: Account) -> None:
    create_project(client, account, "BDA")
    duplicate = client.post("/projects", headers=account.headers, json={"name": "BDA"})
    assert duplicate.status_code == 409

    other = register_and_login(client)
    create_project(client, other, "BDA")  # another user's namespace


def test_update_renames_edits_and_clears(client: Any, account: Account) -> None:
    created = create_project(client, account, "DL", description="Deep learning", instructions="Be brief.")
    other = create_project(client, account, "BDA")

    renamed = client.patch(f"/projects/{created['id']}", headers=account.headers, json={"name": "DL Unit 5"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "DL Unit 5"
    assert renamed.json()["instructions"] == "Be brief."  # fields not sent are kept

    cleared = client.patch(f"/projects/{created['id']}", headers=account.headers, json={"instructions": "  "})
    assert cleared.json()["instructions"] is None
    assert cleared.json()["description"] == "Deep learning"

    clash = client.patch(f"/projects/{created['id']}", headers=account.headers, json={"name": other["name"]})
    assert clash.status_code == 409


# --- archive --------------------------------------------------------------------------------------

def test_an_archived_project_takes_no_new_files_or_chats_but_old_chats_continue(
    client: Any, account: Account, gemini: FakeGemini
) -> None:
    created = create_project(client, account)
    assert upload_into(client, account, created["id"]).status_code == 200
    first = assert_contract(parse_sse(chat_in(client, account, created["id"]).text))
    session_id = first["metadata"]["session_id"]

    archived = client.patch(f"/projects/{created['id']}", headers=account.headers, json={"archived": True})
    assert archived.json()["archived"] is True

    assert upload_into(client, account, created["id"], file_name="new.pdf").status_code == 409
    assert chat_in(client, account, created["id"]).status_code == 409
    loose = upload_into(client, account, None, file_name="loose.pdf").json()["document_id"]
    moved = client.patch(f"/documents/{loose}", headers=account.headers, json={"project_id": created["id"]})
    assert moved.status_code == 409
    # The existing chat keeps working (the owner's choice for Day 18).
    assert_contract(parse_sse(chat_in(client, account, None, session_id=session_id).text))

    client.patch(f"/projects/{created['id']}", headers=account.headers, json={"archived": False})
    assert upload_into(client, account, created["id"], file_name="new.pdf").status_code == 200


# --- uploads, sessions and moves ----------------------------------------------------------------

def test_the_same_file_name_in_two_projects_is_two_documents(
    client: Any, account: Account, gemini: FakeGemini
) -> None:
    dl, bda = create_project(client, account, "DL"), create_project(client, account, "BDA")

    first = upload_into(client, account, dl["id"])
    embeds_after_first = gemini.embed_calls
    second = upload_into(client, account, bda["id"])

    assert (first.json()["status"], second.json()["status"]) == ("new", "new")
    assert first.json()["document_id"] != second.json()["document_id"]
    assert second.json()["chunks_indexed"] == first.json()["chunks_indexed"]
    assert gemini.embed_calls == embeds_after_first, "identical chunks reuse their stored vectors (CO3)"
    listed = {(d["project_name"], d["filename"]) for d in documents(client, account)}
    assert listed == {("DL", "samples.pdf"), ("BDA", "samples.pdf")}

    # A changed upload in DL is a new version of DL's file only.
    changed = upload_into(client, account, dl["id"], content=SAMPLE_PDF.read_bytes() + b"\n%changed")
    assert changed.json()["status"] == "changed"
    by_project = {d["project_name"]: d for d in documents(client, account)}
    assert by_project["DL"]["version"] == 2
    assert by_project["BDA"]["id"] == second.json()["document_id"]


def test_moving_a_document_moves_every_version(client: Any, account: Account) -> None:
    dl = create_project(client, account, "DL")
    first = upload_into(client, account, None).json()
    upload_into(client, account, None, content=SAMPLE_PDF.read_bytes() + b"\n%v2")
    (current,) = documents(client, account)
    assert current["version"] == 2 and current["project_id"] is None

    moved = client.patch(f"/documents/{current['id']}", headers=account.headers, json={"project_id": dl["id"]})

    assert moved.status_code == 200
    assert moved.json()["doc_version"] > first["doc_version"]
    (listed,) = documents(client, account)
    assert (listed["project_id"], listed["project_name"]) == (dl["id"], "DL")
    with SessionLocal() as db:
        rows = db.query(Document).filter(Document.file_name == "samples.pdf", Document.id.in_(
            [first["document_id"], current["id"]])).all()
        assert {row.project_id for row in rows} == {dl["id"]}, "the inactive version moved too"

    back = client.patch(f"/documents/{current['id']}", headers=account.headers, json={"project_id": None})
    assert back.status_code == 200
    assert documents(client, account)[0]["project_id"] is None


def test_moving_onto_an_existing_file_name_is_refused(client: Any, account: Account) -> None:
    dl = create_project(client, account, "DL")
    upload_into(client, account, dl["id"])
    loose = upload_into(client, account, None).json()["document_id"]

    clash = client.patch(f"/documents/{loose}", headers=account.headers, json={"project_id": dl["id"]})

    assert clash.status_code == 409
    assert "samples.pdf" in clash.json()["detail"]
    assert {d["project_id"] for d in documents(client, account)} == {None, dl["id"]}


def test_a_new_chat_joins_its_project_and_an_existing_chat_keeps_its_own(
    client: Any, account: Account, gemini: FakeGemini
) -> None:
    dl, bda = create_project(client, account, "DL"), create_project(client, account, "BDA")
    started = assert_contract(parse_sse(chat_in(client, account, dl["id"]).text))
    session_id = started["metadata"]["session_id"]

    # A stale client sends another project with the existing session: the session keeps DL.
    assert_contract(parse_sse(chat_in(client, account, bda["id"], session_id=session_id).text))

    (listed,) = sessions(client, account)
    assert (listed["id"], listed["project_id"], listed["project_name"]) == (session_id, dl["id"], "DL")


def test_moving_a_chat(client: Any, account: Account, gemini: FakeGemini) -> None:
    dl = create_project(client, account, "DL")
    session_id = assert_contract(chat(client, account))["metadata"]["session_id"]
    assert sessions(client, account)[0]["project_id"] is None

    moved = client.patch(f"/sessions/{session_id}/project", headers=account.headers, json={"project_id": dl["id"]})
    assert moved.status_code == 200
    assert sessions(client, account)[0]["project_id"] == dl["id"]

    back = client.patch(f"/sessions/{session_id}/project", headers=account.headers, json={"project_id": None})
    assert back.status_code == 200
    assert sessions(client, account)[0]["project_id"] is None


# --- delete -------------------------------------------------------------------------------------

def test_deleting_a_project_requires_a_documents_choice(client: Any, account: Account) -> None:
    created = create_project(client, account)
    assert client.delete(f"/projects/{created['id']}", headers=account.headers).status_code == 422
    assert client.delete(f"/projects/{created['id']}?documents=keep", headers=account.headers).status_code == 422
    assert project(client, account, created["id"]).status_code == 200


def test_deleting_a_project_with_its_documents(
    client: Any, account: Account, gemini: FakeGemini
) -> None:
    created = create_project(client, account)
    uploaded = upload_into(client, account, created["id"]).json()
    session_id = assert_contract(parse_sse(chat_in(client, account, created["id"]).text))["metadata"]["session_id"]
    kept = upload_into(client, account, None, file_name="kept.pdf").json()["document_id"]
    storage = client.app.state.services.file_storage
    with SessionLocal() as db:
        key = db.get(Document, uploaded["document_id"]).file_path

    deleted = client.delete(f"/projects/{created['id']}?documents=delete", headers=account.headers)

    assert deleted.status_code == 200, deleted.text
    body = deleted.json()
    assert (body["documents_deleted"], body["documents_unassigned"], body["chats_unassigned"]) == (1, 0, 1)
    assert body["doc_version"] > uploaded["doc_version"]
    assert [d["id"] for d in documents(client, account)] == [kept]
    assert not storage.exists(key)
    (chat_row,) = sessions(client, account)
    assert (chat_row["id"], chat_row["project_id"]) == (session_id, None)  # the chat is kept (Decision 4A)
    assert project(client, account, created["id"]).status_code == 404


def test_deleting_a_project_but_keeping_its_documents(client: Any, account: Account) -> None:
    created = create_project(client, account)
    uploaded = upload_into(client, account, created["id"]).json()

    deleted = client.delete(f"/projects/{created['id']}?documents=unassign", headers=account.headers)

    assert deleted.status_code == 200
    assert (deleted.json()["documents_deleted"], deleted.json()["documents_unassigned"]) == (0, 1)
    (listed,) = documents(client, account)
    assert (listed["id"], listed["project_id"], listed["chunks"]) == (uploaded["document_id"], None, uploaded["chunks_indexed"])


def test_keeping_documents_that_would_clash_is_refused(client: Any, account: Account) -> None:
    created = create_project(client, account)
    upload_into(client, account, created["id"])
    upload_into(client, account, None)  # an unassigned samples.pdf already exists

    refused = client.delete(f"/projects/{created['id']}?documents=unassign", headers=account.headers)

    assert refused.status_code == 409
    assert project(client, account, created["id"]).status_code == 200
    assert len(documents(client, account)) == 2


# --- ownership: another user's project id is a 404 everywhere ------------------------------------

def _open(client: Any, intruder: Account, pid: int) -> Any:
    return client.get(f"/projects/{pid}", headers=intruder.headers)


def _edit(client: Any, intruder: Account, pid: int) -> Any:
    return client.patch(f"/projects/{pid}", headers=intruder.headers, json={"name": "mine now", "instructions": "x"})


def _archive(client: Any, intruder: Account, pid: int) -> Any:
    return client.patch(f"/projects/{pid}", headers=intruder.headers, json={"archived": True})


def _delete(client: Any, intruder: Account, pid: int) -> Any:
    return client.delete(f"/projects/{pid}?documents=delete", headers=intruder.headers)


def _upload_into(client: Any, intruder: Account, pid: int) -> Any:
    return upload_into(client, intruder, pid, file_name="intruder.pdf")


def _move_document_into(client: Any, intruder: Account, pid: int) -> Any:
    own_document = upload_into(client, intruder, None, file_name="intruder.pdf").json()["document_id"]
    return client.patch(f"/documents/{own_document}", headers=intruder.headers, json={"project_id": pid})


def _move_chat_into(client: Any, intruder: Account, pid: int) -> Any:
    own_session = assert_contract(chat(client, intruder))["metadata"]["session_id"]
    return client.patch(f"/sessions/{own_session}/project", headers=intruder.headers, json={"project_id": pid})


def _start_chat_in(client: Any, intruder: Account, pid: int) -> Any:
    return chat_in(client, intruder, pid)


INTRUSIONS: Dict[str, Callable[[Any, Account, int], Any]] = {
    "open": _open,
    "edit": _edit,
    "archive": _archive,
    "delete": _delete,
    "upload-into": _upload_into,
    "move-document-into": _move_document_into,
    "move-chat-into": _move_chat_into,
    "start-chat-in": _start_chat_in,
}


@pytest.mark.parametrize("route", list(INTRUSIONS))
def test_another_users_project_is_not_found(
    client: Any, account: Account, gemini: FakeGemini, route: str
) -> None:
    owned = create_project(client, account, "Owner's course", instructions="Owner's instructions")
    upload_into(client, account, owned["id"])
    intruder = register_and_login(client)
    intruder_documents_before = documents(client, intruder)

    response = INTRUSIONS[route](client, intruder, owned["id"])

    assert response.status_code == 404, f"{route}: {response.status_code} {response.text}"
    assert response.json()["detail"] == "Project not found"
    # Nothing leaked and nothing changed, on either side.
    assert "Owner's" not in response.text
    after = project(client, account, owned["id"]).json()
    assert (after["name"], after["instructions"], after["archived"]) == (
        "Owner's course", "Owner's instructions", False,
    )
    assert after["document_count"] == 1
    assert all(d["project_id"] is None for d in documents(client, intruder))
    assert all(s["project_id"] is None for s in sessions(client, intruder))
    if route == "upload-into":
        assert documents(client, intruder) == intruder_documents_before
    if route == "start-chat-in":
        assert sessions(client, intruder) == []


def test_another_users_documents_and_chats_cannot_be_moved(
    client: Any, account: Account, gemini: FakeGemini
) -> None:
    owner_document = upload_into(client, account, None).json()["document_id"]
    owner_session = assert_contract(chat(client, account))["metadata"]["session_id"]
    intruder = register_and_login(client)
    intruder_project = create_project(client, intruder, "Intruder's")

    document = client.patch(
        f"/documents/{owner_document}", headers=intruder.headers, json={"project_id": intruder_project["id"]}
    )
    session = client.patch(
        f"/sessions/{owner_session}/project", headers=intruder.headers, json={"project_id": intruder_project["id"]}
    )

    assert document.status_code == 404 and session.status_code == 404
    assert documents(client, account)[0]["project_id"] is None
    assert sessions(client, account)[0]["project_id"] is None


def test_projects_are_listed_for_their_owner_only(client: Any, account: Account) -> None:
    create_project(client, account, "Mine")
    other = register_and_login(client)

    assert client.get("/projects", headers=other.headers).json() == []
