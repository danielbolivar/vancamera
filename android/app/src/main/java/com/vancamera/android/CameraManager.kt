package com.vancamera.android

import android.content.Context
import android.util.Size
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import kotlinx.coroutines.tasks.await
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/**
 * Gestor de captura de video usando CameraX
 */
class CameraManager(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner
) {
    private var camera: Camera? = null
    private var cameraProvider: ProcessCameraProvider? = null
    private var imageAnalysis: ImageAnalysis? = null
    private val cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    private var frameCallback: ((ImageProxy) -> Unit)? = null
    private var videoConfig: VideoConfig? = null

    /**
     * Inicializa la cámara con la configuración especificada
     */
    suspend fun initialize(config: VideoConfig) {
        videoConfig = config

        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
        cameraProvider = cameraProviderFuture.await()

        val cameraSelector = CameraSelector.DEFAULT_BACK_CAMERA

        // Configurar análisis de imagen para obtener frames
        imageAnalysis = ImageAnalysis.Builder()
            .setTargetResolution(config.resolution)
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
            .also {
                it.setAnalyzer(cameraExecutor) { imageProxy ->
                    frameCallback?.invoke(imageProxy)
                }
            }

        // Configurar preview (opcional, para mostrar en UI)
        val preview = Preview.Builder()
            .setTargetResolution(config.resolution)
            .build()

        try {
            // Desvincular todos los casos de uso antes de volver a vincular
            cameraProvider?.unbindAll()

            // Vincular casos de uso a ciclo de vida
            camera = cameraProvider?.bindToLifecycle(
                lifecycleOwner,
                cameraSelector,
                preview,
                imageAnalysis
            )
        } catch (e: Exception) {
            throw CameraException("Error al inicializar la cámara: ${e.message}", e)
        }
    }

    /**
     * Establece el callback para recibir frames de video
     */
    fun setFrameCallback(callback: (ImageProxy) -> Unit) {
        frameCallback = callback
    }

    /**
     * Obtiene las resoluciones disponibles para la cámara
     * Retorna resoluciones comunes soportadas
     */
    suspend fun getAvailableResolutions(): List<Size> {
        // Resoluciones comunes soportadas por la mayoría de dispositivos
        return listOf(
            Size(1280, 720),   // 720p
            Size(1920, 1080),  // 1080p
            Size(640, 480),    // 480p (fallback)
            Size(3840, 2160)   // 4K (si está disponible)
        )
    }

    /**
     * Cambia entre cámara frontal y trasera
     */
    suspend fun switchCamera() {
        val currentSelector = if (camera?.cameraInfo?.lensFacing == CameraSelector.LENS_FACING_BACK) {
            CameraSelector.DEFAULT_FRONT_CAMERA
        } else {
            CameraSelector.DEFAULT_BACK_CAMERA
        }

        val config = videoConfig ?: return
        cameraProvider?.unbindAll()

        val imageAnalysis = ImageAnalysis.Builder()
            .setTargetResolution(config.resolution)
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
            .also {
                it.setAnalyzer(cameraExecutor) { imageProxy ->
                    frameCallback?.invoke(imageProxy)
                }
            }

        camera = cameraProvider?.bindToLifecycle(
            lifecycleOwner,
            currentSelector,
            imageAnalysis
        )
    }

    /**
     * Obtiene el preview use case para mostrar en la UI
     */
    fun getPreviewUseCase(): Preview? {
        return null // Se maneja internamente
    }

    /**
     * Libera los recursos de la cámara
     */
    fun release() {
        frameCallback = null
        cameraProvider?.unbindAll()
        camera = null
        imageAnalysis = null
        cameraExecutor.shutdown()
    }

    /**
     * Verifica si la cámara está inicializada
     */
    fun isInitialized(): Boolean {
        return camera != null && cameraProvider != null
    }

    /**
     * Obtiene la configuración actual de video
     */
    fun getCurrentConfig(): VideoConfig? {
        return videoConfig
    }
}

/**
 * Excepción personalizada para errores de cámara
 */
class CameraException(message: String, cause: Throwable? = null) : Exception(message, cause)
