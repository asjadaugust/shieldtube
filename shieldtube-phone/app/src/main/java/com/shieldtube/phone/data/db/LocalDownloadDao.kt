package com.shieldtube.phone.data.db

import androidx.room.Dao
import androidx.room.Query
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface LocalDownloadDao {

    @Query("SELECT * FROM local_downloads ORDER BY createdAt DESC")
    fun getAll(): Flow<List<LocalDownloadEntity>>

    @Query("SELECT * FROM local_downloads WHERE videoId = :id")
    suspend fun getById(id: String): LocalDownloadEntity?

    @Upsert
    suspend fun upsert(entity: LocalDownloadEntity)

    @Query("UPDATE local_downloads SET progress = :progress, status = :status WHERE videoId = :id")
    suspend fun updateProgress(id: String, progress: Int, status: String)

    @Query("UPDATE local_downloads SET status = 'complete', progress = 100, filePath = :path, fileSize = :size WHERE videoId = :id")
    suspend fun markComplete(id: String, path: String, size: Long)

    @Query("DELETE FROM local_downloads WHERE videoId = :id")
    suspend fun delete(id: String)
}
