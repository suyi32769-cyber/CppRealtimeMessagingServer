#pragma once
#include <cstdint>
#include <string>
#include <vector>

struct StoredMessage {
    std::int64_t id;
    std::string room, sender, client_id, content, created_at;
};
struct InsertResult {
    StoredMessage message;
    bool inserted;
};

// A storage adapter is used by only its owning worker thread.
class MessageStore {
public:
    virtual ~MessageStore() = default;
    virtual bool create_room(const std::string &room, const std::string &user) = 0;
    virtual bool join_room(const std::string &room, const std::string &user) = 0;
    virtual bool leave_room(const std::string &room, const std::string &user) = 0;
    virtual bool is_member(const std::string &room, const std::string &user) = 0;
    virtual std::vector<std::string> room_members(const std::string &room) = 0;
    virtual InsertResult insert(const std::string &room, const std::string &sender,
                                const std::string &client_id, const std::string &content) = 0;
    virtual std::vector<StoredMessage> history(const std::string &room, std::int64_t after, int limit) = 0;
    virtual bool acknowledge(const std::string &user, const std::string &room, std::int64_t id) = 0;
    virtual std::int64_t offset(const std::string &user, const std::string &room) = 0;
};
