// SPDX-License-Identifier: GPL-3.0-or-later
#include "quickshare/core.h"
#include <iostream>

int main(int argc, char **argv) {
    using namespace quickshare;
    try {
        if(argc==2 && std::string(argv[1])=="--capabilities") {
            std::cout << "{\"backend\":\"cpp\",\"stage\":\"secure-channel\",\"fileTransfer\":false,\"networkListener\":false}\n";
            return 0;
        }
        if(argc!=3 || std::string(argv[1])!="--interop" ||
           (std::string(argv[2])!="client" && std::string(argv[2])!="server")) {
            std::cerr << "Usage: sfos-quickshare-native-probe --capabilities | --interop client|server\n";
            return 2;
        }
        const bool client=std::string(argv[2])=="client";
        Handshake handshake(client ? Role::Client : Role::Server);
        if(client) {
            writeFrame(std::cout,handshake.start());
            writeFrame(std::cout,handshake.consume(readFrame(std::cin)));
        } else {
            writeFrame(std::cout,handshake.consume(readFrame(std::cin)));
            handshake.consume(readFrame(std::cin));
        }
        auto session=handshake.takeSession();
        const Bytes mine=bytes(client ? "client-message" : "server-message");
        const Bytes expected=bytes(client ? "server-message" : "client-message");
        if(client) {
            writeFrame(std::cout,session->seal(mine));
            if(session->open(readFrame(std::cin))!=expected) throw Error("Unexpected probe payload");
        } else {
            if(session->open(readFrame(std::cin))!=expected) throw Error("Unexpected probe payload");
            writeFrame(std::cout,session->seal(mine));
        }
        // This PIN belongs only to this synthetic test exchange. No key material
        // is printed. stdout is exclusively the framed protocol transport.
        std::cerr << "INTEROP_PASS pin=" << session->verificationPin() << '\n';
        return 0;
    } catch(const std::exception &error) {
        std::cerr << "Native protocol probe failed: " << error.what() << '\n'; return 1;
    }
}
