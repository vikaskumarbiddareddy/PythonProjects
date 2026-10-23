package com.cameradirector.ui

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.os.SystemClock
import android.view.MotionEvent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TimePicker
import androidx.compose.material3.rememberTimePickerState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.cameradirector.camera.CameraController
import com.cameradirector.engine.PlayerStatus
import com.cameradirector.engine.ScriptPlayer
import com.cameradirector.model.ShotScript
import com.cameradirector.model.formatDuration
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.util.Calendar
import kotlin.math.roundToInt

private enum class StartMode(val label: String) { NOW("Now"), COUNTDOWN("Countdown"), AT_TIME("At time") }

private sealed interface RunPhase {
    data object Idle : RunPhase
    data class Waiting(val remainingMs: Long) : RunPhase
    data class Running(val status: PlayerStatus) : RunPhase
    data class Finished(val message: String) : RunPhase
}

@Composable
fun RunScreen(script: ShotScript, onExit: () -> Unit) {
    val context = LocalContext.current
    fun granted(p: String) = ContextCompat.checkSelfPermission(context, p) == PackageManager.PERMISSION_GRANTED

    var cameraGranted by remember { mutableStateOf(granted(Manifest.permission.CAMERA)) }
    var audioGranted by remember { mutableStateOf(granted(Manifest.permission.RECORD_AUDIO)) }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) {
        cameraGranted = granted(Manifest.permission.CAMERA)
        audioGranted = granted(Manifest.permission.RECORD_AUDIO)
    }
    LaunchedEffect(Unit) {
        if (!cameraGranted || !audioGranted) {
            launcher.launch(arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO))
        }
    }

    if (!cameraGranted) {
        Column(
            Modifier.fillMaxSize().safeDrawingPadding().padding(24.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text("Camera permission is needed to record.")
            Spacer(Modifier.size(12.dp))
            Button(onClick = { launcher.launch(arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)) }) {
                Text("Grant permission")
            }
            TextButton(onClick = onExit) { Text("Back") }
        }
        return
    }

    CameraRun(script = script, withAudio = audioGranted, onExit = onExit)
}

