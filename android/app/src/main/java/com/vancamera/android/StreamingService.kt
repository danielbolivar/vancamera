package com.vancamera.android

import android.app.Service
import android.content.Intent
import android.os.IBinder
import android.util.Log
import androidx.camera.core.ImageProxy
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Servicio en background para mantener la transmisión activa
 */
class StreamingService : Service() {

    companion object {
        private const val TAG = "StreamingService"
    }

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var cameraManager: CameraManager? = null
    private var h264Encoder: H264Encoder? = null
    private var videoStreamer: VideoStreamer? = null
    private var videoConfig: VideoConfig? = null
    private var connectionConfig: ConnectionConfig? = null

    override fun onBind(intent: Intent?): IBinder? {
        return null
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            "START_STREAMING" -> {
                val config = intent.getParcelableExtra<VideoConfig>("video_config")
                val connConfig = intent.getParcelableExtra<ConnectionConfig>("connection_config")
                if (config != null && connConfig != null) {
                    startStreaming(config, connConfig)
                }
            }
            "STOP_STREAMING" -> {
                stopStreaming()
            }
        }
        return START_NOT_STICKY
    }

    private fun startStreaming(config: VideoConfig, connConfig: ConnectionConfig) {
        serviceScope.launch {
            try {
                videoConfig = config
                connectionConfig = connConfig

                // Inicializar componentes
                val certificateManager = CertificateManager(applicationContext)
                videoStreamer = VideoStreamer(applicationContext, connConfig, certificateManager)

                h264Encoder = H264Encoder(config).apply {
                    initialize()
                    setEncodedFrameCallback { encodedData ->
                        serviceScope.launch(Dispatchers.IO) {
                            videoStreamer?.sendVideoData(encodedData)
                        }
                    }
                }

                // Conectar al servidor
                videoStreamer?.connect()

                Log.d(TAG, "Streaming iniciado")
            } catch (e: Exception) {
                Log.e(TAG, "Error al iniciar streaming: ${e.message}", e)
            }
        }
    }

    private fun stopStreaming() {
        serviceScope.launch {
            try {
                h264Encoder?.release()
                videoStreamer?.disconnect()
                cameraManager?.release()

                h264Encoder = null
                videoStreamer = null
                cameraManager = null

                Log.d(TAG, "Streaming detenido")
                stopSelf()
            } catch (e: Exception) {
                Log.e(TAG, "Error al detener streaming: ${e.message}", e)
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        stopStreaming()
    }
}
