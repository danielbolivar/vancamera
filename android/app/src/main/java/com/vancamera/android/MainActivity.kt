package com.vancamera.android

import android.Manifest
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.content.res.ColorStateList
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.view.View
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.core.content.edit
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.google.android.material.button.MaterialButton
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import java.util.Locale

/**
 * Main screen. It is only a remote control for [StreamingService]: the service owns the camera
 * and keeps streaming after this activity is closed.
 */
class MainActivity : AppCompatActivity() {

    companion object {
        private const val PREFS = "vancamera"
        private const val PREF_PREVIEW = "preview_enabled"
    }

    private lateinit var previewView: PreviewView
    private lateinit var previewOff: View
    private lateinit var statusDot: View
    private lateinit var statusText: TextView
    private lateinit var detailText: TextView
    private lateinit var streamButton: MaterialButton
    private lateinit var flipButton: MaterialButton
    private lateinit var previewButton: MaterialButton

    private var service: StreamingService? = null
    private var bound = false
    private var stateJob: Job? = null
    private var previewEnabled = true
    private var lastPhase: StreamingService.Phase? = null

    private val requestCameraPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) {
            attachPreview()
        } else {
            Toast.makeText(this, R.string.error_camera_permission, Toast.LENGTH_LONG).show()
        }
        render(service?.state?.value ?: StreamingService.State())
    }

    // Notifications are optional: streaming works without them, the user just won't see the
    // ongoing notification with the Stop button.
    private val requestNotificationPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { }

    private val connection = object : ServiceConnection {
        override fun onServiceConnected(name: ComponentName, binder: IBinder) {
            val svc = (binder as StreamingService.LocalBinder).service
            service = svc
            svc.refreshAddresses()
            attachPreview()
            stateJob?.cancel()
            stateJob = lifecycleScope.launch {
                repeatOnLifecycle(Lifecycle.State.STARTED) {
                    svc.state.collect { render(it) }
                }
            }
        }

        override fun onServiceDisconnected(name: ComponentName) {
            service = null
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        previewView = findViewById(R.id.previewView)
        previewOff = findViewById(R.id.previewOff)
        statusDot = findViewById(R.id.statusDot)
        statusText = findViewById(R.id.tvStatus)
        detailText = findViewById(R.id.tvDetail)
        streamButton = findViewById(R.id.btnStream)
        flipButton = findViewById(R.id.btnFlipCamera)
        previewButton = findViewById(R.id.btnPreview)

        // PERFORMANCE mode uses a SurfaceView: cheaper to compose than a TextureView.
        previewView.implementationMode = PreviewView.ImplementationMode.PERFORMANCE
        previewEnabled = getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(PREF_PREVIEW, true)

        streamButton.setOnClickListener { onStreamButton() }
        flipButton.setOnClickListener { service?.switchCamera() }
        previewButton.setOnClickListener { togglePreview() }

        if (!hasCameraPermission()) {
            requestCameraPermission.launch(Manifest.permission.CAMERA)
        }
        render(StreamingService.State())
    }

    override fun onStart() {
        super.onStart()
        bound = bindService(Intent(this, StreamingService::class.java), connection, Context.BIND_AUTO_CREATE)
    }

    override fun onStop() {
        // The preview is only useful while visible: detaching it lets the service turn the camera
        // off completely (or keep only the encoder path while a PC is connected).
        service?.setPreviewSurfaceProvider(null)
        stateJob?.cancel()
        stateJob = null
        if (bound) {
            unbindService(connection)
            bound = false
        }
        service = null
        super.onStop()
    }

    private fun hasCameraPermission() =
        ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED

    private fun attachPreview() {
        val svc = service ?: return
        val show = previewEnabled && hasCameraPermission()
        svc.setPreviewSurfaceProvider(if (show) previewView.surfaceProvider else null)
        previewView.visibility = if (show) View.VISIBLE else View.INVISIBLE
        previewOff.visibility = if (previewEnabled || !hasCameraPermission()) View.GONE else View.VISIBLE
        previewButton.setIconResource(if (previewEnabled) R.drawable.ic_visibility else R.drawable.ic_visibility_off)
    }

    private fun togglePreview() {
        previewEnabled = !previewEnabled
        getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit { putBoolean(PREF_PREVIEW, previewEnabled) }
        attachPreview()
    }

    private fun onStreamButton() {
        if (!hasCameraPermission()) {
            requestCameraPermission.launch(Manifest.permission.CAMERA)
            return
        }
        val state = service?.state?.value ?: StreamingService.State()
        if (state.isActive) {
            service?.stopStreaming()
            Toast.makeText(this, R.string.toast_streaming_stopped, Toast.LENGTH_SHORT).show()
        } else {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
                ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
                PackageManager.PERMISSION_GRANTED
            ) {
                requestNotificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
            }
            StreamingService.start(this)
        }
    }

    private fun render(state: StreamingService.State) {
        if (!hasCameraPermission()) {
            setStatus(R.color.status_error, getString(R.string.status_permission), getString(R.string.detail_permission))
            streamButton.setText(R.string.grant_permission)
            streamButton.setIconResource(R.drawable.ic_videocam)
            streamButton.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, R.color.brand_blue))
            return
        }

        when (state.phase) {
            StreamingService.Phase.IDLE -> setStatus(
                R.color.status_idle, getString(R.string.status_ready), getString(R.string.detail_ready)
            )
            StreamingService.Phase.STARTING -> setStatus(
                R.color.status_waiting, getString(R.string.status_starting), ""
            )
            StreamingService.Phase.LISTENING -> setStatus(
                R.color.status_waiting, getString(R.string.status_waiting),
                buildString {
                    appendLine(addressLines(state))
                    appendLine(getString(R.string.detail_waiting_usb))
                    append(getString(R.string.detail_background))
                }
            )
            StreamingService.Phase.STREAMING -> setStatus(
                R.color.status_live,
                getString(R.string.status_streaming, state.clientAddress ?: ""),
                buildString {
                    appendLine(
                        getString(
                            R.string.detail_stats, state.fps,
                            String.format(Locale.getDefault(), "%.1f", state.kbps / 1000f)
                        )
                    )
                    append(getString(R.string.detail_background))
                }
            )
            StreamingService.Phase.ERROR -> setStatus(
                R.color.status_error, getString(R.string.status_error), state.error ?: ""
            )
        }

        val active = state.isActive
        streamButton.setText(if (active) R.string.stop_streaming else R.string.start_streaming)
        streamButton.setIconResource(if (active) R.drawable.ic_stop else R.drawable.ic_videocam)
        streamButton.backgroundTintList = ColorStateList.valueOf(
            ContextCompat.getColor(this, if (active) R.color.stop_red else R.color.brand_blue)
        )

        if (lastPhase == StreamingService.Phase.STARTING && state.phase == StreamingService.Phase.LISTENING) {
            service?.refreshAddresses()
        }
        lastPhase = state.phase
    }

    private fun addressLines(state: StreamingService.State): String {
        if (state.addresses.isEmpty()) return getString(R.string.detail_no_network)
        return state.addresses.joinToString("\n") { address ->
            val label = when (address.kind) {
                LocalAddress.Kind.WIFI -> R.string.address_wifi
                LocalAddress.Kind.HOTSPOT -> R.string.address_hotspot
                LocalAddress.Kind.ETHERNET -> R.string.address_ethernet
                LocalAddress.Kind.USB_TETHER -> R.string.address_usb_tether
                LocalAddress.Kind.OTHER -> R.string.address_other
            }
            getString(R.string.detail_address, getString(label), "${address.ip}:${state.port}")
        }
    }

    private fun setStatus(colorRes: Int, title: String, detail: String) {
        statusDot.backgroundTintList = ColorStateList.valueOf(ContextCompat.getColor(this, colorRes))
        statusText.text = title
        detailText.text = detail
        detailText.visibility = if (detail.isEmpty()) View.GONE else View.VISIBLE
    }
}
