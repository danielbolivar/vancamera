package com.vancamera.android

import org.junit.Assert.assertEquals
import org.junit.Test

class NetworkAddressesTest {
    @Test
    fun classifiesInterfaces() {
        assertEquals(LocalAddress.Kind.WIFI, NetworkAddresses.kindForInterface("wlan0"))
        assertEquals(LocalAddress.Kind.HOTSPOT, NetworkAddresses.kindForInterface("swlan0"))
        assertEquals(LocalAddress.Kind.HOTSPOT, NetworkAddresses.kindForInterface("ap0"))
        assertEquals(LocalAddress.Kind.ETHERNET, NetworkAddresses.kindForInterface("eth0"))
        assertEquals(LocalAddress.Kind.USB_TETHER, NetworkAddresses.kindForInterface("rndis0"))
        assertEquals(LocalAddress.Kind.OTHER, NetworkAddresses.kindForInterface("rmnet_data0"))
    }
}