@OptIn(ExperimentalMaterial3Api::class)
@SuppressLint("ClickableViewAccessibility")
@Composable
private fun CameraRun(script: ShotScript, withAudio: Boolean, onExit: () -> Unit) {
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    val scope = rememberCoroutineScope()

    val controller = remember { CameraController(context) }
    val previewView = remember {
        PreviewView(context).apply {
            scaleType = PreviewView.ScaleType.FIT_CENTER
            keepScreenOn = true
        }
    }
    LaunchedEffect(Unit) { controller.bind(lifecycleOwner, previewView) }
    DisposableEffect(Unit) { onDispose { controller.release() } }

    val zoom by controller.zoom.collectAsState()
    val recording by controller.isRecording.collectAsState()
    val error by controller.error.collectAsState()

    var phase by remember { mutableStateOf<RunPhase>(RunPhase.Idle) }
    var job by remember { mutableStateOf<Job?>(null) }
    var mode by remember { mutableStateOf(StartMode.COUNTDOWN) }
    var countdownSec by remember { mutableStateOf(10) }
    var atHour by remember { mutableStateOf(Calendar.getInstance().get(Calendar.HOUR_OF_DAY)) }
    var atMinute by remember { mutableStateOf((Calendar.getInstance().get(Calendar.MINUTE) + 2) % 60) }
    var showTimePicker by remember { mutableStateOf(false) }

    val busy = phase is RunPhase.Waiting || phase is RunPhase.Running

    fun start() {
        job = scope.launch {
            try {
                val waitUntil = SystemClock.elapsedRealtime() + when (mode) {
                    StartMode.NOW -> 0L
                    StartMode.COUNTDOWN -> countdownSec * 1000L
                    StartMode.AT_TIME -> millisUntil(atHour, atMinute)
                }
                while (true) {
                    val left = waitUntil - SystemClock.elapsedRealtime()
                    if (left <= 0) break
                    phase = RunPhase.Waiting(left)
                    delay(minOf(left, 200L))
                }
                ScriptPlayer(controller, withAudio).play(script) { phase = RunPhase.Running(it) }
                phase = RunPhase.Finished("Done — video saved to Movies/CameraDirector")
            } catch (e: CancellationException) {
                phase = RunPhase.Finished("Stopped — any recorded video was saved")
                throw e
            } catch (e: Exception) {
                phase = RunPhase.Finished("Failed: ${e.message}")
            }
        }
    }

    Box(Modifier.fillMaxSize().background(Color.Black)) {
        AndroidView(
            factory = {
                previewView.apply {
                    setOnTouchListener { _, ev ->
                        if (ev.action == MotionEvent.ACTION_UP) controller.focusAtView(ev.x, ev.y)
                        true
                    }
                }
            },
            modifier = Modifier.fillMaxSize(),
        )

        // Top status bar
        Row(
            Modifier.fillMaxWidth().safeDrawingPadding().padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Pill {
                if (recording) {
                    Box(Modifier.size(10.dp).clip(CircleShape).background(Color.Red))
                    Spacer(Modifier.size(6.dp))
                    Text("REC", color = Color.White)
                } else {
                    Text(script.name, color = Color.White)
                }
            }
            Spacer(Modifier.weight(1f))
            Pill { Text("%.1fx".format(zoom.current), color = Color.White) }
        }

        // Bottom control panel
        Column(
            Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .safeDrawingPadding()
                .padding(12.dp)
                .clip(RoundedCornerShape(16.dp))
                .background(Color.Black.copy(alpha = 0.6f))
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            when (val p = phase) {
                is RunPhase.Waiting -> {
                    Text("Starting in ${formatDuration(p.remainingMs)}", color = Color.White, style = MaterialTheme.typography.headlineSmall)
                    Text("Leave the phone in place. Script: ${script.name}", color = Color.White)
                }
                is RunPhase.Running -> {
                    val s = p.status
                    Text("Step ${s.stepIndex + 1}/${script.steps.size}: ${s.stepTitle}", color = Color.White, style = MaterialTheme.typography.titleMedium)
                    script.steps.getOrNull(s.stepIndex + 1)?.let { Text("Next: ${it.title}", color = Color.LightGray) }
                    LinearProgressIndicator(
                        progress = { if (s.totalMs > 0) (s.elapsedMs.toFloat() / s.totalMs).coerceIn(0f, 1f) else 0f },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Text("${formatDuration(s.elapsedMs)} / ${formatDuration(s.totalMs)}", color = Color.White)
                }
                is RunPhase.Finished -> Text(p.message, color = Color.White)
                RunPhase.Idle -> {}
            }

            if (!busy) {
                if (zoom.max > zoom.min) {
                    Text("Manual zoom (range %.1fx–%.1fx)".format(zoom.min, zoom.max), color = Color.White)
                    Slider(
                        value = zoom.current.coerceIn(zoom.min, zoom.max),
                        onValueChange = { controller.setZoom(it) },
                        valueRange = zoom.min..zoom.max,
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    StartMode.entries.forEach { m ->
                        FilterChip(selected = mode == m, onClick = { mode = m }, label = { Text(m.label) })
                    }
                }
                when (mode) {
                    StartMode.COUNTDOWN -> {
                        Text("Countdown: $countdownSec s", color = Color.White)
                        Slider(
                            value = countdownSec.toFloat(),
                            onValueChange = { countdownSec = it.roundToInt() },
                            valueRange = 3f..300f,
                        )
                    }
                    StartMode.AT_TIME -> OutlinedButton(onClick = { showTimePicker = true }) {
                        Text("Start at %02d:%02d".format(atHour, atMinute))
                    }
                    StartMode.NOW -> {}
                }
                if (!withAudio) Text("Microphone permission not granted — video will have no sound.", color = Color.LightGray)
                Text("Tap the preview to focus.", color = Color.LightGray)
            }

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (busy) {
                    Button(
                        onClick = { job?.cancel() },
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFD32F2F)),
                        modifier = Modifier.weight(1f),
                    ) { Text("STOP") }
                } else {
                    OutlinedButton(onClick = onExit) { Text("Back") }
                    Button(onClick = ::start, modifier = Modifier.weight(1f)) {
                        Text("Start (${formatDuration(script.totalDurationMs)})")
                    }
                }
            }
        }
    }

    if (showTimePicker) {
        val state = rememberTimePickerState(initialHour = atHour, initialMinute = atMinute, is24Hour = true)
        AlertDialog(
            onDismissRequest = { showTimePicker = false },
            confirmButton = {
                TextButton(onClick = {
                    atHour = state.hour
                    atMinute = state.minute
                    showTimePicker = false
                }) { Text("OK") }
            },
            dismissButton = { TextButton(onClick = { showTimePicker = false }) { Text("Cancel") } },
            text = { TimePicker(state = state) },
        )
    }

    error?.let { msg ->
        AlertDialog(
            onDismissRequest = controller::clearError,
            title = { Text("Camera problem") },
            text = { Text(msg) },
            confirmButton = { TextButton(onClick = controller::clearError) { Text("OK") } },
        )
    }
}

@Composable
private fun Pill(content: @Composable () -> Unit) {
    Row(
        Modifier
            .clip(RoundedCornerShape(50))
            .background(Color.Black.copy(alpha = 0.55f))
            .padding(horizontal = 12.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) { content() }
}

/** Milliseconds from now until the next occurrence of hour:minute (today or tomorrow). */
private fun millisUntil(hour: Int, minute: Int): Long {
    val now = Calendar.getInstance()
    val target = (now.clone() as Calendar).apply {
        set(Calendar.HOUR_OF_DAY, hour)
        set(Calendar.MINUTE, minute)
        set(Calendar.SECOND, 0)
        set(Calendar.MILLISECOND, 0)
        if (!after(now)) add(Calendar.DAY_OF_MONTH, 1)
    }
    return target.timeInMillis - now.timeInMillis
}
