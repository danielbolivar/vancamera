package com.vancamera.android

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.os.Build
import android.util.Log

/**
 * Publishes the VanCamera service via mDNS/DNS-SD (Network Service Discovery).
 *
 * This allows Windows clients to automatically discover Android devices
 * on the local network when they start streaming.
 *
 * Service type: _vancamera._tcp
 * Service name: VanCamera-<device_model>
 */
class NsdServicePublisher(private val context: Context) {

    companion object {
        private const val TAG = "NsdServicePublisher"
        private const val SERVICE_TYPE = "_vancamera._tcp."
    }

    private val nsdManager: NsdManager =
        context.getSystemService(Context.NSD_SERVICE) as NsdManager

    private var registrationListener: NsdManager.RegistrationListener? = null
    private var isRegistered = false
    private var serviceName: String? = null

    /**
     * Publishes the VanCamera service on the network.
     *
     * @param port The port number the server is listening on
     */
    fun publishService(port: Int) {
        if (isRegistered) {
            Log.w(TAG, "Service already registered, skipping")
            return
        }

        val deviceName = getDeviceName()

        val serviceInfo = NsdServiceInfo().apply {
            serviceName = "VanCamera-$deviceName"
            serviceType = SERVICE_TYPE
            setPort(port)
        }

        registrationListener = object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(info: NsdServiceInfo) {
                // The system may have changed the service name to avoid conflicts
                this@NsdServicePublisher.serviceName = info.serviceName
                isRegistered = true
                Log.i(TAG, "Service registered: ${info.serviceName} on port $port")
            }

            override fun onRegistrationFailed(serviceInfo: NsdServiceInfo, errorCode: Int) {
                isRegistered = false
                Log.e(TAG, "Registration failed: error code $errorCode")
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
            nsdManager.registerService(
                serviceInfo,
                NsdManager.PROTOCOL_DNS_SD,
                registrationListener
            )
            Log.d(TAG, "Registering service: VanCamera-$deviceName on port $port")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to register service: ${e.message}", e)
        }
    }

    /**
     * Unpublishes the service from the network.
     */
    fun unpublishService() {
        if (!isRegistered || registrationListener == null) {
            Log.d(TAG, "Service not registered, nothing to unpublish")
            return
        }

        try {
            nsdManager.unregisterService(registrationListener)
            Log.d(TAG, "Unregistering service")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to unregister service: ${e.message}", e)
        } finally {
            registrationListener = null
            isRegistered = false
            serviceName = null
        }
    }

    /**
     * Gets the device model name for the service name.
     */
    private fun getDeviceName(): String {
        val manufacturer = Build.MANUFACTURER.replaceFirstChar { it.uppercase() }
        val model = Build.MODEL

        // If model already contains manufacturer, just use model
        return if (model.startsWith(manufacturer, ignoreCase = true)) {
            model.replace(" ", "_")
        } else {
            "${manufacturer}_$model".replace(" ", "_")
        }
    }

    /**
     * Returns whether the service is currently registered.
     */
    fun isServiceRegistered(): Boolean = isRegistered
}
