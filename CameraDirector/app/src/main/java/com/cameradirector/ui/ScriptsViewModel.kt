package com.cameradirector.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.cameradirector.data.ScriptRepository
import com.cameradirector.model.ShotScript
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.util.UUID

class ScriptsViewModel(app: Application) : AndroidViewModel(app) {
    private val repo = ScriptRepository(app)
    private val _scripts = MutableStateFlow<List<ShotScript>>(emptyList())
    val scripts: StateFlow<List<ShotScript>> = _scripts.asStateFlow()

    init {
        viewModelScope.launch { _scripts.value = repo.load() }
    }

    fun find(id: String): ShotScript? = _scripts.value.firstOrNull { it.id == id }

    fun upsert(script: ShotScript) = update { list ->
        if (list.any { it.id == script.id }) list.map { if (it.id == script.id) script else it }
        else list + script
    }

    fun delete(id: String) = update { list -> list.filterNot { it.id == id } }

    fun duplicate(id: String) = update { list ->
        val src = list.firstOrNull { it.id == id } ?: return@update list
        list + src.copy(id = UUID.randomUUID().toString(), name = "${src.name} (copy)")
    }

    fun restorePresets() = update { list -> list + ScriptRepository.builtInPresets() }

    private fun update(transform: (List<ShotScript>) -> List<ShotScript>) {
        val next = transform(_scripts.value)
        _scripts.value = next
        viewModelScope.launch { repo.save(next) }
    }
}
