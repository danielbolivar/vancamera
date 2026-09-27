package com.vancamera.android

import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.hardware.SensorManager
import android.net.wifi.WifiManager
import android.os.Binder
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import android.view.OrientationEventListener
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Owns the camera, the H.264 encoder and the TLS server.
 *
 * - While the app is visible it is bound by [MainActivity] and drives the camera preview.
 * - When the user starts streaming it becomes a *camera foreground service*: streaming continues
 *   with the screen off (issue #4) and after the app is closed or swiped away from recents. A
 *   persistent notification shows the state and has Stop / Switch camera actions.
 *
 * Power: the camera only runs while a PC is connected or the preview is on screen, the encoder
 * only exists while a PC is connected, and wake/Wi-Fi locks are only held while streaming.
 */
class StreamingService : LifecycleService() {

    companion object {
        private const val TAG = "StreamingService"

        const val ACTION_START = "com.vancamera.android.action.START"
        const val ACTION_STOP = "com.vancamera.android.action.STOP"
        const val ACTION_SWITCH_CAMERA = "com.vancamera.android.action.SWITCH_CAMERA"

        private const val CHANNEL_ID = "streaming"
        private const val NOTIFICATION_ID = 1

        const val SERVER_PORT = 8443
        private const val I_FRAME_INTERVAL_S = 2
        private const val WAKE_LOCK_TIMEOUT_MS = 8 * 60 * 60 * 1000L
        private const val ENCODER_RETRY_DELAY_MS = 2_000L

        fun start(context: Context) {
            ContextCompat.startForegroundService(
                context,
                Intent(context, StreamingService::class.java).setAction(ACTION_START)
            )
        }

        fun stop(context: Context) {
            context.startService(Intent(context, StreamingService::class.java).setAction(ACTION_STOP))
        }
    }

    enum class Phase { IDLE, STARTING, LISTENING, STREAMING, ERROR }

    data class State(
        val phase: Phase = Phase.IDLE,
        val clientAddress: String? = null,
        val addresses: List<LocalAddress> = emptyList(),
        val port: Int = SERVER_PORT,
        val fps: Int = 0,
        val kbps: Int = 0,
        val frontCamera: Boolean = false,
        val quality: StreamQuality = StreamQuality.DEFAULT,
        val availableQualities: List<StreamQuality> = listOf(StreamQuality.DEFAULT),
        val error: String? = null
    ) {
        val isActive: Boolean get() = phase == Phase.STARTING || phase == Phase.LISTENING || phase == Phase.STREAMING
    }

    inner class LocalBinder : Binder() {
        val service: StreamingService get() = this@StreamingService
    }

    private val binder = LocalBinder()
    private val _state = MutableStateFlow(State())
    val state: StateFlow<State> = _state.asStateFlow()

    private lateinit var cameraManager: CameraManager
    private var cameraReady = false
    private val certificateManager by lazy { CertificateManager(applicationContext) }
    private val nsdPublisher by lazy { NsdServicePublisher(applicationContext) }

    @Volatile
    private var streamer: VideoStreamer? = null
    private var previewSurfaceProvider: Preview.SurfaceProvider? = null

    // Encoder state, only touched on the camera thread (and released on it).
    @Volatile
    private var encoder: H264Encoder? = null

    @Volatile
    private var encoderSessionRequested = false
    // Read on the camera thread, replaced on the main thread when the preset changes.
    @Volatile
    private var quality = StreamQuality.DEFAULT
    @Volatile
    private var frameRateLimiter = FrameRateLimiter(quality.fps)
    private var encoderRetryAtMs = 0L

    @Volatile
    private var orientationDegrees = 90
    private var orientationListener: OrientationEventListener? = null

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var multicastLock: WifiManager.MulticastLock? = null
    private var statsJob: Job? = null

    override fun onCreate() {
        super.onCreate()
        quality = StreamQuality.load(this)
        frameRateLimiter = FrameRateLimiter(quality.fps)
        cameraManager = CameraManager(this, this, quality.size, quality.fps)
        _state.update { it.copy(addresses = NetworkAddresses.list(), quality = quality) }
        lifecycleScope.launch {
            try {
                cameraManager.initialize()
                cameraReady = true
                _state.update { it.copy(frontCamera = cameraManager.isFrontCamera) }
                refreshAvailableQualities()
                updateCamera()
            } catch (e: Exception) {
                Log.e(TAG, "Camera init failed", e)
                _state.update { it.copy(phase = Phase.ERROR, error = e.message) }
            }
        }
    }

    override fun onBind(intent: Intent): IBinder {
        super.onBind(intent)
        return binder
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        when (intent?.action) {
            ACTION_START -> startStreaming()
            ACTION_STOP -> stopStreaming()
            ACTION_SWITCH_CAMERA -> switchCamera()
        }
        // Not sticky: a camera foreground service may not be restarted from the background.
        return START_NOT_STICKY
    }

    // ---------------------------------------------------------------------------------------
    // Public API (main thread)
    // ---------------------------------------------------------------------------------------

    /** Shows the preview on the activity's PreviewView (null = no preview, saves battery). */
    fun setPreviewSurfaceProvider(provider: Preview.SurfaceProvider?) {
        previewSurfaceProvider = provider
        updateCamera()
    }

    fun switchCamera() {
        if (!cameraReady) return
        runCatching { cameraManager.switchCamera() }
            .onFailure { Log.e(TAG, "Switch camera failed", it) }
        _state.update { it.copy(frontCamera = cameraManager.isFrontCamera) }
        refreshAvailableQualities()
        // Frame size may change with the camera: start a fresh encoder session.
        encoderSessionRequested = true
    }

    /** Applies and saves a stream preset; takes effect immediately, even while streaming. */
    fun setQuality(newQuality: StreamQuality) {
        if (newQuality == quality) return
        quality = newQuality
        StreamQuality.save(this, newQuality)
        frameRateLimiter = FrameRateLimiter(newQuality.fps)
        _state.update { it.copy(quality = newQuality) }
        if (cameraReady) {
            runCatching { cameraManager.setStreamFormat(newQuality.size, newQuality.fps) }
                .onFailure { e -> _state.update { it.copy(error = e.message) } }
        }
        encoderSessionRequested = true
    }

    /** The front camera often can't do 60 fps: fall back to the default preset there. */
    private fun refreshAvailableQualities() {
        val available = StreamQuality.available(cameraManager.maxSupportedFps())
        _state.update { it.copy(availableQualities = available) }
        if (quality !in available) setQuality(StreamQuality.DEFAULT)
    }

    fun refreshAddresses() {
        _state.update { it.copy(addresses = NetworkAddresses.list()) }
    }

    fun startStreaming() {
        // startForegroundService() requires startForeground() promptly, even if we bail out.
        if (!promoteToForeground()) return
        if (_state.value.isActive) return
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            _state.update { it.copy(phase = Phase.ERROR, error = getString(R.string.error_camera_permission)) }
            stopForegroundCompat()
            stopSelf()
            return
        }

        _state.update {
            it.copy(phase = Phase.STARTING, error = null, clientAddress = null, addresses = NetworkAddresses.list())
        }
        updateNotification()

        lifecycleScope.launch {
            try {
                val server = VideoStreamer(SERVER_PORT, certificateManager, streamerListener)
                withContext(Dispatchers.IO) { server.start() }
                streamer = server
                acquireMulticastLock()
                nsdPublisher.publishService(SERVER_PORT)
                _state.update { it.copy(phase = Phase.LISTENING) }
                updateNotification()
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start server", e)
                _state.update { it.copy(phase = Phase.ERROR, error = e.message) }
                stopStreaming(keepError = true)
            }
        }
    }

    fun stopStreaming(keepError: Boolean = false) {
        streamer?.stop()
        streamer = null
        nsdPublisher.unpublishService()
        onClientGone()
        releaseMulticastLock()
        if (!keepError) {
            _state.update { it.copy(phase = Phase.IDLE, clientAddress = null, fps = 0, kbps = 0, error = null) }
        }
        stopForegroundCompat()
        // Stays alive while the activity is bound (for the preview), otherwise goes away.
        stopSelf()
    }

    // ---------------------------------------------------------------------------------------
    // Streaming internals
    // ---------------------------------------------------------------------------------------

    private val streamerListener = object : VideoStreamer.Listener {
        override fun onClientConnected(address: String) {
            lifecycleScope.launch {
                encoderSessionRequested = true
                _state.update { it.copy(phase = Phase.STREAMING, clientAddress = address) }
                onClientPresent()
            }
        }

        override fun onClientDisconnected() {
            lifecycleScope.launch {
                if (streamer?.hasClient == true) return@launch // already replaced by a new client
                onClientGone()
                if (streamer != null) {
                    _state.update { it.copy(phase = Phase.LISTENING, clientAddress = null, fps = 0, kbps = 0) }
                }
                updateNotification()
            }
        }

        override fun onKeyFrameNeeded() {
            encoder?.requestKeyFrame()
        }
    }

    private fun onClientPresent() {
        acquireStreamingLocks()
        startOrientationListener()
        updateCamera()
        startStats()
        updateNotification()
    }

    private fun onClientGone() {
        statsJob?.cancel()
        statsJob = null
        stopOrientationListener()
        releaseStreamingLocks()
        updateCamera()
    }

    /** Binds exactly what is needed: analysis while a PC is connected, preview while visible. */
    private fun updateCamera() {
        if (!cameraReady) return
        val streaming = streamer?.hasClient == true
        try {
            cameraManager.setAnalyzer(if (streaming) frameAnalyzer else null)
            cameraManager.setPreviewSurfaceProvider(previewSurfaceProvider)
        } catch (e: Exception) {
            _state.update { it.copy(error = e.message) }
        }
        if (!streaming) {
            // Release the encoder on the camera thread's next opportunity; if the analyzer is
            // unbound no more frames arrive, so release it here.
            releaseEncoder()
        }
    }

    /** Runs on the camera thread for every frame while a PC is connected. */
    private val frameAnalyzer: (ImageProxy) -> Unit = { image ->
        try {
            processFrame(image)
        } catch (e: Exception) {
            Log.e(TAG, "Frame processing failed: ${e.message}")
        } finally {
            image.close()
        }
    }

    private fun processFrame(image: ImageProxy) {
        val server = streamer ?: return
        if (!server.hasClient) return
        if (!frameRateLimiter.shouldProcess(image.imageInfo.timestamp)) return

        val width = image.width and 1.inv()
        val height = image.height and 1.inv()
        var current = encoder
        if (current == null || encoderSessionRequested || current.isFailed ||
            current.width != width || current.height != height
        ) {
            // New client, camera switch or size change: a fresh encoder guarantees the next frame
            // is a keyframe with SPS/PPS so the PC can start decoding immediately.
            if (SystemClock.elapsedRealtime() < encoderRetryAtMs) return
            encoderSessionRequested = false
            releaseEncoder()
            val preset = quality
            current = H264Encoder(width, height, preset.fps, preset.bitrate, I_FRAME_INTERVAL_S) { frame ->
                val backCamera = !cameraManager.isFrontCamera
                streamer?.send(frame, StreamProtocol.flags(orientationDegrees, backCamera))
            }
            try {
                current.start()
            } catch (e: Exception) {
                Log.e(TAG, "Encoder start failed", e)
                _state.update { it.copy(error = e.message) }
                // Don't retry on every frame (30 times per second).
                encoderRetryAtMs = SystemClock.elapsedRealtime() + ENCODER_RETRY_DELAY_MS
                encoderSessionRequested = true
                return
            }
            encoder = current
            frameRateLimiter.reset()
        }
        current.encode(image)
    }

    @Synchronized
    private fun releaseEncoder() {
        encoder?.release()
        encoder = null
    }

    private fun startStats() {
        statsJob?.cancel()
        val server = streamer ?: return
        statsJob = lifecycleScope.launch {
            var lastFrames = server.framesSent.get()
            var lastBytes = server.bytesSent.get()
            while (isActive) {
                delay(1000)
                val frames = server.framesSent.get()
                val bytes = server.bytesSent.get()
                _state.update {
                    it.copy(fps = (frames - lastFrames).toInt(), kbps = ((bytes - lastBytes) * 8 / 1000).toInt())
                }
                lastFrames = frames
                lastBytes = bytes
            }
        }
    }

    // ---------------------------------------------------------------------------------------
    // Orientation
    // ---------------------------------------------------------------------------------------

    private fun startOrientationListener() {
        if (orientationListener != null) return
        orientationListener = object : OrientationEventListener(this, SensorManager.SENSOR_DELAY_UI) {
            override fun onOrientationChanged(orientation: Int) {
                if (orientation == ORIENTATION_UNKNOWN) return
                orientationDegrees = StreamProtocol.orientationFromSensorDegrees(orientation)
            }
        }.also { if (it.canDetectOrientation()) it.enable() }
    }

    private fun stopOrientationListener() {
        orientationListener?.disable()
        orientationListener = null
    }

    // ---------------------------------------------------------------------------------------
    // Locks: keep CPU and Wi-Fi awake only while actually streaming
    // ---------------------------------------------------------------------------------------

    @Suppress("DEPRECATION")
    private fun acquireStreamingLocks() {
        if (wakeLock == null) {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "VanCamera:streaming").apply {
                setReferenceCounted(false)
                // Re-acquired on every new PC connection; the timeout is only a safety net.
                acquire(WAKE_LOCK_TIMEOUT_MS)
            }
        }
        if (wifiLock == null) {
            // Wi-Fi power save batches packets and causes multi-second stalls (issue #3).
            val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            val mode = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                WifiManager.WIFI_MODE_FULL_LOW_LATENCY
            } else {
                WifiManager.WIFI_MODE_FULL_HIGH_PERF
            }
            wifiLock = wm.createWifiLock(mode, "VanCamera:streaming").apply {
                setReferenceCounted(false)
                acquire()
            }
        }
    }

    private fun releaseStreamingLocks() {
        wakeLock?.let { if (it.isHeld) it.release() }
        wakeLock = null
        wifiLock?.let { if (it.isHeld) it.release() }
        wifiLock = null
    }

    private fun acquireMulticastLock() {
        if (multicastLock != null) return
        try {
            val wm = applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            multicastLock = wm.createMulticastLock("VanCamera:mdns").apply {
                setReferenceCounted(false)
                acquire()
            }
        } catch (e: Exception) {
            Log.w(TAG, "Multicast lock unavailable: ${e.message}")
        }
    }

    private fun releaseMulticastLock() {
        multicastLock?.let { if (it.isHeld) it.release() }
        multicastLock = null
    }

    // ---------------------------------------------------------------------------------------
    // Foreground notification
    // ---------------------------------------------------------------------------------------

    private fun promoteToForeground(): Boolean {
        createChannel()
        return try {
            val notification = buildNotification()
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                startForeground(NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA)
            } else {
                startForeground(NOTIFICATION_ID, notification)
            }
            true
        } catch (e: Exception) {
            // e.g. ForegroundServiceStartNotAllowedException when started from the background.
            Log.e(TAG, "Cannot start foreground service", e)
            _state.update { it.copy(phase = Phase.ERROR, error = e.message) }
            stopSelf()
            false
        }
    }

    private fun stopForegroundCompat() {
        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java)
        if (nm.getNotificationChannel(CHANNEL_ID) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, getString(R.string.notification_channel), NotificationManager.IMPORTANCE_LOW).apply {
                    description = getString(R.string.notification_channel_description)
                    setShowBadge(false)
                }
            )
        }
    }

    private fun updateNotification() {
        if (!_state.value.isActive) return
        try {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.notify(NOTIFICATION_ID, buildNotification())
        } catch (e: SecurityException) {
            // POST_NOTIFICATIONS denied: the service keeps running, the notification is hidden.
        }
    }

    private fun buildNotification(): Notification {
        val state = _state.value
        val text = when (state.phase) {
            Phase.STREAMING -> getString(R.string.notification_streaming, state.clientAddress ?: "")
            else -> getString(R.string.notification_waiting)
        }
        val flags = PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        val openApp = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            flags
        )
        val stop = PendingIntent.getService(
            this, 1, Intent(this, StreamingService::class.java).setAction(ACTION_STOP), flags
        )
        val switch = PendingIntent.getService(
            this, 2, Intent(this, StreamingService::class.java).setAction(ACTION_SWITCH_CAMERA), flags
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_videocam)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setContentIntent(openApp)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .addAction(R.drawable.ic_switch_camera, getString(R.string.action_switch_camera), switch)
            .addAction(R.drawable.ic_stop, getString(R.string.action_stop), stop)
            .build()
    }

    override fun onDestroy() {
        streamer?.stop()
        streamer = null
        nsdPublisher.unpublishService()
        stopOrientationListener()
        releaseStreamingLocks()
        releaseMulticastLock()
        statsJob?.cancel()
        releaseEncoder()
        if (::cameraManager.isInitialized) cameraManager.release()
        super.onDestroy()
    }
}
