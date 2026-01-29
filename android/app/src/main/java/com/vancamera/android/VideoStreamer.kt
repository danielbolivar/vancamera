package com.vancamera.android

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.io.OutputStream
import java.net.InetSocketAddress
import java.net.ServerSocket
import javax.net.ssl.SSLServerSocket
import javax.net.ssl.SSLSocket

/**
 * Video streaming manager over TLS 1.3.
 */
class VideoStreamer(
    private val context: Context,
    private val connectionConfig: ConnectionConfig,
    private val certificateManager: CertificateManager
) {

    companion object {
        private const val TAG = "VideoStreamer"
    }

    private var serverSocket: SSLServerSocket? = null
    private var sslSocket: SSLSocket? = null
    private var outputStream: OutputStream? = null
    private val isConnected = MutableStateFlow(false)
    private val connectionState: StateFlow<Boolean> = isConnected

    // mDNS service publisher for WiFi discovery
    private val nsdPublisher = NsdServicePublisher(context)

    /**
     * Observable connection state.
     */
    fun getConnectionState(): StateFlow<Boolean> = connectionState

    /**
     * Starts a TLS 1.3 server socket and waits for a Windows client to connect.
     *
     * Note: Windows acts as the TLS client and should connect to this device's IP and port.
     */
    suspend fun connect() = withContext(Dispatchers.IO) {
        try {
            // Ensure any previous socket is closed first
            closeAllSockets()

            Log.d(TAG, "Waiting for client on 0.0.0.0:${connectionConfig.serverPort}")

            // Create SSLContext with our certificate/private key.
            val sslContext = certificateManager.createSSLContext()

            // Create UNBOUND SSL server socket first, then set options, then bind.
            // This ensures SO_REUSEADDR takes effect before binding.
            val ss = sslContext.serverSocketFactory.createServerSocket() as SSLServerSocket
            ss.reuseAddress = true
            ss.enabledProtocols = arrayOf("TLSv1.3")
            ss.needClientAuth = false
            ss.bind(InetSocketAddress(connectionConfig.serverPort))

            serverSocket = ss

            // Publish mDNS service so Windows can discover us
            nsdPublisher.publishService(connectionConfig.serverPort)

            // Accept a single client connection.
            val socket = ss.accept() as SSLSocket
            socket.enabledProtocols = arrayOf("TLSv1.3")

            // === LOW LATENCY NETWORK SETTINGS ===
            // TCP_NODELAY - send immediately, no Nagle buffering
            socket.tcpNoDelay = true
            // Smaller buffers - 64KB instead of default (reduces latency)
            socket.sendBufferSize = 65536
            socket.receiveBufferSize = 65536

            // Perform handshake.
            socket.startHandshake()

            sslSocket = socket
            outputStream = socket.outputStream

            isConnected.value = true
            Log.d(TAG, "Client connected successfully")

        } catch (e: Exception) {
            Log.e(TAG, "Connection error: ${e.message}", e)
            closeAllSockets()
            isConnected.value = false
            throw StreamException("Failed to accept client: ${e.message}", e)
        }
    }

    /**
     * Closes all sockets safely, ignoring any exceptions.
     */
    private fun closeAllSockets() {
        try { outputStream?.close() } catch (_: Exception) { }
        try { sslSocket?.close() } catch (_: Exception) { }
        try { serverSocket?.close() } catch (_: Exception) { }
        outputStream = null
        sslSocket = null
        serverSocket = null
    }

    /**
     * Envía datos de video codificados con metadatos de orientación y mirror.
     * @param data H.264 encoded frame data
     * @param orientationDegrees Device orientation in degrees (0, 90, 180, 270)
     * @param mirror Whether to flip horizontally (for back camera fix)
     * Returns true if sent successfully, false if connection was lost.
     *
     * Protocol: [4 bytes: total size][1 byte: flags][H.264 data]
     * - flags: bits 0-1 = orientation (0=0°, 1=90°, 2=180°, 3=270°), bit 7 = mirror
     */
    suspend fun sendVideoData(data: ByteArray, orientationDegrees: Int = 0, mirror: Boolean = false): Boolean = withContext(Dispatchers.IO) {
        if (!isConnected.value || outputStream == null) {
            Log.w(TAG, "No active connection, ignoring data")
            return@withContext false
        }

        try {
            // Convert degrees to orientation bits (0, 1, 2, 3)
            var flagsByte: Int = when (orientationDegrees) {
                90 -> 1
                180 -> 2
                270 -> 3
                else -> 0  // 0 degrees (landscape)
            }

            // Add mirror flag in bit 7
            if (mirror) {
                flagsByte = flagsByte or 0x80
            }

            // Total packet size = 1 (flags) + data size
            val totalSize = 1 + data.size
            val sizeBytes = intToByteArray(totalSize)
            outputStream?.write(sizeBytes)

            // Send flags byte
            outputStream?.write(byteArrayOf(flagsByte.toByte()))

            // Send H.264 data
            outputStream?.write(data)
            outputStream?.flush()
            return@withContext true

        } catch (e: Exception) {
            Log.e(TAG, "Error sending data (connection lost): ${e.message}")
            // Gracefully mark as disconnected - do NOT throw.
            // This prevents app crash on "Broken pipe".
            closeAllSockets()
            isConnected.value = false
            return@withContext false
        }
    }

    /**
     * Convierte un entero a array de bytes (big-endian)
     */
    private fun intToByteArray(value: Int): ByteArray {
        return byteArrayOf(
            (value shr 24).toByte(),
            (value shr 16).toByte(),
            (value shr 8).toByte(),
            value.toByte()
        )
    }

    /**
     * Disconnects the current client and stops the server socket.
     */
    suspend fun disconnect() = withContext(Dispatchers.IO) {
        Log.d(TAG, "Disconnecting...")

        // Unpublish mDNS service
        nsdPublisher.unpublishService()

        closeAllSockets()
        isConnected.value = false
        Log.d(TAG, "Disconnected")
    }

    /**
     * Verifica si está conectado
     */
    fun isConnected(): Boolean {
        return isConnected.value && sslSocket?.isConnected == true
    }

    /**
     * Restarts the server socket and waits again.
     */
    suspend fun reconnect() {
        disconnect()
        connect()
    }
}

/**
 * Excepción personalizada para errores de transmisión
 */
class StreamException(message: String, cause: Throwable? = null) : Exception(message, cause)
