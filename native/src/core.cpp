// SPDX-License-Identifier: GPL-3.0-or-later
// Wire behavior ported from the Apache-2.0 Bada core at the revision recorded
// in native/UPSTREAM.json; see native/NOTICE for attribution.
#include "quickshare/core.h"
#include <openssl/bn.h>
#include <openssl/crypto.h>
#include <openssl/ec.h>
#include <openssl/evp.h>
#include <openssl/hmac.h>
#include <openssl/obj_mac.h>
#include <openssl/rand.h>
#include <algorithm>
#include <climits>
#include <cstdlib>
#include <iomanip>
#include <sstream>

namespace quickshare {
namespace {
void require(bool value, const char *message) { if (!value) throw Error(message); }
void wipe(Bytes &value) { if (!value.empty()) OPENSSL_cleanse(value.data(), value.size()); }
Bytes randomBytes(std::size_t size) {
    require(size <= INT_MAX, "Random request too large");
    Bytes value(size); require(RAND_bytes(value.data(), int(size)) == 1, "Random generation failed"); return value;
}
Bytes digest(const Bytes &value, const EVP_MD *algorithm) {
    Bytes out(EVP_MAX_MD_SIZE); unsigned size = 0;
    require(EVP_Digest(value.data(), value.size(), out.data(), &size, algorithm, nullptr) == 1, "Digest failed");
    out.resize(size); return out;
}
Bytes aes(const Bytes &value, const Bytes &key, const Bytes &iv, bool encrypt) {
    require(key.size() == 32 && iv.size() == 16, "Invalid AES key or IV size");
    require(value.size() < FrameLimit, "AES message too large");
    if (!encrypt) require(!value.empty() && value.size() % 16 == 0, "Invalid AES ciphertext size");
    std::unique_ptr<EVP_CIPHER_CTX, decltype(&EVP_CIPHER_CTX_free)> ctx(EVP_CIPHER_CTX_new(), EVP_CIPHER_CTX_free);
    require(bool(ctx), "AES context allocation failed");
    Bytes out(value.size() + 16); int first = 0, last = 0;
    require(EVP_CipherInit_ex(ctx.get(), EVP_aes_256_cbc(), nullptr, key.data(), iv.data(), encrypt ? 1 : 0) == 1, "AES initialization failed");
    if (EVP_CipherUpdate(ctx.get(), out.data(), &first, value.data(), int(value.size())) != 1 ||
        EVP_CipherFinal_ex(ctx.get(), out.data() + first, &last) != 1) {
        wipe(out); throw Error("AES operation failed");
    }
    out.resize(std::size_t(first + last)); return out;
}
using Ec = std::unique_ptr<EC_KEY, decltype(&EC_KEY_free)>;
using Bn = std::unique_ptr<BIGNUM, decltype(&BN_clear_free)>;
Bytes coordinate(const BIGNUM *number) {
    Bytes result(32); require(BN_bn2binpad(number, result.data(), 32) == 32, "Invalid P-256 coordinate");
    if (result[0] & 0x80) result.insert(result.begin(), 0); // Signed BigInteger peers.
    return result;
}
Bytes publicKey(const EC_KEY *key) {
    Bn x(BN_new(), BN_clear_free), y(BN_new(), BN_clear_free);
    require(bool(x) && bool(y), "Coordinate allocation failed");
    require(EC_POINT_get_affine_coordinates_GFp(EC_KEY_get0_group(key), EC_KEY_get0_public_key(key), x.get(), y.get(), nullptr) == 1, "Public key encoding failed");
    return wire::join(wire::integer(1, 1), wire::blob(2, wire::join(wire::blob(1, coordinate(x.get())), wire::blob(2, coordinate(y.get())))));
}
Bn parseCoordinate(Bytes data) {
    require(!data.empty() && data.size() <= 33, "Invalid coordinate length");
    if (data.size() == 33) { require(data[0] == 0, "Invalid coordinate sign byte"); data.erase(data.begin()); }
    Bn result(BN_bin2bn(data.data(), int(data.size()), nullptr), BN_clear_free);
    require(bool(result), "Coordinate decoding failed"); return result;
}
Ec parseKey(const Bytes &data) {
    auto generic = wire::parse(data);
    require(wire::one(generic, 1, 0).integer == 1, "Expected P-256 public key");
    auto pointData = wire::parse(wire::one(generic, 2, 2).data);
    auto x = parseCoordinate(wire::one(pointData, 1, 2).data), y = parseCoordinate(wire::one(pointData, 2, 2).data);
    Ec key(EC_KEY_new_by_curve_name(NID_X9_62_prime256v1), EC_KEY_free);
    require(bool(key), "P-256 allocation failed");
    auto group = EC_KEY_get0_group(key.get());
    Bn prime(BN_new(), BN_clear_free); require(bool(prime), "Field allocation failed");
    require(EC_GROUP_get_curve_GFp(group, prime.get(), nullptr, nullptr, nullptr) == 1, "Field lookup failed");
    require(BN_cmp(x.get(), prime.get()) < 0 && BN_cmp(y.get(), prime.get()) < 0, "Coordinate outside field");
    std::unique_ptr<EC_POINT, decltype(&EC_POINT_free)> point(EC_POINT_new(group), EC_POINT_free);
    require(bool(point), "Point allocation failed");
    require(EC_POINT_set_affine_coordinates_GFp(group, point.get(), x.get(), y.get(), nullptr) == 1 &&
            EC_POINT_is_at_infinity(group, point.get()) == 0 && EC_POINT_is_on_curve(group, point.get(), nullptr) == 1,
            "Invalid P-256 public point");
    require(EC_KEY_set_public_key(key.get(), point.get()) == 1 && EC_KEY_check_key(key.get()) == 1, "Public key validation failed");
    return key;
}
Secret sharedSecret(EC_KEY *key, const Bytes &encoded) {
    auto peer = parseKey(encoded); Bytes secret(32);
    require(ECDH_compute_key(secret.data(), secret.size(), EC_KEY_get0_public_key(peer.get()), key, nullptr) == 32, "ECDH failed");
    // Bada/NearDrop hash the unsigned X magnitude, not a fixed-width value.
    auto first = std::find_if(secret.begin(), secret.end() - 1, [](unsigned char c) { return c != 0; });
    Secret magnitude(Bytes(first, secret.end())); wipe(secret);
    return Secret(hash256(magnitude.get()));
}
Bytes wrap(unsigned type, const Bytes &data) { return wire::join(wire::integer(1, type), wire::blob(2, data)); }
Bytes unwrap(const Bytes &message, unsigned type) {
    require(message.size() <= 65536, "Handshake message too large");
    auto fields = wire::parse(message);
    require(wire::one(fields, 1, 0).integer == type, "Unexpected handshake message type");
    return wire::one(fields, 2, 2).data;
}
}

Bytes bytes(const std::string &value) { return Bytes(value.begin(), value.end()); }
Bytes unhex(const std::string &value) {
    require(value.size() % 2 == 0, "Invalid hexadecimal length"); Bytes out;
    auto digit = [](char c) -> int { if (c >= '0' && c <= '9') return c-'0'; if(c >= 'a' && c <= 'f') return c-'a'+10; if(c >= 'A' && c <= 'F') return c-'A'+10; return -1; };
    for (std::size_t i=0; i<value.size(); i+=2) { int a=digit(value[i]), b=digit(value[i+1]); require(a>=0 && b>=0, "Invalid hexadecimal digit"); out.push_back(unsigned(a*16+b)); }
    return out;
}
Bytes hash256(const Bytes &value) { return digest(value, EVP_sha256()); }
Bytes hmac256(const Bytes &key, const Bytes &value) {
    require(key.size() <= INT_MAX, "HMAC key too large"); Bytes out(32); unsigned length = 0;
    require(HMAC(EVP_sha256(), key.data(), int(key.size()), value.data(), value.size(), out.data(), &length) != nullptr && length == 32, "HMAC failed"); return out;
}
bool equal(const Bytes &a, const Bytes &b) { return a.size() == b.size() && (a.empty() || CRYPTO_memcmp(a.data(), b.data(), a.size()) == 0); }
Secret::Secret(Bytes value) : value_(std::move(value)) {}
Secret::~Secret() { wipe(value_); }
Secret::Secret(Secret &&other) noexcept : value_(std::move(other.value_)) {}
Secret &Secret::operator=(Secret &&other) noexcept { if(this != &other) { wipe(value_); value_ = std::move(other.value_); } return *this; }
Secret hkdf(const Bytes &input, const Bytes &salt, const Bytes &info, std::size_t length) {
    require(length > 0 && length <= 255 * 32, "Invalid HKDF output size");
    Secret prk(hmac256(salt.empty() ? Bytes(32, 0) : salt, input));
    Secret previous; Bytes result; result.reserve(length);
    for (unsigned block=1; result.size()<length; ++block) {
        Bytes data = wire::join(previous.get(), info); data.push_back(static_cast<unsigned char>(block));
        previous = Secret(hmac256(prk.get(), data)); wipe(data);
        const auto count = std::min(previous.get().size(), length-result.size());
        result.insert(result.end(), previous.get().begin(), previous.get().begin()+count);
    }
    return Secret(std::move(result));
}
namespace wire {
namespace {
void varint(Bytes &out, std::uint64_t value) { do { out.push_back((value & 127) | (value >= 128 ? 128 : 0)); value >>= 7; } while(value); }
std::uint64_t readVarint(const Bytes &data, std::size_t &pos) {
    std::uint64_t value = 0;
    for(unsigned i=0; i<10; ++i) {
        require(pos < data.size(), "Truncated protobuf varint"); unsigned byte=data[pos++];
        require(i != 9 || byte <= 1, "Protobuf varint overflow"); value |= std::uint64_t(byte & 127) << (7*i);
        if(!(byte & 128)) return value;
    }
    throw Error("Protobuf varint overflow");
}
}
Bytes integer(unsigned field, std::uint64_t value) { require(field && field<=0x1fffffff, "Invalid field number"); Bytes out; varint(out, std::uint64_t(field)<<3); varint(out,value); return out; }
Bytes blob(unsigned field, const Bytes &value) { require(field && field<=0x1fffffff && value.size()<FrameLimit, "Invalid blob"); Bytes out; varint(out,(std::uint64_t(field)<<3)|2); varint(out,value.size()); out.insert(out.end(),value.begin(),value.end()); return out; }
Bytes join(const Bytes &a, const Bytes &b) { require(a.size()+b.size()<FrameLimit, "Message too large"); Bytes out=a; out.insert(out.end(),b.begin(),b.end()); return out; }
Fields parse(const Bytes &value) {
    require(value.size()<FrameLimit, "Protobuf message too large"); Fields out; std::size_t pos=0;
    while(pos<value.size()) {
        require(out.size()<4096, "Too many protobuf fields"); auto tag=readVarint(value,pos);
        require((tag>>3)>0 && (tag>>3)<=0x1fffffff, "Invalid protobuf tag");
        Field field{unsigned(tag>>3),unsigned(tag&7),0,{}};
        if(field.type==0) field.integer=readVarint(value,pos);
        else {
            std::uint64_t count=0;
            if(field.type==2) count=readVarint(value,pos);
            else if(field.type==1) count=8;
            else if(field.type==5) count=4;
            else throw Error("Unsupported protobuf wire type");
            require(count<=value.size()-pos, "Truncated protobuf field");
            field.data.assign(value.begin()+pos,value.begin()+pos+std::size_t(count)); pos+=std::size_t(count);
        }
        out.push_back(std::move(field));
    }
    return out;
}
const Field &one(const Fields &fields, unsigned number, unsigned type) {
    const Field *result=nullptr;
    for(const auto &field:fields) if(field.number==number) { require(!result && field.type==type, "Duplicate or mistyped field"); result=&field; }
    require(result, "Missing protobuf field"); return *result;
}
bool has(const Fields &fields, unsigned number) { for(const auto &field:fields) if(field.number==number) return true; return false; }
}

Keys deriveKeys(const Bytes &dhs, const Bytes &clientInit, const Bytes &serverInit, Role role) {
    require(dhs.size()==32, "Invalid DH hash size"); auto transcript=wire::join(clientInit,serverInit);
    auto auth=hkdf(dhs,bytes("UKEY2 v1 auth"),transcript);
    auto next=hkdf(dhs,bytes("UKEY2 v1 next"),transcript);
    auto client=hkdf(next.get(),hash256(bytes("D2D")),bytes("client"));
    auto server=hkdf(next.get(),hash256(bytes("D2D")),bytes("server"));
    const auto &send=role==Role::Client ? client.get() : server.get();
    const auto &receive=role==Role::Client ? server.get() : client.get();
    auto salt=hash256(bytes("SecureMessage"));
    return Keys{std::move(auth), hkdf(send,salt,bytes("ENC:2")), hkdf(send,salt,bytes("SIG:1")),
                hkdf(receive,salt,bytes("ENC:2")), hkdf(receive,salt,bytes("SIG:1"))};
}
std::string pin(const Bytes &auth) {
    require(auth.size()==32, "Invalid auth string size"); int value=0,multiplier=1;
    for(auto byte:auth) { int signedByte=byte<128 ? int(byte) : int(byte)-256; value=(value+signedByte*multiplier)%9973; multiplier=(multiplier*31)%9973; }
    std::ostringstream result; result<<std::setw(4)<<std::setfill('0')<<std::abs(value); return result.str();
}
Session::Session(Keys keys) : keys_(std::move(keys)) {}
std::string Session::verificationPin() const { return pin(keys_.auth.get()); }
Bytes Session::seal(const Bytes &payload) {
    require(!failed_, "Session is closed"); require(payload.size()<FrameLimit-1024, "Payload too large");
    require(sent_<INT_MAX, "Send sequence exhausted");
    Secret plaintext(wire::join(wire::blob(1,payload),wire::integer(2,sent_+1)));
    auto iv=randomBytes(16), ciphertext=aes(plaintext.get(),keys_.sendEncryption.get(),iv,true);
    auto metadata=wire::join(wire::integer(1,13),wire::integer(2,1));
    auto header=wire::join(wire::join(wire::integer(1,1),wire::integer(2,2)),wire::join(wire::blob(5,iv),wire::blob(6,metadata)));
    auto body=wire::join(wire::blob(1,header),wire::blob(2,ciphertext));
    auto result=wire::join(wire::blob(1,body),wire::blob(2,hmac256(keys_.sendMac.get(),body)));
    ++sent_; return result;
}
Bytes Session::open(const Bytes &message) {
    require(!failed_, "Session is closed");
    try {
        auto outer=wire::parse(message);
        const auto &body=wire::one(outer,1,2).data, &signature=wire::one(outer,2,2).data;
        require(equal(hmac256(keys_.receiveMac.get(),body),signature), "Message authentication failed");
        auto parts=wire::parse(body), header=wire::parse(wire::one(parts,1,2).data);
        require(wire::one(header,1,0).integer==1 && wire::one(header,2,0).integer==2, "Unsupported secure message scheme");
        require(!wire::has(header,3) && !wire::has(header,4), "Unexpected key identifiers");
        if(wire::has(header,7)) require(wire::one(header,7,0).integer==0, "Associated data unsupported");
        auto metadata=wire::parse(wire::one(header,6,2).data);
        require(wire::one(metadata,1,0).integer==13 && wire::one(metadata,2,0).integer==1, "Invalid secure message metadata");
        Secret plain(aes(wire::one(parts,2,2).data,keys_.receiveEncryption.get(),wire::one(header,5,2).data,false));
        auto d2d=wire::parse(plain.get());
        require(received_<INT_MAX && wire::one(d2d,2,0).integer==received_+1, "Unexpected message sequence");
        Bytes result=wire::one(d2d,1,2).data; ++received_; return result;
    } catch(...) { failed_=true; throw; }
}

struct Handshake::Impl {
    Role role; unsigned stage=0; Ec key{nullptr,EC_KEY_free}; Bytes client,server,finished,commitment; Secret dhs;
    explicit Impl(Role value) : role(value) {}
    void generate() { key.reset(EC_KEY_new_by_curve_name(NID_X9_62_prime256v1)); require(bool(key) && EC_KEY_generate_key(key.get())==1, "P-256 generation failed"); }
};
Handshake::Handshake(Role role) : impl_(new Impl(role)) {}
Handshake::~Handshake() = default;
Bytes Handshake::start() {
    auto &s=*impl_; require(s.role==Role::Client && s.stage==0, "Invalid handshake start");
    s.stage=99; s.generate(); s.finished=wrap(4,wire::blob(1,publicKey(s.key.get())));
    auto commitment=wire::join(wire::integer(1,100),wire::blob(2,digest(s.finished,EVP_sha512())));
    auto init=wire::join(wire::join(wire::integer(1,1),wire::blob(2,randomBytes(32))),
                         wire::join(wire::blob(3,commitment),wire::blob(4,bytes("AES_256_CBC-HMAC_SHA256"))));
    s.client=wrap(2,init); s.stage=1; return s.client;
}
Bytes Handshake::consume(const Bytes &message) {
    auto &s=*impl_;
    try {
        require(message.size() <= 65536, "Handshake message too large");
        if(s.role==Role::Client) {
            require(s.stage==1, "Unexpected client handshake state");
            auto init=wire::parse(unwrap(message,3));
            require(wire::one(init,1,0).integer==1 && wire::one(init,2,2).data.size()==32 && wire::one(init,3,0).integer==100, "Invalid server initialization");
            s.dhs=sharedSecret(s.key.get(),wire::one(init,4,2).data); s.server=message; s.stage=2; return s.finished;
        }
        if(s.stage==0) {
            auto init=wire::parse(unwrap(message,2));
            require(wire::one(init,1,0).integer==1 && wire::one(init,2,2).data.size()==32, "Invalid client initialization");
            require(wire::one(init,4,2).data==bytes("AES_256_CBC-HMAC_SHA256"), "Unsupported next protocol");
            for(const auto &field:init) if(field.number==3) {
                require(field.type==2, "Invalid cipher commitment field"); auto cipher=wire::parse(field.data);
                if(wire::one(cipher,1,0).integer==100) {
                    require(s.commitment.empty(), "Duplicate cipher commitment"); s.commitment=wire::one(cipher,2,2).data;
                }
            }
            require(s.commitment.size()==64, "Missing or invalid P256_SHA512 commitment");
            s.generate(); s.client=message;
            auto initOut=wire::join(wire::join(wire::integer(1,1),wire::blob(2,randomBytes(32))),
                                   wire::join(wire::integer(3,100),wire::blob(4,publicKey(s.key.get()))));
            s.server=wrap(3,initOut); s.stage=1; return s.server;
        }
        require(s.stage==1, "Unexpected server handshake state");
        require(equal(s.commitment,digest(message,EVP_sha512())), "Client commitment mismatch");
        auto finish=wire::parse(unwrap(message,4));
        s.dhs=sharedSecret(s.key.get(),wire::one(finish,1,2).data); s.stage=2; return {};
    } catch(...) { s.stage=99; s.key.reset(); s.dhs=Secret(); throw; }
}
bool Handshake::complete() const { return impl_->stage==2; }
std::unique_ptr<Session> Handshake::takeSession() {
    auto &s=*impl_; require(s.stage==2, "Handshake not complete or already consumed");
    auto keys=deriveKeys(s.dhs.get(),s.client,s.server,s.role);
    s.dhs=Secret(); s.key.reset(); s.stage=3;
    return std::unique_ptr<Session>(new Session(std::move(keys)));
}
Bytes readFrame(std::istream &input) {
    unsigned char header[4]; input.read(reinterpret_cast<char*>(header),4); require(input.gcount()==4, "Truncated frame header");
    std::uint32_t length=0; for(auto byte:header) length=(length<<8)|byte;
    require(length>0 && length<FrameLimit, "Invalid frame length"); Bytes out(length);
    input.read(reinterpret_cast<char*>(out.data()),length); require(std::size_t(input.gcount())==length, "Truncated frame body"); return out;
}
void writeFrame(std::ostream &output, const Bytes &value) {
    require(!value.empty() && value.size()<FrameLimit, "Invalid frame length"); auto size=std::uint32_t(value.size());
    unsigned char header[4]={static_cast<unsigned char>(size>>24),static_cast<unsigned char>(size>>16),static_cast<unsigned char>(size>>8),static_cast<unsigned char>(size)};
    output.write(reinterpret_cast<char*>(header),4); output.write(reinterpret_cast<const char*>(value.data()),value.size()); output.flush(); require(bool(output), "Frame write failed");
}
}
