#pragma once
#include <App.h>
#include <atomic>
#include <csignal>
#include <pthread.h>
#include <stdexcept>
#include <thread>

// Block signals before creating worker threads; only the watcher consumes them.
inline sigset_t block_shutdown_signals() {
    sigset_t signals;
    sigemptyset(&signals);
    sigaddset(&signals, SIGINT);
    sigaddset(&signals, SIGTERM);
    if (pthread_sigmask(SIG_BLOCK, &signals, nullptr) != 0)
        throw std::runtime_error("cannot block shutdown signals");
    return signals;
}

class SignalWatcher {
public:
    SignalWatcher(sigset_t signals, uWS::Loop *loop, uWS::App &app)
        : thread_([this, signals, loop, &app] {
            while (!stop_) {
                timespec timeout{0, 100000000};
                int signal = sigtimedwait(&signals, nullptr, &timeout);
                if (signal == SIGINT || signal == SIGTERM) {
                    loop->defer([&app] { app.close(); });
                    break;
                }
            }
        }) {}
    ~SignalWatcher() { stop_ = true; thread_.join(); }
private:
    std::atomic<bool> stop_{false};
    std::thread thread_;
};
