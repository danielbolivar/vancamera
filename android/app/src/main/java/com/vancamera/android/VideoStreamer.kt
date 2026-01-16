package com.vancamera.android

import android.content.Context
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import java.io.OutputStream
import java.net.Socket
import javax.net.ssl.SSLContext
import javax.net.ssl.SSLSocket
import javax.net.ssl.SSLSocketFactory

/**
 * Gestor de transmisión de video vía TLS 1.3
 */
class VideoStreamer(
    private val context: Context,
    private val connectionConfig: ConnectionConfig,
    private val certificateManager: CertificateManager
) {

    companion object {
        private const val TAG = "VideoStreamer"
    }

    private var sslSocket: SSLSocket? = null
    private var outputStream: OutputStream? = null
    private val isConnected = MutableStateFlow(false)
    private val connectionState: StateFlow<Boolean> = isConnected

    /**
     * Estado de conexión observable
     */
    fun getConnectionState(): StateFlow<Boolean> = connectionState

    /**
     * Conecta al servidor Windows usando TLS 1.3
     */
    suspend fun connect() = withContext(Dispatchers.IO) {
        try {
            Log.d(TAG, "Conectando a ${connectionConfig.serverIp}:${connectionConfig.serverPort}")

            // Crear SSLContext con el certificado
            val sslContext = certificateManager.createSSLContext()

            // Crear socket SSL
            val socketFactory = sslContext.socketFactory
            val socket = socketFactory.createSocket(
                connectionConfig.serverIp,
                connectionConfig.serverPort
            ) as SSLSocket

            // Forzar TLS 1.3
            socket.enabledProtocols = arrayOf("TLSv1.3")
            socket.enabledCipherSuites = socket.supportedCipherSuites

            // Iniciar handshake
            socket.startHandshake()

            sslSocket = socket
            outputStream = socket.getOutputStream()

            isConnected.value = true
            Log.d(TAG, "Conexión establecida exitosamente")

        } catch (e: Exception) {
            Log.e(TAG, "Error al conectar: ${e.message}", e)
            isConnected.value = false
            throw StreamException("Error al conectar: ${e.message}", e)
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
     * Desconecta del servidor
     */
    suspend fun disconnect() = withContext(Dispatchers.IO) {
        try {
            outputStream?.close()
            sslSocket?.close()
            outputStream = null
            sslSocket = null
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
     * Reintenta la conexión
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
