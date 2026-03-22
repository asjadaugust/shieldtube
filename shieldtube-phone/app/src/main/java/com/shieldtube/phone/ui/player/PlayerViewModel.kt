package com.shieldtube.phone.ui.player

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shieldtube.phone.data.api.CastBody
import com.shieldtube.phone.data.api.PlaybackCommandBody
import com.shieldtube.phone.data.api.PlaybackStatus
import com.shieldtube.phone.data.api.ProgressBody
import com.shieldtube.phone.data.api.ShieldTubeApi
import com.shieldtube.phone.data.api.SponsorSegment
import com.shieldtube.phone.service.LanDetector
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import javax.inject.Inject

data class PlayerUiState(
    val videoId: String = "",
    val streamUrl: String = "",
    val sponsorSegments: List<SponsorSegment> = emptyList(),
    val isLoading: Boolean = true,
    val error: String? = null,
)

@HiltViewModel
class PlayerViewModel @Inject constructor(
    savedStateHandle: SavedStateHandle,
    private val api: ShieldTubeApi,
    private val lanDetector: LanDetector,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PlayerUiState())
    val uiState: StateFlow<PlayerUiState> = _uiState.asStateFlow()

    private val _remoteStatus = MutableStateFlow<PlaybackStatus?>(null)
    val remoteStatus: StateFlow<PlaybackStatus?> = _remoteStatus.asStateFlow()

    private var remotePollingJob: Job? = null

    init {
        val videoId = savedStateHandle.get<String>("videoId") ?: ""
        _uiState.update { it.copy(videoId = videoId) }
        viewModelScope.launch {
            load(videoId)
        }
    }

    private suspend fun load(videoId: String) {
        if (videoId.isBlank()) {
            _uiState.update { it.copy(isLoading = false, error = "No video ID provided") }
            return
        }
        try {
            val streamBaseUrl = lanDetector.getStreamBaseUrl()
            val streamUrl = "$streamBaseUrl/api/video/$videoId/stream"

            val segments = try {
                api.getSponsorSegments(videoId).segments
            } catch (e: Exception) {
                emptyList()
            }

            _uiState.update {
                it.copy(
                    streamUrl = streamUrl,
                    sponsorSegments = segments,
                    isLoading = false,
                )
            }
        } catch (e: Exception) {
            _uiState.update {
                it.copy(isLoading = false, error = e.message ?: "Failed to load video")
            }
        }
    }

    fun reportProgress(positionSeconds: Int, duration: Int) {
        viewModelScope.launch {
            try {
                api.reportProgress(
                    id = _uiState.value.videoId,
                    body = ProgressBody(
                        positionSeconds = positionSeconds,
                        duration = duration,
                        event = null,
                    ),
                )
            } catch (_: Exception) {
                // Silently ignore progress reporting failures
            }
        }
    }

    fun castToShield() {
        viewModelScope.launch {
            try {
                api.castToShield(CastBody(url = _uiState.value.streamUrl))
                startRemoteMode()
            } catch (_: Exception) {
                // Silently ignore cast failures
            }
        }
    }

    fun sendCommand(action: String, value: String? = null) {
        viewModelScope.launch {
            try {
                api.sendPlaybackCommand(PlaybackCommandBody(action = action, value = value))
            } catch (_: Exception) {}
        }
    }

    fun startRemoteMode() {
        if (remotePollingJob?.isActive == true) return
        remotePollingJob = viewModelScope.launch {
            while (isActive) {
                try {
                    val status = api.getPlaybackStatus()
                    _remoteStatus.value = status
                    // Shield stopped playing — exit remote mode
                    if (status.videoId == null) {
                        stopRemoteMode()
                        return@launch
                    }
                } catch (_: Exception) {}
                delay(1000)
            }
        }
    }

    fun stopRemoteMode() {
        remotePollingJob?.cancel()
        remotePollingJob = null
        _remoteStatus.value = null
    }
}
