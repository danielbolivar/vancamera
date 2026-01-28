package com.vancamera.android

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.camera.view.PreviewView
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.launch

/**
 * Main activity for VanCamera Android.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var cameraManager: CameraManager
    private lateinit var h264Encoder: H264Encoder
    private lateinit var videoStreamer: VideoStreamer
    private lateinit var certificateManager: CertificateManager

    private var videoConfig: VideoConfig = VideoConfig.fromPreset(VideoPreset.PRESET_720P_30FPS)
    private var connectionConfig: ConnectionConfig = ConnectionConfig.default()
    private var isStreaming = false

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        if (isGranted) {
            initializeCamera()
        } else {
            Toast.makeText(this, "Camera permission is required", Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        certificateManager = CertificateManager(this)

        // Check permissions.
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            == PackageManager.PERMISSION_GRANTED) {
            initializeCamera()
        } else {
            requestPermissionLauncher.launch(Manifest.permission.CAMERA)
        }

        // Configure UI listeners.
        setupUI()
    }

    private fun setupUI() {
        findViewById<com.google.android.material.button.MaterialButton>(R.id.btnStream)
            .setOnClickListener {
                if (isStreaming) {
                    stopStreaming()
                } else {
                    startStreaming()
                }
            }

        findViewById<com.google.android.material.button.MaterialButton>(R.id.btnSettings)
            .setOnClickListener {
                // TODO: Abrir diálogo de configuración
                Toast.makeText(this, "Settings coming soon", Toast.LENGTH_SHORT).show()
            }
    }

    private fun initializeCamera() {
        lifecycleScope.launch {
            try {
                cameraManager = CameraManager(this@MainActivity, this@MainActivity)
                cameraManager.initialize(videoConfig)

                // Set callback to receive frames.
                cameraManager.setFrameCallback { imageProxy ->
                    if (isStreaming) {
                        // encodeFrame is a suspend function; run it in a coroutine.
                        lifecycleScope.launch {
                            h264Encoder.encodeFrame(imageProxy)
                        }
                    } else {
                        imageProxy.close()
                    }
                }
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity,
                    "Failed to initialize camera: ${e.message}",
                    Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun startStreaming() {
        lifecycleScope.launch {
            try {
                // Initialize encoder.
                h264Encoder = H264Encoder(videoConfig).apply {
                    initialize()
                    setEncodedFrameCallback { encodedData ->
                        lifecycleScope.launch {
                            videoStreamer.sendVideoData(encodedData)
                        }
                    }
                }

                // Initialize streamer.
                certificateManager = CertificateManager(this@MainActivity)
                videoStreamer = VideoStreamer(
                    this@MainActivity,
                    connectionConfig,
                    certificateManager
                )

                // Connect.
                videoStreamer.connect()

                isStreaming = true
                Toast.makeText(this@MainActivity, "Streaming started", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity,
                    "Failed to start streaming: ${e.message}",
                    Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun stopStreaming() {
        lifecycleScope.launch {
            try {
                h264Encoder.release()
                videoStreamer.disconnect()
                isStreaming = false
                Toast.makeText(this@MainActivity, "Streaming stopped", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity,
                    "Failed to stop streaming: ${e.message}",
                    Toast.LENGTH_LONG).show()
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        if (::cameraManager.isInitialized) {
            cameraManager.release()
        }
        if (::h264Encoder.isInitialized) {
            h264Encoder.release()
        }
        if (::videoStreamer.isInitialized) {
            lifecycleScope.launch {
                videoStreamer.disconnect()
            }
        }
    }
}
