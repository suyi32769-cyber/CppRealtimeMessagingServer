#pragma once
#include <cstddef>
#include <deque>
#include <string>
#include <unordered_set>
#include <utility>

// Confined to the Redis subscriber thread; old entries are evicted to bound memory.
class RecentEvents {
public:
    explicit RecentEvents(std::size_t capacity) : capacity_(capacity) {}
    bool claim(std::string key) {
        if (!capacity_ || entries_.count(key)) return false;
        if (order_.size() == capacity_) {
            entries_.erase(order_.front());
            order_.pop_front();
        }
        entries_.insert(key);
        order_.push_back(std::move(key));
        return true;
    }
private:
    std::size_t capacity_;
    std::deque<std::string> order_;
    std::unordered_set<std::string> entries_;
};
