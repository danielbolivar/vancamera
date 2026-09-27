package com.vancamera.android

import android.annotation.SuppressLint
import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CaptureRequest
import android.util.Log
import android.util.Range
import android.util.Size
import androidx.camera.camera2.interop.Camera2CameraInfo
import androidx.camera.camera2.interop.Camera2Interop
import androidx.camera.camera2.interop.ExperimentalCamera2Interop
import androidx.camera.core.AspectRatio
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.UseCase
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.core.resolutionselector.ResolutionStrategy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.google.common.util.concurrent.ListenableFuture
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.Executor
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Camera capture manager using CameraX.
 *
 * Only binds the use cases that are actually needed:
 * - ImageAnalysis (frames for the encoder) only while a PC is connected;
 * - Preview only while the app is visible and the preview is enabled.
 * With neither, the camera is closed completely. Keeping the camera and ISP idle while nobody is
 * watching is one of the biggest battery/heat savings.
 *
 * All methods must be called on the main thread.
 */
class CameraManager(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private var targetSize: Size,
    private var targetFps: Int
) {
    companion object {
        private const val TAG = "CameraManager"
    }

    private var cameraProvider: ProcessCameraProvider? = null
    private val cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor { r ->
        Thread(r, "vancamera-camera")
    }

    private var analyzer: ((ImageProxy) -> Unit)? = null
    private var previewSurfaceProvider: Preview.SurfaceProvider? = null
    @Volatile
    private var lensFacing: Int = CameraSelector.LENS_FACING_BACK
    private var boundUseCases: List<UseCase> = emptyList()

    val isFrontCamera: Boolean get() = lensFacing == CameraSelector.LENS_FACING_FRONT

    suspend fun initialize() {
        if (cameraProvider != null) return
        cameraProvider = ProcessCameraProvider.getInstance(context)
            .await(ContextCompat.getMainExecutor(context))
        // Fall back to the front camera on devices without a back camera.
        if (!hasCamera(lensFacing)) {
            lensFacing = CameraSelector.LENS_FACING_FRONT
        }
    }

    /** Starts (or stops, with null) delivering frames to [analyzer] on the camera thread. */
    fun setAnalyzer(analyzer: ((ImageProxy) -> Unit)?) {
        if (this.analyzer === analyzer) return
        this.analyzer = analyzer
        rebind()
    }

    /** Shows the camera preview on [provider], or stops the preview with null. */
    fun setPreviewSurfaceProvider(provider: Preview.SurfaceProvider?) {
        if (previewSurfaceProvider === provider) return
        previewSurfaceProvider = provider
        rebind()
    }

    /** Changes the capture size and frame rate (stream quality preset). */
    fun setStreamFormat(size: Size, fps: Int) {
        if (size == targetSize && fps == targetFps) return
        targetSize = size
        targetFps = fps
        rebind()
    }

    /** Highest auto-exposure frame rate the current camera supports (30 if unknown). */
    @SuppressLint("UnsafeOptInUsageError")
    @androidx.annotation.OptIn(ExperimentalCamera2Interop::class)
    fun maxSupportedFps(): Int = try {
        val provider = cameraProvider
        val selector = CameraSelector.Builder().requireLensFacing(lensFacing).build()
        provider?.let { selector.filter(it.availableCameraInfos).firstOrNull() }
            ?.let { Camera2CameraInfo.from(it).getCameraCharacteristic(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES) }
            ?.maxOfOrNull { it.upper } ?: 30
    } catch (e: Exception) {
        30
    }

    /** Switches between front and back cameras. */
    fun switchCamera() {
        val next = if (lensFacing == CameraSelector.LENS_FACING_BACK) {
            CameraSelector.LENS_FACING_FRONT
        } else {
            CameraSelector.LENS_FACING_BACK
        }
        if (!hasCamera(next)) return
        lensFacing = next
        rebind()
    }

    private fun hasCamera(facing: Int): Boolean = try {
        cameraProvider?.hasCamera(CameraSelector.Builder().requireLensFacing(facing).build()) == true
    } catch (_: Exception) {
        false
    }

    private fun rebind() {
        val provider = cameraProvider ?: return
        val useCases = mutableListOf<UseCase>()
        val selector = CameraSelector.Builder().requireLensFacing(lensFacing).build()
        val fpsRange = selectFpsRange(provider, selector)

        // Ask for the stream size we encode (720p/1080p) instead of the largest 16:9 size: the old
        // selector could make the camera produce 1080p/4K YUV frames just to crop them.
        val resolutionSelector = ResolutionSelector.Builder()
            .setAspectRatioStrategy(
                AspectRatioStrategy(AspectRatio.RATIO_16_9, AspectRatioStrategy.FALLBACK_RULE_AUTO)
            )
            .setResolutionStrategy(
                ResolutionStrategy(targetSize, ResolutionStrategy.FALLBACK_RULE_CLOSEST_HIGHER_THEN_LOWER)
            )
            .build()

        previewSurfaceProvider?.let { surfaceProvider ->
            val builder = Preview.Builder().setResolutionSelector(resolutionSelector)
            applyFpsRange(builder, fpsRange)
            useCases += builder.build().also { it.setSurfaceProvider(surfaceProvider) }
        }

        analyzer?.let { callback ->
            val builder = ImageAnalysis.Builder()
                .setResolutionSelector(resolutionSelector)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_YUV_420_888)
            applyFpsRange(builder, fpsRange)
            useCases += builder.build().also { it.setAnalyzer(cameraExecutor, callback) }
        }

        try {
            provider.unbindAll()
            boundUseCases = emptyList()
            if (useCases.isNotEmpty()) {
                provider.bindToLifecycle(lifecycleOwner, selector, *useCases.toTypedArray())
                boundUseCases = useCases
            }
            Log.d(TAG, "Camera bound: preview=${previewSurfaceProvider != null} analysis=${analyzer != null} fps=$fpsRange")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to bind camera: ${e.message}", e)
            throw CameraException("Failed to start camera: ${e.message}", e)
        }
    }

    @SuppressLint("UnsafeOptInUsageError")
    @androidx.annotation.OptIn(ExperimentalCamera2Interop::class)
    private fun selectFpsRange(provider: ProcessCameraProvider, selector: CameraSelector): Range<Int>? = try {
        val info = selector.filter(provider.availableCameraInfos).firstOrNull()
        val ranges = info?.let {
            Camera2CameraInfo.from(it)
                .getCameraCharacteristic(CameraCharacteristics.CONTROL_AE_AVAILABLE_TARGET_FPS_RANGES)
        }
        ranges?.map { it.lower to it.upper }
            ?.let { FpsRangeSelector.select(it, targetFps) }
            ?.let { Range(it.first, it.second) }
    } catch (e: Exception) {
        Log.w(TAG, "Could not query FPS ranges: ${e.message}")
        null
    }

    @SuppressLint("UnsafeOptInUsageError")
    @androidx.annotation.OptIn(ExperimentalCamera2Interop::class)
    private fun <T> applyFpsRange(builder: androidx.camera.core.ExtendableBuilder<T>, range: Range<Int>?) {
        if (range == null) return
        Camera2Interop.Extender(builder)
            .setCaptureRequestOption(CaptureRequest.CONTROL_AE_TARGET_FPS_RANGE, range)
    }

    /** Releases camera resources. */
    fun release() {
        analyzer = null
        previewSurfaceProvider = null
        try {
            cameraProvider?.unbindAll()
        } catch (_: Exception) {
        }
        boundUseCases = emptyList()
        cameraExecutor.shutdown()
    }
}

private suspend fun <T> ListenableFuture<T>.await(executor: Executor): T =
    suspendCancellableCoroutine { cont ->
        addListener(
            {
                try {
                    cont.resume(get())
                } catch (t: Throwable) {
                    cont.resumeWithException(t)
                }
            },
            executor
        )

        cont.invokeOnCancellation {
            cancel(true)
        }
    }

/**
 * Custom exception for camera errors.
 */
class CameraException(message: String, cause: Throwable? = null) : Exception(message, cause)
