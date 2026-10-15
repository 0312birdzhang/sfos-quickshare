// SPDX-License-Identifier: GPL-3.0-or-later
package org.sailfishos.quickshare

import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.location.nearby.connections.proto.OfflineWireFormatsProto.PayloadTransferFrame.PayloadHeader
import dev.bluehouse.bada.protocol.connection.*
import dev.bluehouse.bada.protocol.endpoint.DeviceType
import dev.bluehouse.bada.protocol.endpoint.EndpointInfo
import dev.bluehouse.bada.protocol.payload.FileDestinationFactory
import kotlinx.coroutines.*
import java.net.InetAddress
import java.net.ServerSocket
import java.nio.channels.SeekableByteChannel
import java.nio.file.*
import java.nio.file.attribute.PosixFilePermissions
import java.security.SecureRandom
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Semaphore

private val gson = Gson()
private val random = SecureRandom()
@Synchronized private fun event(vararg fields: Pair<String, Any?>) {
    println(gson.toJson(mapOf(*fields)))
    System.out.flush()
}

private fun endpoint(name: String): ByteArray = EndpointInfo(
    1, false, DeviceType.TABLET, false,
    ByteArray(16).also(random::nextBytes), name.take(60),
).serialize()

/** All files stay private until the entire announced transfer completes. */
internal class Destination(private val root: Path) : FileDestinationFactory {
    private val staging = Files.createTempDirectory(root, ".pending-")
    private val allowed = mutableMapOf<Long, TransferItem.File>()
    private val opened = mutableMapOf<Long, Pair<Path, SeekableByteChannel>>()
    private val completed = mutableSetOf<Long>()
    @Volatile private var accepted = false
    @Volatile private var metadataReady = false
    init {
        if (staging.fileSystem.supportedFileAttributeViews().contains("posix")) {
            Files.setPosixFilePermissions(staging, PosixFilePermissions.fromString("rwx------"))
        }
    }
    fun authorize(metadata: TransferMetadata) {
        require(metadata.items.isNotEmpty() && metadata.items.size <= 64) { "Expected 1..64 files" }
        require(metadata.items.all { it is TransferItem.File }) { "Only file transfers are supported" }
        var total = 0L
        metadata.items.forEach {
            val file = it as TransferItem.File
            require(file.size in 0..MAX_BYTES && file.payloadId != 0L) { "Invalid file size or payload ID" }
            total = Math.addExact(total, file.size)
            require(total <= MAX_BYTES) { "Transfer exceeds 8 GiB" }
            safeLeaf(file.name)
            require(file.parentFolder.isEmpty()) { "Folder transfer is not supported yet" }
            require(allowed.put(file.payloadId, file) == null) { "Duplicate payload ID" }
        }
        require(Files.getFileStore(root).usableSpace >= total + 16 * 1024 * 1024) { "Not enough free space" }
        metadataReady = true
    }
    fun consent(value: Boolean) {
        require(metadataReady) { "Transfer metadata is not ready" }
        accepted = value
    }
    override fun open(header: PayloadHeader): SeekableByteChannel {
        require(accepted) { "User consent is required" }
        val file = requireNotNull(allowed[header.id]) { "Unannounced payload" }
        require(header.type == PayloadHeader.PayloadType.FILE && header.totalSize == file.size) { "Payload does not match consent" }
        require(header.parentFolder.isEmpty()) { "Unexpected folder" }
        require(header.fileName.isEmpty() || header.fileName == file.name) { "Filename changed after consent" }
        require(!opened.containsKey(header.id)) { "Payload already opened" }
        val leaf = safeLeaf(file.name)
        val target = staging.resolve(if (Files.exists(staging.resolve(leaf))) "${header.id}-$leaf" else leaf)
        val channel = Files.newByteChannel(target, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE, StandardOpenOption.READ)
        opened[header.id] = target to channel
        return channel
    }
    override fun commit(payloadId: Long): Boolean {
        val entry = opened[payloadId] ?: return false
        require(Files.size(entry.first) == allowed.getValue(payloadId).size) { "Incomplete payload" }
        completed.add(payloadId)
        return true
    }
    override fun abort(payloadId: Long): Boolean {
        val entry = opened.remove(payloadId) ?: return false
        entry.second.close()
        Files.deleteIfExists(entry.first)
        completed.remove(payloadId)
        return true
    }
    override fun abortAll(): Int {
        // Bada calls this even after successful run(): committed payloads must survive
        // until our batch-level publish, while uncommitted payloads are removed.
        val pending = opened.keys.filter { it !in completed }
        val count = pending.size
        pending.forEach(::abort)
        if (completed.isEmpty()) Files.deleteIfExists(staging)
        return count
    }
    fun discard() {
        opened.keys.toList().forEach(::abort)
        Files.deleteIfExists(staging)
    }
    fun publish(): Path {
        require(accepted && completed == allowed.keys) { "Not all files completed" }
        opened.values.forEach { it.second.close() }
        val target = root.resolve("transfer-${UUID.randomUUID()}")
        Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE)
        return target
    }
    companion object {
        const val MAX_BYTES = 8L * 1024 * 1024 * 1024
        fun safeLeaf(name: String): String {
            require(name.isNotEmpty() && name != "." && name != ".." && name.toByteArray(Charsets.UTF_8).size <= 180) { "Invalid filename" }
            require(name.none { it == '/' || it == '\\' || it.code < 32 || it.code == 127 }) { "Unsafe filename" }
            return name
        }
    }
}

