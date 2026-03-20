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
    @SerializedName("thumbnail_url") val thumbnailUrl: String
)

data class FeedResponse(
    @SerializedName("feed_type") val feedType: String,
    val videos: List<Video>,
    @SerializedName("cached_at") val cachedAt: String?,
    @SerializedName("from_cache") val fromCache: Boolean
)

data class ProgressBody(
    @SerializedName("position_seconds") val positionSeconds: Int,
    val duration: Int
)

data class VideoMeta(
    val id: String,
    val title: String,
    @SerializedName("channel_name") val channelName: String,
    @SerializedName("channel_id") val channelId: String,
    val duration: Int?,
    @SerializedName("cache_status") val cacheStatus: String?,
    @SerializedName("last_position_seconds") val lastPositionSeconds: Int
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
