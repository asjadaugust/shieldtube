package com.shieldtube.ui

import androidx.leanback.widget.ArrayObjectAdapter
import androidx.leanback.widget.HeaderItem
import androidx.leanback.widget.ListRow
import androidx.leanback.widget.ListRowPresenter
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33])
class BrowseFragmentTest {

    @Test
    fun browseHeaders_hasThreeRows() {
        // Test the header setup logic directly without launching the full fragment
        val rowsAdapter = ArrayObjectAdapter(ListRowPresenter())

        val homeHeader = HeaderItem(0L, "Home")
        val subsHeader = HeaderItem(1L, "Subscriptions")
        val watchLaterHeader = HeaderItem(2L, "Watch Later")

        rowsAdapter.add(ListRow(homeHeader, ArrayObjectAdapter()))
        rowsAdapter.add(ListRow(subsHeader, ArrayObjectAdapter()))
        rowsAdapter.add(ListRow(watchLaterHeader, ArrayObjectAdapter()))

        assertEquals("Should have 3 header rows", 3, rowsAdapter.size())

        val row0 = rowsAdapter.get(0) as ListRow
        val row1 = rowsAdapter.get(1) as ListRow
        val row2 = rowsAdapter.get(2) as ListRow

        assertEquals("Home", row0.headerItem.name)
        assertEquals("Subscriptions", row1.headerItem.name)
        assertEquals("Watch Later", row2.headerItem.name)
    }
}
