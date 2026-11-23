#pragma once
#include "MessageRepository.h"
#include <condition_variable>
#include <deque>
#include <functional>
#include <future>
#include <memory>
#include <mutex>
#include <sqlite3.h>
#include <thread>

class StorageWorker {
public:
    using Job = std::function<void(MessageRepository &)>;
    explicit StorageWorker(const std::string &path) {
        std::promise<void> ready;
        auto started = ready.get_future();
        thread_ = std::thread([this, path, ready = std::move(ready)]() mutable {
            try {
                std::unique_ptr<MessageRepository> repository;
                for (int attempt = 0; !repository; ++attempt) {
                    try { repository = std::make_unique<MessageRepository>(path); }
                    catch (const SQLite::Exception &e) {
                        int code = e.getErrorCode() & 0xff;
                        if ((code != SQLITE_BUSY && code != SQLITE_LOCKED) || attempt >= 29) throw;
                        std::this_thread::sleep_for(std::chrono::milliseconds(100));
                    }
                }
                ready.set_value();
                for (;;) {
                    Job job;
                    {
                        std::unique_lock<std::mutex> lock(mutex_);
                        condition_.wait(lock, [this] { return stopping_ || !jobs_.empty(); });
                        if (jobs_.empty() && stopping_) break;
                        job = std::move(jobs_.front());
                        jobs_.pop_front();
                    }
                    job(*repository);
                }
            } catch (...) {
                try { ready.set_exception(std::current_exception()); } catch (...) { std::terminate(); }
            }
        });
        try { started.get(); }
        catch (...) { thread_.join(); throw; }
    }
    ~StorageWorker() {
        {
            std::lock_guard<std::mutex> lock(mutex_);
            stopping_ = true;
        }
        condition_.notify_one();
        if (thread_.joinable()) thread_.join();
    }
    bool submit(Job job) {
        std::lock_guard<std::mutex> lock(mutex_);
        if (stopping_ || jobs_.size() >= 256) return false;
        jobs_.push_back(std::move(job));
        condition_.notify_one();
        return true;
    }
private:
    std::mutex mutex_;
    std::condition_variable condition_;
    std::deque<Job> jobs_;
    bool stopping_ = false;
    std::thread thread_;
};
