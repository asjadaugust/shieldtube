package com.shieldtube.phone.data.preferences

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.dataStore: DataStore<Preferences> by preferencesDataStore(name = "shieldtube_prefs")

@Singleton
class AppPreferences @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    companion object {
        private val KEY_BACKEND_URL = stringPreferencesKey("backend_url")
        private val KEY_API_SECRET = stringPreferencesKey("api_secret")
        private val KEY_LAN_URL = stringPreferencesKey("lan_url")
    }

    val backendUrl: Flow<String> = context.dataStore.data
        .map { prefs -> prefs[KEY_BACKEND_URL] ?: "" }

    val apiSecret: Flow<String> = context.dataStore.data
        .map { prefs -> prefs[KEY_API_SECRET] ?: "" }

    val lanUrl: Flow<String> = context.dataStore.data
        .map { prefs -> prefs[KEY_LAN_URL] ?: "" }

    /** Prefer LAN URL when configured, fall back to backend (tunnel) URL. */
    val effectiveBaseUrl: Flow<String> = combine(lanUrl, backendUrl) { lan, backend ->
        lan.takeIf { it.isNotBlank() } ?: backend
    }

    val isConfigured: Flow<Boolean> = combine(backendUrl, apiSecret) { url, secret ->
        url.isNotBlank() && secret.isNotBlank()
    }

    suspend fun save(url: String, secret: String, lanUrl: String) {
        context.dataStore.edit { prefs ->
            prefs[KEY_BACKEND_URL] = url
            prefs[KEY_API_SECRET] = secret
            prefs[KEY_LAN_URL] = lanUrl
        }
    }
}
