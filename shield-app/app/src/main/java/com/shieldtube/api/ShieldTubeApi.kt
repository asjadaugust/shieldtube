package com.shieldtube.api

import retrofit2.http.GET
import retrofit2.http.Query

interface ShieldTubeApi {
    @GET("/api/feed/home")
    suspend fun getFeedHome(): FeedResponse

    @GET("/api/feed/subscriptions")
    suspend fun getFeedSubscriptions(): FeedResponse

    @GET("/api/search")
    suspend fun search(@Query("q") query: String): FeedResponse
}
