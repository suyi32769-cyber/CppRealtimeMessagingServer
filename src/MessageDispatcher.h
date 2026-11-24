#pragma once
#include "MessageStore.h"
#include <nlohmann/json.hpp>
#include <cstdint>
#include <string>

struct DispatchRequest {
    std::string type, room, user, content, client_id;
    std::int64_t number = 0;
    bool use_offset = false;
};
struct DispatchResult {
    nlohmann::json response;
    nlohmann::json broadcast;
    std::vector<std::string> recipients;
};

// Runs on the database worker's thread. Callers validate authorization and fields first.
class MessageDispatcher {
public:
    static DispatchResult dispatch(MessageStore &repo, const DispatchRequest &request);
};
