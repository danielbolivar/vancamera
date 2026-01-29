package com.vancamera.android

import android.media.Image
import android.media.MediaCodec
import android.media.MediaCodecInfo
import android.media.MediaFormat
import android.util.Log
import androidx.camera.core.ImageProxy
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Codificador H.264 usando MediaCodec (hardware acceleration)
 */
class H264Encoder(private val config: VideoConfig) {

    companion object {
        private const val TAG = "H264Encoder"
        private const val MIME_TYPE = "video/avc" // H.264
        private const val TIMEOUT_USEC = 10000L // 10ms timeout
    }

    private var mediaCodec: MediaCodec? = null
    private val isRunning = AtomicBoolean(false)
    private var frameCallback: ((ByteArray) -> Unit)? = null

    // Store SPS/PPS codec config to prepend to keyframes
    private var codecConfigData: ByteArray? = null
    private var configSentWithFirstFrame = false

    /**
     * Inicializa el codificador MediaCodec
     */
    fun initialize() {
        try {
            val format = MediaFormat.createVideoFormat(MIME_TYPE, config.width, config.height)

            // Configurar parámetros de codificación
            // Usar COLOR_FormatYUV420SemiPlanar (NV12) que es común en Android
            format.setInteger(MediaFormat.KEY_COLOR_FORMAT, MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420SemiPlanar)
            format.setInteger(MediaFormat.KEY_BIT_RATE, config.bitrate)
            format.setInteger(MediaFormat.KEY_FRAME_RATE, config.fps)
            format.setInteger(MediaFormat.KEY_I_FRAME_INTERVAL, config.iFrameInterval)

            // === LOW LATENCY SETTINGS ===
            // Use Baseline profile - NO B-frames (B-frames cause seconds of decoder delay!)
            format.setInteger(MediaFormat.KEY_PROFILE, MediaCodecInfo.CodecProfileLevel.AVCProfileBaseline)
            format.setInteger(MediaFormat.KEY_LEVEL, MediaCodecInfo.CodecProfileLevel.AVCLevel31)

            // Explicitly disable B-frames
            format.setInteger(MediaFormat.KEY_MAX_B_FRAMES, 0)

            // CBR mode for consistent bitrate
            format.setInteger(MediaFormat.KEY_BITRATE_MODE, MediaCodecInfo.EncoderCapabilities.BITRATE_MODE_CBR)

            // Low latency flag (API 30+)
            if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
                format.setInteger(MediaFormat.KEY_LOW_LATENCY, 1)
            }

            // Real-time priority
            format.setInteger(MediaFormat.KEY_PRIORITY, 0) // 0 = realtime

            // Crear codificador
            mediaCodec = MediaCodec.createEncoderByType(MIME_TYPE)
            mediaCodec?.configure(format, null, null, MediaCodec.CONFIGURE_FLAG_ENCODE)
            mediaCodec?.start()

            isRunning.set(true)
            Log.d(TAG, "H264Encoder inicializado: ${config.width}x${config.height} @ ${config.fps}fps")
        } catch (e: Exception) {
            Log.e(TAG, "Error al inicializar H264Encoder: ${e.message}", e)
            throw EncoderException("Error al inicializar codificador: ${e.message}", e)
        }
    }

    /**
     * Codifica un frame de imagen desde ImageProxy
     * Convierte el formato YUV de CameraX a NV12 para MediaCodec
     */
    suspend fun encodeFrame(imageProxy: ImageProxy) = withContext(Dispatchers.IO) {
        if (!isRunning.get() || mediaCodec == null) {
            imageProxy.close()
            return@withContext
        }

        try {
            val image = imageProxy.image ?: return@withContext

            // Convertir Image YUV a formato NV12 (YUV420SemiPlanar)
            val nv12Data = convertYUV420ToNV12(image, config.width, config.height)

            // Codificar el frame convertido
            encodeFrameFromBytes(nv12Data, config.width, config.height)

        } catch (e: Exception) {
            Log.e(TAG, "Error al codificar frame: ${e.message}", e)
        } finally {
            imageProxy.close()
        }
    }

    /**
     * Convierte Image YUV420 a formato NV12 (YUV420SemiPlanar)
     */
    private fun convertYUV420ToNV12(image: Image, width: Int, height: Int): ByteArray {
        // IMPORTANT:
        // Do NOT use plane.buffer.remaining() sizes here. YUV_420_888 planes often include
        // row-stride padding, which would create a larger-than-expected array and then
        // overflow MediaCodec input buffers. NV12 must be tightly packed:
        // size = width * height * 3 / 2

        val yPlane = image.planes[0]
        val uPlane = image.planes[1]
        val vPlane = image.planes[2]

        val yBuffer = yPlane.buffer
        val uBuffer = uPlane.buffer
        val vBuffer = vPlane.buffer

        val outSize = width * height * 3 / 2
        val out = ByteArray(outSize)

        // Copy Y plane (luma): width bytes per row.
        val yRowStride = yPlane.rowStride
        var outIndex = 0
        for (row in 0 until height) {
            val yRowStart = row * yRowStride
            for (col in 0 until width) {
                out[outIndex++] = yBuffer.get(yRowStart + col)
            }
        }

        // Copy UV planes interleaved (NV12 = U then V), subsampled 2x2.
        val uRowStride = uPlane.rowStride
        val vRowStride = vPlane.rowStride
        val uPixelStride = uPlane.pixelStride
        val vPixelStride = vPlane.pixelStride

        val chromaHeight = height / 2
        val chromaWidth = width / 2

        for (row in 0 until chromaHeight) {
            val uRowStart = row * uRowStride
            val vRowStart = row * vRowStride
            for (col in 0 until chromaWidth) {
                val uIndex = uRowStart + col * uPixelStride
                val vIndex = vRowStart + col * vPixelStride
                out[outIndex++] = uBuffer.get(uIndex)
                out[outIndex++] = vBuffer.get(vIndex)
            }
        }

        return out
    }

    /**
     * Codifica un frame desde un array de bytes (formato NV21/YUV)
     */
    suspend fun encodeFrameFromBytes(frameData: ByteArray, width: Int, height: Int) = withContext(Dispatchers.IO) {
        if (!isRunning.get() || mediaCodec == null) {
            return@withContext
        }

        try {
            val inputBufferIndex = mediaCodec?.dequeueInputBuffer(TIMEOUT_USEC) ?: -1
            if (inputBufferIndex >= 0) {
                val inputBuffer = mediaCodec?.getInputBuffer(inputBufferIndex)
                inputBuffer?.let { buffer ->
                    buffer.clear()
                    // Guard against BufferOverflowException if encoder input buffers are smaller.
                    if (frameData.size > buffer.capacity()) {
                        Log.e(
                            TAG,
                            "Frame too large for encoder input buffer. " +
                                "frameSize=${frameData.size}, capacity=${buffer.capacity()}, " +
                                "w=$width, h=$height"
                        )
                        mediaCodec?.queueInputBuffer(inputBufferIndex, 0, 0, 0, 0)
                        return@withContext
                    }
                    buffer.put(frameData)

                    val presentationTimeUs = System.nanoTime() / 1000
                    mediaCodec?.queueInputBuffer(
                        inputBufferIndex,
                        0,
                        frameData.size,
                        presentationTimeUs,
                        0
                    )
                }
            }

            // Get encoded data
            val bufferInfo = MediaCodec.BufferInfo()
            var outputBufferIndex = mediaCodec?.dequeueOutputBuffer(bufferInfo, TIMEOUT_USEC) ?: -1

            while (outputBufferIndex >= 0) {
                val outputBuffer = mediaCodec?.getOutputBuffer(outputBufferIndex)
                outputBuffer?.let { buffer ->
                    val data = ByteArray(bufferInfo.size)
                    buffer.get(data)

                    // Check if this is codec config data (SPS/PPS)
                    if ((bufferInfo.flags and MediaCodec.BUFFER_FLAG_CODEC_CONFIG) != 0) {
                        // Store SPS/PPS for later use
                        codecConfigData = data.copyOf()
                        Log.d(TAG, "Received codec config (SPS/PPS): ${data.size} bytes")
                        // Don't send config data alone - it will be prepended to keyframes
                    } else {
                        // Regular frame data
                        val isKeyFrame = (bufferInfo.flags and MediaCodec.BUFFER_FLAG_KEY_FRAME) != 0

                        // Prepend SPS/PPS to keyframes (or first frame) so decoder can initialize
                        val outputData = if ((isKeyFrame || !configSentWithFirstFrame) && codecConfigData != null) {
                            configSentWithFirstFrame = true
                            Log.d(TAG, "Prepending SPS/PPS to ${if (isKeyFrame) "keyframe" else "first frame"}")
                            codecConfigData!! + data
                        } else {
                            data
                        }

                        frameCallback?.invoke(outputData)
                    }

                    mediaCodec?.releaseOutputBuffer(outputBufferIndex, false)
                }

                outputBufferIndex = mediaCodec?.dequeueOutputBuffer(bufferInfo, TIMEOUT_USEC) ?: -1
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error al codificar frame desde bytes: ${e.message}", e)
        }
    }

    /**
     * Establece el callback para recibir datos codificados
     */
    fun setEncodedFrameCallback(callback: (ByteArray) -> Unit) {
        frameCallback = callback
    }

    /**
     * Libera los recursos del codificador
     */
    fun release() {
        isRunning.set(false)
        try {
            mediaCodec?.stop()
            mediaCodec?.release()
            mediaCodec = null
            codecConfigData = null
            configSentWithFirstFrame = false
            Log.d(TAG, "H264Encoder released")
        } catch (e: Exception) {
            Log.e(TAG, "Error releasing H264Encoder: ${e.message}", e)
        }
    }

    /**
     * Verifica si el codificador está inicializado y funcionando
     */
    fun isInitialized(): Boolean {
        return mediaCodec != null && isRunning.get()
    }
}

/**
 * Excepción personalizada para errores de codificación
 */
class EncoderException(message: String, cause: Throwable? = null) : Exception(message, cause)
