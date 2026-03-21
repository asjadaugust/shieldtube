package com.shieldtube.phone.data.repository

import com.shieldtube.phone.data.api.ActiveDownloadsResponse
import com.shieldtube.phone.data.api.EnqueueBody
import com.shieldtube.phone.data.api.EnqueueResponse
import com.shieldtube.phone.data.api.LibraryResponse
import com.shieldtube.phone.data.api.ShieldTubeApi
import com.shieldtube.phone.data.api.VideoItem
import com.shieldtube.phone.data.db.LocalDownloadDao
import com.shieldtube.phone.data.db.LocalDownloadEntity
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class DownloadRepository @Inject constructor(
    private val api: ShieldTubeApi,
    private val dao: LocalDownloadDao,
) {

    // --- Server-side downloads ---

    suspend fun enqueueServer(videoId: String): EnqueueResponse =
        api.enqueueServerDownload(EnqueueBody(videoId = videoId))

    suspend fun getActiveDownloads(): ActiveDownloadsResponse =
        api.getActiveDownloads()

    suspend fun getLibrary(): LibraryResponse =
        api.getDownloadLibrary()

    // --- Local downloads (Room) ---

    fun getLocalDownloads(): Flow<List<LocalDownloadEntity>> = dao.getAll()

    suspend fun addLocalDownload(video: VideoItem) {
        val entity = LocalDownloadEntity(
            videoId = video.id,
            title = video.title,
            channelName = video.channelName,
            duration = video.duration,
            filePath = "",
            fileSize = 0L,
            status = "pending",
            progress = 0,
            createdAt = System.currentTimeMillis(),
        )
        dao.upsert(entity)
    }

    suspend fun deleteLocal(videoId: String) = dao.delete(videoId)
}
