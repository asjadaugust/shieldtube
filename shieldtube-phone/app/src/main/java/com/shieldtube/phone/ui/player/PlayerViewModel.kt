package com.shieldtube.phone.ui.player

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shieldtube.phone.data.api.CastBody
import com.shieldtube.phone.data.api.ProgressBody
import com.shieldtube.phone.data.api.ShieldTubeApi
import com.shieldtube.phone.data.api.SponsorSegment
import com.shieldtube.phone.service.LanDetector
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
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
            } catch (_: Exception) {
                // Silently ignore cast failures
            }
        }
    }
}
