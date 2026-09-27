package com.vancamera.android

import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import androidx.camera.core.ImageProxy
import java.util.concurrent.ConcurrentLinkedQueue

/** One encoded access unit ready to be sent. SPS/PPS are already prepended to keyframes. */
class EncodedFrame(val data: ByteArray, val isKeyFrame: Boolean)

/**
 * Hardware H.264 encoder (MediaCodec) running in asynchronous mode.
 *
 * Compared to the previous implementation:
 * - frames are fed synchronously from the camera thread (no coroutine per frame, no concurrent
 *   access to the codec, frames can no longer be encoded out of order);
 * - if the encoder has no free input buffer the camera frame is dropped instead of blocking the
 *   camera pipeline;
 * - output is delivered as soon as it is ready through [MediaCodec.Callback] instead of being
 *   polled with timeouts after each input frame (lower latency, less CPU);
 * - YUV data is written straight into the codec's input buffer with bulk row copies.
 *
 * The encoder is sized from the actual camera frames, so it always matches what CameraX delivers.
 */
class H264Encoder(
    val width: Int,
    val height: Int,
    private val fps: Int,
    private val bitrate: Int,
    private val iFrameIntervalSec: Int,
    private val onFrame: (EncodedFrame) -> Unit
) {

    companion object {
        private const val TAG = "H264Encoder"
        private const val MIME_TYPE = MediaFormat.MIMETYPE_VIDEO_AVC
        private const val COLOR_FORMAT_FLEXIBLE = MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible
    }

    private val lock = Any()
    private var codec: MediaCodec? = null
    private var callbackThread: HandlerThread? = null
    private val freeInputBuffers = ConcurrentLinkedQueue<Int>()
    private val converter = YuvConverter()
    private var layout = YuvLayout.NV12
    private var codecConfig: ByteArray? = null

    @Volatile
    var isFailed = false
        private set

    /** Frames dropped because the encoder was still busy with previous ones. */
    @Volatile
    var droppedInputFrames = 0L
        private set

    fun start() {
        val thread = HandlerThread("vancamera-encoder").also { it.start() }
        callbackThread = thread

        val mediaCodec = MediaCodec.createEncoderByType(MIME_TYPE)
        try {
            val capabilities = mediaCodec.codecInfo.getCapabilitiesForType(MIME_TYPE)
            val colorFormat = pickColorFormat(capabilities.colorFormats)
            layout = if (colorFormat == MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Planar) {
                YuvLayout.I420
            } else {
                YuvLayout.NV12
            }

            mediaCodec.setCallback(EncoderCallback(), Handler(thread.looper))

            val cbrSupported = capabilities.encoderCapabilities
                ?.isBitrateModeSupported(MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR) == true

            // Some encoders reject explicit profile/level keys: retry without them.
            try {
                mediaCodec.configure(buildFormat(colorFormat, cbrSupported, withProfile = true), null, null,
                    MediaCodec.CONFIGURE_FLAG_ENCODE)
            } catch (e: Exception) {
                Log.w(TAG, "Encoder rejected profile/level, retrying with defaults: ${e.message}")
                mediaCodec.reset()
                mediaCodec.setCallback(EncoderCallback(), Handler(thread.looper))
                mediaCodec.configure(buildFormat(colorFormat, cbrSupported, withProfile = false), null, null,
                    MediaCodec.CONFIGURE_FLAG_ENCODE)
            }
            mediaCodec.start()
        } catch (e: Exception) {
            mediaCodec.release()
            thread.quitSafely()
            callbackThread = null
            throw EncoderException("Failed to start H.264 encoder: ${e.message}", e)
        }

        codec = mediaCodec
        Log.i(TAG, "Encoder started: ${width}x$height @ ${fps}fps, ${bitrate / 1000} kbps, layout=$layout")
    }

    private fun pickColorFormat(formats: IntArray): Int = when {
        formats.contains(MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420SemiPlanar) ->
            MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420SemiPlanar
        formats.contains(MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Planar) ->
            MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Planar
        // Flexible encoders on Android accept NV12 in byte-buffer mode in practice.
        else -> COLOR_FORMAT_FLEXIBLE
    }

    private fun buildFormat(colorFormat: Int, cbr: Boolean, withProfile: Boolean): MediaFormat =
        MediaFormat.createVideoFormat(MIME_TYPE, width, height).apply {
            setInteger(MediaFormat.KEY_COLOR_FORMAT, colorFormat)
            setInteger(MediaFormat.KEY_BIT_RATE, bitrate)
            setInteger(MediaFormat.KEY_FRAME_RATE, fps)
            setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, iFrameIntervalSec)

            // === LOW LATENCY SETTINGS ===
            // Baseline profile: no B-frames (B-frames add decoder delay on the PC).
            if (withProfile) {
                setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline)
                setInteger(MediaFormat.KEY_LEVEL, MediaCodecInfo.CodecProfileLevel.AVCLevel31)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                setInteger(MediaFormat.KEY_MAX_B_FRAMES, 0)
            }
            if (cbr) {
                setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR)
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                setInteger(MediaFormat.KEY_LOW_LATENCY, 1)
            }
            // Realtime priority, at the configured frame rate only (lets the encoder clock down).
            setInteger(MediaFormat.KEY_PRIORITY, 0)
        }

    /**
     * Encodes one camera frame. Must be called from a single thread (the camera analyzer).
     * The [image] is NOT closed here.
     *
     * @return false if the frame was dropped because the encoder is busy.
     */
    fun encode(image: ImageProxy): Boolean {
        val index = freeInputBuffers.poll()
        if (index == null) {
            droppedInputFrames++
            return false
        }
        synchronized(lock) {
            val mediaCodec = codec ?: return false
            try {
                val buffer = mediaCodec.getInputBuffer(index) ?: return false
                buffer.clear()
                val planes = image.planes
                converter.convert(
                    YuvPlane(planes[0].buffer, planes[0].rowStride, planes[0].pixelStride),
                    YuvPlane(planes[1].buffer, planes[1].rowStride, planes[1].pixelStride),
                    YuvPlane(planes[2].buffer, planes[2].rowStride, planes[2].pixelStride),
                    width,
                    height,
                    layout,
                    buffer
                )
                val ptsUs = image.imageInfo.timestamp / 1000
                mediaCodec.queueInputBuffer(index, 0, YuvConverter.requiredSize(width, height), ptsUs, 0)
                return true
            } catch (e: Exception) {
                Log.e(TAG, "Failed to queue frame: ${e.message}")
                // Give the buffer back so the encoder does not starve.
                try {
                    mediaCodec.queueInputBuffer(index, 0, 0, 0, 0)
                } catch (_: Exception) {
                }
                return false
            }
        }
    }

    /** Asks the encoder for an IDR frame as soon as possible (after network drops). */
    fun requestKeyFrame() {
        synchronized(lock) {
            try {
                codec?.setParameters(Bundle().apply {
                    putInt(MediaCodec.PARAMETER_KEY_REQUEST_SYNC_FRAME, 0)
                })
            } catch (e: Exception) {
                Log.w(TAG, "Keyframe request failed: ${e.message}")
            }
        }
    }

    fun release() {
        synchronized(lock) {
            val mediaCodec = codec
            codec = null
            try {
                mediaCodec?.stop()
            } catch (_: Exception) {
            }
            try {
                mediaCodec?.release()
            } catch (_: Exception) {
            }
            freeInputBuffers.clear()
            codecConfig = null
        }
        callbackThread?.quitSafely()
        callbackThread = null
        Log.d(TAG, "Encoder released")
    }

    private inner class EncoderCallback : MediaCodec.Callback() {
        override fun onInputBufferAvailable(codec: MediaCodec, index: Int) {
            freeInputBuffers.offer(index)
        }

        override fun onOutputBufferAvailable(codec: MediaCodec, index: Int, info: MediaCodec.BufferInfo) {
            val frame: EncodedFrame?
            synchronized(lock) {
                if (this@H264Encoder.codec !== codec) return
                frame = try {
                    readOutput(codec, index, info)
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to read encoder output: ${e.message}")
                    null
                } finally {
                    try {
                        codec.releaseOutputBuffer(index, false)
                    } catch (_: Exception) {
                    }
                }
            }
            frame?.let(onFrame)
        }

        override fun onError(codec: MediaCodec, e: MediaCodec.CodecException) {
            Log.e(TAG, "Encoder error: ${e.diagnosticInfo}", e)
            isFailed = true
        }

        override fun onOutputFormatChanged(codec: MediaCodec, format: MediaFormat) {
            // Some encoders only expose SPS/PPS through the output format.
            if (codecConfig == null) {
                val sps = format.getByteBuffer("csd-0")
                val pps = format.getByteBuffer("csd-1")
                if (sps != null && pps != null) {
                    val config = ByteArray(sps.remaining() + pps.remaining())
                    sps.get(config, 0, sps.remaining())
                    pps.get(config, config.size - pps.remaining(), pps.remaining())
                    codecConfig = config
                }
            }
        }
    }

    private fun readOutput(codec: MediaCodec, index: Int, info: MediaCodec.BufferInfo): EncodedFrame? {
        if (info.size <= 0) return null
        val buffer = codec.getOutputBuffer(index) ?: return null
        buffer.position(info.offset)
        buffer.limit(info.offset + info.size)

        if ((info.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) {
            // SPS/PPS: keep them and prepend them to every keyframe so the PC decoder can
            // (re)start from any keyframe, e.g. after a reconnect or dropped frames.
            codecConfig = ByteArray(info.size).also { buffer.get(it) }
            return null
        }

        val isKeyFrame = (info.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0
        val config = codecConfig
        val data = if (isKeyFrame && config != null) {
            ByteArray(config.size + info.size).also {
                System.arraycopy(config, 0, it, 0, config.size)
                buffer.get(it, config.size, info.size)
            }
        } else {
            ByteArray(info.size).also { buffer.get(it) }
        }
        return EncodedFrame(data, isKeyFrame)
    }
}

class EncoderException(message: String, cause: Throwable? = null) : Exception(message, cause)
