package com.vancamera.android

import android.util.Log
import java.io.BufferedOutputStream
import java.io.IOException
import java.net.InetSocketAddress
import java.net.SocketException
import java.util.concurrent.atomic.AtomicLong
import javax.net.ssl.SSLServerSocket
import javax.net.ssl.SSLSocket

/**
 * TLS 1.3 video server.
 *
 * Android is the TLS server, the Windows app connects to it (directly over Wi-Fi, or through an
 * `adb forward` tunnel over USB).
 *
 * Robustness changes compared to the previous single-shot `accept()`:
 * - The server keeps accepting connections for as long as streaming is on. When the PC reconnects
 *   (after a Wi-Fi hiccup, or after the user clicks Disconnect/Connect) the new connection simply
 *   replaces the old one; the phone never has to be restarted.
 * - Connections that fail the TLS handshake (port scanners and security probes that are common on
 *   enterprise networks, half-open connections...) are closed and ignored instead of killing the
 *   stream.
 * - A single sender thread per client writes packets from a bounded [FrameQueue], so writes can no
 *   longer interleave and slow networks drop frames instead of accumulating latency.
 * - A write that stays blocked for [STALLED_WRITE_TIMEOUT_MS] (dead Wi-Fi link) drops the client so
 *   the PC can reconnect.
 */