private suspend fun send(config: JsonObject): Unit = coroutineScope {
    val files = config.getAsJsonArray("files").map { element ->
        val path = Paths.get(element.asString).toRealPath()
        require(Files.isRegularFile(path)) { "Source is not a regular file" }
        val size = Files.size(path)
        require(size <= Destination.MAX_BYTES) { "File exceeds 8 GiB" }
        FileSource(path.fileName.toString(), size, Files.probeContentType(path) ?: "application/octet-stream",
            Files.getLastModifiedTime(path).toMillis(), random.nextLong().ushr(1).coerceAtLeast(1)) {
            Files.newByteChannel(path, StandardOpenOption.READ)
        }
    }
    require(files.size in 1..64)
    require(files.sumOf { it.size } <= Destination.MAX_BYTES)
    val connection = OutboundConnection(InetAddress.getByName(config.get("host").asString),
        config.get("port").asInt, endpointInfo = endpoint(config.get("name").asString), logger = { System.err.println(it) })
    val observer = launch(start = CoroutineStart.UNDISPATCHED) {
        connection.state.collect { state ->
            when (state) {
                is OutboundConnectionState.AwaitingRemoteAcceptance -> event("state" to "waiting", "pin" to state.pin)
                is OutboundConnectionState.Sending -> event("state" to "running", "pin" to state.pin,
                    "progress" to state.progress.fraction, "bytes" to state.bytesSent, "total" to state.totalSize)
                else -> Unit
            }
        }
    }
    val input = Thread {
        while (true) {
            val line = readLine() ?: break
            try {
                if (gson.fromJson(line, JsonObject::class.java).get("command")?.asString == "cancel") connection.cancel()
            } catch (_: Exception) { }
        }
        connection.cancel()
    }.apply { isDaemon = true; start() }
    try {
        when (val result = connection.run(files)) {
            OutboundResult.Completed -> event("state" to "finished", "progress" to 1.0)
            is OutboundResult.Failed -> event("state" to "failed", "error" to result.reason)
            is OutboundResult.Rejected -> event("state" to "failed", "error" to "Peer rejected: ${result.status}")
            is OutboundResult.Cancelled -> event("state" to "canceled")
        }
    } finally { observer.cancelAndJoin() }
}

