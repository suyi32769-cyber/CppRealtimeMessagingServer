#include "MessageRepository.h"
#include <algorithm>
#include <stdexcept>

namespace {
StoredMessage read_message(SQLite::Statement &q) {
    return {q.getColumn(0).getInt64(), q.getColumn(1).getString(), q.getColumn(2).getString(),
            q.getColumn(3).getString(), q.getColumn(4).getString(), q.getColumn(5).getString()};
}
}

MessageRepository::MessageRepository(const std::string &path)
    : db_(path, SQLite::OPEN_READWRITE | SQLite::OPEN_CREATE) {
    db_.setBusyTimeout(3000);
    db_.exec("PRAGMA journal_mode=WAL");
    db_.exec("PRAGMA foreign_keys=ON");
    db_.exec("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY)");
    db_.exec("CREATE TABLE IF NOT EXISTS rooms (room_id TEXT PRIMARY KEY)");
    db_.exec("CREATE TABLE IF NOT EXISTS messages (message_id INTEGER PRIMARY KEY AUTOINCREMENT, "
             "room_id TEXT NOT NULL REFERENCES rooms(room_id), sender_id TEXT NOT NULL REFERENCES users(user_id), "
             "client_msg_id TEXT NOT NULL, content TEXT NOT NULL, "
             "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), "
             "UNIQUE(sender_id, client_msg_id))");
    db_.exec("CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room_id, message_id)");
    db_.exec("CREATE TABLE IF NOT EXISTS user_room_offsets (user_id TEXT NOT NULL REFERENCES users(user_id), "
             "room_id TEXT NOT NULL REFERENCES rooms(room_id), message_id INTEGER NOT NULL, "
             "PRIMARY KEY(user_id,room_id))");
}

InsertResult MessageRepository::insert(const std::string &room, const std::string &sender,
                                       const std::string &client_id, const std::string &content) {
    SQLite::Transaction transaction(db_);
    SQLite::Statement user(db_, "INSERT OR IGNORE INTO users(user_id) VALUES (?)");
    user.bind(1, sender); user.exec();
    SQLite::Statement room_insert(db_, "INSERT OR IGNORE INTO rooms(room_id) VALUES (?)");
    room_insert.bind(1, room); room_insert.exec();
    SQLite::Statement insert(db_, "INSERT OR IGNORE INTO messages(room_id,sender_id,client_msg_id,content) VALUES (?,?,?,?)");
    insert.bind(1, room); insert.bind(2, sender); insert.bind(3, client_id); insert.bind(4, content);
    const bool inserted = insert.exec() == 1;
    SQLite::Statement find(db_, "SELECT message_id,room_id,sender_id,client_msg_id,content,created_at FROM messages WHERE sender_id=? AND client_msg_id=?");
    find.bind(1, sender); find.bind(2, client_id);
    if (!find.executeStep()) throw std::runtime_error("inserted message not found");
    StoredMessage message = read_message(find);
    // Conflicting retries must not silently alias a different request.
    if (!inserted && (message.room != room || message.content != content))
        throw std::invalid_argument("client message ID already used for different content or room");
    transaction.commit();
    return {std::move(message), inserted};
}

std::vector<StoredMessage> MessageRepository::history(const std::string &room, std::int64_t after, int limit) {
    SQLite::Statement q(db_, "SELECT message_id,room_id,sender_id,client_msg_id,content,created_at FROM messages WHERE room_id=? AND message_id>? ORDER BY message_id LIMIT ?");
    q.bind(1, room); q.bind(2, after); q.bind(3, std::clamp(limit, 1, 100));
    std::vector<StoredMessage> result;
    while (q.executeStep()) result.push_back(read_message(q));
    return result;
}

bool MessageRepository::acknowledge(const std::string &user, const std::string &room, std::int64_t id) {
    SQLite::Transaction transaction(db_);
    SQLite::Statement exists(db_, "SELECT 1 FROM messages WHERE room_id=? AND message_id=?");
    exists.bind(1, room); exists.bind(2, id);
    if (!exists.executeStep()) return false;
    SQLite::Statement u(db_, "INSERT OR IGNORE INTO users(user_id) VALUES (?)");
    u.bind(1, user); u.exec();
    SQLite::Statement q(db_, "INSERT INTO user_room_offsets(user_id,room_id,message_id) VALUES (?,?,?) "
                             "ON CONFLICT(user_id,room_id) DO UPDATE SET message_id=MAX(message_id,excluded.message_id)");
    q.bind(1, user); q.bind(2, room); q.bind(3, id); q.exec();
    transaction.commit();
    return true;
}

std::int64_t MessageRepository::offset(const std::string &user, const std::string &room) {
    SQLite::Statement q(db_, "SELECT message_id FROM user_room_offsets WHERE user_id=? AND room_id=?");
    q.bind(1, user); q.bind(2, room);
    return q.executeStep() ? q.getColumn(0).getInt64() : 0;
}
