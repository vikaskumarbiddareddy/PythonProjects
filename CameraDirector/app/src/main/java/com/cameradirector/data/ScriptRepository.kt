package com.cameradirector.data

import android.content.Context
import com.cameradirector.model.Easing
import com.cameradirector.model.ShotScript
import com.cameradirector.model.Step
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import java.io.File

/** Stores all shot scripts as one JSON file in app-private storage. */
class ScriptRepository(context: Context) {
    private val file = File(context.filesDir, "scripts.json")
    private val json = Json { ignoreUnknownKeys = true; prettyPrint = true }

    suspend fun load(): List<ShotScript> = withContext(Dispatchers.IO) {
        if (!file.exists()) return@withContext builtInPresets().also { saveBlocking(it) }
        runCatching { json.decodeFromString<List<ShotScript>>(file.readText()) }
            .getOrElse { builtInPresets() }
    }

    suspend fun save(scripts: List<ShotScript>) = withContext(Dispatchers.IO) { saveBlocking(scripts) }

    private fun saveBlocking(scripts: List<ShotScript>) {
        val tmp = File(file.parentFile, "scripts.json.tmp")
        tmp.writeText(json.encodeToString(scripts))
        tmp.renameTo(file)
    }

    companion object {
        fun builtInPresets() = listOf(
            ShotScript(
                name = "Zoom in, then out",
                steps = listOf(
                    Step.StartRecording,
                    Step.Hold(5f),
                    Step.Zoom(3f, 2f, Easing.SMOOTH),
                    Step.Hold(4f),
                    Step.Zoom(1f, 3f, Easing.SMOOTH),
                    Step.Hold(3f),
                    Step.StopRecording,
                ),
            ),
            ShotScript(
                name = "Slow push-in",
                steps = listOf(
                    Step.StartRecording,
                    Step.Hold(2f),
                    Step.Zoom(2.5f, 15f, Easing.LINEAR),
                    Step.Hold(3f),
                    Step.StopRecording,
                ),
            ),
            ShotScript(
                name = "Punch zoom",
                steps = listOf(
                    Step.StartRecording,
                    Step.Hold(3f),
                    Step.Zoom(4f, 0.3f, Easing.LINEAR),
                    Step.Hold(2f),
                    Step.Zoom(1f, 0.3f, Easing.LINEAR),
                    Step.Hold(3f),
                    Step.StopRecording,
                ),
            ),
            ShotScript(
                name = "Breathing zoom",
                steps = listOf(
                    Step.StartRecording,
                    Step.Zoom(1.5f, 4f, Easing.SMOOTH),
                    Step.Zoom(1f, 4f, Easing.SMOOTH),
                    Step.Zoom(1.5f, 4f, Easing.SMOOTH),
                    Step.Zoom(1f, 4f, Easing.SMOOTH),
                    Step.StopRecording,
                ),
            ),
        )
    }
}
