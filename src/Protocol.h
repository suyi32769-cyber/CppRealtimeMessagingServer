#pragma once
#include <nlohmann/json.hpp>
#include <cstdint>
#include <limits>
#include <string>
#include <string_view>

namespace Protocol {
using Json = nlohmann::json;

inline Json parse_object(std::string_view input, std::size_t limit = 16 * 1024) {
    if (input.size() > limit) return Json();
    try {
        Json value = Json::parse(input, nullptr, false);
        return value.is_object() ? value : Json();
    } catch (const Json::exception &) {
        return Json();
    }
}
inline bool text_field(const Json &v, const char *key, std::size_t max) {
    if (!v.is_object()) return false;
    auto it = v.find(key);
    return it != v.end() && it->is_string() && !it->get_ref<const std::string &>().empty()
        && it->get_ref<const std::string &>().size() <= max;
}
inline bool nonnegative_integer(const Json &v, const char *key, std::int64_t &out) {
    if (!v.is_object()) return false;
    auto it = v.find(key);
    if (it == v.end() || !it->is_number_integer()) return false;
    if (it->is_number_unsigned() && it->get<std::uint64_t>() > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) return false;
    out = it->get<std::int64_t>();
    return out >= 0;
}
}
