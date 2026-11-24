#include "Protocol.h"
#include <gtest/gtest.h>
#include <limits>

TEST(Protocol, RejectsMalformedAndNonObject) {
    EXPECT_TRUE(Protocol::parse_object("{broken").is_null());
    EXPECT_TRUE(Protocol::parse_object("[]").is_null());
    EXPECT_TRUE(Protocol::parse_object(std::string(16385, 'x')).is_null());
    EXPECT_TRUE(Protocol::parse_object("{\"n\":1e99999}").is_null());
    EXPECT_TRUE(Protocol::parse_object("{\"type\":\"ping\"}").is_object());
}

TEST(Protocol, ChecksFieldTypesAndIntegerBounds) {
    auto object = Protocol::parse_object(R"({"type":"send","empty":"","number":7,"negative":-1,"too_large":18446744073709551615})");
    EXPECT_TRUE(Protocol::text_field(object, "type", 4));
    EXPECT_FALSE(Protocol::text_field(object, "type", 3));
    EXPECT_FALSE(Protocol::text_field(object, "empty", 4));
    EXPECT_FALSE(Protocol::text_field(object, "number", 4));
    EXPECT_FALSE(Protocol::text_field(object, "missing", 4));
    std::int64_t value = 0;
    EXPECT_TRUE(Protocol::nonnegative_integer(object, "number", value));
    EXPECT_EQ(value, 7);
    EXPECT_FALSE(Protocol::nonnegative_integer(object, "negative", value));
    EXPECT_FALSE(Protocol::nonnegative_integer(object, "too_large", value));
    EXPECT_FALSE(Protocol::nonnegative_integer(object, "type", value));
}
