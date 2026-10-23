package com.cameradirector

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.lifecycle.viewmodel.compose.viewModel
import com.cameradirector.model.ShotScript
import com.cameradirector.ui.RunScreen
import com.cameradirector.ui.ScriptEditorScreen
import com.cameradirector.ui.ScriptListScreen
import com.cameradirector.ui.ScriptsViewModel

private sealed interface Screen {
    data object List : Screen
    data class Edit(val script: ShotScript) : Screen
    data class Run(val scriptId: String) : Screen
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) { App() }
        }
    }
}

@Composable
private fun App(vm: ScriptsViewModel = viewModel()) {
    val scripts by vm.scripts.collectAsState()
    var screen by remember { mutableStateOf<Screen>(Screen.List) }

    BackHandler(enabled = screen != Screen.List) { screen = Screen.List }

    when (val s = screen) {
        Screen.List -> ScriptListScreen(
            scripts = scripts,
            onNew = { screen = Screen.Edit(ShotScript()) },
            onEdit = { screen = Screen.Edit(it) },
            onRun = { screen = Screen.Run(it.id) },
            onDuplicate = { vm.duplicate(it.id) },
            onDelete = { vm.delete(it.id) },
            onRestorePresets = vm::restorePresets,
        )
        is Screen.Edit -> ScriptEditorScreen(
            initial = s.script,
            onSave = { vm.upsert(it); screen = Screen.List },
            onCancel = { screen = Screen.List },
        )
        is Screen.Run -> {
            val script = vm.find(s.scriptId)
            if (script == null) screen = Screen.List
            else RunScreen(script = script, onExit = { screen = Screen.List })
        }
    }
}
