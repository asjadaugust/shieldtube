package com.shieldtube.api

import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

interface ShieldTubeApi {
    @GET("/api/feed/home")
    suspend fun getFeedHome(): FeedResponse

    @GET("/api/feed/history")
    suspend fun getFeedHistory(): FeedResponse

    @GET("/api/feed/channels")
    suspend fun getFeedChannels(): FeedResponse

    @GET("/api/feed/recommended")
    suspend fun getFeedRecommended(): FeedResponse

    @GET("/api/download/library")
    suspend fun getDownloadLibrary(): FeedResponse

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

    @GET("/api/video/{videoId}/subtitles")
    suspend fun getSubtitles(@Path("videoId") videoId: String): SubtitleResponse

    @GET("/api/video/{videoId}/formats")
    suspend fun getFormats(@Path("videoId") videoId: String): FormatsResponse

    @GET("/api/auth/status")
    suspend fun getAuthStatus(): AuthStatusResponse

    @GET("/api/auth/login")
    suspend fun authLogin(): DeviceFlowResponse

    @GET("/api/auth/callback")
    suspend fun authCallback(@Query("device_code") deviceCode: String): AuthCallbackResponse

    @GET("/api/playback/commands")
    suspend fun getPlaybackCommands(): PlaybackCommandsResponse

    @PUT("/api/playback/status")
    suspend fun updatePlaybackStatus(@Body body: PlaybackStatusBody)

    @DELETE("/api/playback/status")
    suspend fun clearPlaybackStatus()

    @GET("/api/feed/shorts/recommended")
    suspend fun getShortsRecommended(): FeedResponse

    @GET("/api/feed/shorts/trending")
    suspend fun getShortsTrending(): FeedResponse
}
