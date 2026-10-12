"""API tests — Chat: customer conversations, Staff queue/claim/reply, privacy of staff identities."""

from .support import (
    expect,
    expect_forbidden,
    expect_unauthorized,
    expect_validation,
    random_id,
    requires_postgres,
)

pytestmark = requires_postgres


def start(api, person, mode="Staff"):
    return api.client.post("/conversations", headers=person.headers, json={"Mode": mode})


def say(api, person, conversation_id, content, admin_route=False):
    prefix = "/admin" if admin_route else ""
    return api.client.post(f"{prefix}/conversations/{conversation_id}/messages", headers=person.headers,
                           json={"MessageType": "Text", "Content": content})


def test_success_customer_and_staff_conversation(api, staff, customer):
    conversation = expect(start(api, customer), 201)
    conversation_id = conversation["ConversationId"]
    expect(say(api, customer, conversation_id, "Cho tôi hỏi giá iPhone"), 201)
    queue = expect(api.client.get("/admin/conversations/unassigned", headers=staff.headers), 200)
    assert conversation_id in [c["ConversationId"] for c in queue["Items"]]
    claimed = expect(api.client.post(f"/admin/conversations/{conversation_id}/claim", headers=staff.headers), 200)
    assert claimed["AssignedStaffId"] == staff.id
    expect(say(api, staff, conversation_id, "Dạ máy đang có giá 20 triệu", admin_route=True), 201)
    messages = expect(api.client.get(f"/conversations/{conversation_id}/messages", headers=customer.headers), 200)
    assert [m["SenderType"] for m in messages["Items"]] == ["Customer", "Staff"]
    assert all(m["SenderUserId"] is None for m in messages["Items"] if m["SenderType"] == "Staff")  # staff hidden
    closed = expect(api.client.post(f"/admin/conversations/{conversation_id}/close", headers=staff.headers), 200)
    assert closed["Status"] == "Closed"


def test_401_without_token(api):
    expect_unauthorized(api.client.post("/conversations", json={"Mode": "Staff"}))
    expect_unauthorized(api.client.get("/conversations"))
    expect_unauthorized(api.client.get("/admin/conversations"))


def test_403_roles(api, staff, customer):
    conversation_id = expect(start(api, customer), 201)["ConversationId"]
    expect_forbidden(api.client.get(f"/admin/conversations/{conversation_id}", headers=customer.headers))
    expect_forbidden(api.client.post(f"/admin/conversations/{conversation_id}/claim", headers=customer.headers))
    expect_forbidden(start(api, staff))  # conversations are opened by customers


def test_404_unknown_or_foreign(api, staff, customer, other_customer):
    foreign = expect(start(api, other_customer), 201)["ConversationId"]
    expect(api.client.get(f"/conversations/{foreign}", headers=customer.headers), 404)  # not revealed
    expect(say(api, customer, foreign, "Xin chào"), 404)
    expect(api.client.get(f"/conversations/{random_id()}", headers=customer.headers), 404)
    expect(api.client.post(f"/admin/conversations/{random_id()}/claim", headers=staff.headers), 404)


def test_409_conversation_already_claimed(api, staff, customer):
    other_staff = api.person("Staff")
    conversation_id = expect(start(api, customer), 201)["ConversationId"]
    expect(api.client.post(f"/admin/conversations/{conversation_id}/claim", headers=staff.headers), 200)
    expect(api.client.post(f"/admin/conversations/{conversation_id}/claim", headers=other_staff.headers), 409,
           "conversation_already_claimed")


def test_422_validation(api, customer):
    expect_validation(start(api, customer, mode="Bot"), "Mode")
    conversation_id = expect(start(api, customer), 201)["ConversationId"]
    expect_validation(api.client.post(f"/conversations/{conversation_id}/messages", headers=customer.headers,
                                      json={"MessageType": "Video", "Content": "x"}), "MessageType")
    expect_validation(api.client.post("/conversations", headers=customer.headers,
                                      json={"Mode": "Staff", "AssignedStaffId": random_id()}), "AssignedStaffId")


def test_business_rules_chat(api, staff, customer):
    first = expect(start(api, customer), 201)["ConversationId"]
    assert expect(start(api, customer), 201)["ConversationId"] == first  # one open conversation per customer
    expect(say(api, staff, first, "Chào bạn", admin_route=True), 400, "conversation_not_assigned_to_you")
    expect(api.client.post(f"/conversations/{first}/close", headers=customer.headers), 200)
    expect(say(api, customer, first, "Còn câu hỏi"), 400, "conversation_closed")
    expect(api.client.post(f"/conversations/{expect(start(api, customer), 201)['ConversationId']}/messages",
                           headers=customer.headers, json={"MessageType": "Text", "Content": "   "}), 400,
           "message_content_required")
