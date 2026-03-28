package com.shieldtube.phone.ui.downloads

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.workDataOf
import com.shieldtube.phone.data.api.ActiveDownload
import com.shieldtube.phone.data.api.LibraryVideo
import com.shieldtube.phone.data.api.VideoItem
import com.shieldtube.phone.data.db.LocalDownloadEntity
import com.shieldtube.phone.data.preferences.AppPreferences
import com.shieldtube.phone.data.repository.DownloadRepository
import com.shieldtube.phone.service.VideoDownloadWorker
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.io.File
import javax.inject.Inject

data class DownloadsUiState(
    val selectedTab: Int = 0,  // 0 = Phone, 1 = Server
    val localDownloads: List<LocalDownloadEntity> = emptyList(),
    val serverLibrary: List<LibraryVideo> = emptyList(),
    val serverActive: List<ActiveDownload> = emptyList(),
    val isLoading: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class DownloadsViewModel @Inject constructor(
    private val repository: DownloadRepository,
    private val prefs: AppPreferences,
    private val workManager: WorkManager,
    @ApplicationContext private val context: Context,
) : ViewModel() {

    private val _uiState = MutableStateFlow(DownloadsUiState())
    val uiState: StateFlow<DownloadsUiState> = _uiState.asStateFlow()

    val baseUrl: StateFlow<String> = prefs.backendUrl
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), "")

    init {
        // Collect local downloads from Room Flow
        viewModelScope.launch {
            repository.getLocalDownloads().collect { downloads ->
                _uiState.update { it.copy(localDownloads = downloads) }
            }
        }
        loadServerData()
    }

    fun selectTab(tab: Int) {
        _uiState.update { it.copy(selectedTab = tab) }
        if (tab == 1) loadServerData()
    }

    fun loadServerData() {
        _uiState.update { it.copy(isLoading = true, error = null) }
        viewModelScope.launch {
            try {
                val active = repository.getActiveDownloads()
                val library = repository.getLibrary()
                _uiState.update {
                    it.copy(
                        isLoading = false,
                        serverActive = active.active,
                        serverLibrary = library.videos,
                    )
                }
            } catch (e: Exception) {
                _uiState.update {
                    it.copy(isLoading = false, error = e.message ?: "Failed to load server data")
                }
            }
        }
    }

    fun startPhoneDownload(video: VideoItem) {
        viewModelScope.launch {
            repository.addLocalDownload(video)
            val workRequest = OneTimeWorkRequestBuilder<VideoDownloadWorker>()
                .setInputData(workDataOf("video_id" to video.id))
                .build()
            workManager.enqueue(workRequest)
        }
    }

    fun deleteLocal(videoId: String) {
        viewModelScope.launch {
            // Delete file if it exists
            val videosDir = context.getExternalFilesDir("videos")
            val file = File(videosDir, "$videoId.mp4")
            if (file.exists()) file.delete()
            repository.deleteLocal(videoId)
        }
    }

    fun copyServerToPhone(video: LibraryVideo) {
        viewModelScope.launch {
            // Reuse the same download worker — it downloads from the server stream URL
            repository.addLocalDownload(
                VideoItem(
                    id = video.id,
                    title = video.title,
                    channelName = video.channelName,
                    channelId = "",
                    viewCount = null,
                    duration = video.duration?.toString(),
                    publishedAt = null,
                    thumbnailUrl = null,
                )
            )
            val workRequest = OneTimeWorkRequestBuilder<VideoDownloadWorker>()
                .setInputData(workDataOf("video_id" to video.id))
                .build()
            workManager.enqueue(workRequest)
        }
    }

    fun downloadMp3(video: LibraryVideo) {
        viewModelScope.launch {
            // Download MP3 from server's audio extraction endpoint
            repository.addLocalDownload(
                VideoItem(
                    id = video.id,
                    title = "${video.title} (MP3)",
                    channelName = video.channelName,
                    channelId = "",
                    viewCount = null,
                    duration = video.duration?.toString(),
                    publishedAt = null,
                    thumbnailUrl = null,
                )
            )
            val workRequest = OneTimeWorkRequestBuilder<VideoDownloadWorker>()
                .setInputData(workDataOf(
                    "video_id" to video.id,
                    "audio_only" to true,
                ))
                .build()
            workManager.enqueue(workRequest)
        }
    }

    fun enqueueServer(videoId: String) {
        viewModelScope.launch {
            try {
                repository.enqueueServer(videoId)
                loadServerData()
            } catch (e: Exception) {
                _uiState.update { it.copy(error = e.message ?: "Failed to enqueue on server") }
            }
        }
    }
}
