#include "MessageRepository.h"
#include <gtest/gtest.h>
#include <cstdio>
#include <unistd.h>

TEST(MessageRepository, StoresAndDeduplicates) {
    MessageRepository repo(":memory:");
    ASSERT_TRUE(repo.create_room("room", "alice"));
    ASSERT_TRUE(repo.create_room("other", "alice"));
    auto first = repo.insert("room", "alice", "client-1", "hello");
    auto duplicate = repo.insert("room", "alice", "client-1", "hello");
    EXPECT_TRUE(first.inserted);
    EXPECT_FALSE(duplicate.inserted);
    EXPECT_EQ(first.message.id, duplicate.message.id);
    EXPECT_FALSE(first.message.created_at.empty());
    EXPECT_THROW(repo.insert("other", "alice", "client-1", "different"), std::invalid_argument);
    EXPECT_EQ(repo.history("room", 0, 20).size(), 1u);
    EXPECT_TRUE(repo.history("other", 0, 20).empty());
}

TEST(MessageRepository, HistoryAndMonotonicAcknowledgement) {
    MessageRepository repo(":memory:");
    ASSERT_TRUE(repo.create_room("room", "alice"));
    auto one = repo.insert("room", "alice", "1", "first");
    auto two = repo.insert("room", "alice", "2", "second");
    auto page = repo.history("room", one.message.id, 10);
    ASSERT_EQ(page.size(), 1u);
    EXPECT_EQ(page[0].id, two.message.id);
    EXPECT_FALSE(repo.acknowledge("bob", "other", two.message.id));
    EXPECT_TRUE(repo.acknowledge("bob", "room", two.message.id));
    EXPECT_EQ(repo.offset("bob", "room"), 0);
    EXPECT_TRUE(repo.acknowledge("bob", "room", one.message.id));
    EXPECT_EQ(repo.offset("bob", "room"), two.message.id);
}

TEST(MessageRepository, UpgradePreservesLegacyOffsetAndReplaysPotentialGaps) {
    char path[] = "/tmp/realtime-migration-XXXXXX";
    int fd = mkstemp(path);
    ASSERT_GE(fd, 0);
    close(fd);
    struct Cleanup {
        std::string path;
        ~Cleanup() { std::remove(path.c_str()); std::remove((path + "-wal").c_str()); std::remove((path + "-shm").c_str()); }
    } cleanup{path};
    {
        SQLite::Database db(path, SQLite::OPEN_READWRITE);
        db.exec("CREATE TABLE users(user_id TEXT PRIMARY KEY)");
        db.exec("CREATE TABLE rooms(room_id TEXT PRIMARY KEY)");
        db.exec("CREATE TABLE messages(message_id INTEGER PRIMARY KEY AUTOINCREMENT, room_id TEXT NOT NULL, sender_id TEXT NOT NULL, client_msg_id TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(sender_id,client_msg_id))");
        db.exec("CREATE TABLE user_room_offsets(user_id TEXT NOT NULL, room_id TEXT NOT NULL, message_id INTEGER NOT NULL, PRIMARY KEY(user_id,room_id))");
        db.exec("INSERT INTO users VALUES('alice'),('bob')");
        db.exec("INSERT INTO rooms VALUES('room')");
        db.exec("INSERT INTO messages VALUES(1,'room','alice','1','first','time'),(2,'room','alice','2','second','time')");
        db.exec("INSERT INTO user_room_offsets VALUES('bob','room',2)");
    }
    {
        MessageRepository repo(path);
        EXPECT_EQ(repo.offset("bob", "room"), 0);
        EXPECT_EQ(repo.history("room", repo.offset("bob", "room"), 10).size(), 2u);
        ASSERT_TRUE(repo.acknowledge("bob", "room", 2));
        EXPECT_EQ(repo.offset("bob", "room"), 0);
        ASSERT_TRUE(repo.acknowledge("bob", "room", 1));
        EXPECT_EQ(repo.offset("bob", "room"), 2);
    }
    {
        MessageRepository repo(path);
        EXPECT_EQ(repo.offset("bob", "room"), 2);
        SQLite::Database db(path, SQLite::OPEN_READONLY);
        SQLite::Statement legacy(db, "SELECT message_id FROM user_room_offsets_legacy WHERE user_id='bob' AND room_id='room'");
        ASSERT_TRUE(legacy.executeStep());
        EXPECT_EQ(legacy.getColumn(0).getInt64(), 2);
    }
}

TEST(MessageRepository, PersistsAcrossReopen) {
    char path[] = "/tmp/realtime-repository-XXXXXX";
    int fd = mkstemp(path);
    ASSERT_GE(fd, 0);
    close(fd);
    struct Cleanup {
        std::string path;
        ~Cleanup() {
            std::remove(path.c_str());
            std::remove((path + "-wal").c_str());
            std::remove((path + "-shm").c_str());
        }
    } cleanup{path};
    std::int64_t id = 0;
    {
        MessageRepository repo(path);
        ASSERT_TRUE(repo.create_room("room", "alice"));
        id = repo.insert("room", "alice", "persist-1", "saved").message.id;
        ASSERT_TRUE(repo.acknowledge("bob", "room", id));
    }
    {
        MessageRepository repo(path);
        auto messages = repo.history("room", 0, 10);
        ASSERT_EQ(messages.size(), 1u);
        EXPECT_EQ(messages[0].content, "saved");
        EXPECT_EQ(repo.offset("bob", "room"), id);
    }
}
