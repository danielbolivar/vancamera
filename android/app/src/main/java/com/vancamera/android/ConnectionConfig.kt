package com.vancamera.android

import android.os.Parcelable
import kotlinx.parcelize.Parcelize

/**
 * Configuración de conexión para transmisión de video
 */
@Parcelize
data class ConnectionConfig(
    val serverIp: String,
    // Avoid privileged ports (<1024) on Android.
    val serverPort: Int = 8443,
    val connectionMode: ConnectionMode = ConnectionMode.WIFI
) : Parcelable {
    /**
     * Valida que la configuración sea correcta
     */
    fun isValid(): Boolean {
        return serverIp.isNotBlank() &&
               serverPort in 1..65535 &&
               isValidIpAddress(serverIp)
    }

    /**
     * Valida formato de dirección IP
     */
    private fun isValidIpAddress(ip: String): Boolean {
        val parts = ip.split(".")
        if (parts.size != 4) return false
        return parts.all { part ->
            val num = part.toIntOrNull()
            num != null && num in 0..255
        }
    }

    /**
     * Obtiene la URL completa de conexión
     */
    fun getConnectionUrl(): String {
        return "$serverIp:$serverPort"
    }

    companion object {
        /**
         * Configuración por defecto
         */
        fun default(): ConnectionConfig {
            return ConnectionConfig(
                serverIp = "192.168.1.100", // IP común de ejemplo
                serverPort = 8443,
                connectionMode = ConnectionMode.WIFI
            )
        }
    }
}

/**
 * Modo de conexión disponible
 */
enum class ConnectionMode {
    /**
     * Conexión directa por WiFi
     */
    WIFI,

    /**
     * Conexión por USB usando ADB port forwarding
     */
    USB
}
