#include "RedisBridge.h"
#include <hiredis/hiredis.h>
#include <chrono>
#include <iostream>
#include <memory>
#include <poll.h>
#include <utility>

namespace {
constexpr char channel[] = "cpp-realtime-messages-v1";
using Context = std::unique_ptr<redisContext, decltype(&redisFree)>;
using Reply = std::unique_ptr<redisReply, decltype(&freeReplyObject)>;
Context connect(const std::string &host, int port) {
    timeval timeout{1, 0};
    Context context(redisConnectWithTimeout(host.c_str(), port, timeout), redisFree);
    if (!context || context->err || redisSetTimeout(context.get(), timeout) != REDIS_OK) return Context(nullptr, redisFree);
    return context;
}
}

RedisPublisher::RedisPublisher(std::string host, int port)
    : host_(std::move(host)), port_(port), thread_(&RedisPublisher::run, this) {}
RedisPublisher::~RedisPublisher() {
    {
        std::lock_guard<std::mutex> lock(mutex_);
        stopping_ = true;
        if (!queue_.empty()) std::cerr << "Redis shutdown: queued live events remain available in SQLite history" << std::endl;
        queue_.clear();
    }
    cv_.notify_one();
    thread_.join();
}
bool RedisPublisher::publish(std::string event) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (stopping_ || queue_.size() >= 256) return false;
    queue_.push_back(std::move(event));
    cv_.notify_one();
    return true;
}
void RedisPublisher::run() {
    Context context(nullptr, redisFree);
    for (;;) {
        std::string event;
        {
            std::unique_lock<std::mutex> lock(mutex_);
            cv_.wait(lock, [this] { return stopping_ || !queue_.empty(); });
            if (queue_.empty() && stopping_) break;
            event = std::move(queue_.front()); queue_.pop_front();
        }
        if (!context) context = connect(host_, port_);
        if (!context) { std::cerr << "Redis publish unavailable; message retained in SQLite" << std::endl; continue; }
        Reply reply(static_cast<redisReply *>(redisCommand(context.get(), "PUBLISH %s %b", channel, event.data(), event.size())), freeReplyObject);
        if (!reply || reply->type != REDIS_REPLY_INTEGER) {
            std::cerr << "Redis publish failed; message retained in SQLite" << std::endl;
            context.reset();
        }
    }
}

RedisSubscriber::RedisSubscriber(std::string host, int port, Callback callback)
    : host_(std::move(host)), port_(port), callback_(std::move(callback)), thread_(&RedisSubscriber::run, this) {}
RedisSubscriber::~RedisSubscriber() { stopping_ = true; thread_.join(); }
void RedisSubscriber::run() {
    while (!stopping_) {
        auto context = connect(host_, port_);
        if (context) {
            Reply subscribed(static_cast<redisReply *>(redisCommand(context.get(), "SUBSCRIBE %s", channel)), freeReplyObject);
            if (subscribed && subscribed->type == REDIS_REPLY_ARRAY && subscribed->elements == 3) {
                std::cerr << "Redis subscriber connected" << std::endl;
                while (!stopping_) {
                    void *raw = nullptr;
                    if (redisGetReplyFromReader(context.get(), &raw) != REDIS_OK) break;
                    if (raw) {
                        Reply reply(static_cast<redisReply *>(raw), freeReplyObject);
                        if (reply->type == REDIS_REPLY_ARRAY && reply->elements == 3 &&
                            reply->element[0]->type == REDIS_REPLY_STRING &&
                            std::string(reply->element[0]->str, reply->element[0]->len) == "message" &&
                            reply->element[2]->type == REDIS_REPLY_STRING && reply->element[2]->len <= 65536) {
                            callback_(std::string(reply->element[2]->str, reply->element[2]->len));
                        }
                        continue;
                    }
                    pollfd fd{context->fd, POLLIN, 0};
                    int result = poll(&fd, 1, 250);
                    if (result < 0 || (result > 0 && (fd.revents & (POLLERR | POLLHUP | POLLNVAL)))) break;
                    if (result > 0 && (fd.revents & POLLIN) && redisBufferRead(context.get()) != REDIS_OK) break;
                }
                if (!stopping_) std::cerr << "Redis subscriber disconnected; retrying" << std::endl;
            }
        }
        for (int i = 0; i < 5 && !stopping_; ++i) std::this_thread::sleep_for(std::chrono::milliseconds(200));
    }
}
