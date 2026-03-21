package com.shieldtube.phone.data.api

import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

interface ShieldTubeApi {

    @GET("api/feed/{type}")
    suspend fun getFeed(@Path("type") type: String): FeedResponse

    @GET("api/search")
    suspend fun search(@Query("q") q: String): FeedResponse

    @GET("api/sponsorblock/{id}")
    suspend fun getSponsorSegments(@Path("id") id: String): SponsorResponse

    @POST("api/video/{id}/progress")
    suspend fun reportProgress(
        @Path("id") id: String,
        @Body body: ProgressBody,
    ): Unit

    @POST("api/download/enqueue")
    suspend fun enqueueServerDownload(@Body body: EnqueueBody): EnqueueResponse

    @GET("api/download/active")
    suspend fun getActiveDownloads(): ActiveDownloadsResponse

    @GET("api/download/library")
    suspend fun getDownloadLibrary(): LibraryResponse

    @POST("api/cast")
    suspend fun castToShield(@Body body: CastBody): Unit

    @GET("api/auth/status")
    suspend fun authStatus(): AuthStatusResponse

    @GET("api/cache/status")
    suspend fun cacheStatus(): CacheStatusResponse
}
