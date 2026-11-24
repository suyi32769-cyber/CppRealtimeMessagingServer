#pragma once
#include <App.h>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <unordered_set>

struct Connection {
    std::uint64_t id = 0;
    std::string user;
    std::unordered_set<std::string> rooms;
    bool backpressure_reported = false;
};
using Socket = uWS::WebSocket<false, true, Connection>;

// Event-loop thread only. Deferred work must resolve an ID rather than retaining a socket.
class ConnectionManager {
public:
    void attach(Socket *socket);
    void detach(Socket *socket);
    void send(std::uint64_t id, const std::string &payload);
    bool change_room(std::uint64_t id, const std::string &room, const std::string &topic, bool join);
private:
    std::uint64_t next_id_ = 0;
    std::unordered_map<std::uint64_t, Socket *> sockets_;
};
