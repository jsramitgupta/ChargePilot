package in.chargepilot.agent

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

data class AgentConfiguration(
    val serverOrigin: String,
    val installationId: String,
    val endpointId: String,
    val label: String,
)

class AgentStore(context: Context) {
    private val preferences = context.getSharedPreferences("chargepilot-agent", Context.MODE_PRIVATE)

    fun configuration(): AgentConfiguration? {
        val server = preferences.getString(KEY_SERVER, null) ?: return null
        val installationId = preferences.getString(KEY_INSTALLATION, null) ?: return null
        val endpointId = preferences.getString(KEY_ENDPOINT, null) ?: return null
        val label = preferences.getString(KEY_LABEL, null) ?: return null
        if (preferences.getString(KEY_CREDENTIAL, null) == null) return null
        return AgentConfiguration(server, installationId, endpointId, label)
    }

    fun saveEnrollment(
        configuration: AgentConfiguration,
        credential: String,
    ) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val ciphertext = cipher.doFinal(credential.toByteArray(Charsets.UTF_8))
        check(
            preferences.edit()
                .putString(KEY_SERVER, configuration.serverOrigin)
                .putString(KEY_INSTALLATION, configuration.installationId)
                .putString(KEY_ENDPOINT, configuration.endpointId)
                .putString(KEY_LABEL, configuration.label)
                .putString(KEY_CREDENTIAL, Base64.encodeToString(ciphertext, Base64.NO_WRAP))
                .putString(KEY_IV, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
                .commit(),
        ) { "Secure local storage is unavailable." }
    }

    fun credential(): String {
        val ciphertext = preferences.getString(KEY_CREDENTIAL, null)
            ?: error("This device is not enrolled.")
        val iv = preferences.getString(KEY_IV, null)
            ?: error("The saved credential is incomplete.")
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(
            Cipher.DECRYPT_MODE,
            secretKey(),
            GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)),
        )
        return String(
            cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP)),
            Charsets.UTF_8,
        )
    }

    fun lastSuccess(): String? = preferences.getString(KEY_LAST_SUCCESS, null)

    fun lastError(): String? = preferences.getString(KEY_LAST_ERROR, null)

    fun recordSuccess(timestamp: String) {
        preferences.edit()
            .putString(KEY_LAST_SUCCESS, timestamp)
            .remove(KEY_LAST_ERROR)
            .apply()
    }

    fun recordError(message: String) {
        preferences.edit().putString(KEY_LAST_ERROR, message).apply()
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEY_STORE).apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .setUserAuthenticationRequired(false)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val ANDROID_KEY_STORE = "AndroidKeyStore"
        const val KEY_ALIAS = "chargepilot-endpoint-credential"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val KEY_SERVER = "server-origin"
        const val KEY_INSTALLATION = "installation-id"
        const val KEY_ENDPOINT = "endpoint-id"
        const val KEY_LABEL = "device-label"
        const val KEY_CREDENTIAL = "credential-ciphertext"
        const val KEY_IV = "credential-iv"
        const val KEY_LAST_SUCCESS = "last-success"
        const val KEY_LAST_ERROR = "last-error"
    }
}
