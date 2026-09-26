package com.vancamera.android

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test
import java.nio.ByteBuffer

class YuvConverterTest {

    private val width = 8
    private val height = 4

    private fun lumaAt(x: Int, y: Int) = (y * 16 + x).toByte()
    private fun uAt(x: Int, y: Int) = (100 + y * 8 + x).toByte()
    private fun vAt(x: Int, y: Int) = (-100 + y * 8 + x).toByte()

    /** Y plane with row padding, like most camera HALs produce. */
    private fun yPlane(rowStride: Int): YuvPlane {
        val buf = ByteBuffer.allocateDirect(rowStride * (height - 1) + width)
        for (y in 0 until height) for (x in 0 until width) buf.put(y * rowStride + x, lumaAt(x, y))
        return YuvPlane(buf, rowStride, 1)
    }

    /**
     * Semi-planar chroma as delivered by YUV_420_888 with pixelStride 2. [vFirst] = true models
     * the common NV21 memory layout (V buffer starts one byte before U).
     */
    private fun semiPlanarChroma(rowStride: Int, vFirst: Boolean): Pair<YuvPlane, YuvPlane> {
        val cw = width / 2
        val ch = height / 2
        val backing = ByteBuffer.allocateDirect(rowStride * ch + 1)
        for (y in 0 until ch) for (x in 0 until cw) {
            val base = y * rowStride + x * 2
            if (vFirst) {
                backing.put(base, vAt(x, y)); backing.put(base + 1, uAt(x, y))
            } else {
                backing.put(base, uAt(x, y)); backing.put(base + 1, vAt(x, y))
            }
        }
        val length = rowStride * (ch - 1) + (cw - 1) * 2 + 1
        fun sliceAt(offset: Int): ByteBuffer {
            val dup = backing.duplicate()
            dup.position(offset)
            dup.limit(offset + length)
            return dup.slice()
        }
        val u = sliceAt(if (vFirst) 1 else 0)
        val v = sliceAt(if (vFirst) 0 else 1)
        return YuvPlane(u, rowStride, 2) to YuvPlane(v, rowStride, 2)
    }

    private fun planarChroma(rowStride: Int): Pair<YuvPlane, YuvPlane> {
        val cw = width / 2
        val ch = height / 2
        val u = ByteBuffer.allocateDirect(rowStride * (ch - 1) + cw)
        val v = ByteBuffer.allocateDirect(rowStride * (ch - 1) + cw)
        for (y in 0 until ch) for (x in 0 until cw) {
            u.put(y * rowStride + x, uAt(x, y))
            v.put(y * rowStride + x, vAt(x, y))
        }
        return YuvPlane(u, rowStride, 1) to YuvPlane(v, rowStride, 1)
    }

    private fun expectedNv12(): ByteArray {
        val out = ArrayList<Byte>()
        for (y in 0 until height) for (x in 0 until width) out += lumaAt(x, y)
        for (y in 0 until height / 2) for (x in 0 until width / 2) {
            out += uAt(x, y); out += vAt(x, y)
        }
        return out.toByteArray()
    }

    private fun expectedI420(): ByteArray {
        val out = ArrayList<Byte>()
        for (y in 0 until height) for (x in 0 until width) out += lumaAt(x, y)
        for (y in 0 until height / 2) for (x in 0 until width / 2) out += uAt(x, y)
        for (y in 0 until height / 2) for (x in 0 until width / 2) out += vAt(x, y)
        return out.toByteArray()
    }

    private fun convert(y: YuvPlane, u: YuvPlane, v: YuvPlane, layout: YuvLayout): ByteArray {
        val out = ByteBuffer.allocateDirect(YuvConverter.requiredSize(width, height))
        YuvConverter().convert(y, u, v, width, height, layout, out)
        assertEquals("output must be completely filled", 0, out.remaining())
        out.flip()
        return ByteArray(out.remaining()).also { out.get(it) }
    }

    @Test
    fun nv21MemoryToNv12_withPadding() {
        val (u, v) = semiPlanarChroma(rowStride = 12, vFirst = true)
        assertArrayEquals(expectedNv12(), convert(yPlane(rowStride = 12), u, v, YuvLayout.NV12))
    }

    @Test
    fun nv12MemoryToNv12_noPadding() {
        val (u, v) = semiPlanarChroma(rowStride = width, vFirst = false)
        assertArrayEquals(expectedNv12(), convert(yPlane(rowStride = width), u, v, YuvLayout.NV12))
    }

    @Test
    fun planarToNv12() {
        val (u, v) = planarChroma(rowStride = 6)
        assertArrayEquals(expectedNv12(), convert(yPlane(rowStride = 10), u, v, YuvLayout.NV12))
    }

    @Test
    fun semiPlanarToI420() {
        val (u, v) = semiPlanarChroma(rowStride = 16, vFirst = true)
        assertArrayEquals(expectedI420(), convert(yPlane(rowStride = 16), u, v, YuvLayout.I420))
    }

    @Test
    fun planarToI420() {
        val (u, v) = planarChroma(rowStride = width / 2)
        assertArrayEquals(expectedI420(), convert(yPlane(rowStride = width), u, v, YuvLayout.I420))
    }

    @Test
    fun cropsLargerSourceToRequestedSize() {
        // Source is 8x4 but we only encode the top-left 4x2.
        val (u, v) = semiPlanarChroma(rowStride = 12, vFirst = true)
        val out = ByteBuffer.allocate(YuvConverter.requiredSize(4, 2))
        YuvConverter().convert(yPlane(12), u, v, 4, 2, YuvLayout.NV12, out)
        val expected = byteArrayOf(
            lumaAt(0, 0), lumaAt(1, 0), lumaAt(2, 0), lumaAt(3, 0),
            lumaAt(0, 1), lumaAt(1, 1), lumaAt(2, 1), lumaAt(3, 1),
            uAt(0, 0), vAt(0, 0), uAt(1, 0), vAt(1, 0)
        )
        assertArrayEquals(expected, out.array())
    }

    @Test(expected = IllegalArgumentException::class)
    fun rejectsTooSmallOutput() {
        val (u, v) = semiPlanarChroma(rowStride = 8, vFirst = true)
        YuvConverter().convert(yPlane(8), u, v, width, height, YuvLayout.NV12, ByteBuffer.allocate(10))
    }
}
