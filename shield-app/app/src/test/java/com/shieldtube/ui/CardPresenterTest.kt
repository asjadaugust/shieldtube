package com.shieldtube.ui

import org.junit.Assert.*
import org.junit.Test

class CardPresenterTest {
    @Test
    fun `formatDuration short video`() {
        assertEquals("3:33", CardPresenter.formatDuration(213))
    }

    @Test
    fun `formatDuration long video`() {
        assertEquals("1:02:03", CardPresenter.formatDuration(3723))
    }

    @Test
    fun `formatDuration seconds only`() {
        assertEquals("0:30", CardPresenter.formatDuration(30))
    }

    @Test
    fun `formatDuration null returns empty`() {
        assertEquals("", CardPresenter.formatDuration(null))
    }

    @Test
    fun `formatDuration zero returns empty`() {
        assertEquals("", CardPresenter.formatDuration(0))
    }

    @Test
    fun `getChannelColor is deterministic`() {
        val color1 = CardPresenter.getChannelColor("Rick Astley")
        val color2 = CardPresenter.getChannelColor("Rick Astley")
        assertEquals(color1, color2)
    }

    @Test
    fun `getChannelColor varies by name`() {
        val color1 = CardPresenter.getChannelColor("Rick Astley")
        val color2 = CardPresenter.getChannelColor("PewDiePie")
        assertNotEquals(color1, color2)
    }
}
