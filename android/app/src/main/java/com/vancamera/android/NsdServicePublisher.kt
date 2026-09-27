package com.vancamera.android

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Build
import android.util.Log
import androidx.core.content.edit
import java.util.UUID

/**
 * Publishes the VanCamera service via mDNS/DNS-SD (Network Service Discovery).
 *
 * This allows Windows clients to automatically discover Android devices
 * on the local network while streaming is on.
 *
 * Service type: _vancamera._tcp
 * Service name: VanCamera-<device_model>
 * TXT record:   id=<stable per-install id>, model=<device model>
 *
 * The stable id lets Windows recognize the same phone even when NSD renames the service
 * (e.g. "VanCamera-Pixel_8 (2)") because a stale registration from a previous session is still
 * cached on the network (issue #1).
 */
class NsdServicePublisher(private val context: Context) {

    companion object {
        private const val TAG = "NsdServicePublisher"
        private const val SERVICE_TYPE = "_vancamera._tcp."
        private const val PREFS = "vancamera"
        private const val PREF_DEVICE_ID = "device_id"

        /** Stable identifier for this install, shared with the PC through the TXT record. */
        fun deviceId(context: Context): String {
            val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            prefs.getString(PREF_DEVICE_ID, null)?.let { return it }
            val id = UUID.randomUUID().toString().replace("-", "").take(16)
            prefs.edit { putString(PREF_DEVICE_ID, id) }
            return id
        }

        fun deviceName(): String {
            val manufacturer = Build.MANUFACTURER.replaceFirstChar { it.uppercase() }
            val model = Build.MODEL
            // If model already contains manufacturer, just use model
            return if (model.startsWith(manufacturer, ignoreCase = true)) {
                model.replace(" ", "_")
            } else {
                "${manufacturer}_$model".replace(" ", "_")
            }
        }
    }

    private val nsdManager: NsdManager =
        context.getSystemService(Context.NSD_SERVICE) as NsdManager

    private var registrationListener: NsdManager.RegistrationListener? = null

    @Volatile
    private var isRegistered = false

    /**
     * Publishes the VanCamera service on the network. Calling it again while already published
     * is a no-op.
     */
    @Synchronized
    fun publishService(port: Int) {
        if (registrationListener != null) {
            Log.d(TAG, "Service already published")
            return
        }

        val name = "VanCamera-${deviceName()}"
        val serviceInfo = NsdServiceInfo().apply {
            serviceName = name
            serviceType = SERVICE_TYPE
            setPort(port)
            setAttribute("id", deviceId(context))
            setAttribute("model", Build.MODEL)
        }

        val listener = object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(info: NsdServiceInfo) {
                // The system may have changed the service name to avoid conflicts
                isRegistered = true
                Log.i(TAG, "Service registered: ${info.serviceName} on port $port")
            }

            override fun onRegistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                isRegistered = false
                Log.e(TAG, "Registration failed: error code $errorCode")
                synchronized(this@NsdServicePublisher) {
                    if (registrationListener === this) registrationListener = null
                }
            }

            override fun onServiceUnregistered(serviceInfo: NsdServiceInfo) {
                isRegistered = false
                Log.i(TAG, "Service unregistered: ${serviceInfo.serviceName}")
            }

            override fun onUnregistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                Log.e(TAG, "Unregistration failed: error code $errorCode")
            }
        }

        try {
            registrationListener = listener
            nsdManager.registerService(serviceInfo, NsdManager.PROTOCOL_DNS_SD, listener)
            Log.d(TAG, "Registering service: $name on port $port")
        } catch (e: Exception) {
            registrationListener = null
            Log.e(TAG, "Failed to register service: ${e.message}", e)
        }
    }

    /**
     * Unpublishes the service from the network.
     *
     * Registration is asynchronous: the old code skipped unregistering when stop was pressed
     * before `onServiceRegistered` fired, leaking a registration that made the phone show up
     * twice on the PC. Always unregister the listener we handed to NsdManager.
     */
    @Synchronized
    fun unpublishService() {
        val listener = registrationListener ?: return
        registrationListener = null
        try {
            nsdManager.unregisterService(listener)
            Log.d(TAG, "Unregistering service")
        } catch (e: Exception) {
            Log.w(TAG, "Failed to unregister service: ${e.message}")
        } finally {
            isRegistered = false
        }
    }

    /**
     * Returns whether the service is currently registered.
     */
    fun isServiceRegistered(): Boolean = isRegistered
}
