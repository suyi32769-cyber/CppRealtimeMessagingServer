#include "ConnectionManager.h"

void ConnectionManager::attach(Socket *socket) {
    auto id = ++next_id_;
    socket->getUserData()->id = id;
    sockets_.emplace(id, socket);
}
void ConnectionManager::detach(Socket *socket) {
    sockets_.erase(socket->getUserData()->id);
}
void ConnectionManager::send(std::uint64_t id, const std::string &payload) {
    auto found = sockets_.find(id);
    if (found != sockets_.end()) found->second->send(payload, uWS::OpCode::TEXT);
}
bool ConnectionManager::change_room(std::uint64_t id, const std::string &room, const std::string &topic, bool join) {
    auto found = sockets_.find(id);
    if (found == sockets_.end()) return false;
    auto *socket = found->second;
    if (join) {
        if (!socket->getUserData()->rooms.count(room) && socket->getUserData()->rooms.size() >= 32) return false;
        socket->getUserData()->rooms.insert(room);
        socket->subscribe(topic);
    } else {
        socket->getUserData()->rooms.erase(room);
        socket->unsubscribe(topic);
    }
    return true;
}
