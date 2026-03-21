package com.shieldtube.phone.data.db

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "local_downloads")
data class LocalDownloadEntity(
    @PrimaryKey val videoId: String,
    val title: String,
    val channelName: String,
    val duration: String?,
    val filePath: String,
    val fileSize: Long,
    val status: String, // "pending" | "downloading" | "complete" | "error"
    val progress: Int,  // 0-100
    val createdAt: Long,
)
