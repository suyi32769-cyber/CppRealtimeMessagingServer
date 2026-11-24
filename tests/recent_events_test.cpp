#include "RecentEvents.h"
#include <gtest/gtest.h>

TEST(RecentEvents, SuppressesDuplicatesAndEvictsOldest) {
    RecentEvents seen(2);
    EXPECT_TRUE(seen.claim("a:1"));
    EXPECT_FALSE(seen.claim("a:1"));
    EXPECT_TRUE(seen.claim("b:2"));
    EXPECT_TRUE(seen.claim("c:3"));
    EXPECT_TRUE(seen.claim("a:1"));
}
