#include "MessageDispatcher.h"
#include <stdexcept>

using Json = nlohmann::json;
static Json message_json(const StoredMessage &m) {
    return {{"type", "message"}, {"message_id", m.id}, {"room_id", m.room}, {"sender_id", m.sender},
            {"client_msg_id", m.client_id}, {"content", m.content}, {"created_at", m.created_at}};
}

DispatchResult MessageDispatcher::dispatch(MessageStore &repo, const DispatchRequest &request) {
    DispatchResult result;
    if (request.type == "create_room") {
        if (repo.create_room(request.room, request.user)) result.response = {{"type", "room_created"}, {"room_id", request.room}};
        else result.response = {{"type", "error"}, {"message", "room already exists"}};
    } else if (request.type == "join") {
        if (repo.join_room(request.room, request.user)) result.response = {{"type", "joined"}, {"room_id", request.room}};
        else result.response = {{"type", "error"}, {"message", "room not found"}};
    } else if (request.type == "leave") {
        if (repo.leave_room(request.room, request.user)) result.response = {{"type", "left"}, {"room_id", request.room}};
        else result.response = {{"type", "error"}, {"message", "not a room member"}};
    } else if (!repo.is_member(request.room, request.user)) {
        result.response = {{"type", "error"}, {"message", "not a room member"}};
    } else if (request.type == "send") {
        auto stored = repo.insert(request.room, request.user, request.client_id, request.content);
        result.response = {{"type", "send_ok"}, {"message_id", stored.message.id},
                           {"client_msg_id", request.client_id}, {"duplicate", !stored.inserted}};
        if (stored.inserted) { result.broadcast = message_json(stored.message); result.recipients = repo.room_members(request.room); }
    } else if (request.type == "history") {
        auto after = request.use_offset ? repo.offset(request.user, request.room) : request.number;
        Json messages = Json::array();
        for (const auto &message : repo.history(request.room, after, 100)) messages.push_back(message_json(message));
        result.response = {{"type", "history"}, {"room_id", request.room}, {"after_message_id", after}, {"messages", std::move(messages)}};
    } else if (request.type == "ack") {
        if (repo.acknowledge(request.user, request.room, request.number))
            result.response = {{"type", "ack_ok"}, {"room_id", request.room}, {"message_id", request.number}};
        else result.response = {{"type", "error"}, {"message", "message not found in room"}};
    } else throw std::logic_error("unsupported dispatcher request");
    return result;
}
