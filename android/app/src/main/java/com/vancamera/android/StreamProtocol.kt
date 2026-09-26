package com.vancamera.android

/**
 * Wire format shared with the Windows client (see docs/PROTOCOL.md).
 *
 * Each frame is sent as: [4 bytes big-endian size][1 byte flags][H.264 data]
 * where size = 1 (flags) + H.264 data length.
 *
 * flags: bits 0-1 = orientation (0=0°, 1=90°, 2=180°, 3=270°), bit 7 = back camera.
 */
object StreamProtocol {

    const val HEADER_SIZE = 5
    private const val BACK_CAMERA_FLAG = 0x80

    fun flags(orientationDegrees: Int, backCamera: Boolean): Int {
        var flags = when (orientationDegrees) {
            90 -> 1
            180 -> 2
            270 -> 3
            else -> 0
        }
        if (backCamera) flags = flags or BACK_CAMERA_FLAG
        return flags
    }

    /**
     * Builds a complete packet in a single array so it goes out as a single TLS record
     * (the old code did three separate writes per frame).
     */
    fun frame(payload: ByteArray, flags: Int): ByteArray {
        val totalSize = 1 + payload.size
        val packet = ByteArray(4 + totalSize)
        packet[0] = (totalSize ushr 24).toByte()
        packet[1] = (totalSize ushr 16).toByte()
        packet[2] = (totalSize ushr 8).toByte()
        packet[3] = totalSize.toByte()
        packet[4] = flags.toByte()
        System.arraycopy(payload, 0, packet, HEADER_SIZE, payload.size)
        return packet
    }

    /**
     * Maps [android.view.OrientationEventListener] degrees to the rotation Windows applies.
     *
     * The camera sensor outputs landscape frames while the phone is held in portrait, so
     * portrait maps to 90° and so on.
     */
    fun orientationFromSensorDegrees(orientation: Int): Int = when {
        orientation >= 315 || orientation < 45 -> 90    // Portrait
        orientation < 135 -> 180                        // Landscape (top to the left)
        orientation < 225 -> 270                        // Portrait upside-down
        else -> 0                                       // Landscape (top to the right)
    }
}
