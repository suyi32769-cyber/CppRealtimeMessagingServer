#include "MessageRepository.h"
#include <gtest/gtest.h>
#include <cstdio>
#include <unistd.h>

TEST(MessageRepository, StoresAndDeduplicates) {
    MessageRepository repo(":memory:");
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
    auto one = repo.insert("room", "alice", "1", "first");
    auto two = repo.insert("room", "alice", "2", "second");
    auto page = repo.history("room", one.message.id, 10);
    ASSERT_EQ(page.size(), 1u);
    EXPECT_EQ(page[0].id, two.message.id);
    EXPECT_FALSE(repo.acknowledge("bob", "other", two.message.id));
    EXPECT_TRUE(repo.acknowledge("bob", "room", two.message.id));
    EXPECT_TRUE(repo.acknowledge("bob", "room", one.message.id));
    EXPECT_EQ(repo.offset("bob", "room"), two.message.id);
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
