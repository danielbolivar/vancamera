package com.vancamera.android

import android.Manifest
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.os.Bundle
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.camera.view.PreviewView
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.drop
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
    private var previewView: PreviewView? = null
    private var connectionObserverJob: Job? = null

    private lateinit var statusText: android.widget.TextView
    private lateinit var streamButton: com.google.android.material.button.MaterialButton

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
        previewView = findViewById(R.id.previewView)
        statusText = findViewById(R.id.tvStatus)
        streamButton = findViewById(R.id.btnStream)

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
        streamButton.setOnClickListener {
            if (isStreaming) stopStreaming() else startStreaming()
        }

        findViewById<com.google.android.material.button.MaterialButton>(R.id.btnFlipCamera)
            .setOnClickListener {
                lifecycleScope.launch {
                    try {
                        if (::cameraManager.isInitialized) {
                            cameraManager.switchCamera()
                        }
                    } catch (e: Exception) {
                        Toast.makeText(this@MainActivity, "Failed to switch camera: ${e.message}", Toast.LENGTH_SHORT).show()
                    }
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
                cameraManager.initialize(videoConfig, previewView)

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
                // Update UI immediately: we are starting / listening.
                isStreaming = true
                streamButton.text = "Stop streaming"
                statusText.text = "Listening..."

                // Adjust encoder config based on current orientation.
                val currentOrientation = resources.configuration.orientation
                val basePreset = VideoConfig.fromPreset(VideoPreset.PRESET_720P_30FPS)
                videoConfig = if (currentOrientation == Configuration.ORIENTATION_PORTRAIT) {
                    VideoConfig(
                        width = basePreset.height,
                        height = basePreset.width,
                        fps = basePreset.fps,
                        bitrate = basePreset.bitrate,
                        iFrameInterval = basePreset.iFrameInterval
                    )
                } else {
                    basePreset
                }

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

                // Connect (blocks until client connects).
                videoStreamer.connect()

                // NOW that we are connected, set up the observer to detect disconnection.
                // Use drop(1) to skip the current value and only react to CHANGES.
                connectionObserverJob?.cancel()
                connectionObserverJob = lifecycleScope.launch {
                    videoStreamer.getConnectionState()
                        .drop(1)  // Skip initial value, only react to changes
                        .collectLatest { connected ->
                            if (!connected && isStreaming) {
                                // Connection was lost while streaming.
                                runOnUiThread {
                                    isStreaming = false
                                    streamButton.text = "Start streaming"
                                    statusText.text = "Disconnected"
                                    Toast.makeText(
                                        this@MainActivity,
                                        "Connection lost",
                                        Toast.LENGTH_SHORT
                                    ).show()
                                }
                            }
                        }
                }

                statusText.text = "Connected"
                Toast.makeText(this@MainActivity, "Streaming started", Toast.LENGTH_SHORT).show()
            } catch (e: Exception) {
                isStreaming = false
                connectionObserverJob?.cancel()
                streamButton.text = "Start streaming"
                statusText.text = "Disconnected"
                Toast.makeText(this@MainActivity,
                    "Failed to start streaming: ${e.message}",
                    Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun stopStreaming() {
        lifecycleScope.launch {
            try {
                connectionObserverJob?.cancel()
                connectionObserverJob = null
                if (::h264Encoder.isInitialized) {
                    h264Encoder.release()
                }
                if (::videoStreamer.isInitialized) {
                    videoStreamer.disconnect()
                }
                isStreaming = false
                streamButton.text = "Start streaming"
                statusText.text = "Disconnected"
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
