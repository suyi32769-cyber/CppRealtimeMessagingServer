#include <SQLiteCpp/SQLiteCpp.h>
#include <hiredis/hiredis.h>
#include <nlohmann/json.hpp>
#include <iostream>
#include <memory>
#include <stdexcept>

int main() {
    try {
        SQLite::Database db(":memory:", SQLite::OPEN_READWRITE | SQLite::OPEN_CREATE);
        db.exec("CREATE TABLE sample (value TEXT NOT NULL)");
        SQLite::Statement insert(db, "INSERT INTO sample(value) VALUES (?)");
        insert.bind(1, "sqlite-ok");
        insert.exec();
        SQLite::Statement select(db, "SELECT value FROM sample");
        if (!select.executeStep() || select.getColumn(0).getString() != "sqlite-ok") throw std::runtime_error("SQLite read failed");
        std::cout << "PASS: SQLiteCpp insert and read" << std::endl;
        auto value = nlohmann::json::parse(R"({"ok":true})");
        if (!value.at("ok").get<bool>()) throw std::runtime_error("JSON read failed");
        std::cout << "PASS: nlohmann/json parse" << std::endl;
        using Context = std::unique_ptr<redisContext, decltype(&redisFree)>;
        using Reply = std::unique_ptr<redisReply, decltype(&freeReplyObject)>;
        Context context(redisConnect("127.0.0.1", 16379), redisFree);
        if (!context || context->err) throw std::runtime_error("Redis connection failed");
        Reply reply(static_cast<redisReply *>(redisCommand(context.get(), "PING")), freeReplyObject);
        if (!reply || reply->type != REDIS_REPLY_STATUS || std::string(reply->str, reply->len) != "PONG") throw std::runtime_error("Redis PING failed");
        std::cout << "PASS: Hiredis Redis PING -> PONG" << std::endl;
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "FAIL: " << e.what() << std::endl;
        return 1;
    }
}
