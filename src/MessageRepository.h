#pragma once

#include "MessageStore.h"
#include <SQLiteCpp/SQLiteCpp.h>

// Own and use each instance on one thread; SQLite serializes concurrent writers.
class MessageRepository final : public MessageStore {
public:
    explicit MessageRepository(const std::string &path);
    bool create_room(const std::string &room, const std::string &user) override;
    bool join_room(const std::string &room, const std::string &user) override;
    bool leave_room(const std::string &room, const std::string &user) override;
    bool is_member(const std::string &room, const std::string &user) override;
    std::vector<std::string> room_members(const std::string &room) override;
    InsertResult insert(const std::string &room, const std::string &sender,
                        const std::string &client_id, const std::string &content) override;
    std::vector<StoredMessage> history(const std::string &room, std::int64_t after, int limit) override;
    bool acknowledge(const std::string &user, const std::string &room, std::int64_t id) override;
    std::int64_t offset(const std::string &user, const std::string &room) override;
private:
    InsertResult insert_once(const std::string &room, const std::string &sender,
                             const std::string &client_id, const std::string &content);
    bool acknowledge_once(const std::string &user, const std::string &room, std::int64_t id);
    SQLite::Database db_;
};
