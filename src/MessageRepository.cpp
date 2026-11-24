#include "MessageRepository.h"
#include <algorithm>
#include <chrono>
#include <sqlite3.h>
#include <stdexcept>
#include <thread>

namespace {
StoredMessage read_message(SQLite::Statement &q) {
    return {q.getColumn(0).getInt64(), q.getColumn(1).getString(), q.getColumn(2).getString(),
            q.getColumn(3).getString(), q.getColumn(4).getString(), q.getColumn(5).getString()};
}
template <typename F>
auto retry_busy(F operation) -> decltype(operation()) {
    for (int attempt = 0;; ++attempt) {
        try { return operation(); }
        catch (const SQLite::Exception &e) {
            const int code = e.getErrorCode() & 0xff;
            if ((code != SQLITE_BUSY && code != SQLITE_LOCKED) || attempt >= 5) throw;
            std::this_thread::sleep_for(std::chrono::milliseconds(25 * (1 << attempt)));
        }
    }
}
}

MessageRepository::MessageRepository(const std::string &path)
    : db_(path, SQLite::OPEN_READWRITE | SQLite::OPEN_CREATE) {
    db_.setBusyTimeout(750);
    db_.exec("PRAGMA journal_mode=WAL");
    db_.exec("PRAGMA foreign_keys=ON");
    db_.exec("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY)");
    db_.exec("CREATE TABLE IF NOT EXISTS rooms (room_id TEXT PRIMARY KEY)");
    db_.exec("CREATE TABLE IF NOT EXISTS room_members (room_id TEXT NOT NULL REFERENCES rooms(room_id), "
             "user_id TEXT NOT NULL REFERENCES users(user_id), PRIMARY KEY(room_id,user_id))");
    db_.exec("CREATE TABLE IF NOT EXISTS messages (message_id INTEGER PRIMARY KEY AUTOINCREMENT, "
             "room_id TEXT NOT NULL REFERENCES rooms(room_id), sender_id TEXT NOT NULL REFERENCES users(user_id), "
             "client_msg_id TEXT NOT NULL, content TEXT NOT NULL, "
             "created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), "
             "UNIQUE(sender_id, client_msg_id))");
    db_.exec("CREATE INDEX IF NOT EXISTS idx_messages_room_id ON messages(room_id, message_id)");
    db_.exec("CREATE TABLE IF NOT EXISTS user_room_offsets (user_id TEXT NOT NULL REFERENCES users(user_id), "
             "room_id TEXT NOT NULL REFERENCES rooms(room_id), message_id INTEGER NOT NULL, "
             "PRIMARY KEY(user_id,room_id))");
    // Existing prefix offsets cannot prove that earlier messages were actually received.
    // Preserve them for audit and conservatively replay history once on upgrade.
    SQLite::Transaction migration(db_, SQLite::TransactionBehavior::IMMEDIATE);
    db_.exec("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)");
    db_.exec("CREATE TABLE IF NOT EXISTS user_message_acks (user_id TEXT NOT NULL REFERENCES users(user_id), "
             "room_id TEXT NOT NULL REFERENCES rooms(room_id), message_id INTEGER NOT NULL REFERENCES messages(message_id), "
             "PRIMARY KEY(user_id,room_id,message_id))");
    SQLite::Statement applied(db_, "SELECT 1 FROM schema_migrations WHERE name = 'individual_ack_v1'");
    if (!applied.executeStep()) {
        db_.exec("CREATE TABLE user_room_offsets_legacy AS SELECT user_id, room_id, message_id FROM user_room_offsets");
        db_.exec("UPDATE user_room_offsets SET message_id = 0");
        db_.exec("INSERT INTO schema_migrations(name) VALUES ('individual_ack_v1')");
    }
    migration.commit();
}

bool MessageRepository::create_room(const std::string &room, const std::string &user) {
    return retry_busy([&] {
        SQLite::Transaction tx(db_, SQLite::TransactionBehavior::IMMEDIATE);
        SQLite::Statement q(db_, "INSERT OR IGNORE INTO rooms(room_id) VALUES (?)");
        q.bind(1, room);
        if (!q.exec()) return false;
        SQLite::Statement u(db_, "INSERT OR IGNORE INTO users(user_id) VALUES (?)");
        u.bind(1, user); u.exec();
        SQLite::Statement member(db_, "INSERT INTO room_members(room_id,user_id) VALUES (?,?)");
        member.bind(1, room); member.bind(2, user); member.exec();
        tx.commit();
        return true;
    });
}

