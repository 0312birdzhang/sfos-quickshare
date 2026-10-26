// SPDX-License-Identifier: GPL-3.0-or-later
#include "quickshare/core.h"
#include <functional>
#include <iostream>
#include <random>
#include <sstream>
using namespace quickshare;
namespace {
unsigned checks=0;
void check(bool condition, const char *name) { if(!condition) throw Error(name); ++checks; }
void rejects(const std::function<void()> &fn, const char *name) {
    try { fn(); } catch(const Error &) { ++checks; return; }
    throw Error(name);
}
std::pair<std::unique_ptr<Session>,std::unique_ptr<Session>> sessions() {
    Handshake client(Role::Client),server(Role::Server);
    auto response=server.consume(client.start());
    auto init=wire::parse(wire::one(wire::parse(response),2,2).data);
    auto generic=wire::parse(wire::one(init,4,2).data);
    auto point=wire::parse(wire::one(generic,2,2).data);
    for(unsigned field:{1u,2u}) {
        auto coordinate=wire::one(point,field,2).data;
        check((coordinate.size()==32 && coordinate[0]<128) ||
              (coordinate.size()==33 && coordinate[0]==0 && coordinate[1]>=128),"Non-positive public key encoding");
    }
    auto finished=client.consume(response); server.consume(finished);
    check(client.complete() && server.complete(),"Handshake incomplete");
    auto a=client.takeSession(),b=server.takeSession();
    check(a->verificationPin()==b->verificationPin(),"PIN mismatch");
    rejects([&]{ client.takeSession(); },"Reused handshake accepted");
    return {std::move(a),std::move(b)};
}
}
int main() {
    try {
        auto key=hkdf(Bytes(22,0x0b),unhex("000102030405060708090a0b0c"),unhex("f0f1f2f3f4f5f6f7f8f9"),42);
        check(key.get()==unhex("3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"),"RFC5869 mismatch");
        rejects([]{ hkdf({}, {}, {}, 8161); },"Oversized HKDF accepted");
        rejects([]{ wire::parse(unhex("00")); },"Zero protobuf tag accepted");
        rejects([]{ wire::parse(unhex("1280")); },"Truncated varint accepted");
        rejects([]{ wire::parse(unhex("12ffffffffffffffffff01")); },"Oversized length accepted");
        rejects([]{ wire::parse(unhex("08ffffffffffffffffff02")); },"Overflow varint accepted");
        rejects([]{ wire::one(wire::parse(unhex("08010802")),1,0); },"Duplicate field accepted");
        rejects([]{ wire::parse(unhex("0b")); },"Unsupported protobuf group accepted");
        std::mt19937 generator(0x71756963);
        for(unsigned i=0;i<10000;++i) {
            Bytes input(generator()%256);
            for(auto &byte:input) byte=static_cast<unsigned char>(generator());
            try { wire::parse(input); } catch(const Error &) {}
        }
        check(true,"Bounded decoder corpus");
        std::ostringstream output; writeFrame(output,bytes("test")); std::istringstream input(output.str());
        check(readFrame(input)==bytes("test"),"Frame round trip failed");
        for(const auto &frame:{std::string("\0\0\0\0",4),std::string("\0\x50\0\0",4),std::string("\0\0\0\x03x",5),std::string("\0",1)}) {
            rejects([&]{ std::istringstream stream(frame); readFrame(stream); },"Invalid frame accepted");
        }
        {
            Handshake client(Role::Client),server(Role::Server);
            auto response=server.consume(client.start()); auto finish=client.consume(response); finish.back()^=1;
            rejects([&]{ server.consume(finish); },"Bad commitment accepted");
            check(!server.complete(),"Failed handshake completed");
            rejects([&]{ server.takeSession(); },"Failed handshake made keys");
        }
        {
            Handshake client(Role::Client); client.start();
            auto point=wire::join(wire::blob(1,Bytes(32,0)),wire::blob(2,Bytes(32,0)));
            auto publicKey=wire::join(wire::integer(1,1),wire::blob(2,point));
            auto data=wire::join(wire::join(wire::integer(1,1),wire::blob(2,Bytes(32,1))),wire::join(wire::integer(3,100),wire::blob(4,publicKey)));
            auto response=wire::join(wire::integer(1,3),wire::blob(2,data));
            rejects([&]{ client.consume(response); },"Invalid curve point accepted");
        }
        for(unsigned round=0;round<32;++round) {
            auto pair=sessions(); Bytes payload={0,1,2,255,128,0,42};
            check(pair.second->open(pair.first->seal(payload))==payload,"Client encryption failed");
            check(pair.first->open(pair.second->seal(bytes("response")))==bytes("response"),"Server encryption failed");
            check(pair.second->open(pair.first->seal({})).empty(),"Empty payload failed");
        }
        {
            auto pair=sessions(); auto message=pair.first->seal(bytes("test")); message.back()^=1;
            rejects([&]{ pair.second->open(message); },"Invalid HMAC accepted");
            rejects([&]{ pair.second->open(pair.first->seal(bytes("retry"))); },"Poisoned session reused");
        }
        {
            auto pair=sessions(); auto message=pair.first->seal(bytes("test")); pair.second->open(message);
            rejects([&]{ pair.second->open(message); },"Replay accepted");
        }
        {
            auto pair=sessions(); pair.first->seal(bytes("one")); auto second=pair.first->seal(bytes("two"));
            rejects([&]{ pair.second->open(second); },"Out-of-order sequence accepted");
        }
        // Forge authenticated but unsupported headers with known test keys.
        // These must fail even though their HMAC is valid.
        for(unsigned variant=0;variant<4;++variant) {
            auto sendKeys=deriveKeys(Bytes(32,1),bytes("client-init"),bytes("server-init"),Role::Client);
            Session sender(deriveKeys(Bytes(32,1),bytes("client-init"),bytes("server-init"),Role::Client));
            Session receiver(deriveKeys(Bytes(32,1),bytes("client-init"),bytes("server-init"),Role::Server));
            auto original=wire::parse(sender.seal(bytes("test")));
            auto parts=wire::parse(wire::one(original,1,2).data);
            auto meta=wire::join(wire::integer(1,13),wire::integer(2,variant==0 ? 2 : 1));
            auto header=wire::join(wire::join(wire::integer(1,1),wire::integer(2,2)),
                wire::join(wire::blob(5,Bytes(variant==1 ? 1 : 16,0)),wire::blob(6,meta)));
            if(variant==2) header=wire::join(header,wire::integer(7,1));
            auto ciphertext=variant==3 ? Bytes(1,0) : wire::one(parts,2,2).data;
            auto body=wire::join(wire::blob(1,header),wire::blob(2,ciphertext));
            auto forged=wire::join(wire::blob(1,body),wire::blob(2,hmac256(sendKeys.sendMac.get(),body)));
            rejects([&]{ receiver.open(forged); },"Authenticated invalid header accepted");
        }
        check(pin(Bytes(32,0))=="0000","Zero PIN mismatch");
        std::cout << checks << " native protocol checks PASS\n"; return 0;
    } catch(const std::exception &error) { std::cerr << "FAIL: " << error.what() << '\n'; return 1; }
}
