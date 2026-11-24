#include <App.h>
#include <nlohmann/json.hpp>
#include "StorageWorker.h"
#include "RedisBridge.h"
#include "SignalWatcher.h"
#include "ConnectionManager.h"
#include "MessageDispatcher.h"
#include "Protocol.h"
#include "RecentEvents.h"
#include <atomic>
#include <cstdint>
#include <iostream>
#include <memory>
#include <string>

using Json = nlohmann::json;
using Protocol::text_field;
using Protocol::nonnegative_integer;
static std::string member_topic(const std::string &room, const std::string &user) {
    return "member:" + Json::array({room, user}).dump();
}
int main(int argc, char **argv) {
    std::string database = "messages.db";
    try {
        std::string redis_host = "127.0.0.1", instance;
        int port = 9001, redis_port = 6379;
        bool redis_enabled = true;
        auto parse_port = [](const std::string &s) {
            std::size_t consumed = 0;
            int value = std::stoi(s, &consumed);
            if (consumed != s.size() || value < 1 || value > 65535) throw std::invalid_argument("invalid port");
            return value;
        };
        for (int i = 1; i < argc; ++i) {
            const std::string arg = argv[i];
            if (arg == "--no-redis") { redis_enabled = false; continue; }
            if (++i >= argc) throw std::invalid_argument("missing option value");
            if (arg == "--db") database = argv[i];
            else if (arg == "--port") port = parse_port(argv[i]);
            else if (arg == "--redis-host") redis_host = argv[i];
            else if (arg == "--redis-port") redis_port = parse_port(argv[i]);
            else if (arg == "--instance-id") instance = argv[i];
            else throw std::invalid_argument("unknown option: " + arg);
        }
        if (instance.empty()) instance = "instance-" + std::to_string(port);
        if (instance.size() > 64) throw std::invalid_argument("instance ID too long");
        sigset_t signals = block_shutdown_signals();
        uWS::App app;
        auto *loop = uWS::Loop::get();
        ConnectionManager connections;
        std::size_t in_flight = 0;
        std::unique_ptr<RedisPublisher> publisher;
        std::unique_ptr<RedisSubscriber> subscriber;
        auto pending_redis = std::make_shared<std::atomic<unsigned>>(0);
        auto recent_events = std::make_shared<RecentEvents>(8192);
        if (redis_enabled) {
            publisher = std::make_unique<RedisPublisher>(redis_host, redis_port);
            subscriber = std::make_unique<RedisSubscriber>(redis_host, redis_port,
                [instance, pending_redis, recent_events, loop, &app](std::string raw) {
                    Json event = Protocol::parse_object(raw, 65536);
                    if (!event.is_object() || !text_field(event, "instance_id", 64) || event["instance_id"] == instance ||
                        !event.contains("message") || !event["message"].is_object() || !event.contains("recipients") ||
                        !event["recipients"].is_array() || event["recipients"].size() > 4096) return;
                    for (const auto &user : event["recipients"]) if (!user.is_string() || user.get_ref<const std::string &>().empty() || user.get_ref<const std::string &>().size() > 64) return;
                    Json message = std::move(event["message"]);
                    std::int64_t id = 0;
                    if (!text_field(message, "room_id", 64) || !text_field(message, "sender_id", 64) ||
                        !text_field(message, "client_msg_id", 128) || !text_field(message, "content", 4096) ||
                        !text_field(message, "created_at", 64) || !nonnegative_integer(message, "message_id", id) || id == 0 ||
                        !message.contains("type") || message["type"] != "message") return;
                    unsigned count = pending_redis->load();
                    do {
                        if (count >= 256) { std::cerr << "Redis delivery queue full; use history" << std::endl; return; }
                    } while (!pending_redis->compare_exchange_weak(count, count + 1));
                    const std::string key = event["instance_id"].get<std::string>() + ":" + std::to_string(id);
                    if (!recent_events->claim(key)) { --*pending_redis; return; }
                    loop->defer([message = std::move(message), recipients = std::move(event["recipients"]), pending_redis, &app]() {
                        --*pending_redis;
                        const auto payload = message.dump();
                        for (const auto &user : recipients)
                            app.publish(member_topic(message["room_id"], user), payload, uWS::OpCode::TEXT);
                    });
                });
        }
        StorageWorker worker(database);
        SignalWatcher signal_watcher(signals, loop, app);
        uWS::App::WebSocketBehavior<Connection> behavior{};
        behavior.maxPayloadLength = 16 * 1024;
        behavior.maxBackpressure = 64 * 1024;
        behavior.closeOnBackpressureLimit = true;
        behavior.idleTimeout = 30;
        behavior.sendPingsAutomatically = true;
        behavior.open = [&connections](auto *ws) { connections.attach(ws); };
        behavior.dropped = [](auto *ws, std::string_view, uWS::OpCode) {
            auto *connection = ws->getUserData();
            if (!connection->backpressure_reported) {
                connection->backpressure_reported = true;
                std::cerr << "backpressure limit reached for connection " << connection->id << std::endl;
            }
        };
        behavior.close = [&connections](auto *ws, int, std::string_view) {
            if (ws->getUserData()->backpressure_reported)
                std::cerr << "backpressured connection closed " << ws->getUserData()->id << std::endl;
            connections.detach(ws);
        };
        behavior.message = [&app, &connections, &worker, &in_flight, &publisher, instance, loop](auto *ws, std::string_view input, uWS::OpCode opcode) {
            auto reply = [ws](const Json &value) { ws->send(value.dump(), uWS::OpCode::TEXT); };
            auto error = [&reply](const char *message) { reply(Json{{"type", "error"}, {"message", message}}); };
            if (opcode != uWS::OpCode::TEXT) { error("text frames only"); return; }
            Json value = Protocol::parse_object(input);
            if (!value.is_object() || !text_field(value, "type", 16)) { error("expected JSON object with type ping"); return; }
            const std::string type = value["type"];
            auto *connection = ws->getUserData();
            if (type == "ping") { reply(Json{{"type", "pong"}}); return; }
            if (type == "auth") {
                if (!connection->user.empty()) { error("already authenticated"); return; }
                if (!text_field(value, "token", 64)) { error("invalid credentials"); return; }
                const auto &token = value["token"].get_ref<const std::string &>();
                if (token == "demo-alice") connection->user = "alice";
                else if (token == "demo-bob") connection->user = "bob";
                else { error("invalid credentials"); return; }
                reply(Json{{"type", "auth_ok"}, {"user_id", connection->user}}); return;
            }
            if (connection->user.empty()) { error("authentication required"); return; }
            if (type != "create_room" && type != "join" && type != "leave" && type != "send" && type != "history" && type != "ack") { error("unknown type"); return; }
            if (!text_field(value, "room_id", 64)) { error("invalid room_id"); return; }
            const std::string room = value["room_id"];
            const auto topic = member_topic(room, connection->user);
            if (type == "join") {
                if (!connection->rooms.count(room) && connection->rooms.size() >= 32) { error("room limit reached"); return; }
            }
            if (type == "leave") {
                if (!connection->rooms.count(room)) { error("not in room"); return; }
            }
            if (type != "create_room" && type != "join" && type != "leave" && !connection->rooms.count(room)) { error("not in room"); return; }
            if (type == "send" && (!text_field(value, "content", 4096) || !text_field(value, "client_msg_id", 128))) {
                error("invalid message fields"); return;
            }
            std::int64_t number = 0;
            if (type == "ack" && (!nonnegative_integer(value, "message_id", number) || number == 0)) { error("invalid message_id"); return; }
            bool use_offset = false;
            if (type == "history") {
                use_offset = !value.contains("after_message_id");
                if (!use_offset && !nonnegative_integer(value, "after_message_id", number)) { error("invalid after_message_id"); return; }
            }
            if (in_flight >= 256) { error("storage queue full"); return; }
            const auto id = connection->id;
            const std::string user = connection->user;
            const std::string content = type == "send" ? value["content"].get<std::string>() : "";
            const std::string client_id = type == "send" ? value["client_msg_id"].get<std::string>() : "";
            const DispatchRequest request{type, room, user, content, client_id, number, use_offset};
            ++in_flight;
            bool accepted = worker.submit([=, &app, &connections, &in_flight, &publisher](MessageStore &repo) {
                Json response, broadcast;
                std::vector<std::string> recipients;
                try {
                    auto result = MessageDispatcher::dispatch(repo, request);
                    response = std::move(result.response);
                    broadcast = std::move(result.broadcast);
                    recipients = std::move(result.recipients);
                } catch (const std::invalid_argument &) {
                    response = {{"type", "error"}, {"message", "client_msg_id conflict"}};
                } catch (const std::exception &e) {
                    std::cerr << "storage error: " << e.what() << std::endl;
                    response = {{"type", "error"}, {"message", "storage failure"}};
                }
                loop->defer([id, topic, room, type, instance, response = std::move(response), broadcast = std::move(broadcast), recipients = std::move(recipients), &app, &connections, &in_flight, &publisher]() mutable {
                    --in_flight;
                    if (response.value("type", "") == "joined" && !connections.change_room(id, room, topic, true)) response = {{"type", "error"}, {"message", "room limit reached"}};
                    if (response.value("type", "") == "left") connections.change_room(id, room, topic, false);
                    connections.send(id, response.dump());
                    if (!broadcast.is_null()) {
                        for (const auto &user : recipients) app.publish(member_topic(room, user), broadcast.dump(), uWS::OpCode::TEXT);
                        if (publisher && !publisher->publish(Json{{"instance_id", instance}, {"message", broadcast}, {"recipients", recipients}}.dump()))
                            std::cerr << "Redis publish queue full; message retained in SQLite" << std::endl;
                    }
                });
            });
            if (!accepted) { --in_flight; error("storage queue full"); }
        };
        bool listening = false;
        app.ws<Connection>("/*", std::move(behavior)).listen("127.0.0.1", port, [&](auto *socket) {
            listening = socket != nullptr;
            if (listening) std::cout << "Listening on 127.0.0.1:" << port << std::endl;
            else std::cerr << "Failed to listen on 127.0.0.1:" << port << std::endl;
        }).run();
        return listening ? 0 : 1;
    } catch (const std::exception &e) {
        std::cerr << "startup failure: " << e.what() << std::endl;
        return 1;
    }
}
