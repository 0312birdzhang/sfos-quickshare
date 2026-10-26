# Native protocol LAN worker

This is a transport-independent C++11/OpenSSL implementation of the Quick Share
UKEY2 P256_SHA512 handshake and authenticated encrypted channel. It does not link
Qt, protobuf, Kotlin or Java. Wire definitions and interoperability behavior are
ported from the pinned core referenced by `native/UPSTREAM.json`; see NOTICE.
See [dated host and device validation](VALIDATION.md) for completed checks and limits.

Implemented:

- Bounded big-endian stream framing and a bounded protobuf wire decoder.
- Ephemeral P-256 ECDH, public-point validation, SHA-512 commitment verification,
  transcript-bound HKDF-SHA256 and directional traffic keys.
- Signed-coordinate interoperability and the unsigned shared-X magnitude rule.
- Four-digit verification PIN, AES-256-CBC/PKCS7, HMAC-SHA256 verified before
  decryption, authenticated metadata and strictly ordered sequence numbers.
- Move-only key owners that wipe their bytes; failed receive sessions are closed
  to further use. Public transport messages may be inspected; secret keys are not logged.

## Default backend

The C++ worker implements connection/paired-key exchange, metadata, PIN consent,
encrypted streaming, keepalive, rejection and cancellation. Python retains mDNS,
D-Bus and Transfer Engine integration. `sfos-quickshare-native --capabilities`
reports file-transfer support; the separate probe is a synthetic crypto tool.

Receivers validate names, IDs, sizes and chunk coverage. Files are staged with
private permissions (0700 directories, 0600 files), then atomically published
without overwriting existing destinations. Failed/interrupted batches are removed.
Symlink destinations and conflicting chunks are rejected. Limits: 64 files,
8 GiB per batch and three receiver sessions. LAN only; no AirDrop/Wi-Fi Direct.

Runtime 2.0.0 contains Python dependencies only. The JVM backend was removed in
0.2.2; native is the only supported protocol implementation.

## Host tests

Requires CMake, C++11 compiler and OpenSSL >= 1.1.1 development headers:

```sh
cmake -S native -B native/build -DCMAKE_BUILD_TYPE=Debug
cmake --build native/build -j2
ctest --test-dir native/build --output-on-failure
python3 native/tests/transfer_tests.py --binary native/build/sfos-quickshare-native
```

Earlier cross-implementation tests used an independent JVM reference before its
removal; see VALIDATION.md. Current tests need no Java tools. The native core and
LAN worker are built into the application RPM; changes do not require a runtime
package update. The retained .proto files are format documentation, not generated
code or a protobuf runtime dependency.
