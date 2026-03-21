package com.shieldtube.phone.ui.settings

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shieldtube.phone.data.api.ShieldTubeApi
import com.shieldtube.phone.data.preferences.AppPreferences
import com.shieldtube.phone.service.LanDetector
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SettingsUiState(
    val backendUrl: String = "",
    val lanUrl: String = "",
    val apiSecret: String = "",
    val lanAvailable: Boolean = false,
    val cacheUsedGb: Double = 0.0,
    val cacheTotalGb: Double = 0.0,
    val isLoadingCache: Boolean = false,
    val isSaving: Boolean = false,
    val saveSuccess: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class SettingsViewModel @Inject constructor(
    private val prefs: AppPreferences,
    private val api: ShieldTubeApi,
    val lanDetector: LanDetector,
) : ViewModel() {

    private val _uiState = MutableStateFlow(SettingsUiState())
    val uiState: StateFlow<SettingsUiState> = _uiState.asStateFlow()

    val lanAvailable: StateFlow<Boolean> = lanDetector.isAvailable
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), false)

    init {
        viewModelScope.launch {
            combine(prefs.backendUrl, prefs.lanUrl, prefs.apiSecret) { url, lan, secret ->
                Triple(url, lan, secret)
            }.collect { (url, lan, secret) ->
                _uiState.update {
                    it.copy(backendUrl = url, lanUrl = lan, apiSecret = secret)
                }
            }
        }
        loadCacheStatus()
    }

    fun updateBackendUrl(value: String) = _uiState.update { it.copy(backendUrl = value) }
    fun updateLanUrl(value: String) = _uiState.update { it.copy(lanUrl = value) }
    fun updateApiSecret(value: String) = _uiState.update { it.copy(apiSecret = value) }

    fun save() {
        val state = _uiState.value
        _uiState.update { it.copy(isSaving = true, saveSuccess = false, error = null) }
        viewModelScope.launch {
            try {
                prefs.save(state.backendUrl, state.apiSecret, state.lanUrl)
                _uiState.update { it.copy(isSaving = false, saveSuccess = true) }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isSaving = false, error = e.message ?: "Failed to save")
                }
            }
        }
    }

    fun disconnect() {
        viewModelScope.launch {
            prefs.save("", "", "")
        }
    }

    fun loadCacheStatus() {
        _uiState.update { it.copy(isLoadingCache = true) }
        viewModelScope.launch {
            try {
                val status = api.cacheStatus()
                _uiState.update {
                    it.copy(
                        isLoadingCache = false,
                        cacheUsedGb = status.usedGb,
                        cacheTotalGb = status.totalGb,
                    )
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingCache = false) }
            }
        }
    }
}
