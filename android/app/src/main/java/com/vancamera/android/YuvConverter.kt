package com.vancamera.android

import java.nio.ByteBuffer

/**
 * One plane of a YUV_420_888 image.
 *
 * Kept independent from [android.media.Image] so the conversion can be unit tested on the JVM.
 */
class YuvPlane(val buffer: ByteBuffer, val rowStride: Int, val pixelStride: Int)

/** Tightly packed layouts accepted by MediaCodec byte-buffer input. */
enum class YuvLayout {
    /** COLOR_FormatYUV420SemiPlanar: Y plane followed by interleaved U/V. */
    NV12,

    /** COLOR_FormatYUV420Planar: Y plane, then U plane, then V plane. */
    I420
}

/**
 * Converts camera YUV_420_888 frames to the tightly packed layout the encoder expects.
 *
 * Performance matters a lot here (this runs 30 times per second): the previous implementation
 * read every pixel with `ByteBuffer.get(index)` (~1.4 million calls per 720p frame), which kept a
 * CPU core busy and was the main reason the phone got hot. This version copies whole rows with
 * bulk `get`/`put` calls, only touches individual bytes when interleaving chroma, and reuses its
 * scratch buffers so it does not allocate per frame.
 *
 * Not thread safe: use one instance per encoding thread.
 */
class YuvConverter {

    private var rowA = ByteArray(0)
    private var rowB = ByteArray(0)
    private var rowOut = ByteArray(0)

    /**
     * Writes a [width]x[height] frame from the three source planes into [out], starting at its
     * current position. [width] and [height] must be even and not larger than the source image.
     */
    fun convert(
        y: YuvPlane,
        u: YuvPlane,
        v: YuvPlane,
        width: Int,
        height: Int,
        layout: YuvLayout,
        out: ByteBuffer
    ) {
        require(width > 0 && height > 0 && width % 2 == 0 && height % 2 == 0) {
            "Frame size must be positive and even: ${width}x$height"
        }
        require(out.remaining() >= requiredSize(width, height)) {
            "Output buffer too small: ${out.remaining()} < ${requiredSize(width, height)}"
        }
        ensureScratch(width)

        copyLuma(y, width, height, out)

        val chromaWidth = width / 2
        val chromaHeight = height / 2
        when (layout) {
            YuvLayout.NV12 -> copyChromaInterleaved(u, v, chromaWidth, chromaHeight, out)
            YuvLayout.I420 -> {
                copyChromaPlanar(u, chromaWidth, chromaHeight, out)
                copyChromaPlanar(v, chromaWidth, chromaHeight, out)
            }
        }
    }

    private fun ensureScratch(width: Int) {
        // A chroma row spans at most (width/2 - 1) * pixelStride + 1 bytes; pixelStride is 1 or 2
        // in practice, but leave room for larger strides.
        val needed = width * 2
        if (rowA.size < needed) {
            rowA = ByteArray(needed)
            rowB = ByteArray(needed)
            rowOut = ByteArray(needed)
        }
    }

    private fun copyLuma(plane: YuvPlane, width: Int, height: Int, out: ByteBuffer) {
        val src = plane.buffer.duplicate()
        if (plane.pixelStride == 1) {
            if (plane.rowStride == width && src.capacity() >= width * height) {
                // Fast path: no row padding, one bulk copy for the whole plane.
                src.clear()
                src.limit(width * height)
                out.put(src)
                return
            }
            for (row in 0 until height) {
                val start = row * plane.rowStride
                src.clear()
                src.position(start)
                src.limit(start + width)
                out.put(src)
            }
            return
        }

        // Unusual: luma with a pixel stride. Read rows and pick every Nth byte.
        for (row in 0 until height) {
            readRow(plane, src, row, width, rowA)
            var i = 0
            for (col in 0 until width) {
                rowOut[col] = rowA[i]
                i += plane.pixelStride
            }
            out.put(rowOut, 0, width)
        }
    }

    private fun copyChromaInterleaved(
        u: YuvPlane,
        v: YuvPlane,
        chromaWidth: Int,
        chromaHeight: Int,
        out: ByteBuffer
    ) {
        val uSrc = u.buffer.duplicate()
        val vSrc = v.buffer.duplicate()
        val uStride = u.pixelStride
        val vStride = v.pixelStride
        val rowBytes = chromaWidth * 2

        for (row in 0 until chromaHeight) {
            readRow(u, uSrc, row, chromaWidth, rowA)
            readRow(v, vSrc, row, chromaWidth, rowB)
            var o = 0
            var iu = 0
            var iv = 0
            for (col in 0 until chromaWidth) {
                rowOut[o++] = rowA[iu]
                rowOut[o++] = rowB[iv]
                iu += uStride
                iv += vStride
            }
            out.put(rowOut, 0, rowBytes)
        }
    }

    private fun copyChromaPlanar(plane: YuvPlane, chromaWidth: Int, chromaHeight: Int, out: ByteBuffer) {
        val src = plane.buffer.duplicate()
        for (row in 0 until chromaHeight) {
            readRow(plane, src, row, chromaWidth, rowA)
            if (plane.pixelStride == 1) {
                out.put(rowA, 0, chromaWidth)
            } else {
                var i = 0
                for (col in 0 until chromaWidth) {
                    rowOut[col] = rowA[i]
                    i += plane.pixelStride
                }
                out.put(rowOut, 0, chromaWidth)
            }
        }
    }

    /**
     * Bulk-reads the bytes that cover [samples] samples of [row] into [dst].
     * The last row of a plane is often shorter than rowStride, so only read what is needed.
     */
    private fun readRow(plane: YuvPlane, src: ByteBuffer, row: Int, samples: Int, dst: ByteArray) {
        val start = row * plane.rowStride
        val length = (samples - 1) * plane.pixelStride + 1
        src.clear()
        src.position(start)
        src.get(dst, 0, length)
    }

    companion object {
        fun requiredSize(width: Int, height: Int): Int = width * height * 3 / 2
    }
}
