package com.cameradirector.engine

import android.os.SystemClock
import com.cameradirector.camera.CameraController
import com.cameradirector.model.ShotScript
import com.cameradirector.model.Step
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

data class PlayerStatus(
    val stepIndex: Int,
    val stepTitle: String,
    val elapsedMs: Long,
    val totalMs: Long,
)

/**
 * Runs a [ShotScript] against the camera. Cancel the calling coroutine to abort;
 * any recording in progress is always stopped and saved.
 */
class ScriptPlayer(
    private val camera: CameraController,
    private val withAudio: Boolean,
) {
    suspend fun play(script: ShotScript, onStatus: (PlayerStatus) -> Unit) {
        val start = SystemClock.elapsedRealtime()
        val total = script.totalDurationMs
        fun report(index: Int, step: Step) =
            onStatus(PlayerStatus(index, step.title, SystemClock.elapsedRealtime() - start, total))

        try {
            script.steps.forEachIndexed { index, step ->
                report(index, step)
                when (step) {
                    Step.StartRecording -> {
                        check(camera.startRecording(withAudio)) { "Recording did not start" }
                    }
                    Step.StopRecording -> camera.stopRecording()
                    Step.FocusCenter -> camera.focusCenter()
                    is Step.Hold -> waitFor(step.durationMs) { report(index, step) }
                    is Step.Zoom -> animateZoom(step) { report(index, step) }
                }
            }
        } finally {
            withContext(NonCancellable) { camera.stopRecording() }
        }
    }

    private suspend fun waitFor(durationMs: Long, onTick: () -> Unit) {
        val end = SystemClock.elapsedRealtime() + durationMs
        while (true) {
            val left = end - SystemClock.elapsedRealtime()
            if (left <= 0) break
            onTick()
            delay(minOf(left, TICK_MS * 6))
        }
    }

    private suspend fun animateZoom(step: Step.Zoom, onTick: () -> Unit) {
        val from = camera.requestedZoom
        val to = camera.clampZoom(step.targetZoom)
        val duration = step.durationMs
        if (duration <= 0) {
            camera.setZoom(to)
            return
        }
        val begin = SystemClock.elapsedRealtime()
        while (true) {
            val t = ((SystemClock.elapsedRealtime() - begin).toFloat() / duration).coerceAtMost(1f)
            camera.setZoom(from + (to - from) * step.easing.apply(t))
            onTick()
            if (t >= 1f) break
            delay(TICK_MS)
        }
    }

    private companion object {
        const val TICK_MS = 16L
    }
}
