package com.shieldtube.api

import com.google.gson.annotations.SerializedName

data class Video(
    val id: String,
    val title: String,
    @SerializedName("channel_name") val channelName: String,
    @SerializedName("channel_id") val channelId: String,
    @SerializedName("view_count") val viewCount: Long?,
    val duration: Int?,
    @SerializedName("published_at") val publishedAt: String?,
    @SerializedName("thumbnail_url") val thumbnailUrl: String,
    @SerializedName("pre_cached") val preCached: Boolean = false,
    @SerializedName("watch_percentage") val watchPercentage: Float? = null,
    val completed: Boolean? = null
)

data class FeedResponse(
    @SerializedName("feed_type") val feedType: String,
    val videos: List<Video>,
    @SerializedName("cached_at") val cachedAt: String?,
    @SerializedName("from_cache") val fromCache: Boolean,
    val source: String? = null,
    val freshness: String? = null
)

data class ProgressBody(
    @SerializedName("position_seconds") val positionSeconds: Int,
    val duration: Int,
    val event: String? = null,
    val speed: Float? = null
)

data class Chapter(
    val title: String,
    @SerializedName("start_time") val startTime: Double,
    @SerializedName("end_time") val endTime: Double
)

data class VideoMeta(
    val id: String,
    val title: String,
    @SerializedName("channel_name") val channelName: String,
    @SerializedName("channel_id") val channelId: String,
    val duration: Int?,
    @SerializedName("cache_status") val cacheStatus: String?,
    @SerializedName("last_position_seconds") val lastPositionSeconds: Int,
    val chapters: List<Chapter>? = null
)

data class SponsorSegment(
    val start: Double,
    val end: Double,
    val category: String
)

data class SponsorResponse(
    @SerializedName("video_id") val videoId: String,
    val segments: List<SponsorSegment>
)

data class NowPlaying(
    @SerializedName("video_id") val videoId: String?
)

data class SubtitleTrack(
    val lang: String,
    val name: String,
    val auto: Boolean = false
)

data class SubtitleResponse(
    @SerializedName("video_id") val videoId: String,
    val tracks: List<SubtitleTrack>
)

data class VideoFormat(val quality: String, val label: String)

data class FormatsResponse(
    @SerializedName("video_id") val videoId: String,
    val formats: List<VideoFormat>
)

data class AuthStatusResponse(val authenticated: Boolean)

data class DeviceFlowResponse(
    @SerializedName("device_code") val deviceCode: String,
    @SerializedName("user_code") val userCode: String,
    @SerializedName("verification_url") val verificationUrl: String,
    @SerializedName("expires_in") val expiresIn: Int,
    val interval: Int
)

data class AuthCallbackResponse(val status: String)

// Playback remote control models
data class PlaybackCommand(
    val action: String,
    val value: String?
)

data class PlaybackCommandsResponse(
    val commands: List<PlaybackCommand>
)

data class PlaybackStatusBody(
    @SerializedName("video_id") val videoId: String,
    val title: String,
    @SerializedName("position_ms") val positionMs: Long,
    @SerializedName("duration_ms") val durationMs: Long,
    @SerializedName("is_playing") val isPlaying: Boolean,
    val speed: Float = 1.0f
)
