package com.vancamera.android

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class StreamProtocolTest {

    @Test
    fun flagsEncodeOrientationAndCamera() {
        assertEquals(0x00, StreamProtocol.flags(0, backCamera = false))
        assertEquals(0x01, StreamProtocol.flags(90, backCamera = false))
        assertEquals(0x02, StreamProtocol.flags(180, backCamera = false))
        assertEquals(0x03, StreamProtocol.flags(270, backCamera = false))
        assertEquals(0x81, StreamProtocol.flags(90, backCamera = true))
        assertEquals(0x80, StreamProtocol.flags(45, backCamera = true))
    }

    @Test
    fun frameHasBigEndianSizeFlagsAndPayload() {
        val payload = ByteArray(300) { it.toByte() }
        val packet = StreamProtocol.frame(payload, 0x83)
        assertEquals(4 + 1 + 300, packet.size)
        // size = 1 (flags) + payload = 301 = 0x0000012D
        assertArrayEquals(byteArrayOf(0, 0, 0x01, 0x2D), packet.copyOfRange(0, 4))
        assertEquals(0x83.toByte(), packet[4])
        assertArrayEquals(payload, packet.copyOfRange(5, packet.size))
    }

    @Test
    fun sensorOrientationMapping() {
        assertEquals(90, StreamProtocol.orientationFromSensorDegrees(0))
        assertEquals(90, StreamProtocol.orientationFromSensorDegrees(350))
        assertEquals(180, StreamProtocol.orientationFromSensorDegrees(90))
        assertEquals(270, StreamProtocol.orientationFromSensorDegrees(180))
        assertEquals(0, StreamProtocol.orientationFromSensorDegrees(270))
    }
}