class VideoStreamer(
    private val port: Int,
    private val certificateManager: CertificateManager,
    private val listener: Listener
) {

    interface Listener {
        /** A client completed the TLS handshake. Called on a background thread. */
        fun onClientConnected(address: String)

        /** The current client went away. Called on a background thread. */
        fun onClientDisconnected()

        /** Frames were dropped: the encoder should produce a keyframe. */
        fun onKeyFrameNeeded()
    }

    companion object {
        private const val TAG = "VideoStreamer"
        private const val HANDSHAKE_TIMEOUT_MS = 5_000
        private const val STALLED_WRITE_TIMEOUT_MS = 5_000L
        private const val SOCKET_BUFFER_BYTES = 256 * 1024
    }

    @Volatile
    private var running = false
    private var serverSocket: SSLServerSocket? = null
    private var acceptThread: Thread? = null

    @Volatile
    private var client: ClientConnection? = null

    val bytesSent = AtomicLong(0)
    val framesSent = AtomicLong(0)
    val framesDropped = AtomicLong(0)

    val hasClient: Boolean get() = client?.isOpen == true
    val clientAddress: String? get() = client?.address

    /**
     * Binds the server socket and starts accepting clients in the background.
     * Must not be called on the main thread (certificate generation can take a while).
     */
    fun start() {
        if (running) return
        val sslContext = certificateManager.createSSLContextBlocking()

        // Create UNBOUND so SO_REUSEADDR takes effect before binding (fast restart after stop).
        val ss = sslContext.serverSocketFactory.createServerSocket() as SSLServerSocket
        ss.reuseAddress = true
        ss.enabledProtocols = arrayOf("TLSv1.3")
        ss.needClientAuth = false
        ss.bind(InetSocketAddress(port))
        serverSocket = ss
        running = true

        acceptThread = Thread({ acceptLoop(ss) }, "vancamera-accept").also {
            it.isDaemon = true
            it.start()
        }
        Log.i(TAG, "Listening on 0.0.0.0:$port")
    }

    private fun acceptLoop(ss: SSLServerSocket) {
        while (running) {
            val socket = try {
                ss.accept() as SSLSocket
            } catch (e: IOException) {
                if (running) {
                    Log.w(TAG, "accept() failed: ${e.message}")
                    Thread.sleep(200)
                }
                continue
            }

            val address = socket.inetAddress?.hostAddress ?: "unknown"
            try {
                socket.enabledProtocols = arrayOf("TLSv1.3")
                // === LOW LATENCY NETWORK SETTINGS ===
                socket.tcpNoDelay = true
                socket.keepAlive = true
                socket.sendBufferSize = SOCKET_BUFFER_BYTES
                socket.soTimeout = HANDSHAKE_TIMEOUT_MS
                socket.startHandshake()
                socket.soTimeout = 0
            } catch (e: Exception) {
                // Not a VanCamera client (or a broken one): ignore it and keep listening.
                Log.w(TAG, "Rejected connection from $address: ${e.message}")
                try {
                    socket.close()
                } catch (_: Exception) {
                }
                continue
            }

            Log.i(TAG, "Client connected: $address")
            val newClient = ClientConnection(socket, address)
            val previous = synchronized(this) {
                val old = client
                client = newClient
                old
            }
            // A new connection replaces the old one (e.g. the PC reconnected after a drop).
            previous?.close(notify = false)
            newClient.start()
            listener.onClientConnected(address)
        }
    }

    /**
     * Queues an encoded frame for the current client. Never blocks.
     */
    fun send(frame: EncodedFrame, flags: Int) {
        val current = client ?: return
        if (!current.isOpen) return
        current.checkStalled()
        when (current.queue.offer(StreamProtocol.frame(frame.data, flags), frame.isKeyFrame)) {
            FrameQueue.OfferResult.QUEUED -> Unit
            FrameQueue.OfferResult.DROPPED -> framesDropped.incrementAndGet()
            FrameQueue.OfferResult.DROPPED_NEED_KEYFRAME -> {
                framesDropped.incrementAndGet()
                listener.onKeyFrameNeeded()
            }
        }
    }

    /** Disconnects the current client (the server keeps listening). */
    fun dropClient() {
        client?.close(notify = true)
    }

    /** Stops listening and disconnects the client. */
    fun stop() {
        running = false
        try {
            serverSocket?.close()
        } catch (_: Exception) {
        }
        serverSocket = null
        val current = synchronized(this) {
            val c = client
            client = null
            c
        }
        current?.close(notify = false)
        acceptThread?.interrupt()
        acceptThread = null
        Log.i(TAG, "Server stopped")
    }

    private inner class ClientConnection(private val socket: SSLSocket, val address: String) {
        val queue = FrameQueue()

        @Volatile
        var isOpen = true
            private set

        @Volatile
        private var writeStartedAtMs = 0L
        private val output = BufferedOutputStream(socket.outputStream, 64 * 1024)
        private val thread = Thread({ sendLoop() }, "vancamera-sender")

        fun start() {
            thread.isDaemon = true
            thread.start()
        }

        private fun sendLoop() {
            try {
                while (isOpen) {
                    val packet = queue.poll(500) ?: continue
                    writeStartedAtMs = System.currentTimeMillis()
                    output.write(packet)
                    output.flush()
                    writeStartedAtMs = 0L
                    bytesSent.addAndGet(packet.size.toLong())
                    framesSent.incrementAndGet()
                }
            } catch (e: SocketException) {
                if (isOpen) Log.i(TAG, "Client $address disconnected: ${e.message}")
            } catch (e: Exception) {
                if (isOpen) Log.w(TAG, "Send error to $address: ${e.message}")
            } finally {
                close(notify = true)
            }
        }

        /** Detects a write stuck on a dead link (TCP may take minutes to notice). */
        fun checkStalled() {
            val started = writeStartedAtMs
            if (started != 0L && System.currentTimeMillis() - started > STALLED_WRITE_TIMEOUT_MS) {
                Log.w(TAG, "Write to $address stalled for more than ${STALLED_WRITE_TIMEOUT_MS}ms, dropping client")
                close(notify = true)
            }
        }

        fun close(notify: Boolean) {
            val wasCurrent: Boolean
            synchronized(this@VideoStreamer) {
                if (!isOpen) return
                isOpen = false
                wasCurrent = client === this
                if (wasCurrent) client = null
            }
            queue.close()
            // Closing a TLS socket can block while a write is stuck on a dead link, so never do
            // it on the caller's thread (accept loop / encoder callback).
            Thread({
                try {
                    socket.close()
                } catch (_: Exception) {
                }
            }, "vancamera-close").apply { isDaemon = true }.start()
            if (notify && wasCurrent) {
                listener.onClientDisconnected()
            }
        }
    }
}

class StreamException(message: String, cause: Throwable? = null) : Exception(message, cause)
