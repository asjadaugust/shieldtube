package com.shieldtube.ui

import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.util.TypedValue
import android.view.Gravity
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.shieldtube.R
import com.shieldtube.api.ApiClient
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class LoginFragment : Fragment() {

    private lateinit var statusText: TextView
    private lateinit var userCodeText: TextView
    private lateinit var urlText: TextView
    private lateinit var spinner: ProgressBar
    private lateinit var retryButton: Button

    private var pollJob: Job? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        val layout = LinearLayout(requireContext()).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setBackgroundColor(resources.getColor(R.color.background_dark, null))
            setPadding(64, 64, 64, 64)
        }

        statusText = TextView(requireContext()).apply {
            text = "Checking authentication…"
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 20f)
            gravity = Gravity.CENTER
        }

        userCodeText = TextView(requireContext()).apply {
            setTextColor(resources.getColor(R.color.nvidia_green, null))
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 40f)
            setTypeface(null, Typeface.BOLD)
            gravity = Gravity.CENTER
            visibility = View.GONE
        }

        urlText = TextView(requireContext()).apply {
            setTextColor(0xFFcccccc.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
            gravity = Gravity.CENTER
            visibility = View.GONE
        }

        spinner = ProgressBar(requireContext()).apply {
            visibility = View.GONE
        }

        retryButton = Button(requireContext()).apply {
            text = "Retry"
            visibility = View.GONE
            isFocusable = true
            isFocusableInTouchMode = true
            setOnClickListener { startDeviceFlow() }
        }

        val spacer = { View(requireContext()).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 24
            )
        }}

        layout.addView(statusText)
        layout.addView(spacer())
        layout.addView(userCodeText)
        layout.addView(spacer())
        layout.addView(urlText)
        layout.addView(spacer())
        layout.addView(spinner)
        layout.addView(spacer())
        layout.addView(retryButton)

        return layout
    }

    override fun onStart() {
        super.onStart()
        checkAuthAndProceed()
    }

    override fun onStop() {
        super.onStop()
        pollJob?.cancel()
    }

    private fun checkAuthAndProceed() {
        lifecycleScope.launch {
            try {
                val status = ApiClient.api.getAuthStatus()
                if (status.authenticated) {
                    navigateToBrowse()
                } else {
                    startDeviceFlow()
                }
            } catch (e: Exception) {
                statusText.text = "Cannot reach server: ${e.javaClass.simpleName}: ${e.message}"
                retryButton.visibility = View.VISIBLE
                retryButton.requestFocus()
            }
        }
    }

    private fun startDeviceFlow() {
        pollJob?.cancel()
        retryButton.visibility = View.GONE

        lifecycleScope.launch {
            try {
                val flow = ApiClient.api.authLogin()

                statusText.text = "Go to the URL below and enter this code:"
                userCodeText.text = flow.userCode
                userCodeText.visibility = View.VISIBLE
                urlText.text = flow.verificationUrl
                urlText.visibility = View.VISIBLE
                spinner.visibility = View.VISIBLE

                pollForAuth(flow.deviceCode, flow.interval.toLong(), flow.expiresIn)
            } catch (e: Exception) {
                statusText.text = "Login failed: ${e.javaClass.simpleName}: ${e.message}"
                retryButton.visibility = View.VISIBLE
                retryButton.requestFocus()
            }
        }
    }

    private fun pollForAuth(deviceCode: String, initialInterval: Long, expiresIn: Int) {
        pollJob?.cancel()
        pollJob = lifecycleScope.launch {
            var interval = initialInterval
            val deadline = System.currentTimeMillis() + expiresIn * 1000L

            while (System.currentTimeMillis() < deadline) {
                delay(interval * 1000)
                try {
                    val result = ApiClient.api.authCallback(deviceCode)
                    when (result.status) {
                        "authorized" -> {
                            navigateToBrowse()
                            return@launch
                        }
                        "slow_down" -> {
                            interval += 5
                        }
                        // "authorization_pending" → keep polling
                    }
                } catch (e: Exception) {
                    // Network hiccup — keep trying until deadline
                }
            }

            // Code expired
            statusText.text = "Code expired. Please try again."
            userCodeText.visibility = View.GONE
            urlText.visibility = View.GONE
            spinner.visibility = View.GONE
            retryButton.visibility = View.VISIBLE
            retryButton.requestFocus()
        }
    }

    private fun navigateToBrowse() {
        parentFragmentManager.beginTransaction()
            .replace(android.R.id.content, BrowseFragment())
            .commit()
    }
}
