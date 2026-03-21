package com.shieldtube.phone.ui.search

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shieldtube.phone.data.api.VideoItem
import com.shieldtube.phone.data.preferences.AppPreferences
import com.shieldtube.phone.data.repository.FeedRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SearchUiState(
    val query: String = "",
    val isLoading: Boolean = false,
    val results: List<VideoItem> = emptyList(),
    val error: String? = null,
    val hasSearched: Boolean = false,
)

@HiltViewModel
class SearchViewModel @Inject constructor(
    private val repository: FeedRepository,
    private val prefs: AppPreferences,
) : ViewModel() {

    private val _uiState = MutableStateFlow(SearchUiState())
    val uiState: StateFlow<SearchUiState> = _uiState.asStateFlow()

    val baseUrl: StateFlow<String> = prefs.backendUrl
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), "")

    private var searchJob: Job? = null

    fun updateQuery(q: String) {
        _uiState.update { it.copy(query = q, error = null) }
        searchJob?.cancel()
        if (q.length < 2) {
            _uiState.update { it.copy(results = emptyList(), hasSearched = false, isLoading = false) }
            return
        }
        searchJob = viewModelScope.launch {
            delay(300)
            search(q)
        }
    }

    private suspend fun search(query: String) {
        _uiState.update { it.copy(isLoading = true, error = null) }
        try {
            val response = repository.search(query)
            _uiState.update {
                it.copy(isLoading = false, results = response.videos, hasSearched = true)
            }
        } catch (e: Exception) {
            _uiState.update {
                it.copy(
                    isLoading = false,
                    error = e.message ?: "Search failed",
                    hasSearched = true,
                )
            }
        }
    }
}
