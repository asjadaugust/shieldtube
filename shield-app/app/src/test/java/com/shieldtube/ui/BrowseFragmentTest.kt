package com.shieldtube.ui

import androidx.leanback.widget.ArrayObjectAdapter
import androidx.leanback.widget.ListRow
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.fragment.app.testing.FragmentScenario
import androidx.lifecycle.Lifecycle

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [33])
class BrowseFragmentTest {

    @Test
    fun browseFragment_hasThreeHeaders() {
        val scenario = FragmentScenario.launchInContainer(
            BrowseFragment::class.java,
            themeResId = androidx.leanback.R.style.Theme_Leanback
        )
        scenario.moveToState(Lifecycle.State.CREATED)
        scenario.onFragment { fragment ->
            val adapter = fragment.adapter as? ArrayObjectAdapter
            assertNotNull("Adapter should be set", adapter)
            assertEquals("Should have 3 header rows", 3, adapter!!.size())

            val row0 = adapter.get(0) as ListRow
            val row1 = adapter.get(1) as ListRow
            val row2 = adapter.get(2) as ListRow

            assertEquals("Home", row0.headerItem.name)
            assertEquals("Subscriptions", row1.headerItem.name)
            assertEquals("Watch Later", row2.headerItem.name)
        }
    }
}
