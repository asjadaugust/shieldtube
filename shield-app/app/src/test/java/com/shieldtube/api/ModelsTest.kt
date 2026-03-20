package com.shieldtube.api

import com.google.gson.Gson
import org.junit.Assert.*
import org.junit.Test

class ModelsTest {
    private val gson = Gson()

    @Test
    fun `deserialize Video from backend JSON`() {
        val json = """
        {
            "id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "channel_name": "Rick Astley",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "view_count": 1500000000,
            "duration": 212,
            "published_at": "2009-10-25T06:57:33Z",
            "thumbnail_url": "/api/video/dQw4w9WgXcQ/thumbnail?res=maxres"
        }
        """.trimIndent()

        val video = gson.fromJson(json, Video::class.java)

        assertEquals("dQw4w9WgXcQ", video.id)
        assertEquals("Never Gonna Give You Up", video.title)
        assertEquals("Rick Astley", video.channelName)
        assertEquals("UCuAXFkgsw1L7xaCfnd5JJOw", video.channelId)
        assertEquals(1500000000L, video.viewCount)
        assertEquals(212, video.duration)
        assertEquals("/api/video/dQw4w9WgXcQ/thumbnail?res=maxres", video.thumbnailUrl)
    }

    @Test
    fun `deserialize FeedResponse from backend JSON`() {
        val json = """
        {
            "feed_type": "home",
            "videos": [],
            "cached_at": "2026-03-20T14:30:00Z",
            "from_cache": true
        }
        """.trimIndent()

        val response = gson.fromJson(json, FeedResponse::class.java)

        assertEquals("home", response.feedType)
        assertTrue(response.videos.isEmpty())
        assertEquals("2026-03-20T14:30:00Z", response.cachedAt)
        assertTrue(response.fromCache)
    }

    @Test
    fun `Video handles null optional fields`() {
        val json = """
        {
            "id": "test",
            "title": "Test",
            "channel_name": "Ch",
            "channel_id": "UC",
            "view_count": null,
            "duration": null,
            "published_at": null,
            "thumbnail_url": "/thumb"
        }
        """.trimIndent()

        val video = gson.fromJson(json, Video::class.java)
        assertNull(video.viewCount)
        assertNull(video.duration)
        assertNull(video.publishedAt)
    }
}
