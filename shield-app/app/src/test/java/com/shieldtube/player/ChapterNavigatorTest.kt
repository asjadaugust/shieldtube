package com.shieldtube.player

import com.shieldtube.api.Chapter
import org.junit.Assert.*
import org.junit.Test

class ChapterNavigatorTest {

    private val chapters = listOf(
        Chapter(title = "Intro", startTime = 0.0, endTime = 30.0),
        Chapter(title = "Main Topic", startTime = 30.0, endTime = 120.0),
        Chapter(title = "Demo", startTime = 120.0, endTime = 300.0),
        Chapter(title = "Outro", startTime = 300.0, endTime = 360.0),
    )
    private val nav = ChapterNavigator(chapters)

    @Test
    fun currentChapterIndex_returnsCorrectIndex() {
        assertEquals(0, nav.currentChapterIndex(15.0))
        assertEquals(1, nav.currentChapterIndex(60.0))
        assertEquals(3, nav.currentChapterIndex(350.0))
    }

    @Test
    fun currentChapterIndex_returnsMinusOneBeforeFirstChapter() {
        val nav2 = ChapterNavigator(listOf(
            Chapter(title = "A", startTime = 10.0, endTime = 50.0)
        ))
        assertEquals(-1, nav2.currentChapterIndex(5.0))
    }

    @Test
    fun nextChapterStartTime_returnsNextChapter() {
        assertEquals(30.0, nav.nextChapterStartTime(15.0)!!, 0.01)
        assertEquals(120.0, nav.nextChapterStartTime(60.0)!!, 0.01)
    }

    @Test
    fun nextChapterStartTime_returnsNullAtLastChapter() {
        assertNull(nav.nextChapterStartTime(350.0))
    }

    @Test
    fun previousChapterStartTime_goesToCurrentStartIfDeepIn() {
        // 10 seconds into "Main Topic" (started at 30.0), > 3s → go to 30.0
        assertEquals(30.0, nav.previousChapterStartTime(40.0)!!, 0.01)
    }

    @Test
    fun previousChapterStartTime_goesToPreviousIfNearStart() {
        // 1 second into "Main Topic" (started at 30.0), < 3s → go to Intro (0.0)
        assertEquals(0.0, nav.previousChapterStartTime(31.0)!!, 0.01)
    }

    @Test
    fun previousChapterStartTime_staysAtFirstChapterStart() {
        // Near start of first chapter → go to 0.0
        assertEquals(0.0, nav.previousChapterStartTime(1.0)!!, 0.01)
    }

    @Test
    fun emptyChapters_returnsNull() {
        val emptyNav = ChapterNavigator(emptyList())
        assertEquals(-1, emptyNav.currentChapterIndex(10.0))
        assertNull(emptyNav.nextChapterStartTime(10.0))
        assertNull(emptyNav.previousChapterStartTime(10.0))
    }
}
