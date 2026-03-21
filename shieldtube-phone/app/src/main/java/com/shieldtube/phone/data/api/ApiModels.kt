package com.shieldtube.phone.data.api

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class VideoItem(
    @Json(name = "id") val id: String,
    @Json(name = "title") val title: String,
    @Json(name = "channel_name") val channelName: String,
    @Json(name = "channel_id") val channelId: String,
    @Json(name = "view_count") val viewCount: String?,
    @Json(name = "duration") val duration: String?,
    @Json(name = "published_at") val publishedAt: String?,
    @Json(name = "thumbnail_url") val thumbnailUrl: String?,
)

@JsonClass(generateAdapter = true)
data class FeedResponse(
    @Json(name = "feed_type") val feedType: String,
    @Json(name = "videos") val videos: List<VideoItem>,
    @Json(name = "cached_at") val cachedAt: String?,
    @Json(name = "from_cache") val fromCache: Boolean,
)

@JsonClass(generateAdapter = true)
data class SponsorSegment(
    @Json(name = "start") val start: Double,
    @Json(name = "end") val end: Double,
    @Json(name = "category") val category: String,
)

@JsonClass(generateAdapter = true)
data class SponsorResponse(
    @Json(name = "video_id") val videoId: String,
    @Json(name = "segments") val segments: List<SponsorSegment>,
)

@JsonClass(generateAdapter = true)
data class ProgressBody(
    @Json(name = "position_seconds") val positionSeconds: Int,
    @Json(name = "duration") val duration: Int,
    @Json(name = "event") val event: String?,
)

@JsonClass(generateAdapter = true)
data class AuthStatusResponse(
    @Json(name = "authenticated") val authenticated: Boolean,
)

@JsonClass(generateAdapter = true)
data class EnqueueBody(
    @Json(name = "video_id") val videoId: String,
)

@JsonClass(generateAdapter = true)
data class EnqueueResponse(
    @Json(name = "status") val status: String,
    @Json(name = "video_id") val videoId: String?,
)

@JsonClass(generateAdapter = true)
data class ActiveDownload(
    @Json(name = "video_id") val videoId: String,
    @Json(name = "title") val title: String,
    @Json(name = "channel_name") val channelName: String,
    @Json(name = "status") val status: String,
    @Json(name = "percent") val percent: Int,
    @Json(name = "bytes_downloaded") val bytesDownloaded: Long,
    @Json(name = "bytes_total") val bytesTotal: Long,
)

@JsonClass(generateAdapter = true)
data class ActiveDownloadsResponse(
    @Json(name = "active") val active: List<ActiveDownload>,
    @Json(name = "queue_size") val queueSize: Int,
)

@JsonClass(generateAdapter = true)
data class LibraryVideo(
    @Json(name = "id") val id: String,
    @Json(name = "title") val title: String,
    @Json(name = "channel_name") val channelName: String,
    @Json(name = "duration") val duration: String?,
    @Json(name = "cache_status") val cacheStatus: String,
    @Json(name = "download_source") val downloadSource: String?,
    @Json(name = "cached_at") val cachedAt: String?,
    @Json(name = "file_size") val fileSize: Long?,
)

@JsonClass(generateAdapter = true)
data class LibraryResponse(
    @Json(name = "videos") val videos: List<LibraryVideo>,
)

@JsonClass(generateAdapter = true)
data class CastBody(
    @Json(name = "url") val url: String,
)

@JsonClass(generateAdapter = true)
data class CacheStatusResponse(
    @Json(name = "used_gb") val usedGb: Double,
    @Json(name = "total_gb") val totalGb: Double,
)
