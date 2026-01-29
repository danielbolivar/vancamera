package com.vancamera.android

import android.content.Context
import android.util.Size
import android.view.Surface
import androidx.camera.core.AspectRatio
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.google.common.util.concurrent.ListenableFuture
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.Executor
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Camera capture manager using CameraX.
 */
class CameraManager(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner
) {
    private var camera: Camera? = null
    private var cameraProvider: ProcessCameraProvider? = null
    private var imageAnalysis: ImageAnalysis? = null
    private var preview: Preview? = null
    private val cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    private var frameCallback: ((ImageProxy) -> Unit)? = null
    private var videoConfig: VideoConfig? = null
    private var lensFacing: Int = CameraSelector.LENS_FACING_BACK
    private var boundPreviewView: PreviewView? = null

    /**
     * Initializes the camera with the provided configuration.
     */
    suspend fun initialize(config: VideoConfig, previewView: PreviewView? = null) {
        videoConfig = config
        boundPreviewView = previewView

        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
        cameraProvider = cameraProviderFuture.await(ContextCompat.getMainExecutor(context))

        val cameraSelector = CameraSelector.Builder()
            .requireLensFacing(lensFacing)
            .build()

        val targetRotation = previewView?.display?.rotation ?: Surface.ROTATION_0

        // Use ResolutionSelector with 16:9 aspect ratio to get full field of view
        // without excessive cropping. This matches the encoder's expected aspect ratio.
        val resolutionSelector = ResolutionSelector.Builder()
            .setAspectRatioStrategy(
                AspectRatioStrategy(
                    AspectRatio.RATIO_16_9,
                    AspectRatioStrategy.FALLBACK_RULE_AUTO
                )
            )
            .build()

        // Configure image analysis to receive frames.
        imageAnalysis = ImageAnalysis.Builder()
            .setResolutionSelector(resolutionSelector)
            .setTargetRotation(targetRotation)
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
            .also {
                it.setAnalyzer(cameraExecutor) { imageProxy ->
                    frameCallback?.invoke(imageProxy)
                }
            }

        // Configure preview (optional; for displaying in UI).
        preview = Preview.Builder()
            .setResolutionSelector(resolutionSelector)
            .setTargetRotation(targetRotation)
            .build()
            .also { p ->
                previewView?.surfaceProvider?.let { provider ->
                    p.setSurfaceProvider(provider)
                }
            }

        try {
            // Unbind all use cases before rebinding.
            cameraProvider?.unbindAll()

            // Bind use cases to lifecycle.
            camera = cameraProvider?.bindToLifecycle(
                lifecycleOwner,
                cameraSelector,
                preview,
                imageAnalysis
            )
        } catch (e: Exception) {
            throw CameraException("Failed to initialize camera: ${e.message}", e)
        }
    }

    /**
     * Sets the callback to receive video frames.
     */
    fun setFrameCallback(callback: (ImageProxy) -> Unit) {
        frameCallback = callback
    }

    /**
     * Returns common supported camera resolutions.
     */
    suspend fun getAvailableResolutions(): List<Size> {
        return listOf(
            Size(1280, 720),   // 720p
            Size(1920, 1080),  // 1080p
            Size(640, 480),    // 480p (fallback)
            Size(3840, 2160)   // 4K (si está disponible)
        )
    }

    /**
     * Switches between front and back cameras.
     */
    suspend fun switchCamera() {
        lensFacing = if (lensFacing == CameraSelector.LENS_FACING_BACK) {
            CameraSelector.LENS_FACING_FRONT
        } else {
            CameraSelector.LENS_FACING_BACK
        }

        val config = videoConfig ?: return
        val pv = boundPreviewView
        initialize(config, pv)
    }

    /**
     * Returns the preview use case (if exposed).
     */
    fun getPreviewUseCase(): Preview? {
        return preview
    }

    /**
     * Releases camera resources.
     */
    fun release() {
        frameCallback = null
        cameraProvider?.unbindAll()
        camera = null
        imageAnalysis = null
        cameraExecutor.shutdown()
    }

    /**
     * Returns whether the camera is initialized.
     */
    fun isInitialized(): Boolean {
        return camera != null && cameraProvider != null
    }

    /**
     * Returns the current video configuration.
     */
    fun getCurrentConfig(): VideoConfig? {
        return videoConfig
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
