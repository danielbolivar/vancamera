package com.vancamera.android

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.io.OutputStream
import javax.net.ssl.SSLContext
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
            Log.d(TAG, "Waiting for client on 0.0.0.0:${connectionConfig.serverPort}")

            // Create SSLContext with our certificate/private key.
            val sslContext = certificateManager.createSSLContext()

            // Create SSL server socket.
            val ss = (sslContext.serverSocketFactory.createServerSocket(connectionConfig.serverPort) as SSLServerSocket).apply {
                enabledProtocols = arrayOf("TLSv1.3")
                needClientAuth = false
                reuseAddress = true
            }

            serverSocket = ss

            // Accept a single client connection.
            val socket = ss.accept() as SSLSocket
            socket.enabledProtocols = arrayOf("TLSv1.3")

            // Perform handshake.
            socket.startHandshake()

            sslSocket = socket
            outputStream = socket.outputStream

            isConnected.value = true
            Log.d(TAG, "Client connected successfully")

        } catch (e: Exception) {
            Log.e(TAG, "Error al conectar: ${e.message}", e)
            isConnected.value = false
            throw StreamException("Failed to accept client: ${e.message}", e)
        }
    }

    /**
     * Envía datos de video codificados
     */
    suspend fun sendVideoData(data: ByteArray) = withContext(Dispatchers.IO) {
        if (!isConnected.value || outputStream == null) {
            Log.w(TAG, "No hay conexión activa, ignorando datos")
            return@withContext
        }

        try {
            // Enviar tamaño del paquete (4 bytes)
            val sizeBytes = intToByteArray(data.size)
            outputStream?.write(sizeBytes)

            // Enviar datos
            outputStream?.write(data)
            outputStream?.flush()

        } catch (e: Exception) {
            Log.e(TAG, "Error al enviar datos: ${e.message}", e)
            isConnected.value = false
            throw StreamException("Error al enviar datos: ${e.message}", e)
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
        try {
            outputStream?.close()
            sslSocket?.close()
            serverSocket?.close()
            outputStream = null
            sslSocket = null
            serverSocket = null
            isConnected.value = false
            Log.d(TAG, "Desconectado")
        } catch (e: Exception) {
            Log.e(TAG, "Error al desconectar: ${e.message}", e)
        }
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
