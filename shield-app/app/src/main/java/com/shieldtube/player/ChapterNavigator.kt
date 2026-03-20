package com.shieldtube.player

import com.shieldtube.api.Chapter

/**
 * Pure Kotlin chapter navigation logic, extracted for testability.
 * All times are in seconds (Double).
 */
class ChapterNavigator(private val chapters: List<Chapter>) {

    /**
     * Return the index of the chapter containing [positionSec], or -1 if none.
     */
    fun currentChapterIndex(positionSec: Double): Int {
        return chapters.indexOfLast { it.startTime <= positionSec }
    }

    /**
     * Return the start time of the next chapter after [positionSec],
     * or null if already in the last chapter.
     * Uses a 1-second tolerance to avoid sticking at the boundary.
     */
    fun nextChapterStartTime(positionSec: Double): Double? {
        val next = chapters.firstOrNull { it.startTime > positionSec + 1.0 }
        return next?.startTime
    }

    /**
     * Return the start time to seek to when going "previous":
     * - If more than 3 seconds into the current chapter, seek to its start.
     * - Otherwise, seek to the previous chapter's start.
     * - If at or before the first chapter, seek to the first chapter's start.
     * Returns null if chapters are empty.
     */
    fun previousChapterStartTime(positionSec: Double): Double? {
        if (chapters.isEmpty()) return null
        val idx = chapters.indexOfLast { it.startTime <= positionSec }
        if (idx < 0) return chapters[0].startTime

        val currentStart = chapters[idx].startTime
        return if (positionSec - currentStart > 3.0) {
            currentStart
        } else if (idx > 0) {
            chapters[idx - 1].startTime
        } else {
            chapters[0].startTime
        }
    }
}
