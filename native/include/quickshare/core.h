// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once
#include <cstdint>
#include <istream>
#include <memory>
#include <ostream>
#include <stdexcept>
#include <string>
#include <vector>

namespace quickshare {
using Bytes = std::vector<unsigned char>;
constexpr std::size_t FrameLimit = 5 * 1024 * 1024;
struct Error : std::runtime_error { using std::runtime_error::runtime_error; };
Bytes bytes(const std::string &value);
Bytes unhex(const std::string &value);
Bytes hash256(const Bytes &value);
Bytes hmac256(const Bytes &key, const Bytes &value);
bool equal(const Bytes &a, const Bytes &b);

// Key owners are move-only and wipe their allocated contents before release.
class Secret {
    Bytes value_;
public:
    explicit Secret(Bytes value = {});
    ~Secret();
    Secret(Secret &&other) noexcept;
    Secret &operator=(Secret &&other) noexcept;
    Secret(const Secret &) = delete;
    Secret &operator=(const Secret &) = delete;
    const Bytes &get() const { return value_; }
};
Secret hkdf(const Bytes &input, const Bytes &salt, const Bytes &info, std::size_t length = 32);

// Bounded protobuf wire subset used by the pinned Google/Bada schemas. No
// protobuf runtime is required. Unknown fixed-width fields can be skipped.
namespace wire {
struct Field { unsigned number; unsigned type; std::uint64_t integer; Bytes data; };
using Fields = std::vector<Field>;
Bytes integer(unsigned field, std::uint64_t value);
Bytes blob(unsigned field, const Bytes &value);
Bytes join(const Bytes &a, const Bytes &b);
Fields parse(const Bytes &value);
const Field &one(const Fields &fields, unsigned number, unsigned type);
bool has(const Fields &fields, unsigned number);
}

enum class Role { Client, Server };
struct Keys {
    Secret auth, sendEncryption, sendMac, receiveEncryption, receiveMac;
};
Keys deriveKeys(const Bytes &dhs, const Bytes &clientInit, const Bytes &serverInit, Role role);
std::string pin(const Bytes &auth);

// Single-owner connection state; callers serialize access to each instance.
// One ordered, authenticated channel. A receive error poisons the channel;
// callers must close the transport rather than retrying the damaged session.
class Session {
    Keys keys_;
    std::uint32_t sent_ = 0, received_ = 0;
    bool failed_ = false;
public:
    explicit Session(Keys keys);
    std::string verificationPin() const;
    Bytes seal(const Bytes &payload);
    Bytes open(const Bytes &message);
};

// Transport-independent UKEY2 P256_SHA512 state machine. Wire messages are
// returned to the caller; no listener or file acceptance is enabled here.
class Handshake {
    struct Impl;
    std::unique_ptr<Impl> impl_;
public:
    explicit Handshake(Role role);
    ~Handshake();
    Handshake(const Handshake &) = delete;
    Handshake &operator=(const Handshake &) = delete;
    Bytes start(); // Client only.
    Bytes consume(const Bytes &message);
    bool complete() const;
    std::unique_ptr<Session> takeSession();
};
Bytes readFrame(std::istream &input);
void writeFrame(std::ostream &output, const Bytes &value);
}
