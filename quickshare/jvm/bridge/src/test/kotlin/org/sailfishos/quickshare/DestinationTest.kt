// SPDX-License-Identifier: GPL-3.0-or-later
package org.sailfishos.quickshare

import com.google.location.nearby.connections.proto.OfflineWireFormatsProto.PayloadTransferFrame.PayloadHeader
import dev.bluehouse.bada.protocol.connection.TransferItem
import dev.bluehouse.bada.protocol.connection.TransferMetadata
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.io.TempDir
import java.nio.ByteBuffer
import java.nio.file.Files
import java.nio.file.Path

class DestinationTest {
    @TempDir lateinit var root: Path
    private fun metadata(name: String = "hello.txt", size: Long = 3) =
        TransferMetadata(listOf(TransferItem.File(17, name, size, "text/plain")), "1234")
    private fun header(id: Long = 17, size: Long = 3) = PayloadHeader.newBuilder()
        .setId(id).setType(PayloadHeader.PayloadType.FILE).setTotalSize(size).setFileName("hello.txt").build()

    @Test fun `payload must match consent and be announced`() {
        val destination = Destination(root)
        assertThrows(IllegalArgumentException::class.java) { destination.open(header()) }
        destination.authorize(metadata())
        assertThrows(IllegalArgumentException::class.java) { destination.open(header()) }
        destination.consent(true)
        assertThrows(IllegalArgumentException::class.java) { destination.open(header(id = 18)) }
        assertThrows(IllegalArgumentException::class.java) { destination.open(header(size = 4)) }
        destination.discard()
        assertEquals(0, Files.list(root).use { it.count() })
    }
    @Test fun `traversal and control filenames cannot write outside batch`() {
        for (name in listOf("../escape", "..", "/tmp/file", "a\\b", "a\u0000b", "a\nb")) {
            val destination = Destination(root)
            assertThrows(IllegalArgumentException::class.java) { destination.authorize(metadata(name)) }
            destination.discard()
        }
        assertEquals(0, Files.list(root).use { it.count() })
    }
    @Test fun `committed files survive core teardown but remain hidden until publish`() {
        val destination = Destination(root)
        destination.authorize(metadata())
        destination.consent(true)
        destination.open(header()).use { it.write(ByteBuffer.wrap(byteArrayOf(1, 2, 3))) }
        destination.commit(17)
        destination.abortAll()
        assertFalse(Files.list(root).use { it.anyMatch { path -> path.fileName.toString().startsWith("transfer-") } })
        val final = destination.publish()
        assertArrayEquals(byteArrayOf(1, 2, 3), Files.readAllBytes(final.resolve("hello.txt")))
    }
    @Test fun `failed batch removes even earlier committed files`() {
        val destination = Destination(root)
        destination.authorize(metadata())
        destination.consent(true)
        destination.open(header()).use { it.write(ByteBuffer.wrap(byteArrayOf(1, 2, 3))) }
        destination.commit(17)
        destination.discard()
        assertEquals(0, Files.list(root).use { it.count() })
    }
    @Test fun `short file cannot be committed or published`() {
        val destination = Destination(root)
        destination.authorize(metadata())
        destination.consent(true)
        destination.open(header()).use { it.write(ByteBuffer.wrap(byteArrayOf(1))) }
        assertThrows(IllegalArgumentException::class.java) { destination.commit(17) }
        assertThrows(IllegalArgumentException::class.java) { destination.publish() }
        destination.discard()
    }
    @Test fun `overflow size and duplicate payload identifiers are rejected`() {
        for (items in listOf(
            listOf(TransferItem.File(1, "big", Long.MAX_VALUE, "")),
            listOf(TransferItem.File(1, "a", 1, ""), TransferItem.File(1, "b", 1, ""))
        )) {
            val destination = Destination(root)
            assertThrows(IllegalArgumentException::class.java) { destination.authorize(TransferMetadata(items, "1234")) }
            destination.discard()
        }
    }
}
