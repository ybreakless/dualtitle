#pragma once
/**
 * DualTitleDictService.hpp -- Background dictionary lookup service.
 *
 * A dedicated worker thread services word-lookup requests so the overlay UI
 * thread never blocks on dictionary work (the old code called
 * FamousDictionary::Lookup synchronously inside WM_LBUTTONDOWN).
 *
 * Threading model (no PostMessage, no cross-thread GUI calls):
 *   - Overlay thread:  DictSvc::Query(word, id)  -> enqueue
 *                      WM_TIMER 30 ms            -> DictSvc::Pump(result)
 *   - Worker thread:   pop word -> FamousDictionary::Lookup -> push result
 *   - Shared state guarded by one mutex; lookup runs outside the lock.
 *
 * "found" semantics: a word is "known" iff it resolved to a real dictionary
 * entry (lexical hit). The generic vocabulary-term fallback is reported as
 * not found so the card can show an honest empty state.
 */

#include <algorithm>
#include <atomic>
#include <cctype>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <set>
#include <string>
#include <thread>

#include "DualTitleEngine.hpp"

namespace DualTitle {
namespace DictSvc {

struct DictResult {
    int req = 0;               // request id the overlay is waiting for
    std::string word;
    DictionaryEntry entry;
    bool found = false;
};

namespace detail {

struct QueuedWord {
    std::string word;
    int req = 0;
};

inline std::mutex s_mx;
inline std::condition_variable s_cv;
inline std::deque<QueuedWord> s_queue;           // pending words with their request ids
inline std::deque<DictResult> s_done;            // completed results, FIFO
inline std::set<std::string> s_queued;           // dedup: words already queued
inline std::string s_processing;                 // word currently being looked up
inline std::atomic<bool> s_quit{false};
inline std::atomic<bool> s_started{false};
inline std::thread s_worker;
inline std::atomic<int> s_next_req{1};
inline std::atomic<int> s_active_req{0};         // request id of the visible card
inline std::atomic<bool> s_card_visible{false};

inline bool IsLexicalHit(const DictionaryEntry& e) {
    return e.source != "DualTitle Lexicon";
}

inline void WorkerLoop() {
    for (;;) {
        std::string word;
        int req = 0;
        {
            std::unique_lock<std::mutex> lk(s_mx);
            s_cv.wait(lk, [] { return s_quit.load() || !s_queue.empty(); });
            if (s_quit.load() && s_queue.empty()) return;
            word = s_queue.front().word;
            req = s_queue.front().req;
            s_queue.pop_front();
            s_queued.erase(word);
            s_processing = word;
        }
        // Heavy work outside the lock.
        DictionaryEntry e = FamousDictionary::Lookup(word);
        DictResult r;
        r.req = req;
        r.word = word;
        r.entry = e;
        r.found = IsLexicalHit(e);
        {
            std::lock_guard<std::mutex> lk(s_mx);
            s_done.push_back(std::move(r));
        }
        {
            std::lock_guard<std::mutex> lk(s_mx);
            s_processing.clear();
        }
        s_cv.notify_all();
    }
}

}  // namespace detail

// Start the single worker thread (idempotent). Must be Stop()'d before exit.
inline void Start() {
    if (detail::s_started.exchange(true)) return;
    detail::s_quit.store(false);
    detail::s_worker = std::thread(detail::WorkerLoop);
}

// Drain + join. Safe to call even when never started; joint only once.
inline void Stop() {
    if (!detail::s_started.exchange(false)) return;
    detail::s_quit.store(true);
    detail::s_cv.notify_all();
    if (detail::s_worker.joinable()) detail::s_worker.join();
    std::lock_guard<std::mutex> lk(detail::s_mx);
    detail::s_queue.clear();
    detail::s_done.clear();
    detail::s_queued.clear();
}

// Enqueue a lookup for a specific pending request id. Deduplicates: if the
// same word is queued or in-flight the second request is ignored (the first
// result satisfies the card; word content is identical either way).
inline void Query(const std::string& word, int req_id) {
    std::string w;
    for (char c : word) {
        if (std::isalnum(static_cast<unsigned char>(c)) || static_cast<unsigned char>(c) >= 128) {
            w.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
        }
    }
    if (w.empty()) return;
    std::lock_guard<std::mutex> lk(detail::s_mx);
    if (detail::s_queued.count(w) || detail::s_processing == w) return;
    detail::s_queue.push_back(detail::QueuedWord{w, req_id});
    detail::s_queued.insert(w);
    detail::s_cv.notify_one();
}

// Signature of a request the overlay currently waits for (0 = none).
inline void SetActiveRequest(int id) { detail::s_active_req.store(id); }
inline int  ActiveRequest() { return detail::s_active_req.load(); }

// Card visibility flag (the overlay draws/removes the definition popup).
inline void SetCardVisible(bool v) { detail::s_card_visible.store(v); }
inline bool CardVisible() { return detail::s_card_visible.load(); }

// Opens a new request and returns its id. Call Query(word, id) right after.
inline int BeginRequest() {
    int id = detail::s_next_req.fetch_add(1);
    SetActiveRequest(id);
    SetCardVisible(true);
    return id;
}

// UI thread: pop at most one completed result. Returns false when none ready.
inline bool Pump(DictResult& out) {
    std::lock_guard<std::mutex> lk(detail::s_mx);
    if (detail::s_done.empty()) return false;
    out = std::move(detail::s_done.front());
    detail::s_done.pop_front();
    return true;
}

inline size_t PendingCount() {
    std::lock_guard<std::mutex> lk(detail::s_mx);
    return detail::s_queue.size() + (detail::s_processing.empty() ? 0 : 1);
}

}  // namespace DictSvc
}  // namespace DualTitle