bool MessageRepository::join_room(const std::string &room, const std::string &user) {
    return retry_busy([&] {
        SQLite::Transaction tx(db_, SQLite::TransactionBehavior::IMMEDIATE);
        SQLite::Statement exists(db_, "SELECT 1 FROM rooms WHERE room_id=?");
        exists.bind(1, room);
        if (!exists.executeStep()) return false;
        SQLite::Statement u(db_, "INSERT OR IGNORE INTO users(user_id) VALUES (?)");
        u.bind(1, user); u.exec();
        SQLite::Statement member(db_, "INSERT OR IGNORE INTO room_members(room_id,user_id) VALUES (?,?)");
        member.bind(1, room); member.bind(2, user); member.exec();
        tx.commit();
        return true;
    });
}

bool MessageRepository::leave_room(const std::string &room, const std::string &user) {
    return retry_busy([&] {
        SQLite::Statement q(db_, "DELETE FROM room_members WHERE room_id=? AND user_id=?");
        q.bind(1, room); q.bind(2, user);
        return q.exec() != 0;
    });
}

bool MessageRepository::is_member(const std::string &room, const std::string &user) {
    SQLite::Statement q(db_, "SELECT 1 FROM room_members WHERE room_id=? AND user_id=?");
    q.bind(1, room); q.bind(2, user);
    return q.executeStep();
}

std::vector<std::string> MessageRepository::room_members(const std::string &room) {
    SQLite::Statement q(db_, "SELECT user_id FROM room_members WHERE room_id=? ORDER BY user_id");
    q.bind(1, room);
    std::vector<std::string> members;
    while (q.executeStep()) members.push_back(q.getColumn(0).getString());
    return members;
}

InsertResult MessageRepository::insert(const std::string &room, const std::string &sender,
                                       const std::string &client_id, const std::string &content) {
    return retry_busy([&] { return insert_once(room, sender, client_id, content); });
}

InsertResult MessageRepository::insert_once(const std::string &room, const std::string &sender,
                                            const std::string &client_id, const std::string &content) {
    SQLite::Transaction transaction(db_, SQLite::TransactionBehavior::IMMEDIATE);
    if (!is_member(room, sender)) throw std::runtime_error("not a room member");
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
    return retry_busy([&] { return acknowledge_once(user, room, id); });
}

bool MessageRepository::acknowledge_once(const std::string &user, const std::string &room, std::int64_t id) {
    SQLite::Transaction transaction(db_, SQLite::TransactionBehavior::IMMEDIATE);
    SQLite::Statement exists(db_, "SELECT 1 FROM messages WHERE room_id=? AND message_id=?");
    exists.bind(1, room); exists.bind(2, id);
    if (!exists.executeStep()) return false;
    SQLite::Statement u(db_, "INSERT OR IGNORE INTO users(user_id) VALUES (?)");
    u.bind(1, user); u.exec();
    SQLite::Statement mark(db_, "INSERT OR IGNORE INTO user_message_acks(user_id,room_id,message_id) VALUES (?,?,?)");
    mark.bind(1, user); mark.bind(2, room); mark.bind(3, id); mark.exec();
    const auto current = offset(user, room);
    SQLite::Statement gap(db_, "SELECT COALESCE(MIN(m.message_id),0) FROM messages m "
                               "WHERE m.room_id=? AND m.message_id>? AND NOT EXISTS "
                               "(SELECT 1 FROM user_message_acks a WHERE a.user_id=? AND a.room_id=m.room_id AND a.message_id=m.message_id)");
    gap.bind(1, room); gap.bind(2, current); gap.bind(3, user);
    gap.executeStep();
    const auto first_gap = gap.getColumn(0).getInt64();
    SQLite::Statement prefix(db_, "SELECT COALESCE(MAX(message_id),0) FROM messages "
                                  "WHERE room_id=? AND message_id>? AND (?=0 OR message_id<?)");
    prefix.bind(1, room); prefix.bind(2, current); prefix.bind(3, first_gap); prefix.bind(4, first_gap);
    prefix.executeStep();
    const auto advanced = std::max(current, static_cast<std::int64_t>(prefix.getColumn(0).getInt64()));
    SQLite::Statement q(db_, "INSERT INTO user_room_offsets(user_id,room_id,message_id) VALUES (?,?,?) "
                             "ON CONFLICT(user_id,room_id) DO UPDATE SET message_id=excluded.message_id");
    q.bind(1, user); q.bind(2, room); q.bind(3, advanced); q.exec();
    transaction.commit();
    return true;
}

std::int64_t MessageRepository::offset(const std::string &user, const std::string &room) {
    SQLite::Statement q(db_, "SELECT message_id FROM user_room_offsets WHERE user_id=? AND room_id=?");
    q.bind(1, user); q.bind(2, room);
    return q.executeStep() ? q.getColumn(0).getInt64() : 0;
}
