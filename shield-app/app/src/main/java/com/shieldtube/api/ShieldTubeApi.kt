package com.shieldtube.api

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface ShieldTubeApi {
    @GET("/api/feed/home")
    suspend fun getFeedHome(): FeedResponse

    @GET("/api/feed/subscriptions")
    suspend fun getFeedSubscriptions(): FeedResponse

    @GET("/api/feed/watch-later")
    suspend fun getFeedWatchLater(): FeedResponse

    @GET("/api/search")
    suspend fun search(@Query("q") query: String): FeedResponse

    @POST("/api/video/{videoId}/progress")
    suspend fun reportProgress(
        @Path("videoId") videoId: String,
        @Body body: ProgressBody
    )

    @GET("/api/video/{videoId}/meta")
    suspend fun getVideoMeta(@Path("videoId") videoId: String): VideoMeta

    @GET("/api/sponsorblock/{videoId}")
    suspend fun getSponsorSegments(@Path("videoId") videoId: String): SponsorResponse

    @GET("/api/cast/now-playing")
    suspend fun getNowPlaying(): NowPlaying
}
