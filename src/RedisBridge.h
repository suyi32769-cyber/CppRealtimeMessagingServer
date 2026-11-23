#pragma once
#include <atomic>
#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <string>
#include <thread>

// The two Hiredis contexts are created, used and freed on their owning threads.
class RedisPublisher {
public:
    RedisPublisher(std::string host, int port);
    ~RedisPublisher();
    bool publish(std::string event);
private:
    void run();
    std::string host_;
    int port_;
    std::mutex mutex_;
    std::condition_variable cv_;
    std::deque<std::string> queue_;
    bool stopping_ = false;
    std::thread thread_;
};

class RedisSubscriber {
public:
    using Callback = std::function<void(std::string)>;
    RedisSubscriber(std::string host, int port, Callback callback);
    ~RedisSubscriber();
private:
    void run();
    std::string host_;
    int port_;
    Callback callback_;
    std::atomic<bool> stopping_{false};
    std::thread thread_;
};
