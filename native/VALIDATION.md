# Native protocol validation — 2026-10-26

| Check | Result |
| --- | --- |
| Linux x86-64, OpenSSL 3.0.2, C++11 | Build passed |
| Native core tests | 298 checks passed |
| Bounded protobuf decoder corpus | 10,000 deterministic malformed/random inputs completed |
| AddressSanitizer + UndefinedBehaviorSanitizer | Tests passed |
| Native client vs existing JVM server, host | 8 independent handshakes passed |
| Native server vs existing JVM client, host | 8 independent handshakes passed |
| Native ARM64 client vs JVM server | 4 independent handshakes passed |
| Native ARM64 server vs JVM client | 4 independent handshakes passed |
| Matching PIN and bidirectional encrypted payload | Passed in every cross-implementation exchange |
| ARM64 RPM, Sailfish OS 5.3.0.10 | Installed and capabilities checked |
| C++ production backend after upgrade | Ready; old JRE/JAR removed |

## Native file-transfer validation

The ARM64 worker links system OpenSSL and C/C++ libraries without Qt or JVM.
Native sender -> JVM ARM64 receiver and JVM sender -> native ARM64 receiver both
passed matching PINs, 3 MiB multichunk files, Unicode/emoji names, empty files,
duplicate names, SHA256 comparisons and rejection.

Native TCP tests passed private permissions, interruption, cancellation and
symlink rejection. Incomplete batches leave no published or staged files.
Safety tests cover bounded JSON/UTF8, metadata limits, traversal, conflicting
chunks, incomplete streams and atomic publication. ASan/UBSan tests passed.

Application 0.2.0 and runtime 2.0.0 were installed together on Sailfish OS
5.3.0.10 ARM64. Package payloads contain no JAR/JRE and no world-writable files;
the upgrade removed the old private Java files. System Transfer Engine dispatch,
native send/receive, consent and saved-file SHA256 passed on that device.
After history expiry, the send job/upload record was absent while the saved file,
its SHA256 and the finished download record remained. The streaming SSH test
connection timed out while the phone suspended; these final conditions were
independently verified after reconnecting. Test listeners/discovery were stopped.

The JVM peers used the pinned implementation, not official Google applications.
The user subsequently confirmed official Windows/native transfers and the 0.2.1
receive-error fix. Android testing remains outstanding. The JVM reference tools
were removed in 0.2.2; this records historical cross-implementation evidence. No independent security audit or
visible UI acceptance is claimed.

## JVM removal release 0.2.2

Built only application 0.2.2 and Python runtime 2.0.0 after deleting Java/Kotlin
sources, Gradle, JRE downloads, optional JVM packaging and reference adapters.
C++ protocol/safety tests, native TCP tests and all 37 Linux Python tests passed.
Application 0.2.2 installed on the phone; Transfer Engine send/receive, file SHA256
and post-transfer probe EOF regression passed. No JVM/JAR payload remains.
