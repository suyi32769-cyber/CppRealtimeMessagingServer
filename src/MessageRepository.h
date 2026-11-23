#pragma once

#include <SQLiteCpp/SQLiteCpp.h>
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

// Own and use each instance on one thread; SQLite serializes concurrent writers.
class MessageRepository {
public:
    explicit MessageRepository(const std::string &path);
    InsertResult insert(const std::string &room, const std::string &sender,
                        const std::string &client_id, const std::string &content);
    std::vector<StoredMessage> history(const std::string &room, std::int64_t after, int limit);
    bool acknowledge(const std::string &user, const std::string &room, std::int64_t id);
    std::int64_t offset(const std::string &user, const std::string &room);
private:
    SQLite::Database db_;
};
