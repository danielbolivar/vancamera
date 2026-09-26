package com.vancamera.android

import java.net.Inet4Address
import java.net.NetworkInterface

/** A local IPv4 address the PC can use to reach this phone. */
data class LocalAddress(val kind: Kind, val ip: String) {
    enum class Kind { WIFI, HOTSPOT, ETHERNET, USB_TETHER, OTHER }
}

/**
 * Lists the phone's IPv4 addresses so the user can type one into the PC app.
 *
 * mDNS discovery does not work on many enterprise / university networks (multicast is filtered),
 * so showing the address is what makes the manual "Add by IP" flow usable (issue #5).
 */
object NetworkAddresses {

    fun list(): List<LocalAddress> = try {
        NetworkInterface.getNetworkInterfaces()?.toList().orEmpty()
            .filter { it.isUp && !it.isLoopback }
            .flatMap { nif ->
                val kind = kindForInterface(nif.name)
                nif.inetAddresses.toList()
                    .filterIsInstance<Inet4Address>()
                    .filter { !it.isLoopbackAddress && !it.isLinkLocalAddress }
                    .mapNotNull { addr -> addr.hostAddress?.let { LocalAddress(kind, it) } }
            }
            // Cellular interfaces (rmnet*, ccmni*...) are not reachable from the PC.
            .filter { it.kind != LocalAddress.Kind.OTHER }
            .sortedBy { it.kind.ordinal }
    } catch (_: Exception) {
        emptyList()
    }

    fun kindForInterface(name: String): LocalAddress.Kind {
        val n = name.lowercase()
        return when {
            n.startsWith("wlan") && !n.startsWith("wlan1") -> LocalAddress.Kind.WIFI
            n.startsWith("wlan1") || n.startsWith("ap") || n.startsWith("swlan") ||
                n.startsWith("softap") -> LocalAddress.Kind.HOTSPOT
            n.startsWith("eth") -> LocalAddress.Kind.ETHERNET
            n.startsWith("rndis") || n.startsWith("usb") || n.startsWith("ncm") -> LocalAddress.Kind.USB_TETHER
            else -> LocalAddress.Kind.OTHER
        }
    }
}
