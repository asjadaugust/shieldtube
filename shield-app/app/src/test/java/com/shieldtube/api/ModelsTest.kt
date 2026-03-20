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

    @Test
    fun `deserialize VideoMeta from backend JSON`() {
        val json = """
        {
            "id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "channel_name": "Rick Astley",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "duration": 212,
            "cache_status": "cached",
            "last_position_seconds": 120
        }
        """.trimIndent()

        val meta = gson.fromJson(json, VideoMeta::class.java)

        assertEquals("dQw4w9WgXcQ", meta.id)
        assertEquals("Rick Astley", meta.channelName)
        assertEquals(212, meta.duration)
        assertEquals("cached", meta.cacheStatus)
        assertEquals(120, meta.lastPositionSeconds)
    }

    @Test
    fun `serialize ProgressBody to JSON`() {
        val body = ProgressBody(positionSeconds = 180, duration = 600)
        val json = gson.toJson(body)

        assertTrue(json.contains("\"position_seconds\":180"))
        assertTrue(json.contains("\"duration\":600"))
    }

    @Test
    fun `VideoMeta handles zero position`() {
        val json = """
        {
            "id": "test",
            "title": "Test",
            "channel_name": "Ch",
            "channel_id": "UC",
            "duration": null,
            "cache_status": null,
            "last_position_seconds": 0
        }
        """.trimIndent()

        val meta = gson.fromJson(json, VideoMeta::class.java)
        assertEquals(0, meta.lastPositionSeconds)
        assertNull(meta.duration)
    }

    @Test
    fun `deserialize SponsorResponse from backend JSON`() {
        val json = """
        {
            "video_id": "dQw4w9WgXcQ",
            "segments": [
                {"start": 30.5, "end": 60.2, "category": "sponsor"},
                {"start": 180.0, "end": 195.5, "category": "intro"}
            ]
        }
        """.trimIndent()

        val response = gson.fromJson(json, SponsorResponse::class.java)

        assertEquals("dQw4w9WgXcQ", response.videoId)
        assertEquals(2, response.segments.size)
        assertEquals(30.5, response.segments[0].start, 0.01)
        assertEquals(60.2, response.segments[0].end, 0.01)
        assertEquals("sponsor", response.segments[0].category)
    }

    @Test
    fun `deserialize SponsorResponse with empty segments`() {
        val json = """
        {
            "video_id": "test",
            "segments": []
        }
        """.trimIndent()

        val response = gson.fromJson(json, SponsorResponse::class.java)
        assertTrue(response.segments.isEmpty())
    }

    @Test
    fun `deserialize Chapter from backend JSON`() {
        val json = """
        {
            "title": "Intro",
            "start_time": 0.0,
            "end_time": 30.5
        }
        """.trimIndent()

        val chapter = gson.fromJson(json, Chapter::class.java)

        assertEquals("Intro", chapter.title)
        assertEquals(0.0, chapter.startTime, 0.001)
        assertEquals(30.5, chapter.endTime, 0.001)
    }

    @Test
    fun `deserialize VideoMeta with chapters`() {
        val json = """
        {
            "id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "channel_name": "Rick Astley",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "duration": 212,
            "cache_status": "cached",
            "last_position_seconds": 0,
            "chapters": [
                {"title": "Intro", "start_time": 0.0, "end_time": 30.0},
                {"title": "Main Content", "start_time": 30.0, "end_time": 180.0},
                {"title": "Outro", "start_time": 180.0, "end_time": 212.0}
            ]
        }
        """.trimIndent()

        val meta = gson.fromJson(json, VideoMeta::class.java)

        assertEquals("dQw4w9WgXcQ", meta.id)
        assertEquals(3, meta.chapters.size)
        assertEquals("Intro", meta.chapters[0].title)
        assertEquals(0.0, meta.chapters[0].startTime, 0.001)
        assertEquals(30.0, meta.chapters[0].endTime, 0.001)
        assertEquals("Main Content", meta.chapters[1].title)
        assertEquals(30.0, meta.chapters[1].startTime, 0.001)
        assertEquals("Outro", meta.chapters[2].title)
        assertEquals(212.0, meta.chapters[2].endTime, 0.001)
    }

    @Test
    fun `VideoMeta without chapters defaults to empty list`() {
        val json = """
        {
            "id": "test",
            "title": "Test",
            "channel_name": "Ch",
            "channel_id": "UC",
            "duration": null,
            "cache_status": null,
            "last_position_seconds": 0
        }
        """.trimIndent()

        val meta = gson.fromJson(json, VideoMeta::class.java)

        // When chapters field is absent from JSON, should default to empty list
        assertNotNull(meta.chapters)
        assertTrue(meta.chapters.isEmpty())
    }

    @Test
    fun `VideoMeta with empty chapters array`() {
        val json = """
        {
            "id": "test",
            "title": "Test",
            "channel_name": "Ch",
            "channel_id": "UC",
            "duration": 120,
            "cache_status": "none",
            "last_position_seconds": 0,
            "chapters": []
        }
        """.trimIndent()

        val meta = gson.fromJson(json, VideoMeta::class.java)

        assertNotNull(meta.chapters)
        assertTrue(meta.chapters.isEmpty())
    }
}
