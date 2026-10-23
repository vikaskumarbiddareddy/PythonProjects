package com.cameradirector.camera

import android.annotation.SuppressLint
import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.provider.MediaStore
import android.util.Log
import androidx.camera.core.Camera
import androidx.camera.core.CameraSelector
import androidx.camera.core.FocusMeteringAction
import androidx.camera.core.MeteringPoint
import androidx.camera.core.Preview
import androidx.camera.core.SurfaceOrientedMeteringPointFactory
import androidx.camera.core.resolutionselector.AspectRatioStrategy
import androidx.camera.core.resolutionselector.ResolutionSelector
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FallbackStrategy
import androidx.camera.video.MediaStoreOutputOptions
import androidx.camera.video.Quality
import androidx.camera.video.QualitySelector
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

data class ZoomInfo(val min: Float = 1f, val max: Float = 1f, val current: Float = 1f)

/** Wraps CameraX: preview, video recording, zoom and focus on the back camera. */
class CameraController(private val context: Context) {
    private var provider: ProcessCameraProvider? = null
    private var camera: Camera? = null
    private var videoCapture: VideoCapture<Recorder>? = null
    private var previewView: PreviewView? = null
    private var recording: Recording? = null
    private var finalized: CompletableDeferred<Unit>? = null

    private val _zoom = MutableStateFlow(ZoomInfo())
    val zoom: StateFlow<ZoomInfo> = _zoom.asStateFlow()

    private val _isRecording = MutableStateFlow(false)
    val isRecording: StateFlow<Boolean> = _isRecording.asStateFlow()

    private val _lastSaved = MutableStateFlow<Uri?>(null)
    val lastSaved: StateFlow<Uri?> = _lastSaved.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /** Last zoom ratio we asked for; zoomState lags behind requests, so animations start from this. */
    var requestedZoom: Float = 1f
        private set

    suspend fun bind(owner: LifecycleOwner, view: PreviewView) {
        previewView = view
        val cameraProvider = suspendCancellableCoroutine { cont ->
            val future = ProcessCameraProvider.getInstance(context)
            future.addListener(
                { runCatching { future.get() }.fold(cont::resume, cont::resumeWithException) },
                ContextCompat.getMainExecutor(context),
            )
        }
        provider = cameraProvider

        val resolution = ResolutionSelector.Builder()
            .setAspectRatioStrategy(AspectRatioStrategy.RATIO_16_9_FALLBACK_AUTO_STRATEGY)
            .build()
        val preview = Preview.Builder().setResolutionSelector(resolution).build()
        preview.surfaceProvider = view.surfaceProvider

        val recorder = Recorder.Builder()
            .setQualitySelector(
                QualitySelector.fromOrderedList(
                    listOf(Quality.FHD, Quality.HD),
                    FallbackStrategy.lowerQualityOrHigherThan(Quality.SD),
                )
            )
            .build()
        val capture = VideoCapture.withOutput(recorder)
        videoCapture = capture

        try {
            cameraProvider.unbindAll()
            val cam = cameraProvider.bindToLifecycle(owner, CameraSelector.DEFAULT_BACK_CAMERA, preview, capture)
            camera = cam
            cam.cameraInfo.zoomState.observe(owner) { state ->
                _zoom.value = ZoomInfo(state.minZoomRatio, state.maxZoomRatio, state.zoomRatio)
            }
            requestedZoom = cam.cameraInfo.zoomState.value?.zoomRatio ?: 1f
        } catch (e: Exception) {
            Log.e(TAG, "Camera bind failed", e)
            _error.value = "Could not open camera: ${e.message}"
        }
    }

    fun release() {
        recording?.stop()
        recording = null
        provider?.unbindAll()
        camera = null
    }

    fun clampZoom(ratio: Float): Float {
        val z = _zoom.value
        return ratio.coerceIn(z.min, z.max)
    }

    fun setZoom(ratio: Float) {
        val clamped = clampZoom(ratio)
        requestedZoom = clamped
        camera?.cameraControl?.setZoomRatio(clamped)
    }

    fun focusCenter() {
        focusAt(SurfaceOrientedMeteringPointFactory(1f, 1f).createPoint(0.5f, 0.5f))
    }

    /** Tap-to-focus using view coordinates of the preview. */
    fun focusAtView(x: Float, y: Float) {
        val view = previewView ?: return
        focusAt(view.meteringPointFactory.createPoint(x, y))
    }

    private fun focusAt(point: MeteringPoint) {
        val action = FocusMeteringAction.Builder(point)
            .setAutoCancelDuration(5, TimeUnit.SECONDS)
            .build()
        camera?.cameraControl?.startFocusAndMetering(action)
    }

    /** Starts a recording and waits until the camera confirms it. Returns false on failure. */
    @SuppressLint("MissingPermission")
    suspend fun startRecording(withAudio: Boolean): Boolean {
        val capture = videoCapture ?: return false
        if (recording != null) return true

        previewView?.display?.rotation?.let { capture.targetRotation = it }

        val name = "CameraDirector_" + SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, name)
            put(MediaStore.MediaColumns.MIME_TYPE, "video/mp4")
            put(MediaStore.MediaColumns.RELATIVE_PATH, "Movies/CameraDirector")
        }
        val output = MediaStoreOutputOptions.Builder(context.contentResolver, MediaStore.Video.Media.EXTERNAL_CONTENT_URI)
            .setContentValues(values)
            .build()

        var pending = capture.output.prepareRecording(context, output)
        if (withAudio) pending = pending.withAudioEnabled()

        val started = CompletableDeferred<Boolean>()
        val done = CompletableDeferred<Unit>()
        finalized = done
        recording = pending.start(ContextCompat.getMainExecutor(context)) { event ->
            when (event) {
                is VideoRecordEvent.Start -> {
                    _isRecording.value = true
                    started.complete(true)
                }
                is VideoRecordEvent.Finalize -> {
                    _isRecording.value = false
                    recording = null
                    if (event.hasError()) {
                        _error.value = "Recording error (${event.error}): ${event.cause?.message ?: "unknown"}"
                    }
                    if (event.error == VideoRecordEvent.Finalize.ERROR_NONE ||
                        event.error == VideoRecordEvent.Finalize.ERROR_SOURCE_INACTIVE
                    ) {
                        _lastSaved.value = event.outputResults.outputUri
                    }
                    started.complete(false)
                    done.complete(Unit)
                }
            }
        }
        return withTimeoutOrNull(5_000) { started.await() } ?: false
    }

    /** Stops the current recording and waits until the file is written. */
    suspend fun stopRecording() {
        val rec = recording ?: return
        val done = finalized
        rec.stop()
        withTimeoutOrNull(10_000) { done?.await() }
    }

    fun clearError() {
        _error.value = null
    }

    private companion object {
        const val TAG = "CameraController"
    }
}