private suspend fun receive(config: JsonObject): Unit = coroutineScope {
    val root = Paths.get(config.get("destination").asString).toAbsolutePath()
    Files.createDirectories(root)
    require(!Files.isSymbolicLink(root)) { "Destination must not be a symlink" }
    val server = ServerSocket(config.get("port")?.asInt ?: 0, 4,
        InetAddress.getByName(config.get("bind").asString))
    val active = ConcurrentHashMap<String, InboundConnection>()
    val destinations = ConcurrentHashMap<String, Destination>()
    val slots = Semaphore(3)
    Thread {
        try {
            while (true) {
                val line = readLine() ?: break
                try {
                    val command = gson.fromJson(line, JsonObject::class.java)
                    val id = command.get("id")?.asString
                    when (command.get("command")?.asString) {
                        "approve" -> {
                            val connection = active[id]
                            if (connection?.state?.value is InboundConnectionState.WaitingForUserConsent) {
                                val value = command.get("accepted").asBoolean
                                destinations[id]?.consent(value)
                                connection.submitUserConsent(value)
                            }
                        }
                        "cancel" -> active[id]?.cancel()
                        "stop" -> break
                    }
                } catch (_: Exception) { }
            }
        } finally {
            server.close()
            active.values.forEach { it.cancel() }
        }
    }.apply { isDaemon = true; start() }
    event("event" to "listening", "port" to server.localPort, "endpoint" to java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(endpoint(config.get("name").asString)))
    try {
        while (!server.isClosed) {
            val socket = try { withContext(Dispatchers.IO) { server.accept() } } catch (_: java.net.SocketException) { break }
            if (!slots.tryAcquire()) { socket.close(); continue }
            socket.soTimeout = 65000
            launch(Dispatchers.IO) {
                val id = UUID.randomUUID().toString()
                val connection = InboundConnection(socket, logger = { System.err.println(it) })
                active[id] = connection
                val destination = try { Destination(root) } catch (error: Exception) {
                    event("event" to "ended", "id" to id, "error" to error.message)
                    socket.close(); active.remove(id); slots.release()
                    return@launch
                }
                destinations[id] = destination
                var published = false
                val deadline = launch { delay(30 * 60 * 1000L); connection.cancel(); socket.close() }
                val observer = launch(start = CoroutineStart.UNDISPATCHED) {
                    connection.state.collect { state ->
                        when (state) {
                            is InboundConnectionState.WaitingForUserConsent -> {
                                try {
                                    destination.authorize(state.metadata)
                                    event("event" to "request", "id" to id, "sender" to (state.metadata.sourceDeviceName ?: "Unknown"),
                                        "pin" to state.metadata.pin, "files" to state.metadata.items.map { (it as TransferItem.File).name },
                                        "total" to state.metadata.totalSize)
                                    launch { delay(45000); if (connection.state.value is InboundConnectionState.WaitingForUserConsent) connection.submitUserConsent(false) }
                                } catch (error: Exception) {
                                    event("event" to "rejected", "id" to id, "error" to error.message)
                                    connection.submitUserConsent(false)
                                }
                            }
                            is InboundConnectionState.Receiving -> event("event" to "progress", "id" to id,
                                "progress" to state.progress.fraction, "bytes" to state.bytesReceived, "total" to state.totalSize)
                            else -> Unit
                        }
                    }
                }
                try {
                    val result = connection.run(destination)
                    if (result is InboundResult.Completed) {
                        val final = destination.publish(); published = true
                        event("event" to "received", "id" to id, "destination" to final.toString(), "count" to result.items.size)
                    } else event("event" to "ended", "id" to id, "result" to result.toString())
                } catch (error: Exception) {
                    event("event" to "ended", "id" to id, "error" to error.message)
                } finally {
                    deadline.cancel(); observer.cancelAndJoin()
                    socket.close()
                    if (!published) destination.discard()
                    active.remove(id); destinations.remove(id); slots.release()
                }
            }
        }
    } finally { server.close(); active.values.forEach { it.cancel() } }
}

fun main() = runBlocking {
    try {
        val first = readLine() ?: return@runBlocking
        require(first.length <= 65536) { "Configuration too large" }
        val config = gson.fromJson(first, JsonObject::class.java)
        when (config.get("command").asString) {
            "send" -> send(config)
            "receive" -> receive(config)
            else -> error("Unknown command")
        }
    } catch (error: Exception) {
        event("state" to "failed", "error" to (error.message ?: error.javaClass.simpleName))
        kotlin.system.exitProcess(1)
    }
}
