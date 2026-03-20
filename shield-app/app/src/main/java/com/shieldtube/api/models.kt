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
