plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val releaseSigningConfigured = listOf(
    "ANDROID_KEYSTORE_FILE",
    "ANDROID_KEYSTORE_PASSWORD",
    "ANDROID_KEY_ALIAS",
    "ANDROID_KEY_PASSWORD",
).all { !System.getenv(it).isNullOrBlank() }
val sourceVersionFile = rootProject.file("VERSION").takeIf { it.isFile }
    ?: rootProject.file("../VERSION")
val agentVersion = providers.environmentVariable("AGENT_VERSION")
    .orElse(sourceVersionFile.readText().trim())
    .get()
require(Regex("""(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)""").matches(agentVersion)) {
    "Agent version must use MAJOR.MINOR.PATCH format."
}
val agentVersionParts = agentVersion.split(".").map(String::toInt)
require(agentVersionParts[1] <= 999 && agentVersionParts[2] <= 999) {
    "Agent version minor and patch components must not exceed 999."
}
val agentBuildNumber = providers.environmentVariable("AGENT_BUILD_NUMBER")
    .orElse(
        (
            agentVersionParts[0] * 1_000_000 +
                agentVersionParts[1] * 1_000 +
                agentVersionParts[2]
            ).toString(),
    )
    .get()
    .toInt()

android {
    namespace = "in.chargepilot.agent"
    compileSdk = 35

    defaultConfig {
        applicationId = "in.chargepilot.agent"
        minSdk = 26
        targetSdk = 35
        versionCode = agentBuildNumber
        versionName = agentVersion
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    signingConfigs {
        create("release") {
            if (releaseSigningConfigured) {
                storeFile = file(System.getenv("ANDROID_KEYSTORE_FILE"))
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS")
                keyPassword = System.getenv("ANDROID_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        getByName("release") {
            signingConfig = if (releaseSigningConfigured) {
                signingConfigs.getByName("release")
            } else {
                null
            }
        }
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.work:work-runtime-ktx:2.10.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
