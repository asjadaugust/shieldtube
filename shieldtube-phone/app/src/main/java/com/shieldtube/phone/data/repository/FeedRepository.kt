package com.shieldtube.phone.data.repository

import com.shieldtube.phone.data.api.FeedResponse
import com.shieldtube.phone.data.api.ShieldTubeApi
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class FeedRepository @Inject constructor(
    private val api: ShieldTubeApi,
) {
    suspend fun getFeed(type: String): FeedResponse = api.getFeed(type)

    suspend fun search(query: String): FeedResponse = api.search(query)
}
