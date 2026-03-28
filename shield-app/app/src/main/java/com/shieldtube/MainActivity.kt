package com.shieldtube

import android.os.Bundle
import androidx.fragment.app.FragmentActivity
import com.shieldtube.ui.LoginFragment

class MainActivity : FragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) {
            supportFragmentManager.beginTransaction()
                .replace(android.R.id.content, LoginFragment())
                .commit()
        }
    }
}
