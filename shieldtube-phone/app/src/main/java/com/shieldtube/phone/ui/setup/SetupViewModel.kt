package com.shieldtube.phone.ui.setup

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.shieldtube.phone.data.preferences.AppPreferences
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class SetupViewModel @Inject constructor(
    private val prefs: AppPreferences,
) : ViewModel() {

    val isConfigured: StateFlow<Boolean> = prefs.isConfigured
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), false)

    fun save(url: String, secret: String, lanUrl: String) {
        viewModelScope.launch {
            prefs.save(url, secret, lanUrl)
        }
    }
}
